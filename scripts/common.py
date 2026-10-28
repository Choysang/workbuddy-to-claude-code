"""Shared paths, atomic IO and byte-exact backup for the harness installer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROFILE = REPO / "profile"
STATE_DIRNAME = ".harness"


def valid_compact_window(value: object) -> bool:
    """The engine expects a positive JS-safe integer, not an 'auto' string."""
    return type(value) is int and 0 < value <= 9_007_199_254_740_991

# Keys owned by the product but unrelated to an engineering harness.
REMOVED_SETTINGS = (
    "claw",
    "pluginConfigs",
)

# Keep product preferences/migration markers: deleting them repeats default
# startup or file-association setup. They expose no tools or model context.

# Rule files superseded by CODEBUDDY.md; keeping both duplicates every request.
REMOVED_RULES = ("engineering.md",)

HOOK_SCRIPTS = ("session_start.py", "pre_tool_guard.py", "post_edit_check.py")
OPTIONAL_HOOKS = {"prompt_submit.py": "UserPromptSubmit"}
PROMPT_MARKER = "workbuddy-engineering-v5"

# Claude Code shape: the hot path stays resident (by trace call counts), everything else is
# deferred so its schema costs only a name until ToolSearch loads it.
ACTIVE_TOOLS = (
    "Agent", "AskUserQuestion", "Bash", "DeferExecuteTool", "Edit", "Glob", "Grep", "Read",
    "Skill", "TaskCreate", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate", "ToolSearch",
    "WebFetch", "WebSearch", "Write", "present_files",
    # Only shown while the session is in plan mode; costs nothing otherwise.
    "ExitPlanMode",
)
DEFERRED_TOOLS = (
    "PowerShell", "MultiEdit", "NotebookEdit", "LSP", "TaskGet", "SendMessage",
    "EnterPlanMode", "EnterWorktree", "LeaveWorktree", "Monitor",
    "ListAgents", "InterruptAgent", "TeamCreate", "TeamDelete", "CronCreate", "CronList",
    "CronDelete", "ListMcpResources", "ReadMcpResource", "WaitForMcpServers",
)
CODE_TOOLS = ",".join(ACTIVE_TOOLS + tuple(f"Defer({name})" for name in DEFERRED_TOOLS))
# The engine intersects --tools with the work mode's frontmatter tool list, so craft mode must
# declare the same profile or tools missing from the vendor list (plan mode, worktrees, Monitor)
# never reach the session.
CRAFT_INTERACTION = ("---\nname: craft\ndescription: Coding work mode tool policy (harness profile).\ntools:\n"
                     + "".join(f"  - {spec}\n" for spec in CODE_TOOLS.split(",")) + "---\n").encode("utf-8")

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

    def note_deleted(self, path: Path) -> None:
        entry = self._index.get(str(Path(path)))
        if entry is not None:
            entry["installed_absent"] = True
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
    def order(path: Path):
        return tuple((1, int(part)) if part.isdigit() else (0, part)
                     for part in re.split(r"(\d+)", path.name))
    return sorted((p for p in root.iterdir() if (p / "manifest.json").is_file()), key=order)


def latest_backup(cfg: Path) -> Path | None:
    candidates = list_backups(cfg)
    return candidates[-1] if candidates else None


def restore_backup(backup_root: Path, cfg: Path, dry_run: bool = False,
                   protected: set[str] | None = None,
                   virtual: dict[str, bytes | None] | None = None) -> dict:
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
        if protected and entry["path"] in protected:
            result["kept"].append(entry["path"])
            continue
        target = Path(cfg) / entry["path"]
        current_bytes = (virtual[entry["path"]] if virtual is not None and entry["path"] in virtual
                         else target.read_bytes() if target.is_file() else None)
        if entry.get("existed"):
            source = Path(backup_root) / "files" / entry.get("store", entry["path"])
            if not source.is_file():
                result["missing"].append(entry["path"])
                continue
            expected = entry.get("installed_sha256")
            source_bytes = source.read_bytes()
            if entry.get("installed_absent") and current_bytes is not None and current_bytes != source_bytes:
                result["kept"].append(entry["path"])
                continue
            if expected and current_bytes is not None:
                current = digest(current_bytes)
                if current != expected and current != digest(source_bytes):
                    result["kept"].append(entry["path"])
                    continue
            if not dry_run:
                write_bytes(target, source_bytes)
            elif virtual is not None:
                virtual[entry["path"]] = source_bytes
            result["changed"].append(entry["path"])
            continue
        if current_bytes is None:
            continue
        expected = entry.get("installed_sha256")
        if expected and digest(current_bytes) != expected:
            result["kept"].append(entry["path"])
            continue
        if not dry_run:
            target.unlink()
        elif virtual is not None:
            virtual[entry["path"]] = None
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
