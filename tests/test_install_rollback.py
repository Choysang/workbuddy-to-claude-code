"""Hermetic integration tests: install -> patch -> rollback on a throwaway repo copy and config dir.

Run: python -m unittest -v tests.test_install_rollback
Never touches the real ~/.workbuddy-ai: uses fixture copies of the original settings, identity files and template.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from patch_code_prompt import MARKER  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "synthetic-prompt.tpl"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstallRollbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="wb-harness-"))
        self.repo = self.root / "repo"
        for part in ("scripts", "payload"):
            shutil.copytree(REPO / part, self.repo / part, ignore=shutil.ignore_patterns("__pycache__", "*.log"))
        # Exercise overwrites without shipping any real user's identity files.
        for name in ("SOUL.md", "USER.md"):
            (self.repo / "payload" / name).write_text("Synthetic replacement\n", encoding="utf-8")
        self.wb = self.root / "wb"
        self.backups = self.root / "backups"
        self.wb.mkdir()
        for name in ("settings.json", "SOUL.md", "USER.md"):
            shutil.copy2(FIXTURE.parent / name, self.wb / name)
        cache = self.root / "cache" / "welcomemode-code" / "v1"
        cache.mkdir(parents=True)
        self.prompt = cache / "prompt.tpl"
        self.prompt.write_bytes(FIXTURE.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
        registry = {"version": 2, "plugins": {"welcomemode-code@workbuddy-builtin": [{"installPath": str(cache)}]}}
        (self.wb / "plugins").mkdir()
        (self.wb / "plugins" / "installed_plugins.json").write_text(json.dumps(registry), encoding="utf-8")
        self.originals = {name: digest(self.wb / name) for name in ("settings.json", "SOUL.md", "USER.md")}
        self.original_prompt = digest(self.prompt)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def run_script(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        # This test owns an isolated config tree; the real desktop may stay open.
        self.assertEqual(self.wb.parent, self.root)
        if args[0] in ("install.py", "rollback.py"):
            args = (*args, "--force")
        env = dict(os.environ, WORKBUDDY_CONFIG_DIR=str(self.wb), HARNESS_BACKUP_ROOT=str(self.backups),
                   PYTHONIOENCODING="utf-8", HARNESS_PROFILE="legacy")
        result = subprocess.run([sys.executable, *args], cwd=self.repo / "scripts", env=env, capture_output=True,
                                timeout=120)
        output = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
        self.assertEqual(result.returncode, expect, output)
        return result

    def settings(self) -> dict:
        return json.loads((self.wb / "settings.json").read_text(encoding="utf-8"))

    def assert_fully_restored(self) -> None:
        for name, value in self.originals.items():
            self.assertEqual(digest(self.wb / name), value, f"{name} not restored byte-for-byte")
        for leftover in ("CODEBUDDY.md", "agents", "rules", "hooks", "skills"):
            self.assertFalse((self.wb / leftover).exists(), f"{leftover} left behind")

    def test_full_cycle_restores_everything_byte_for_byte(self) -> None:
        before = self.settings()
        self.run_script("install.py")
        after = self.settings()
        self.assertEqual(after["autoCompactWindow"], 888889)
        self.assertIn("post_edit_check.py", json.dumps(after["hooks"]))
        for key, value in before.items():
            self.assertEqual(after[key], value, f"install changed unrelated key {key}")
        self.assertIn(b"nothing to do", self.run_script("install.py").stdout)

        self.run_script("patch_code_prompt.py", "apply")
        self.assertIn(MARKER, self.prompt.read_text(encoding="utf-8"))
        self.assertIn(b"Already patched", self.run_script("patch_code_prompt.py", "apply").stdout)
        self.assertNotIn("plugin-recommendation", self.prompt.read_text(encoding="utf-8"))
        self.run_script("patch_code_prompt.py", "rollback")
        self.assertEqual(digest(self.prompt), self.original_prompt)
        self.assertIn(b"already the original", self.run_script("patch_code_prompt.py", "rollback").stdout)

        self.run_script("rollback.py")
        self.assert_fully_restored()
        self.assertIn(b"Nothing to roll back", self.run_script("rollback.py").stdout)

    def test_rollback_keeps_edits_to_created_files(self) -> None:
        self.run_script("install.py")
        (self.wb / "CODEBUDDY.md").write_text("user edit", encoding="utf-8")
        self.run_script("rollback.py")
        kept = list(self.backups.glob("*-install/modified-after-install/CODEBUDDY.md"))
        self.assertEqual([k.read_text(encoding="utf-8") for k in kept], ["user edit"])

    def test_rollback_keeps_edits_to_overwritten_files(self) -> None:
        self.run_script("install.py")
        with open(self.wb / "USER.md", "a", encoding="utf-8") as handle:
            handle.write("\n- agent appended fact\n")
        self.run_script("rollback.py")
        self.assertEqual(digest(self.wb / "USER.md"), self.originals["USER.md"])
        kept = list(self.backups.glob("*-install/modified-after-install/USER.md"))
        self.assertEqual(len(kept), 1)
        self.assertIn("agent appended fact", kept[0].read_text(encoding="utf-8"))

    def test_reinstall_after_payload_change_then_rollback_unwinds_everything(self) -> None:
        self.run_script("install.py")
        with open(self.repo / "payload" / "CODEBUDDY.md", "a", encoding="utf-8") as handle:
            handle.write("\n## v2 addition\n")
        self.run_script("install.py")
        self.assertIn("v2 addition", (self.wb / "CODEBUDDY.md").read_text(encoding="utf-8"))
        self.run_script("rollback.py")
        self.assert_fully_restored()
        self.assertEqual(len(list(self.backups.glob("*-install/ROLLED_BACK"))), 2)

    def test_explicit_rolled_back_dir_is_refused(self) -> None:
        self.run_script("install.py")
        self.run_script("rollback.py")
        backup = next(self.backups.glob("*-install"))
        self.assertIn(b"already rolled back", self.run_script("rollback.py", str(backup), expect=1).stdout)

    def test_failed_rollback_removes_hook_first_and_can_be_resumed(self) -> None:
        self.run_script("install.py")
        backup = next(self.backups.glob("*-install"))
        saved = backup / "files" / "SOUL.md"
        parked = self.root / "SOUL.md.parked"
        shutil.move(str(saved), parked)
        self.run_script("rollback.py", expect=1)
        self.assertNotIn("hooks", self.settings(), "hook must be unregistered even when file restore fails")
        self.assertFalse((backup / "ROLLED_BACK").exists())
        shutil.move(str(parked), saved)
        self.run_script("rollback.py")
        self.assert_fully_restored()

    def test_hook_run_log_is_moved_out_so_hooks_dir_is_removed(self) -> None:
        self.run_script("install.py")
        (self.wb / "hooks" / "post_edit_check.log").write_text("2026-10-06T10:00:00\tok\t5ms\tx.py\n",
                                                                encoding="utf-8")
        self.run_script("rollback.py")
        self.assert_fully_restored()
        self.assertEqual(len(list(self.backups.glob("*-install/post_edit_check.log"))), 1)


if __name__ == "__main__":
    unittest.main()
