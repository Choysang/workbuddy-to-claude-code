"""Black-box tests for payload/hooks/post_edit_check.py (run: python -m unittest -v tests.test_post_edit_check)."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "payload" / "hooks" / "post_edit_check.py"
UTF8_BOM = b"\xef\xbb\xbf"
HAS_YAML = importlib.util.find_spec("yaml") is not None
HAS_NODE = shutil.which("node") is not None


class PostEditCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hook测试 "))
        self.log = self.tmp / "run.log"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, stdin: bytes) -> subprocess.CompletedProcess:
        env = dict(os.environ, WB_HOOK_LOG=str(self.log))
        return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, timeout=60, env=env)

    def check(self, name: str, content: bytes, tool: str = "Edit") -> subprocess.CompletedProcess:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        payload = {"hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": {"file_path": str(path)}}
        return self.run_hook(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def assert_ok(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(result.stderr, b"")

    def assert_problem(self, result: subprocess.CompletedProcess, needle: str) -> None:
        self.assertEqual(result.returncode, 2)
        self.assertIn(needle, result.stderr.decode("utf-8"))

    # Python
    def test_python_valid_passes(self) -> None:
        self.assert_ok(self.check("ok.py", "print('中文')\n".encode("utf-8")))

    def test_python_syntax_error_reports_line_and_checker_version(self) -> None:
        result = self.check("bad.py", b"x = 1\ndef f(:\n    pass\n")
        self.assert_problem(result, "第 2 行")
        self.assertIn(f"Python {sys.version_info.major}.{sys.version_info.minor}", result.stderr.decode("utf-8"))

    def test_python_check_writes_no_pycache(self) -> None:
        self.check("ok.py", b"x = 1\n")
        self.assertFalse((self.tmp / "__pycache__").exists())

    # JSON / YAML / TOML / XML
    def test_json_invalid_reported(self) -> None:
        self.assert_problem(self.check("data.json", b'{"a": 1,}'), "JSON")

    def test_json_with_bom_passes(self) -> None:
        self.assert_ok(self.check("data.json", UTF8_BOM + b'{"a": 1}'))

    def test_jsonc_files_skipped(self) -> None:
        commented = b'{ // comment\n "a": 1 }'
        for name in ("tsconfig.json", ".vscode/settings.json", "biome.json", "deno.json", ".devcontainer.json"):
            with self.subTest(name=name):
                self.assert_ok(self.check(name, commented))

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_yaml_custom_tags_pass(self) -> None:
        cloudformation = b"Resources:\n  Bucket:\n    Name: !Sub '${AWS::StackName}-b'\n    Ref: !Ref Other\n"
        self.assert_ok(self.check("template.yaml", cloudformation))

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_yaml_unclosed_flow_reported(self) -> None:
        self.assert_problem(self.check("bad.yml", b"a: [1, 2\nb: 3\n"), "YAML")

    def test_toml_invalid_reported(self) -> None:
        self.assert_problem(self.check("pyproject.toml", b"[tool\nname = 1\n"), "TOML")

    def test_xml_invalid_reported(self) -> None:
        self.assert_problem(self.check("form.ui", b"<ui><widget></ui>"), "XML")

    # shell scripts
    def test_shell_crlf_reported(self) -> None:
        self.assert_problem(self.check("run.sh", b"echo hi\r\necho bye\r\n"), "CRLF")

    def test_shell_lf_passes(self) -> None:
        self.assert_ok(self.check("run.sh", b"echo hi\necho bye\n"))

    @unittest.skipUnless(shutil.which("bash"), "bash not available")
    def test_shell_syntax_error_reported(self) -> None:
        self.assert_problem(self.check("bad.sh", b"#!/bin/bash\nif true; then\n  echo x\n"), "bash -n")

    def test_zsh_script_not_checked_with_bash(self) -> None:
        zsh_only = b"#!/usr/bin/env zsh\nfor f in *(.); do echo $f; done\n"
        self.assert_ok(self.check("zshonly.sh", zsh_only))

    # batch files
    def test_batch_utf8_non_ascii_without_chcp_reported(self) -> None:
        self.assert_problem(self.check("run.bat", "cd C:\\中文\r\n".encode("utf-8")), "chcp 65001")

    def test_batch_utf8_non_ascii_with_chcp_passes(self) -> None:
        self.assert_ok(self.check("run.bat", "@echo off\r\nchcp 65001\r\ncd C:\\中文\r\n".encode("utf-8")))

    def test_batch_gbk_passes(self) -> None:
        self.assert_ok(self.check("run.bat", "@echo off\r\ncd C:\\中文目录\r\n".encode("gbk")))

    def test_batch_lf_only_reported(self) -> None:
        self.assert_problem(self.check("run.bat", b"@echo off\necho hi\n"), "CRLF")

    def test_batch_ascii_crlf_passes(self) -> None:
        self.assert_ok(self.check("run.bat", b"@echo off\r\nchcp 65001\r\n"))

    # PowerShell
    def test_powershell_non_ascii_without_bom_reported(self) -> None:
        self.assert_problem(self.check("a.ps1", "Write-Host '中文'\r\n".encode("utf-8")), "BOM")

    def test_powershell_utf8_bom_passes(self) -> None:
        self.assert_ok(self.check("a.ps1", UTF8_BOM + "Write-Host '中文'\r\n".encode("utf-8")))

    def test_powershell_utf16_bom_passes(self) -> None:
        self.assert_ok(self.check("a.ps1", "Write-Host '中文'\r\n".encode("utf-16")))

    @unittest.skipUnless(shutil.which("powershell"), "powershell not available")
    def test_powershell_syntax_error_reported(self) -> None:
        self.assert_problem(self.check("b.ps1", b"if ($true) {\r\n  Write-Host 'x'\r\n"), "PowerShell")

    # JavaScript
    @unittest.skipUnless(HAS_NODE, "node not available")
    def test_javascript_syntax_error_reported(self) -> None:
        self.assert_problem(self.check("a.mjs", b"export const x = ;\n"), "node --check")

    @unittest.skipUnless(HAS_NODE, "node not available")
    def test_javascript_valid_passes(self) -> None:
        self.assert_ok(self.check("a.js", b"const x = 1;\nconsole.log(x);\n"))

    @unittest.skipUnless(HAS_NODE, "node not available")
    def test_esm_js_syntax_error_reported(self) -> None:
        self.assert_problem(self.check("esm.js", b"import x from 'y';\nconst a = (;\n"), "ES module")

    @unittest.skipUnless(HAS_NODE, "node not available")
    def test_esm_js_valid_passes(self) -> None:
        self.assert_ok(self.check("esm2.js", b"import fs from 'node:fs';\nexport const n = fs ? 1 : 0;\n"))

    # robustness and evidence
    def test_unknown_extension_skipped(self) -> None:
        self.assert_ok(self.check("notes.md", b"# anything {{{"))

    def test_missing_file_skipped(self) -> None:
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(self.tmp / "nope.py")}}
        self.assert_ok(self.run_hook(json.dumps(payload).encode("utf-8")))

    def test_garbage_stdin_skipped(self) -> None:
        self.assert_ok(self.run_hook(b"\x00not json"))
        self.assert_ok(self.run_hook(b"[1, 2]"))

    def test_relative_path_resolved_against_cwd(self) -> None:
        (self.tmp / "rel.py").write_bytes(b"def f(:\n")
        payload = {"cwd": str(self.tmp), "tool_name": "Write", "tool_input": {"file_path": "rel.py"}}
        self.assert_problem(self.run_hook(json.dumps(payload, ensure_ascii=False).encode("utf-8")), "Python")

    def test_every_run_is_logged(self) -> None:
        self.check("ok.py", b"x = 1\n")
        self.check("bad.py", b"def f(:\n")
        self.check("notes.md", b"text")
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual([line.split("\t")[1] for line in lines], ["ok", "problem", "skip"])


if __name__ == "__main__":
    unittest.main()
