#!/usr/bin/env python3
"""PreToolUse hook: block irreversibly destructive shell commands.

Only catastrophic, unrecoverable patterns are blocked. Ordinary deletes inside
the workspace, force-pushes and rebases are left to the agent's judgement and
the user's own approval flow.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SHELL_TOOLS = {"Bash", "PowerShell", "Shell"}

PATTERNS = (
    (r"--no-preserve-root", "禁止 --no-preserve-root"),
    (r"\brm\s+(-[a-zA-Z]*\s+)*-?[a-zA-Z]*[rf][a-zA-Z]*\s+(-[a-zA-Z]+\s+)*(/|/\*|~|~/\*|\$HOME/?\*?)(\s|$)",
     "禁止递归删除根目录或家目录"),
    (r"\b(mkfs(\.\w+)?|mke2fs)\b", "禁止格式化文件系统"),
    (r"\bdd\b[^\n]*\bof=/dev/(sd|nvme|hd)", "禁止直接写块设备"),
    (r">\s*/dev/(sd|nvme|hd)\w", "禁止重定向写块设备"),
    (r":\s*\(\s*\)\s*\{.*\|.*&.*\}\s*;\s*:", "禁止 fork 炸弹"),
    (r"\bformat\s+[a-zA-Z]:", "禁止格式化磁盘"),
    (r"\b(Remove-Item|rm|del|rd|rmdir)\b[^\n]*\b(-Recurse|-r)\b[^\n]*\b(C:\\\\?|C:/?)(\s|\"|'|$)",
     "禁止递归删除系统盘根目录"),
    (r"\bchmod\s+-R\s+777\s+/\s*$", "禁止对根目录递归改权限"),
)


def log(line: str) -> None:
    try:
        root = Path(os.environ.get("WORKBUDDY_CONFIG_DIR") or Path.home() / ".workbuddy-ai")
        path = root / "hooks" / "harness-hooks.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line.replace("\n", " ")[:400] + "\n")
    except Exception:
        pass


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    if not raw.strip():
        return
    payload = json.loads(raw)
    if payload.get("tool_name") not in SHELL_TOOLS:
        return
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return
    for pattern, reason in PATTERNS:
        if re.search(pattern, command, re.IGNORECASE | re.DOTALL):
            log(f"blocked {reason}")
            sys.stderr.write(
                f"已阻止：{reason}。命令：{command[:200]}\n"
                "如果这确实是用户明确要求的操作，先向用户确认具体目标路径，再用最小范围的命令重试。"
            )
            raise SystemExit(2)
    log("pass pre_tool_guard")


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
    except Exception as error:
        log(f"error {type(error).__name__}: {error}")
        raise SystemExit(0)
