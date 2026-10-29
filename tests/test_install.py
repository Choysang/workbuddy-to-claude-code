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
from unittest.mock import patch
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import common as C  # noqa: E402
import install  # noqa: E402
import rollback as rollback_mod  # noqa: E402
import verify  # noqa: E402
import workspace as W  # noqa: E402

ORIGINAL_PROMPT = "ORIGINAL PRODUCT PROMPT\n"


def build_config(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(json.dumps({
        "claw": {"channels": {"wechatmp": {"enabled": True}}},
        "officeFileAssociationsRepairMarker": "v9:win32",
        "officeMarkdownDefaultClaimAttempted": True,
        "autoLaunchDesired": False,
        "autoLaunchDefaultApplied": True,
        "pluginConfigs": {},
        "sandbox": {"extraAllowWrite": ["~/.tmeet"], "orderedRules": {"file": {"rules": []}}},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo user-hook"}]}]},
        "enabledPlugins": {"tmeet@workbuddy-connector-plugins-official": True},
        "skillOverrides": {"kb": "on", "daily": "off"},
        "userOwnedKey": {"keep": True},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "rules").mkdir()
    (root / "rules" / "engineering.md").write_text("# old duplicated rules\n", encoding="utf-8")
    for mode in ("code", "work"):
        prompt = root / "plugins" / "cache" / "workbuddy-builtin" / f"welcomemode-{mode}" / "5.8.4-test"
        prompt.mkdir(parents=True)
        (prompt / "prompt.tpl").write_text(ORIGINAL_PROMPT, encoding="utf-8")
    craft = root / "plugins" / "cache" / "workbuddy-builtin" / "interactionmode-craft" / "5.8.4-test" / "fragments"
    craft.mkdir(parents=True)
    (craft / "interaction.md").write_text("---\nname: craft\ntools:\n  - A2ASendMessage\n---\n", encoding="utf-8")


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
        self.assertNotIn("autoCompactWindow", settings)
        self.assertIs(settings["enabledPlugins"]["tmeet@workbuddy-connector-plugins-official"], False)

    def test_apply_preserves_user_data(self) -> None:
        install.apply(cfg=self.cfg)
        settings = self.settings()
        self.assertEqual(settings["userOwnedKey"], {"keep": True})
        self.assertEqual(settings["skillOverrides"]["kb"], "on")
        self.assertEqual(settings["skillOverrides"]["daily"], "off")
        self.assertIn("Stop", settings["hooks"], "用户自有 hook 必须保留")
        self.assertEqual(settings["officeFileAssociationsRepairMarker"], "v9:win32")
        self.assertIs(settings["officeMarkdownDefaultClaimAttempted"], True)
        self.assertIs(settings["autoLaunchDesired"], False)
        self.assertIs(settings["autoLaunchDefaultApplied"], True)

    def test_upgrade_recovers_missing_startup_preference_only_once(self) -> None:
        install.apply(cfg=self.cfg)
        settings = self.settings()
        settings.pop("autoLaunchDesired")
        C.write_json(self.cfg / "settings.json", settings)
        state = C.read_json(C.state_dir(self.cfg) / "state.json")
        state.pop("product_preferences_restored")
        C.write_json(C.state_dir(self.cfg) / "state.json", state)
        install.apply(cfg=self.cfg)
        self.assertIs(self.settings()["autoLaunchDesired"], False)
        # A later deliberate user deletion is no longer mistaken for v3 damage.
        settings = self.settings()
        settings.pop("autoLaunchDesired")
        C.write_json(self.cfg / "settings.json", settings)
        install.apply(cfg=self.cfg)
        self.assertNotIn("autoLaunchDesired", self.settings())

    def test_ecosystem_controls_merge_without_enabling_user_disabled_tools(self) -> None:
        settings = self.settings()
        settings["toolControl"] = {"version": 1, "customMcpEnabled": False,
                                   "disabledToolIds": ["builtin:user-disabled", "builtin:search_plugins"],
                                   "disabledMcpServerIds": ["user-server"]}
        C.write_json(self.cfg / "settings.json", settings)
        install.apply(cfg=self.cfg)
        settings = self.settings()
        self.assertFalse(settings["toolControl"]["customMcpEnabled"])
        self.assertIn("builtin:user-disabled", settings["toolControl"]["disabledToolIds"])
        self.assertIn("user-server", settings["toolControl"]["disabledMcpServerIds"])
        self.assertNotIn("builtin:search_plugins", settings["toolControl"]["disabledToolIds"])
        self.assertIn("mcp:connector-proxy:search_plugins", settings["toolControl"]["disabledMcpToolIds"])
        for name in C.read_json(C.PROFILE / "builtin-skills-off.json"):
            self.assertEqual(settings["skillOverrides"][name], "off")
        self.assertFalse(install.apply(cfg=self.cfg)["actions"])

    def test_invalid_global_settings_fail_before_any_install_writes(self) -> None:
        for original in (b'{broken', b'[]', b'{"toolControl":{"disabledToolIds":null}}',
                         b'{"toolControl":{"version":2}}', b'{"toolControl":{"version":true}}',
                         b'{"toolControl":{"version":null}}', b'{"toolControl":{"version":"1"}}'):
            with self.subTest(original=original):
                (self.cfg / "settings.json").write_bytes(original)
                with self.assertRaises(ValueError):
                    install.apply(cfg=self.cfg)
                self.assertEqual((self.cfg / "settings.json").read_bytes(), original)
                self.assertFalse((self.cfg / "CODEBUDDY.md").exists())
                self.assertFalse(C.state_dir(self.cfg).exists())

    def test_optional_prompt_hook_is_off_until_enabled_and_choice_survives_apply(self) -> None:
        install.apply(cfg=self.cfg)
        self.assertNotIn("UserPromptSubmit", self.settings()["hooks"])
        self.assertTrue((self.cfg / "commands/plan.md").is_file())
        self.assertTrue((self.cfg / "commands/design.md").is_file())
        self.assertTrue((self.cfg / "output-styles/engineer.md").is_file())
        self.assertNotIn("outputStyle", self.settings())
        install.apply(cfg=self.cfg, prompt_context=True)
        enabled = self.settings()["hooks"]["UserPromptSubmit"]
        self.assertIn("prompt_submit.py", enabled[0]["hooks"][0]["command"])
        again = install.apply(cfg=self.cfg)
        self.assertFalse(again["actions"])
        self.assertEqual(self.settings()["hooks"]["UserPromptSubmit"], enabled)
        install.apply(cfg=self.cfg, prompt_context=False)
        self.assertNotIn("UserPromptSubmit", self.settings()["hooks"])

    def test_reapply_preserves_user_hooks_in_mixed_owned_group(self) -> None:
        install.apply(cfg=self.cfg)
        settings = self.settings()
        settings["hooks"]["SessionStart"][0]["hooks"].append({"type": "command", "command": "echo user-owned"})
        similar = str(self.cfg / "hooks/session_start.py.custom").replace("\\", "/")
        settings["hooks"]["SessionStart"][0]["hooks"].append({"type": "command", "command": f'python "{similar}"'})
        (self.cfg / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        install.apply(cfg=self.cfg)
        commands = [hook["command"] for group in self.settings()["hooks"]["SessionStart"] for hook in group["hooks"]]
        self.assertIn("echo user-owned", commands)
        self.assertIn(f'python "{similar}"', commands)

    def test_rollback_unwinds_profile_upgrade_and_preview_matches(self) -> None:
        source = Path(self.tmp.name) / "source"
        shutil.copytree(C.PROFILE, source)
        with patch.object(C, "PROFILE", source):
            install.apply(cfg=self.cfg)
            extra = source / "commands/new-after-upgrade.md"
            extra.write_text("---\ndescription: Upgrade fixture\n---\n", encoding="utf-8")
            (source / "CODEBUDDY.md").write_text("changed profile\n", encoding="utf-8")
            install.apply(cfg=self.cfg)
            before = (self.cfg / "CODEBUDDY.md").read_bytes()
            preview = rollback_mod.rollback(cfg=self.cfg, dry_run=True)
            self.assertEqual((self.cfg / "CODEBUDDY.md").read_bytes(), before)
            self.assertTrue((self.cfg / "commands/new-after-upgrade.md").exists())
            actual = rollback_mod.rollback(cfg=self.cfg)
            for bucket in ("changed", "kept", "missing"):
                self.assertEqual(preview[bucket], actual[bucket])
            self.assertFalse((self.cfg / "commands/new-after-upgrade.md").exists())
            self.assertFalse((self.cfg / "CODEBUDDY.md").exists())
            self.assertEqual((self.cfg / "settings.json").read_bytes(), self.settings_before)

    def test_workspace_overlay_preserves_local_settings_and_rolls_back(self) -> None:
        root = Path(self.tmp.name) / "项目 workspace"
        root.mkdir()
        local = W.settings_path(root)
        local.parent.mkdir()
        original = b'{"userProjectSetting":true,"enabledPlugins":{"local-custom@example":false}}'
        local.write_bytes(original)
        install.apply(cfg=self.cfg, workspaces=[root], dry_run=True)
        self.assertEqual(local.read_bytes(), original)
        self.assertFalse(C.state_dir(self.cfg).exists())
        install.apply(cfg=self.cfg, workspaces=[root])
        configured = json.loads(local.read_bytes())
        self.assertTrue(configured["userProjectSetting"])
        self.assertFalse(configured["enabledPlugins"]["local-custom@example"])
        plugins = C.read_json(C.PROFILE / "plugins.json")
        for key in plugins["disable"]:
            self.assertIs(configured["enabledPlugins"][key], False)
        self.assertFalse(install.apply(cfg=self.cfg)["actions"])
        before = local.read_bytes()
        preview = rollback_mod.rollback(cfg=self.cfg, dry_run=True)
        self.assertEqual(local.read_bytes(), before)
        actual = rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual(preview["changed"], actual["changed"])
        self.assertEqual(local.read_bytes(), original)

    def test_workspace_overlay_does_not_clobber_invalid_json(self) -> None:
        root = Path(self.tmp.name) / "workspace"
        root.mkdir()
        local = W.settings_path(root)
        local.parent.mkdir()
        local.write_bytes(b'{invalid')
        with self.assertRaises((ValueError, SystemExit)):
            install.apply(cfg=self.cfg, workspaces=[root])
        self.assertEqual(local.read_bytes(), b'{invalid')
        self.assertEqual((self.cfg / "settings.json").read_bytes(), self.settings_before)
        self.assertFalse((self.cfg / "CODEBUDDY.md").exists())

    def test_verify_reports_malformed_workspace_plugin_map(self) -> None:
        root = Path(self.tmp.name) / "workspace"
        root.mkdir()
        install.apply(cfg=self.cfg, workspaces=[root])
        W.settings_path(root).write_text('{"enabledPlugins":null}', encoding="utf-8")
        checks = verify.static_checks(self.cfg)
        result = [state for name, state, _ in checks if name == "工作区插件覆盖"]
        self.assertEqual(result, [verify.FAIL])
        self.assertIn("hook 解释器可用", [name for name, _, _ in checks])

    def test_rollback_preserves_user_edits_to_preexisting_file(self) -> None:
        existing = self.cfg / "CODEBUDDY.md"
        existing.write_text("original user instructions\n", encoding="utf-8")
        install.apply(cfg=self.cfg)
        existing.write_text("new user instructions\n", encoding="utf-8")
        result = rollback_mod.rollback(cfg=self.cfg)
        self.assertIn("CODEBUDDY.md", result["kept"])
        self.assertEqual(existing.read_text(encoding="utf-8"), "new user instructions\n")

    def test_rollback_merges_user_edited_settings(self) -> None:
        before = self.settings()
        install.apply(cfg=self.cfg)
        settings = self.settings()
        settings["userPreferenceAfterInstall"] = True
        settings["skillOverrides"]["kb"] = "user-invocable-only"
        (self.cfg / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        preview = rollback_mod.rollback(cfg=self.cfg, dry_run=True)
        actual = rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual(preview, {**actual, "dry_run": True})
        self.assertIn("settings.json", actual["changed"])
        after = self.settings()
        self.assertTrue(after["userPreferenceAfterInstall"])
        self.assertEqual(after["skillOverrides"], {"kb": "user-invocable-only", "daily": "off"})
        self.assertEqual(after["hooks"], before["hooks"])
        for key in ("claw", "pluginConfigs", "sandbox", "enabledPlugins"):
            self.assertEqual(after[key], before[key], key)
        for key in ("permissions", "toolControl", "memory", "reasoningEffort"):
            self.assertNotIn(key, after)
        self.assertFalse((self.cfg / "hooks/session_start.py").exists())

    def test_old_snapshot_without_installed_hash_keeps_later_user_edits(self) -> None:
        result = install.apply(cfg=self.cfg)
        manifest = Path(result["state"]["backup"]) / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            entry.pop("installed_sha256", None)
        manifest.write_text(json.dumps(data), encoding="utf-8")
        settings = self.settings()
        settings["skillOverrides"]["handoff"] = "user-invocable-only"
        (self.cfg / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        rollback_mod.rollback(cfg=self.cfg, backup=manifest.parent)
        self.assertEqual(self.settings()["skillOverrides"]["handoff"], "user-invocable-only")
        self.assertNotIn("toolControl", self.settings())

    def test_rollback_keeps_recreated_rule(self) -> None:
        install.apply(cfg=self.cfg)
        rule = self.cfg / "rules/engineering.md"
        rule.write_text("NEW USER RULE\n", encoding="utf-8")
        result = rollback_mod.rollback(cfg=self.cfg)
        self.assertIn("rules/engineering.md", result["kept"])
        self.assertEqual(rule.read_text(encoding="utf-8"), "NEW USER RULE\n")

    def test_missing_settings_backup_does_not_leave_dangling_hooks(self) -> None:
        result = install.apply(cfg=self.cfg)
        saved = Path(result["state"]["backup"]) / "files/settings.json"
        saved.unlink()
        preview = rollback_mod.rollback(cfg=self.cfg, dry_run=True)
        actual = rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual(preview["kept"], actual["kept"])
        self.assertIn("settings.json", actual["missing"])
        self.assertTrue((C.state_dir(self.cfg) / "state.json").is_file())
        for name in (*C.HOOK_SCRIPTS, "_hooklib.py"):
            self.assertTrue((self.cfg / "hooks" / name).is_file())

    def test_same_second_backup_sequence_is_reversed_numerically(self) -> None:
        target = self.cfg / "sequence.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(C.time, "strftime", return_value="20261027-120000"):
            snapshots = []
            for index in range(1, 12):
                snapshot = C.Backup(self.cfg)
                snapshot.save(target)
                data = f"version {index}".encode()
                target.write_bytes(data)
                snapshot.note(target, data)
                snapshots.append(snapshot.finish())
        C.write_json(C.state_dir(self.cfg) / "state.json", {"initial_backup": str(snapshots[0])})
        preview = rollback_mod.rollback(cfg=self.cfg, dry_run=True)
        self.assertEqual(target.read_text(encoding="utf-8"), "version 11")
        actual = rollback_mod.rollback(cfg=self.cfg)
        self.assertEqual(preview["kept"], actual["kept"])
        self.assertFalse(actual["kept"])
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_apply_repairs_persisted_auto_string(self) -> None:
        settings = self.settings()
        settings["autoCompactWindow"] = "auto"
        (self.cfg / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        install.apply(cfg=self.cfg)
        self.assertNotIn("autoCompactWindow", self.settings())
        install.apply(cfg=self.cfg)
        self.assertNotIn("autoCompactWindow", self.settings())

    def test_compact_window_type_validation(self) -> None:
        for value in ("auto", "900000", None, True, False, 0, -1, 1.5, float("nan"), 2**53):
            with self.subTest(value=value):
                self.assertFalse(C.valid_compact_window(value))
        for value in (1, 200000, 888889, 1000000):
            self.assertTrue(C.valid_compact_window(value))

    def test_verify_rejects_auto_string_even_after_app_rewrite(self) -> None:
        install.apply(cfg=self.cfg)
        settings = self.settings()
        settings["autoCompactWindow"] = "auto"
        (self.cfg / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        future = time.time() + 30
        os.utime(self.cfg / "settings.json", (future, future))
        self.assertTrue(verify._settings_rewritten(self.cfg))
        checks = {name: state for name, state, _ in verify.static_checks(self.cfg)}
        self.assertEqual(checks["autoCompactWindow"], verify.FAIL)

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
        targets = install.prompt_targets(self.cfg)
        # Automations start in the `work` welcome mode, so it must get the coding prompt too.
        self.assertEqual({t.parent.parent.name for t in targets}, {"welcomemode-code", "welcomemode-work"})
        for target in targets:
            self.assertEqual(target.read_bytes(), (C.PROFILE / "prompt" / "prompt.tpl").read_bytes())
            self.assertIn(C.PROMPT_MARKER, target.read_text(encoding="utf-8"))

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
        self.assertEqual(len(checks), 30, "校验项数量变了就同步更新这里")

    def test_verify_accepts_source_download_without_git_metadata(self) -> None:
        install.apply(cfg=self.cfg)
        source = Path(self.tmp.name) / "source-download"
        source.mkdir()
        with patch.object(C, "REPO", source):
            checks = {name: state for name, state, _ in verify.static_checks(self.cfg)}
        self.assertEqual(checks["hook 会话启动可执行"], verify.PASS)

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
