"""Install, idempotency, verification and byte-exact rollback on a synthetic config dir."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import common as C  # noqa: E402
import install  # noqa: E402
import rollback as rollback_mod  # noqa: E402
import verify  # noqa: E402

ORIGINAL_PROMPT = "ORIGINAL PRODUCT PROMPT\n"


def build_config(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(json.dumps({
        "claw": {"channels": {"wechatmp": {"enabled": True}}},
        "officeFileAssociationsRepairMarker": "v9:win32",
        "autoLaunchDesired": False,
        "pluginConfigs": {},
        "sandbox": {"extraAllowWrite": ["~/.tmeet"], "orderedRules": {"file": {"rules": []}}},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo user-hook"}]}]},
        "enabledPlugins": {"tmeet@workbuddy-connector-plugins-official": True},
        "skillOverrides": {"kb": "on", "daily": "off"},
        "userOwnedKey": {"keep": True},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "rules").mkdir()
    (root / "rules" / "engineering.md").write_text("# old duplicated rules\n", encoding="utf-8")
    prompt = root / "plugins" / "cache" / "workbuddy-builtin" / "welcomemode-code" / "5.8.4-test"
    prompt.mkdir(parents=True)
    (prompt / "prompt.tpl").write_text(ORIGINAL_PROMPT, encoding="utf-8")


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "config"
        build_config(self.cfg)
        self.settings_before = (self.cfg / "settings.json").read_bytes()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def settings(self) -> dict:
        return json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))

    def test_apply_installs_profile(self) -> None:
        result = install.apply(cfg=self.cfg)
        self.assertTrue(result["actions"])

        memory = self.cfg / "CODEBUDDY.md"
        self.assertTrue(memory.is_file())
        self.assertIn("## 委派", memory.read_text(encoding="utf-8"))

        for folder in ("agents", "commands", "hooks"):
            expected = len(list((C.PROFILE / folder).glob("*.*")))
            actual = len(list((self.cfg / folder).glob("*.*")))
            self.assertEqual(actual, expected, folder)

        self.assertFalse((self.cfg / "rules" / "engineering.md").exists())

    def test_apply_prunes_office_settings(self) -> None:
        install.apply(cfg=self.cfg)
        settings = self.settings()
        for key in C.REMOVED_SETTINGS:
            self.assertNotIn(key, settings)
        self.assertEqual(settings["sandbox"]["extraAllowWrite"], [])
        self.assertEqual(settings["permissions"]["defaultMode"], "acceptEdits")
        self.assertEqual(settings["autoCompactWindow"], "auto")
        self.assertIs(settings["enabledPlugins"]["tmeet@workbuddy-connector-plugins-official"], False)

    def test_apply_preserves_user_data(self) -> None:
        install.apply(cfg=self.cfg)
        settings = self.settings()
        self.assertEqual(settings["userOwnedKey"], {"keep": True})
        self.assertEqual(settings["skillOverrides"], {"kb": "on", "daily": "off"})
        self.assertIn("Stop", settings["hooks"], "用户自有 hook 必须保留")

    def test_apply_registers_absolute_hooks(self) -> None:
        install.apply(cfg=self.cfg)
        hooks = self.settings()["hooks"]
        commands = [h["command"] for groups in hooks.values()
                    for group in groups for h in group.get("hooks", [])]
        harness = [c for c in commands if "harness" in c or "post_edit_check" in c]
        self.assertTrue(harness)
        for command in harness:
            path = command.split('"')[1].replace("\\", "/")
            self.assertTrue(Path(path).is_file(), path)

    def test_apply_replaces_prompt(self) -> None:
        install.apply(cfg=self.cfg)
        target = install.prompt_targets(self.cfg)[0]
        self.assertEqual(target.read_bytes(), (C.PROFILE / "prompt" / "prompt.tpl").read_bytes())
        self.assertIn("harness:v3", target.read_text(encoding="utf-8"))

    def test_apply_is_idempotent(self) -> None:
        install.apply(cfg=self.cfg)
        second = install.apply(cfg=self.cfg)
        self.assertEqual(second["actions"], [])

    def test_dry_run_writes_nothing(self) -> None:
        before = sorted(p.name for p in self.cfg.rglob("*"))
        install.apply(cfg=self.cfg, dry_run=True)
        after = sorted(p.name for p in self.cfg.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual((self.cfg / "settings.json").read_bytes(), self.settings_before)

    def test_rollback_restores_bytes(self) -> None:
        install.apply(cfg=self.cfg)
        rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual((self.cfg / "settings.json").read_bytes(), self.settings_before)
        self.assertTrue((self.cfg / "rules" / "engineering.md").is_file())
        self.assertFalse((self.cfg / "CODEBUDDY.md").exists())
        target = install.prompt_targets(self.cfg)[0]
        self.assertEqual(target.read_text(encoding="utf-8"), ORIGINAL_PROMPT)
        self.assertFalse((C.state_dir(self.cfg) / "state.json").exists())

    def test_rollback_keeps_user_edits_made_after_install(self) -> None:
        install.apply(cfg=self.cfg)
        extra = self.cfg / "agents" / "user-own.md"
        extra.write_text("---\nname: user-own\n---\n", encoding="utf-8")
        rollback_mod.rollback(cfg=self.cfg)
        self.assertTrue(extra.is_file(), "回滚不应删除安装后新增的用户文件")

    def test_state_records_initial_backup_across_applies(self) -> None:
        """`initial_backup` is the only snapshot that predates the harness.

        A second apply takes a fresh snapshot that already contains harness output;
        if `initial_backup` were re-derived from it, rollback could never undo the
        install. This regressed once (the key silently went missing).
        """
        install.apply(cfg=self.cfg)
        state_path = C.state_dir(self.cfg) / "state.json"
        first = C.read_json(state_path, default={}) or {}
        self.assertTrue(first.get("initial_backup"), "首次安装必须记录 initial_backup")
        self.assertEqual(first["initial_backup"], first["backup"])

        # Force a second snapshot: removing a managed file makes apply rewrite it.
        (self.cfg / "CODEBUDDY.md").unlink()
        install.apply(cfg=self.cfg)
        second = C.read_json(state_path, default={}) or {}
        self.assertNotEqual(second["backup"], first["backup"], "第二次安装必须另开快照")
        self.assertEqual(second["initial_backup"], first["initial_backup"],
                         "回滚锚点必须停留在安装前的第一份快照")

    def test_initial_backup_skips_snapshot_without_harness_artifacts(self) -> None:
        """A settings-only snapshot must never become the rollback anchor.

        It restores fine, but it cannot undo CODEBUDDY.md, rules/ or agents/, so
        anchoring there would leave the harness half-applied after rollback.
        """
        narrow = C.Backup(self.cfg, "apply")
        narrow.save(self.cfg / "settings.json")
        narrow.finish()

        install.apply(cfg=self.cfg)
        state = C.read_json(C.state_dir(self.cfg) / "state.json", default={}) or {}
        anchor = Path(state["initial_backup"])
        self.assertNotEqual(anchor, narrow.root, "settings-only 快照不能当锚点")
        self.assertTrue(install._covers_harness(anchor), f"锚点 {anchor} 必须覆盖 harness 产物")

        rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual((self.cfg / "settings.json").read_bytes(), self.settings_before)
        self.assertTrue((self.cfg / "rules" / "engineering.md").is_file())
        self.assertFalse((self.cfg / "CODEBUDDY.md").exists())

    def test_stale_settings_only_anchor_is_corrected(self) -> None:
        """An inherited `initial_backup` must prove it predates the harness."""
        install.apply(cfg=self.cfg)
        state_path = C.state_dir(self.cfg) / "state.json"
        good = (C.read_json(state_path, default={}) or {})["initial_backup"]

        narrow = C.Backup(self.cfg, "apply")
        narrow.save(self.cfg / "settings.json")
        narrow.finish()
        state = C.read_json(state_path, default={}) or {}
        state["initial_backup"] = str(narrow.root)
        C.write_json(state_path, state)

        (self.cfg / "CODEBUDDY.md").unlink()  # force a third snapshot
        install.apply(cfg=self.cfg)

        state = C.read_json(state_path, default={}) or {}
        self.assertNotEqual(state["initial_backup"], str(narrow.root),
                            "继承来的无效锚点必须被纠正")
        self.assertEqual(state["initial_backup"], good, "必须回落到最旧的覆盖性快照")

    def test_noop_apply_keeps_previous_backup(self) -> None:
        """Nothing to do must not erase the only record of where changes were saved."""
        install.apply(cfg=self.cfg)
        state_path = C.state_dir(self.cfg) / "state.json"
        first = C.read_json(state_path, default={}) or {}

        second_result = install.apply(cfg=self.cfg)
        self.assertEqual(second_result["actions"], [], "第二次安装应无改动")

        second = C.read_json(state_path, default={}) or {}
        self.assertEqual(second["backup"], first["backup"], "no-op 不得丢掉 backup")
        self.assertEqual(second["initial_backup"], first["initial_backup"])
        self.assertTrue((Path(second["backup"]) / "manifest.json").is_file())

        rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual((self.cfg / "settings.json").read_bytes(), self.settings_before)

    def test_rollback_uses_initial_backup_after_repeated_applies(self) -> None:
        install.apply(cfg=self.cfg)
        (self.cfg / "CODEBUDDY.md").unlink()
        install.apply(cfg=self.cfg)
        rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual((self.cfg / "settings.json").read_bytes(), self.settings_before)
        self.assertTrue((self.cfg / "rules" / "engineering.md").is_file())
        self.assertFalse((self.cfg / "CODEBUDDY.md").exists())

    def test_rollback_keeps_rewritten_managed_file(self) -> None:
        """A file the user edited after install must not be deleted by rollback."""
        install.apply(cfg=self.cfg)
        managed = self.cfg / "agents" / "code-reviewer.md"
        managed.write_text("---\nname: code-reviewer\ndescription: mine\n---\n", encoding="utf-8")
        result = rollback_mod.rollback(cfg=self.cfg)
        self.assertIn("agents/code-reviewer.md", result["kept"])
        self.assertTrue(managed.is_file(), "回滚不应删除被用户改写的文件")
        self.assertIn("mine", managed.read_text(encoding="utf-8"))

    def test_verify_passes_after_apply(self) -> None:
        install.apply(cfg=self.cfg)
        checks = verify.static_checks(self.cfg)
        failures = [f"{name}: {detail}" for name, state, detail in checks if state == verify.FAIL]
        self.assertEqual(failures, [])
        names = [name for name, _, _ in checks]
        self.assertEqual(len(names), len(set(names)), "校验项名称必须唯一")
        # Guards against a refactor silently dropping checks (early return, exception).
        self.assertEqual(len(checks), 25, "校验项数量变了就同步更新这里")

    def test_verify_warns_instead_of_failing_when_app_rewrote_settings(self) -> None:
        """The desktop app flushes settings.json from memory; that must not fail verify."""
        install.apply(cfg=self.cfg)
        settings_path = self.cfg / "settings.json"
        settings = self.settings()
        settings["fileCheckpointingEnabled"] = None
        settings["enabledPlugins"] = {pid: True for pid in
                                     (C.read_json(C.PROFILE / "plugins.json", default={}) or {}).get("disable", [])}
        settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        stamp = settings_path.stat().st_mtime + 30
        os.utime(settings_path, (stamp, stamp))

        checks = verify.static_checks(self.cfg)
        by_name = {name: (state, detail) for name, state, detail in checks}
        self.assertEqual(by_name["记忆与快照开关"][0], verify.WARN)
        self.assertEqual(by_name["办公插件已停用"][0], verify.WARN)
        self.assertIn(verify.STALE_HINT, by_name["记忆与快照开关"][1])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(verify.report(checks), "警告不得导致退出码非零")

    def test_verify_fails_when_settings_drift_is_not_explained_by_a_rewrite(self) -> None:
        install.apply(cfg=self.cfg)
        settings = self.settings()
        settings["memory"]["enabled"] = False
        (self.cfg / "settings.json").write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        # Rewind settings.json so it looks untouched since apply.
        state = C.read_json(C.state_dir(self.cfg) / "state.json", default={}) or {}
        applied = time.mktime(time.strptime(state["applied"], "%Y-%m-%dT%H:%M:%S"))
        os.utime(self.cfg / "settings.json", (applied, applied))

        checks = {name: state for name, state, _ in verify.static_checks(self.cfg)}
        self.assertEqual(checks["记忆与快照开关"], verify.FAIL)


if __name__ == "__main__":
    unittest.main()
