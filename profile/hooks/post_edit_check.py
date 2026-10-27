#!/usr/bin/env python3
"""PostToolUse hook: syntax gate for edited files.

Reads the hook payload from stdin, checks the edited file with the cheapest
available parser, and returns structured PostToolUse context when it is broken.
WorkBuddy 5.8.4 logs exit-2 stderr without passing it to the model. Its supported
additionalContext field reaches the tool result, so syntax feedback uses exit 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 4 * 1024 * 1024
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "ApplyPatch"}


def log(line: str) -> None:
    try:
        root = Path(os.environ.get("WORKBUDDY_CONFIG_DIR") or Path.home() / ".workbuddy-ai")
        path = root / "hooks" / "harness-hooks.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line.replace("\n", " ")[:400] + "\n")
    except Exception:
        pass


def fail(message: str) -> None:
    log(f"syntax-error {message}")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": f"Syntax check failed. Repair this file before continuing:\n{message}",
    }}, ensure_ascii=False))
    raise SystemExit(0)


def check_python(path: Path) -> None:
    source = path.read_bytes()
    try:
        compile(source, str(path), "exec")
    except SyntaxError as error:
        fail(f"{path}:{error.lineno}: {error.msg}\n{(error.text or '').strip()}")


def check_json(path: Path) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{path}:{error.lineno}: JSON 解析失败 {error.msg}")


def check_toml(path: Path) -> None:
    try:
        import tomllib
    except ImportError:
        return
    try:
        tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        fail(f"{path}: TOML 解析失败 {error}")


def check_yaml(path: Path) -> None:
    try:
        import yaml
    except ImportError:
        return
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as error:
        fail(f"{path}: YAML 解析失败 {error}")


def check_shell(path: Path) -> None:
    """Feed the script through stdin so Windows paths never reach bash as arguments."""
    text = path.read_bytes()
    for executable in ("bash", "sh"):
        try:
            result = subprocess.run(
                [executable, "-n"], input=text, capture_output=True, timeout=15
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            message = (result.stderr or result.stdout).decode("utf-8", "replace").strip()
            fail(f"{path}: shell 语法错误\n{message[:600]}")
        return


def check_javascript(path: Path) -> None:
    node = os.environ.get("WORKBUDDY_NODE_BIN") or "node"
    try:
        result = subprocess.run(
            [node, "--check", str(path)], capture_output=True, timeout=20
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    if result.returncode != 0:
        message = (result.stderr or result.stdout).decode("utf-8", "replace").strip()
        fail(f"{path}: JS 语法错误\n{message[:600]}")


def check_notebook(path: Path) -> None:
    """A notebook is JSON whose code cells are Python, so check both layers."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{path}:{error.lineno}: notebook JSON 解析失败 {error.msg}")
    if not isinstance(data, dict):
        fail(f"{path}: notebook 顶层不是对象")
    for index, cell in enumerate(data.get("cells") or []):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source")
        code = "".join(source) if isinstance(source, list) else (source or "")
        # Magics and shell escapes are not Python: skip the whole cell instead of
        # reporting a syntax error the agent cannot fix.
        if any(line.lstrip().startswith(("%", "!", "?")) for line in code.splitlines()):
            continue
        try:
            compile(code, f"{path}[cell {index}]", "exec")
        except SyntaxError as error:
            fail(f"{path}: 单元格 {index} 第 {error.lineno} 行：{error.msg}")


CHECKS = {
    ".py": check_python,
    ".json": check_json,
    ".ipynb": check_notebook,
    ".toml": check_toml,
    ".yaml": check_yaml,
    ".yml": check_yaml,
    ".sh": check_shell,
    ".bash": check_shell,
    ".js": check_javascript,
    ".mjs": check_javascript,
    ".cjs": check_javascript,
}


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    if not raw.strip():
        return
    payload = json.loads(raw)
    if payload.get("tool_name") not in EDIT_TOOLS:
        return
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(target, str) or not target:
        return
    path = Path(target)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        return
    checker = CHECKS.get(path.suffix.lower())
    if checker is None:
        return
    checker(path)
    log(f"ok {path.suffix} {path}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:  # a hook crash must not block editing
        log(f"error {type(error).__name__}: {error}")
        raise SystemExit(0)
