"""Shared helpers for the harness hooks.

Every hook receives the event payload as JSON on stdin and talks back either
through its exit code (2 = block) or through a JSON object on stdout. Keeping the
wire format in one place keeps the context-producing hooks consistent.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE_DIRNAME = ".harness"


def payload() -> dict:
    """Read the hook payload. A malformed payload must never crash a hook: the
    engine treats a crashed hook as a failed hook and the tool call dies with it."""
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace")) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def cwd(payload_data: dict) -> Path:
    for key in ("cwd",):
        value = payload_data.get(key)
        if isinstance(value, str) and value:
            candidate = Path(value)
            if candidate.is_dir():
                return candidate
    return Path.cwd()


def emit(context: str | None = None, *, event: str, decision: str | None = None,
         reason: str | None = None, message: str | None = None) -> None:
    """Print the hook result object.

    `additionalContext` is injected as a system-reminder; `permissionDecision`
    only means something for PreToolUse. Anything else is ignored by the engine,
    so an unknown key here is silently useless — keep the shape minimal.
    """
    specific: dict = {"hookEventName": event}
    if context:
        specific["additionalContext"] = context
    if decision:
        specific["permissionDecision"] = decision
        if reason:
            specific["permissionDecisionReason"] = reason
    body: dict = {"hookSpecificOutput": specific}
    if message:
        body["systemMessage"] = message
    print(json.dumps(body, ensure_ascii=False))


def block(reason: str) -> None:
    """Exit 2 feeds stderr back to the model as the tool result."""
    sys.stderr.write(reason if reason.endswith("\n") else reason + "\n")
    raise SystemExit(2)


def log(name: str, line: str) -> None:
    """Append-only journal. Never raises: a logging failure must not fail a hook."""
    try:
        root = Path(os.environ.get("WORKBUDDY_CONFIG_DIR") or Path.home() / ".workbuddy-ai")
        target = root / "hooks" / "harness-hooks.log"
        target.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {name} {line}\n")
    except OSError:
        pass


def run(args: list[str], cwd_path: Path | None = None, timeout: float = 3.0) -> str:
    """Run a command and return stripped stdout, or '' on any failure.

    Hooks sit in front of every tool call, so a missing binary or a slow repo must
    degrade to "no extra context" instead of blocking the session.
    """
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd_path) if cwd_path else None,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    # git status --porcelain reserves its leading columns for status flags.
    return (result.stdout or "").rstrip("\r\n") if result.returncode == 0 else ""


def tool_input(data: dict) -> dict:
    value = data.get("tool_input")
    return value if isinstance(value, dict) else {}


def command_text(data: dict) -> str:
    """The shell command of a Bash/PowerShell call, whatever the tool names it."""
    fields = tool_input(data)
    for key in ("command", "cmd", "script", "shell_command"):
        value = fields.get(key)
        if isinstance(value, str):
            return value
    return ""


def edited_paths(data: dict) -> list[Path]:
    """Files touched by an edit-family tool call."""
    fields = tool_input(data)
    found: list[Path] = []
    for key in ("file_path", "path", "notebook_path"):
        value = fields.get(key)
        if isinstance(value, str) and value:
            found.append(Path(value))
    for key in ("edits", "files"):
        value = fields.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    candidate = item.get("file_path") or item.get("path")
                    if isinstance(candidate, str) and candidate:
                        found.append(Path(candidate))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in found:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique
