"""Real default-profile install, repeat install, and restoration in a temp tree."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EngineeringInstallTest(unittest.TestCase):
    def test_default_profile_install_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            original = {"autoCompactWindow": 888889, "custom": {"keep": True},
                        "disabledTools": ["TeamCreate", "Unrelated"],
                        "hooks": {"PostToolUse": [{"hooks": [
                            {"command": f'python "{(config / "hooks/post_edit_check.py").as_posix()}"'},
                            {"command": "user-check"}]}]}}
            settings = config / "settings.json"
            settings.write_text(json.dumps(original), encoding="utf-8")
            env = dict(os.environ, WORKBUDDY_CONFIG_DIR=str(config),
                       HARNESS_BACKUP_ROOT=str(root / "backups"), HARNESS_PROFILE="engineering",
                       PYTHONIOENCODING="utf-8")

            def run(script, *args):
                result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args],
                                        env=env, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                return result.stdout

            run("install.py", "--dry-run")
            self.assertEqual(json.loads(settings.read_text()), original)
            self.assertFalse((root / "backups").exists())
            run("install.py", "--force")
            result = json.loads(settings.read_text())
            self.assertNotIn("autoCompactWindow", result)
            self.assertEqual(result["disabledTools"], ["Unrelated"])
            self.assertEqual(result["hooks"]["PostToolUse"][0]["hooks"], [{"command": "user-check"}])
            self.assertEqual(len(list((config / "agents").glob("*.md"))), 3)
            self.assertEqual(len(list((config / "rules").glob("*.md"))), 1)
            self.assertIn(b"nothing to do", run("install.py", "--force"))
            run("rollback.py", "--force")
            self.assertEqual(json.loads(settings.read_text()), original)
            self.assertFalse((config / "agents").exists())
            self.assertFalse((config / "rules").exists())

    def test_rollback_preserves_later_user_settings(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from engineering import changes, configured
        from common import HOOK_SCRIPT
        from rollback import reverted_settings
        original = {"memory": {"autoMemoryEnabled": False},
                    "disabledTools": ["TeamCreate"],
                    "hooks": {"PostToolUse": [{"hooks": [{"command": f'python "{HOOK_SCRIPT.as_posix()}"'}]}]}}
        installed = configured(original)
        installed["memory"]["userAdded"] = True
        installed["disabledTools"].append("UserDisabled")
        installed["hooks"]["PreToolUse"] = [{"hooks": [{"command": "user-after"}]}]
        restored = reverted_settings(installed, {"engineering": changes(original)})
        self.assertTrue(restored["memory"]["userAdded"])
        self.assertFalse(restored["memory"]["autoMemoryEnabled"])
        self.assertEqual(restored["disabledTools"], ["UserDisabled"])
        self.assertEqual(restored["hooks"]["PreToolUse"], installed["hooks"]["PreToolUse"])
        self.assertEqual(restored["hooks"]["PostToolUse"], original["hooks"]["PostToolUse"])

    def test_user_hook_with_same_basename_is_preserved(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from engineering import configured
        hooks = {"PostToolUse": [{"hooks": [{"command": "python D:/my-project/hooks/post_edit_check.py"}]}]}
        self.assertEqual(configured({"hooks": hooks})["hooks"], hooks)
