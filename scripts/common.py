"""Shared paths, atomic IO and byte-exact backup for the harness installer."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROFILE = REPO / "profile"
STATE_DIRNAME = ".harness"

# Keys owned by the product but unrelated to an engineering harness.
REMOVED_SETTINGS = (
    "claw",
    "officeFileAssociationsRepairMarker",
    "officeMarkdownDefaultClaimAttempted",
    "autoLaunchDesired",
    "autoLaunchDefaultApplied",
    "pluginConfigs",
)

# Rule files superseded by CODEBUDDY.md; keeping both duplicates every request.
REMOVED_RULES = ("engineering.md",)

HOOK_SCRIPTS = ("session_start.py", "pre_tool_guard.py", "post_edit_check.py")

# Single source of truth for hook wiring. verify cross-checks profile/settings.json
# against these tables, so a matcher can never drift away from the tools the script
# actually handles (the bug that left `Shell` and `NotebookEdit` unwatched).
HOOK_EVENTS = {
    "session_start.py": "SessionStart",
    "pre_tool_guard.py": "PreToolUse",
    "post_edit_check.py": "PostToolUse",
}
HOOK_MATCHERS = {
    "pre_tool_guard.py": ("Bash", "PowerShell", "Shell"),
    "post_edit_check.py": ("Edit", "Write", "MultiEdit", "NotebookEdit", "ApplyPatch"),
}


def config_dir() -> Path:
    env = os.environ.get("WORKBUDDY_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".workbuddy-ai"


def state_dir(cfg: Path | None = None) -> Path:
    return (cfg or config_dir()) / STATE_DIRNAME


def read_json(path: Path, default=None, strict: bool = False):
    """Read JSON, tolerating a missing file.

    `strict` makes malformed JSON a hard error instead of a silent default: callers
    that then rewrite the file (settings.json) must never treat corruption as `{}`.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, UnicodeDecodeError) as error:
        if strict:
            raise ValueError(f"{path} 无法读取：{error}") from error
        warn(f"{path} 无法读取：{error}")
        return default
    except json.JSONDecodeError as error:
        if strict:
            raise ValueError(f"{path} 不是合法 JSON：{error}") from error
        warn(f"{path} 不是合法 JSON：{error}")
        return default


def write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-harness")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def json_bytes(payload) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, payload) -> None:
    write_bytes(path, json_bytes(payload))


def sha256(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return ""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path, cfg: Path) -> str:
    try:
        return Path(path).resolve().relative_to(cfg.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _store_key(path: Path, cfg: Path) -> str:
    """Storage path inside the backup, safe even when the target lives outside cfg."""
    key = rel(path, cfg)
    if not Path(key).is_absolute():
        return key
    tag = hashlib.sha1(str(Path(path)).encode("utf-8")).hexdigest()[:12]
    return f"_external/{tag}/{Path(path).name}"


def _unique_dir(parent: Path, name: str) -> Path:
    """Two applies inside the same second must not share (and overwrite) a backup."""
    candidate = parent / name
    index = 1
    while candidate.exists():
        index += 1
        candidate = parent / f"{name}-{index}"
    return candidate


class Backup:
    """Snapshot files before the installer touches them.

    Each entry records whether the file existed plus the hash of what the installer
    wrote, so rollback can tell "harness artefact" from "file the user rewrote later".
    The manifest is flushed after every entry: a crash halfway leaves a usable backup.
    """

    def __init__(self, cfg: Path, tag: str = "apply"):
        self.cfg = Path(cfg)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.root = _unique_dir(state_dir(cfg) / "backups", f"{stamp}-{tag}")
        self.entries: list[dict] = []
        self._index: dict[str, dict] = {}

    def save(self, path: Path) -> dict:
        path = Path(path)
        existing = self._index.get(str(path))
        if existing is not None:
            return existing
        entry = {"path": rel(path, self.cfg), "store": _store_key(path, self.cfg),
                 "existed": path.exists()}
        if entry["existed"]:
            target = self.root / "files" / entry["store"]
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(path, target)
            except OSError as error:
                raise OSError(f"备份 {path} 失败：{error}") from error
        self.entries.append(entry)
        self._index[str(path)] = entry
        self._flush()
        return entry

    def note(self, path: Path, data: bytes) -> None:
        """Record the content the installer wrote, so rollback can spot later edits."""
        entry = self._index.get(str(Path(path)))
        if entry is None:
            return
        entry["installed_sha256"] = digest(data)
        self._flush()

    def _flush(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self.root / "manifest.json", {
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "config_dir": str(self.cfg),
            "entries": self.entries,
        })

    def finish(self) -> Path:
        self._flush()
        return self.root


def list_backups(cfg: Path) -> list[Path]:
    """Every snapshot that still has a manifest, oldest first.

    Directory names start with a `%Y%m%d-%H%M%S` stamp, so lexicographic order is
    chronological order. A snapshot whose manifest is gone is skipped: it cannot be
    restored and must never be offered as a rollback anchor.
    """
    root = state_dir(cfg) / "backups"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if (p / "manifest.json").is_file())


def latest_backup(cfg: Path) -> Path | None:
    candidates = list_backups(cfg)
    return candidates[-1] if candidates else None


def restore_backup(backup_root: Path, cfg: Path, dry_run: bool = False) -> dict:
    """Restore a snapshot.

    Returns three buckets so the caller can report the truth instead of claiming a
    clean rollback:
      changed  - paths written back or deleted
      kept     - files the user rewrote after install (never silently destroyed)
      missing  - entries whose backup copy is gone; the target was left untouched

    `dry_run` runs the exact same decisions without touching disk, so the preview
    can never disagree with the real run.
    """
    manifest = read_json(Path(backup_root) / "manifest.json", default={}) or {}
    result = {"changed": [], "kept": [], "missing": []}
    for entry in manifest.get("entries", []):
        target = Path(cfg) / entry["path"]
        if entry.get("existed"):
            source = Path(backup_root) / "files" / entry.get("store", entry["path"])
            if not source.is_file():
                result["missing"].append(entry["path"])
                continue
            if not dry_run:
                write_bytes(target, source.read_bytes())
            result["changed"].append(entry["path"])
            continue
        if not target.exists():
            continue
        expected = entry.get("installed_sha256")
        if expected and digest(target.read_bytes()) != expected:
            result["kept"].append(entry["path"])
            continue
        if not dry_run:
            target.unlink()
        result["changed"].append(f"-{entry['path']}")
    return result


def interpreter() -> str:
    """Absolute interpreter path when available, so hooks survive a bare PATH."""
    candidate = Path(sys.executable)
    return str(candidate).replace("\\", "/") if candidate.is_file() else "python"


def interpreter_available() -> bool:
    return bool(shutil.which(interpreter()))


def info(message: str) -> None:
    print(message, flush=True)


def warn(message: str) -> None:
    print(f"WARN {message}", flush=True)


def fail(message: str) -> None:
    print(f"FAIL {message}", flush=True)
