#!/usr/bin/env python3
"""SessionStart hook: inject a compact repository state block.

Stdout is added to the session context. Keep it small: the goal is orientation
(branch, dirty files, recent commit), not a report.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def git(cwd: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", "replace").strip()


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
    payload = json.loads(raw) if raw.strip() else {}
    cwd = payload.get("cwd") or os.getcwd()
    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        log("session_start non-git")
        return
    status = git(cwd, "status", "--porcelain")
    dirty = len([line for line in status.splitlines() if line.strip()])
    head = git(cwd, "log", "-1", "--pretty=%h %s")
    upstream = git(cwd, "rev-list", "--count", "@{u}..HEAD")
    parts = [f"<repo_state>", f"cwd: {cwd}", f"branch: {branch}"]
    if head:
        parts.append(f"head: {head[:120]}")
    parts.append(f"uncommitted: {dirty} file(s)")
    if upstream:
        parts.append(f"ahead: {upstream} commit(s)")
    parts.append("</repo_state>")
    sys.stdout.write("\n".join(parts) + "\n")
    log(f"session_start {branch} dirty={dirty}")


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
