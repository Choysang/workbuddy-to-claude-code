"""PostToolUse hook for WorkBuddy (CodeBuddy CLI engine).

Runs fast syntax/format checks on a file right after Edit/MultiEdit/Write.

Exit codes:
  0 - nothing to report, or the check was skipped
  2 - a definite problem was found; the message on stderr is fed back to the model

The hook must never break the agent: any internal error ends with exit 0.
Every run appends one line to post_edit_check.log next to this script (evidence that it ran).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Callable

MAX_FILE_BYTES = 5 * 1024 * 1024
SUBPROCESS_TIMEOUT_SEC = 15
MAX_REPORTED_LINES = 8
RUN_LOG = Path(os.environ.get("WB_HOOK_LOG") or Path(__file__).with_suffix(".log"))
RUN_LOG_MAX_BYTES = 512 * 1024
PATH_KEYS = ("file_path", "path", "filePath", "notebook_path")
JSONC_NAME_PATTERN = re.compile(
    r"^(tsconfig.*|jsconfig.*|\.eslintrc|\.?devcontainer|biome|deno|.*\.code-workspace)\.json$", re.IGNORECASE)
SHELL_INTERPRETERS = {"sh", "bash", "dash"}
ESM_SYNTAX = re.compile(rb"^\s*(import|export)\b", re.MULTILINE)
TEXT_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")

Checker = Callable[[Path, bytes], list[str]]


def extract_path(payload: dict) -> Path | None:
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        return None
    raw = next((tool_input[k] for k in PATH_KEYS if isinstance(tool_input.get(k), str)), None)
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(payload.get("cwd") or os.getcwd()) / path
    return path


def run_tool(args: list[str], env_extra: dict[str, str] | None = None,
             stdin: bytes | None = None) -> tuple[int, str] | None:
    """Run an external checker. Returns None when it cannot run (missing, blocked, timed out)."""
    env = dict(os.environ, **(env_extra or {}))
    try:
        proc = subprocess.run(args, input=stdin, capture_output=True, timeout=SUBPROCESS_TIMEOUT_SEC, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    raw = proc.stdout + proc.stderr
    output = raw.decode("utf-8", errors="replace")
    if output.count("�") > 3:
        output = raw.decode("mbcs" if os.name == "nt" else "latin-1", errors="replace")
    return proc.returncode, output.strip()


def first_lines(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[:MAX_REPORTED_LINES]


def check_python(path: Path, data: bytes) -> list[str]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    try:
        source = importlib.util.decode_source(data)
        compile(source, str(path), "exec", dont_inherit=True)
    except SyntaxError as exc:
        return [f"Python 语法错误 第 {exc.lineno} 行: {exc.msg}（按 Python {version} 检查；"
                f"若项目目标版本更新且该语法合法，说明后可忽略）"]
    except (UnicodeDecodeError, ValueError) as exc:
        return [f"Python 源码无法解码/编译: {exc}"]
    return []


def check_json(path: Path, data: bytes) -> list[str]:
    in_vscode_dir = path.parent.name.lower() == ".vscode"
    if in_vscode_dir or JSONC_NAME_PATTERN.match(path.name):
        return []  # JSON-with-comments files; strict parsing would report false errors
    try:
        json.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return []
    except json.JSONDecodeError as exc:
        return [f"JSON 解析失败 第 {exc.lineno} 行第 {exc.colno} 列: {exc.msg}"]
    return []


def check_yaml(path: Path, data: bytes) -> list[str]:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return []
    loader = getattr(yaml, "CBaseLoader", None) or yaml.BaseLoader
    try:
        # compose (not construct): custom tags such as !Ref / !reference stay valid, and it is fast
        list(yaml.compose_all(data.decode("utf-8-sig"), Loader=loader))
    except UnicodeDecodeError:
        return []
    except yaml.YAMLError as exc:
        return [f"YAML 解析失败: {str(exc).splitlines()[0]}"]
    return []


def check_toml(path: Path, data: bytes) -> list[str]:
    try:
        import tomllib
    except ImportError:
        return []
    try:
        tomllib.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return []
    except tomllib.TOMLDecodeError as exc:
        return [f"TOML 解析失败: {exc}"]
    return []


def check_xml(path: Path, data: bytes) -> list[str]:
    try:
        ET.fromstring(data)
    except ET.ParseError as exc:
        return [f"XML 解析失败: {exc}"]
    return []


def shebang_interpreter(data: bytes) -> str | None:
    if not data.startswith(b"#!"):
        return None
    parts = data.split(b"\n", 1)[0][2:].decode("utf-8", errors="replace").split()
    if not parts:
        return None
    name = re.split(r"[\\/]", parts[0])[-1]
    if name == "env":
        rest = [part for part in parts[1:] if not part.startswith("-")]
        name = re.split(r"[\\/]", rest[0])[-1] if rest else ""
    return name.lower()


def check_shell(path: Path, data: bytes) -> list[str]:
    if b"\r\n" in data:
        return [".sh 文件含 CRLF 行尾，shell 执行会出错；改为 LF"]
    interpreter = shebang_interpreter(data)
    if interpreter is not None and interpreter not in SHELL_INTERPRETERS:
        return []  # zsh/ksh/... scripts: bash -n would report false errors
    bash = shutil.which("bash")
    result = run_tool([bash, "-n", str(path)]) if bash else None
    if result and result[0] != 0:
        return ["bash -n 语法检查失败:"] + first_lines(result[1])
    return []


def check_batch(path: Path, data: bytes) -> list[str]:
    problems = []
    if any(byte > 0x7F for byte in data):
        try:
            data.decode("utf-8")
            is_utf8 = True
        except UnicodeDecodeError:
            is_utf8 = False  # e.g. GBK, which cmd.exe reads correctly on Chinese Windows
        if is_utf8 and b"chcp 65001" not in data.lower():
            problems.append(".bat/.cmd 以 UTF-8 保存了非 ASCII 字符但没有 `chcp 65001`，cmd.exe 会按本地代码页解析成乱码。"
                            "中文路径改用 %~dp0 或环境变量，或在开头加 chcp 65001")
    if b"\n" in data.replace(b"\r\n", b""):
        problems.append(".bat/.cmd 含 LF-only 行尾；改为 CRLF（LF 行尾会让 goto/call 标签出错）")
    return problems


def check_powershell(path: Path, data: bytes) -> list[str]:
    if not data.startswith(TEXT_BOMS) and any(byte > 0x7F for byte in data):
        return ["含非 ASCII 字符的 .ps1 没有 BOM；Windows PowerShell 5.1 会按 ANSI 解码导致乱码或语法错误。另存为 UTF-8 with BOM"]
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return []
    script = (
        "$t=$null;$e=$null;"
        "[void][System.Management.Automation.Language.Parser]::ParseFile($env:WB_HOOK_PS_FILE,[ref]$t,[ref]$e);"
        "foreach($x in $e){'{0}:{1}: {2}' -f $x.Extent.StartLineNumber,$x.Extent.StartColumnNumber,$x.Message}"
    )
    result = run_tool([powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                      env_extra={"WB_HOOK_PS_FILE": str(path)})
    if result and result[1]:
        label = "Windows PowerShell 5.1" if Path(powershell).stem.lower() == "powershell" else "PowerShell"
        return [f"{label} 解析错误（行:列）:"] + first_lines(result[1])
    return []


def check_javascript(path: Path, data: bytes) -> list[str]:
    node = shutil.which("node")
    if not node:
        return []
    result = run_tool([node, "--check", str(path)])
    if result and result[0] != 0:
        return ["node --check 语法检查失败:"] + first_lines(result[1])
    if path.suffix.lower() == ".js" and ESM_SYNTAX.search(data):
        # node --check exits 0 for ambiguous .js with import/export; re-check explicitly as an ES module
        module = run_tool([node, "--input-type=module", "--check"], stdin=data)
        if module and module[0] != 0:
            return ["node --check（按 ES module 复查）语法检查失败:"] + first_lines(module[1])
    return []


CHECKERS: dict[str, Checker] = {
    ".py": check_python,
    ".pyw": check_python,
    ".json": check_json,
    ".yaml": check_yaml,
    ".yml": check_yaml,
    ".toml": check_toml,
    ".xml": check_xml,
    ".ui": check_xml,
    ".sh": check_shell,
    ".bat": check_batch,
    ".cmd": check_batch,
    ".ps1": check_powershell,
    ".psm1": check_powershell,
    ".js": check_javascript,
    ".mjs": check_javascript,
    ".cjs": check_javascript,
}


def log_run(result: str, path: Path | None, started: float) -> None:
    try:
        if RUN_LOG.exists() and RUN_LOG.stat().st_size > RUN_LOG_MAX_BYTES:
            os.replace(RUN_LOG, RUN_LOG.with_suffix(".log.1"))
        elapsed_ms = int((time.monotonic() - started) * 1000)
        line = f"{datetime.now().isoformat(timespec='seconds')}\t{result}\t{elapsed_ms}ms\t{path or '-'}\n"
        with open(RUN_LOG, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def main() -> int:
    started = time.monotonic()
    path: Path | None = None
    problems: list[str] = []
    result = "skip"
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        path = extract_path(payload) if isinstance(payload, dict) else None
        checker = CHECKERS.get(path.suffix.lower()) if path else None
        if checker is not None and path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
            problems = checker(path, path.read_bytes())
            result = "problem" if problems else "ok"
    except Exception:  # never break the agent because of the hook itself
        problems, result = [], "error"
    log_run(result, path, started)
    if not problems:
        return 0
    message = "\n".join([f"[编辑后自动检查] {path}", *[f"- {p}" for p in problems],
                         "请先修复上述问题再继续；若确属有意为之，向用户说明原因。"])
    sys.stderr.buffer.write((message + "\n").encode("utf-8"))
    sys.stderr.flush()
    return 2


if __name__ == "__main__":
    sys.exit(main())
