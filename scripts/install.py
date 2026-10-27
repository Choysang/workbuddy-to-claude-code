"""Apply the harness profile to the WorkBuddy configuration directory."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import common as C

MANAGED = (
    ("agents", "*.md"),
    ("commands", "*.md"),
    ("hooks", "*.py"),
)


def _harness_hook_paths(cfg: Path) -> tuple[str, ...]:
    """Absolute command paths this harness owns.

    Matching on the absolute path (not on a bare script name) keeps a user hook
    that happens to call their own `session_start.py` from being deleted.
    """
    hooks_dir = str(Path(cfg) / "hooks").replace("\\", "/").rstrip("/")
    return tuple(f"{hooks_dir}/{name}" for name in C.HOOK_SCRIPTS)


def _is_harness_hook(command: str, owned: tuple[str, ...]) -> bool:
    normalized = command.replace("\\", "/")
    return any(path in normalized for path in owned)


def _snapshot_ok(value: object) -> bool:
    """True when `value` points at a snapshot that can still be restored.

    A stale state.json may reference a backup the user deleted; inheriting it
    would make every later rollback fail with "没有可用的备份".
    """
    if not isinstance(value, str) or not value:
        return False
    return (Path(value) / "manifest.json").is_file()


# Paths that only exist before the harness has written anything: the rule file the
# harness replaces and the folders it populates. A snapshot holding none of them
# was taken by a later, narrower apply (e.g. one that only rewrote settings.json)
# and therefore cannot undo the harness.
_ANCHOR_MARKERS = ("CODEBUDDY.md", "rules/", "agents/", "commands/", "hooks/")


def _covers_harness(manifest_root: Path) -> bool:
    manifest = C.read_json(Path(manifest_root) / "manifest.json", default={}) or {}
    for entry in manifest.get("entries", []):
        path = str(entry.get("path", ""))
        if any(path == marker or path.startswith(marker) for marker in _ANCHOR_MARKERS):
            return True
    return False


def _pick_initial_backup(cfg: Path, previous: dict, current: str | None) -> str | None:
    """Rollback anchor = the oldest snapshot that still predates the harness.

    Only the first snapshot is a valid anchor: every later one already contains
    harness output, so restoring it would leave the harness half-applied. Inheriting
    `previous["backup"]` (the last apply's snapshot) is wrong for the same reason,
    which is why the fallback scans the backup directory oldest-first instead.
    """
    inherited = previous.get("initial_backup")
    # An inherited anchor must prove it predates the harness. A settings-only
    # snapshot recorded by an earlier apply is a valid *restorable* snapshot but
    # a useless anchor: it cannot undo CODEBUDDY.md, rules/ or agents/.
    if _snapshot_ok(inherited) and _covers_harness(Path(inherited)):
        return inherited
    for root in C.list_backups(cfg):
        if _covers_harness(root):
            return str(root)
    if _snapshot_ok(previous.get("backup")):
        return previous["backup"]
    return current


def _render_hooks(groups: dict, cfg: Path) -> dict:
    hooks_dir = cfg / "hooks"
    rendered = {}
    for event, entries in groups.items():
        rendered[event] = []
        for entry in entries:
            new_entry = {"hooks": []}
            if "matcher" in entry:
                new_entry["matcher"] = entry["matcher"]
            for hook in entry["hooks"]:
                command = hook["command"]
                command = command.replace("{python}", C.interpreter())
                for name in C.HOOK_SCRIPTS:
                    command = command.replace(
                        "{hook:%s}" % name.replace(".py", ""),
                        str(hooks_dir / name).replace("\\", "/"),
                    )
                new_entry["hooks"].append({**hook, "command": command})
            rendered[event].append(new_entry)
    return rendered


def _merge_settings(current: dict, cfg: Path) -> dict:
    profile = C.read_json(C.PROFILE / "settings.json") or {}
    plugins = C.read_json(C.PROFILE / "plugins.json") or {}
    data = dict(current)

    for key in C.REMOVED_SETTINGS:
        data.pop(key, None)

    sandbox = data.get("sandbox")
    if isinstance(sandbox, dict) and sandbox.get("extraAllowWrite"):
        sandbox = dict(sandbox)
        sandbox["extraAllowWrite"] = []
        data["sandbox"] = sandbox

    owned = _harness_hook_paths(cfg)
    existing = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    merged: dict = {}
    for event, groups in existing.items():
        kept = [
            group for group in groups
            if not any(_is_harness_hook(h.get("command", ""), owned) for h in group.get("hooks", []))
        ]
        if kept:
            merged[event] = kept
    for event, groups in _render_hooks(profile.get("hooks", {}), cfg).items():
        merged.setdefault(event, []).extend(groups)
    if merged or "hooks" in data:
        data["hooks"] = merged

    # 'auto' is a profile directive. The runtime's /autocompact auto removes
    # the setting; persisting the string makes Math.min return NaN.
    if "autoCompactWindow" in profile:
        window = profile["autoCompactWindow"]
        if window == "auto":
            data.pop("autoCompactWindow", None)
        elif C.valid_compact_window(window):
            data["autoCompactWindow"] = window
        else:
            raise ValueError("autoCompactWindow must be 'auto' or a positive safe integer")

    for key in ("permissions", "alwaysThinkingEnabled",
                "fileCheckpointingEnabled", "deferToolLoading", "reasoningEffort", "memory"):
        if key in profile:
            data[key] = profile[key]

    enabled = dict(data.get("enabledPlugins") or {})
    for plugin_id in plugins.get("disable", []):
        enabled[plugin_id] = False
    # Assign, do not setdefault: a stale `false` from an earlier profile would
    # otherwise survive forever and silently keep a wanted plugin disabled.
    for plugin_id in plugins.get("keep", []):
        enabled[plugin_id] = True
    if enabled or "enabledPlugins" in data:
        data["enabledPlugins"] = enabled
    return data


def prompt_targets(cfg: Path) -> list[Path]:
    root = cfg / "plugins" / "cache" / "workbuddy-builtin" / "welcomemode-code"
    return sorted(root.glob("*/prompt.tpl")) if root.is_dir() else []


def apply(cfg: Path | None = None, dry_run: bool = False) -> dict:
    cfg = Path(cfg or C.config_dir())
    if not cfg.is_dir():
        raise SystemExit(f"配置目录不存在：{cfg}")

    actions: list[str] = []
    backup = C.Backup(cfg, "apply")
    source_prompt = C.PROFILE / "prompt" / "prompt.tpl"

    def write(target: Path, data: bytes, label: str) -> None:
        if target.exists() and target.read_bytes() == data:
            return
        actions.append(label)
        if dry_run:
            return
        backup.save(target)
        C.write_bytes(target, data)
        # Record what we wrote: rollback needs the digest to tell our own artefact
        # from a file the user edited afterwards.
        backup.note(target, data)

    # 1. memory
    memory = (C.PROFILE / "CODEBUDDY.md").read_bytes()
    write(cfg / "CODEBUDDY.md", memory, "memory CODEBUDDY.md")

    # 2. retire duplicated rule files
    rules_dir = cfg / "rules"
    if rules_dir.is_dir():
        for name in C.REMOVED_RULES:
            target = rules_dir / name
            if target.exists():
                actions.append(f"remove rules/{name} (内容已并入 CODEBUDDY.md)")
                if not dry_run:
                    backup.save(target)
                    target.unlink()

    # 3. agents / commands / hooks
    for folder, pattern in MANAGED:
        source = C.PROFILE / folder
        target_dir = cfg / folder
        for src in sorted(source.glob(pattern)):
            write(target_dir / src.name, src.read_bytes(), f"write {folder}/{src.name}")

    # 4. settings
    settings_path = cfg / "settings.json"
    current = C.read_json(settings_path, default={}) or {}
    merged = _merge_settings(current, cfg)
    if merged != current:
        actions.append("update settings.json")
        if not dry_run:
            backup.save(settings_path)
            payload = C.json_bytes(merged)
            C.write_bytes(settings_path, payload)
            backup.note(settings_path, payload)

    # 5. system prompt
    prompt = source_prompt.read_bytes()
    for target in prompt_targets(cfg):
        write(target, prompt, f"prompt {target.relative_to(cfg).as_posix()}")

    # 6. state
    state_path = C.state_dir(cfg) / "state.json"
    previous = C.read_json(state_path, default={}) or {}
    state = {
        "version": "3.0",
        "applied": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config_dir": str(cfg),
        "profile_sha256": C.sha256(source_prompt),
        "managed": [f"{folder}/{name}" for folder, pattern in MANAGED
                    for name in sorted(p.name for p in (C.PROFILE / folder).glob(pattern))],
        "dry_run": dry_run,
    }
    if not dry_run:
        if actions:
            root = backup.finish()
            state["backup"] = str(root)
        elif _snapshot_ok(previous.get("backup")):
            # Nothing to do this round: keep pointing at the last snapshot that
            # actually holds files, otherwise a no-op apply would erase the only
            # record of where the previous changes were saved.
            state["backup"] = previous["backup"]
        anchor = _pick_initial_backup(cfg, previous, state.get("backup"))
        if anchor:
            state["initial_backup"] = anchor
        C.write_json(state_path, state)

    return {"config_dir": str(cfg), "dry_run": dry_run, "actions": actions, "state": state}
