"""Shared paths and helpers for the WorkBuddy harness upgrade scripts."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = os.environ.get("HARNESS_PROFILE", "engineering")
if PROFILE not in ("engineering", "legacy"):
    raise ValueError("HARNESS_PROFILE must be engineering or legacy")
PAYLOAD_DIR = REPO_ROOT / ("profiles/engineering" if PROFILE == "engineering" else "payload")
BACKUP_ROOT = Path(os.environ.get("HARNESS_BACKUP_ROOT") or REPO_ROOT / "backups")
WB_DIR = Path(os.environ.get("WORKBUDDY_CONFIG_DIR") or Path.home() / ".workbuddy-ai")
SETTINGS_PATH = WB_DIR / "settings.json"
INSTALLED_PLUGINS_PATH = WB_DIR / "plugins" / "installed_plugins.json"
PYTHON_VERSIONS_DIR = WB_DIR / "binaries" / "python" / "versions"
HOOK_SCRIPT = WB_DIR / "hooks" / "post_edit_check.py"
HOOK_MARKER = "post_edit_check.py"
HOOK_RUN_LOG = "hooks/post_edit_check.log"
AUTO_COMPACT_WINDOW = 888_889  # engine compacts at min(window, this) * 0.9 -> ~800K on a 1M window
CODE_PLUGIN_KEY = "welcomemode-code@workbuddy-builtin"
WORKBUDDY_PROCESSES = ("WorkBuddyAI.exe", "WorkBuddy.exe")


def hook_command() -> str:
    """Bash command line for the PostToolUse hook (hooks run in Git Bash on Windows).

    Resolves WorkBuddy's managed Python at run time via versions/current, falls back to python on PATH,
    and exits 0 when the script or an interpreter is missing: a missing script must never turn into
    exit code 2, which the engine treats as a blocking error on every edit.
    """
    script, versions = HOOK_SCRIPT.as_posix(), PYTHON_VERSIONS_DIR.as_posix()
    return (f's="{script}"; d="{versions}"; py="$d/$(cat "$d/current" 2>/dev/null)/python.exe"; '
            f'[ -x "$py" ] || py="$(command -v python || command -v python3)"; '
            f'[ -f "$s" ] && [ -n "$py" ] || exit 0; "$py" "$s"')


def hook_group() -> dict:
    return {
        "matcher": "Edit|MultiEdit|Write",
        "hooks": [{"type": "command", "command": hook_command(), "timeout": 30}],
    }


def payload_files() -> list[Path]:
    """Payload files as paths relative to PAYLOAD_DIR, sorted for stable output (runtime artifacts excluded)."""
    return sorted(p.relative_to(PAYLOAD_DIR) for p in PAYLOAD_DIR.rglob("*")
                  if p.is_file() and p.suffix not in (".log", ".pyc", ".1") and "__pycache__" not in p.parts)


def read_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def write_settings(settings: dict) -> None:
    """Write settings.json in the exact format WorkBuddy uses (2-space indent, UTF-8, trailing newline).

    Writes to a temp file first and replaces atomically, so a crash never leaves a truncated file.
    """
    text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)  # sanity check before touching the real file
    tmp = SETTINGS_PATH.with_suffix(".json.harness-tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, SETTINGS_PATH)


def has_our_hook(settings: dict) -> bool:
    groups = settings.get("hooks", {}).get("PostToolUse", [])
    return any(HOOK_MARKER in h.get("command", "") for g in groups for h in g.get("hooks", []))


def new_backup_dir(label: str) -> Path:
    path = BACKUP_ROOT / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{label}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_prompt_path() -> Path:
    """prompt.tpl of the code welcome mode, as loaded at runtime (the plugin cache install path)."""
    registry = json.loads(INSTALLED_PLUGINS_PATH.read_text(encoding="utf-8"))
    entries = registry.get("plugins", {}).get(CODE_PLUGIN_KEY) or []
    if not entries:
        raise SystemExit(f"{CODE_PLUGIN_KEY} not found in {INSTALLED_PLUGINS_PATH}")
    return Path(entries[0]["installPath"]) / "prompt.tpl"


def is_workbuddy_running() -> bool:
    """True when a WorkBuddy process is running. Fails closed: if the check itself fails, assume running."""
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                             timeout=30, errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return any(f'"{name}"' in out for name in WORKBUDDY_PROCESSES)
