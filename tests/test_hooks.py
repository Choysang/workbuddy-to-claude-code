"""Behavioural tests for the harness hooks (hook protocol, exit codes, payloads)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "profile" / "hooks"


def run_hook(script: str, payload: dict, config_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["WORKBUDDY_CONFIG_DIR"] = str(config_dir)
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=60,
        env=env,
    )


class PostEditCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def edit(self, path: Path):
        return run_hook("post_edit_check.py",
                        {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}, self.dir)

    def test_valid_python_passes(self) -> None:
        target = self.dir / "ok.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        self.assertEqual(self.edit(target).returncode, 0)

    def assert_syntax_feedback(self, result, filename: str) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        specific = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PostToolUse")
        self.assertIn(filename, specific["additionalContext"])
        self.assertIn("Syntax check failed", specific["additionalContext"])
        self.assertIn("syntax-error", (self.dir / "hooks/harness-hooks.log").read_text(encoding="utf-8"))

    def test_broken_python_returns_model_context_with_location(self) -> None:
        target = self.dir / "bad.py"
        target.write_text("def f(:\n    pass\n", encoding="utf-8")
        result = self.edit(target)
        self.assert_syntax_feedback(result, "bad.py")

    def test_broken_json_blocks(self) -> None:
        target = self.dir / "bad.json"
        target.write_text('{"a": 1,}', encoding="utf-8")
        self.assert_syntax_feedback(self.edit(target), "bad.json")

    def test_broken_notebook_cell_blocks(self) -> None:
        target = self.dir / "bad.ipynb"
        target.write_text(json.dumps({"cells": [{"cell_type": "code", "source": ["def f(:\n"]}],
                                      "nbformat": 4}), encoding="utf-8")
        result = self.edit(target)
        self.assert_syntax_feedback(result, "bad.ipynb")

    def test_notebook_magic_cell_is_not_flagged(self) -> None:
        target = self.dir / "ok.ipynb"
        target.write_text(json.dumps({"cells": [{"cell_type": "code",
                                                 "source": ["%matplotlib inline\n", "x = 1\n"]}],
                                      "nbformat": 4}), encoding="utf-8")
        self.assertEqual(self.edit(target).returncode, 0)

    @unittest.skipUnless(shutil.which("bash") or shutil.which("sh"), "bash 不可用")
    def test_broken_shell_blocks(self) -> None:
        target = self.dir / "bad.sh"
        target.write_text("if [ -f x ]; then\n", encoding="utf-8")
        self.assert_syntax_feedback(self.edit(target), "bad.sh")

    def test_unknown_extension_is_ignored(self) -> None:
        target = self.dir / "notes.txt"
        target.write_text("anything )(", encoding="utf-8")
        self.assertEqual(self.edit(target).returncode, 0)

    def test_non_edit_tool_is_ignored(self) -> None:
        result = run_hook("post_edit_check.py", {"tool_name": "Read", "tool_input": {}}, self.dir)
        self.assertEqual(result.returncode, 0)

    def test_empty_stdin_does_not_crash(self) -> None:
        env = dict(os.environ)
        env["WORKBUDDY_CONFIG_DIR"] = str(self.dir)
        result = subprocess.run([sys.executable, str(HOOKS / "post_edit_check.py")],
                                input=b"", capture_output=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0)

    def test_writes_log_line(self) -> None:
        target = self.dir / "ok.py"
        target.write_text("x = 1\n", encoding="utf-8")
        self.edit(target)
        log = self.dir / "hooks" / "harness-hooks.log"
        self.assertTrue(log.is_file())
        self.assertIn("ok", log.read_text(encoding="utf-8"))


class PreToolGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def bash(self, command: str):
        return run_hook("pre_tool_guard.py",
                        {"tool_name": "Bash", "tool_input": {"command": command}}, self.dir)

    def test_blocks_root_delete(self) -> None:
        self.assertEqual(self.bash("rm -rf /").returncode, 2)

    def test_blocks_home_delete(self) -> None:
        self.assertEqual(self.bash("rm -rf ~").returncode, 2)

    def test_blocks_disk_format(self) -> None:
        self.assertEqual(self.bash("mkfs.ext4 /dev/sda1").returncode, 2)

    def test_allows_workspace_delete(self) -> None:
        self.assertEqual(self.bash("rm -rf build/").returncode, 0)

    def test_allows_force_push(self) -> None:
        self.assertEqual(self.bash("git push --force origin feature").returncode, 0)

    def test_ignores_non_shell_tools(self) -> None:
        result = run_hook("pre_tool_guard.py",
                          {"tool_name": "Read", "tool_input": {"command": "rm -rf /"}}, self.dir)
        self.assertEqual(result.returncode, 0)


class SessionStartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_outputs_repo_state_in_git_repo(self) -> None:
        result = run_hook("session_start.py", {"cwd": str(REPO)}, self.dir)
        self.assertEqual(result.returncode, 0)
        self.assertIn("<repo_state>", result.stdout.decode("utf-8", "replace"))
        self.assertIn("branch:", result.stdout.decode("utf-8", "replace"))

    def test_non_git_directory_is_silent(self) -> None:
        result = run_hook("session_start.py", {"cwd": self.tmp.name}, self.dir)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), b"")

    @unittest.skipUnless(shutil.which("git"), "git 不可用")
    def test_preserves_modified_filename_and_logs_to_shared_journal(self) -> None:
        root = self.dir / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        target = root / "tracked.txt"
        target.write_text("before\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Harness Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "fixture"], check=True, capture_output=True)
        target.write_text("after\n", encoding="utf-8")
        result = run_hook("session_start.py", {"cwd": str(root)}, self.dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        specific = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "SessionStart")
        self.assertIn("touched: tracked.txt", specific["additionalContext"])
        self.assertIn("session_start", (self.dir / "hooks/harness-hooks.log").read_text(encoding="utf-8"))


class PromptSubmitTest(unittest.TestCase):
    def test_context_protocol_and_optional_parallel_hint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory)
            for prompt, hint in (("检查状态", False), ("parallel tasks", True)):
                with self.subTest(prompt=prompt):
                    result = run_hook("prompt_submit.py", {"cwd": directory, "prompt": prompt}, cfg)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    specific = json.loads(result.stdout)["hookSpecificOutput"]
                    self.assertEqual(specific["hookEventName"], "UserPromptSubmit")
                    self.assertIn("<turn_context>", specific["additionalContext"])
                    self.assertRegex(specific["additionalContext"], r"now: \d{4}-\d{2}-\d{2}")
                    self.assertEqual("/lanes" in specific["additionalContext"], hint)


if __name__ == "__main__":
    unittest.main()
