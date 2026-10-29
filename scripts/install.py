"""Apply the harness profile to the WorkBuddy configuration directory."""

from __future__ import annotations

import shutil
import re
import shlex
import time
from pathlib import Path

import common as C
import workspace as W

MANAGED = (
    ("agents", "*.md"),
    ("commands", "*.md"),
    ("hooks", "*.py"),
    ("output-styles", "*.md"),
)


def _harness_hook_paths(cfg: Path) -> tuple[str, ...]:
    """Absolute command paths this harness owns.

    Matching on the absolute path (not on a bare script name) keeps a user hook
    that happens to call their own `session_start.py` from being deleted.
    """
    hooks_dir = str(Path(cfg) / "hooks").replace("\\", "/").rstrip("/")
    return tuple(f"{hooks_dir}/{name}" for name in (*C.HOOK_SCRIPTS, *C.OPTIONAL_HOOKS))


def _is_harness_hook(command: str, owned: tuple[str, ...]) -> bool:
    normalized = command.replace("\\", "/")
    return any(re.search(re.escape(path) + r'''(?=$|[\s"';&|)])''', normalized, re.IGNORECASE)
               for path in owned)


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
                command = command.replace("{python}", shlex.quote(C.interpreter()))
                for name in (*C.HOOK_SCRIPTS, *C.OPTIONAL_HOOKS):
                    command = command.replace(
                        "{hook:%s}" % name.replace(".py", ""),
                        str(hooks_dir / name).replace("\\", "/"),
                    )
                new_entry["hooks"].append({**hook, "command": command})
            rendered[event].append(new_entry)
    return rendered


def _merge_settings(current: dict, cfg: Path, prompt_context: bool = False) -> dict:
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
        kept = []
        for group in groups:
            hooks = [h for h in group.get("hooks", [])
                     if not _is_harness_hook(h.get("command", ""), owned)]
            if hooks:
                kept.append({**group, "hooks": hooks})
        if kept:
            merged[event] = kept
    for event, groups in _render_hooks(profile.get("hooks", {}), cfg).items():
        merged.setdefault(event, []).extend(groups)
    if prompt_context:
        optional = {"UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 10,
                    "command": '{python} "{hook:prompt_submit}"'}]}]}
        for event, groups in _render_hooks(optional, cfg).items():
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

    overrides = dict(data.get("skillOverrides") or {})
    for name in C.read_json(C.PROFILE / "builtin-skills-off.json"):
        overrides[name] = "off"
    data["skillOverrides"] = overrides

    control = data.get("toolControl", {})
    if not isinstance(control, dict):
        raise ValueError("toolControl must be an object")
    control = dict(control)
    version = control.get("version", 1)
    if type(version) is not int or version != 1:
        raise ValueError("Unsupported toolControl.version; expected integer 1")
    control.setdefault("version", 1)
    required_controls = C.read_json(C.PROFILE / "tool-control.json")
    # Early v4 drafts used builtin IDs for connector MCP tools. Migrate only
    # those exact entries to their supported IDs; preserve other user choices.
    legacy = {"builtin:" + value.split(":", 2)[2]
              for value in required_controls.get("disabledMcpToolIds", [])}
    if isinstance(control.get("disabledToolIds"), list):
        control["disabledToolIds"] = [value for value in control["disabledToolIds"]
                                      if not isinstance(value, str) or value not in legacy]
    for key, required in required_controls.items():
        existing_ids = control.get(key, [])
        if not isinstance(existing_ids, list) or not all(isinstance(v, str) for v in existing_ids):
            raise ValueError(f"toolControl.{key} must be a string array")
        control[key] = list(dict.fromkeys([*existing_ids, *required]))
    data["toolControl"] = control
    return data


def _restore_entry(target: dict, original: dict, key: str) -> None:
    if key in original:
        target[key] = original[key]
    else:
        target.pop(key, None)


def unmerge_settings(current: dict, original: dict, cfg: Path) -> dict:
    """Undo _merge_settings on a settings file the user changed after install.

    Only what the harness owns goes back to its pre-install value; every other key,
    including the user's own plugin, skill and tool choices, stays as it is now.
    """
    profile = C.read_json(C.PROFILE / "settings.json") or {}
    plugins = C.read_json(C.PROFILE / "plugins.json") or {}
    data = dict(current)

    for key in (*C.REMOVED_SETTINGS, *(k for k in profile if k != "hooks")):
        _restore_entry(data, original, key)

    sandbox, before = data.get("sandbox"), original.get("sandbox")
    if isinstance(sandbox, dict) and isinstance(before, dict) and "extraAllowWrite" in before:
        data["sandbox"] = {**sandbox, "extraAllowWrite": before["extraAllowWrite"]}

    if isinstance(data.get("hooks"), dict):
        owned = _harness_hook_paths(cfg)
        hooks: dict = {}
        for event, groups in data["hooks"].items():
            kept = []
            for group in groups:
                entries = [h for h in group.get("hooks", []) if not _is_harness_hook(h.get("command", ""), owned)]
                if entries:
                    kept.append({**group, "hooks": entries})
            if kept:
                hooks[event] = kept
        if hooks or "hooks" in original:
            data["hooks"] = hooks
        else:
            data.pop("hooks")

    def restore_ids(key: str, ids) -> None:
        if not isinstance(data.get(key), dict):
            return
        values, before = dict(data[key]), original.get(key) or {}
        for name in ids:
            _restore_entry(values, before, name)
        data[key] = values

    restore_ids("enabledPlugins", [*plugins.get("disable", []), *plugins.get("keep", [])])
    restore_ids("skillOverrides", C.read_json(C.PROFILE / "builtin-skills-off.json"))

    control, before = data.get("toolControl"), original.get("toolControl") or {}
    if isinstance(control, dict):
        control = dict(control)
        required_controls = C.read_json(C.PROFILE / "tool-control.json")
        for key, required in required_controls.items():
            if isinstance(control.get(key), list):
                kept_ids = set(before.get(key) or [])
                control[key] = [v for v in control[key] if v not in required or v in kept_ids]
        # The harness created the block; drop it again once nothing in it is the user's.
        leftover = {k: v for k, v in control.items() if k != "version" and v != []}
        if "toolControl" not in original and not leftover and set(control) <= {"version", *required_controls}:
            data.pop("toolControl")
        else:
            data["toolControl"] = control
    return data


def prompt_targets(cfg: Path) -> list[Path]:
    """Cached welcome-mode prompts. All of them get the coding prompt: automations start in
    `work`, which otherwise runs the vendor's office assistant prompt."""
    root = cfg / "plugins" / "cache" / "workbuddy-builtin"
    return sorted(p for mode in ("code", "work", "design")
                  for p in (root / f"welcomemode-{mode}").glob("*/prompt.tpl"))


def craft_targets(cfg: Path) -> list[Path]:
    root = cfg / "plugins" / "cache" / "workbuddy-builtin" / "interactionmode-craft"
    return sorted(root.glob("*/fragments/interaction.md")) if root.is_dir() else []


def apply(cfg: Path | None = None, dry_run: bool = False,
          prompt_context: bool | None = None, workspaces: list[Path] | None = None) -> dict:
    cfg = Path(cfg or C.config_dir())
    if not cfg.is_dir():
        raise SystemExit(f"配置目录不存在：{cfg}")

    # Validate before the first write; corrupted settings are not an empty file.
    settings_path = cfg / "settings.json"
    current = C.read_json(settings_path, default={}, strict=True)
    if not isinstance(current, dict):
        raise ValueError("settings.json must be an object")
    on_disk_settings = dict(current)

    state_path = C.state_dir(cfg) / "state.json"
    previous = C.read_json(state_path, default={}) or {}
    if not previous.get("product_preferences_restored") and previous.get("initial_backup"):
        original_path = Path(previous["initial_backup"]) / "files/settings.json"
        original = C.read_json(original_path, default={}, strict=True)
        if isinstance(original, dict):
            for key in ("autoLaunchDesired", "autoLaunchDefaultApplied"):
                if key not in current and key in original:
                    current[key] = original[key]
    if prompt_context is None:
        prompt_context = previous.get("options", {}).get("prompt_context") is True
    merged = _merge_settings(current, cfg, prompt_context=prompt_context)
    roots = [Path(value).resolve() for value in previous.get("workspaces", [])]
    for root in workspaces or []:
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError(f"工作区不存在：{root}")
        if root not in roots:
            roots.append(root)
    overlays = []
    active_roots = []
    for root in roots:
        if not root.is_dir():
            C.warn(f"跳过已不存在的工作区：{root}")
            continue
        target = W.settings_path(root)
        data = C.read_json(target, default={}, strict=True)
        overlays.append((target, C.json_bytes(W.merged(data))))
        active_roots.append(root)

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
                    backup.note_deleted(target)

    # 3. agents / commands / hooks
    for folder, pattern in MANAGED:
        source = C.PROFILE / folder
        target_dir = cfg / folder
        for src in sorted(source.glob(pattern)):
            write(target_dir / src.name, src.read_bytes(), f"write {folder}/{src.name}")

    # 4. settings
    if merged != on_disk_settings:
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
    for target in craft_targets(cfg):
        write(target, C.CRAFT_INTERACTION, f"tools {target.relative_to(cfg).as_posix()}")

    for target, data in overlays:
        write(target, data, f"workspace {target.as_posix()}")

    # 6. state
    state = {
        "version": "4.0",
        "product_preferences_restored": True,
        "applied": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config_dir": str(cfg),
        "profile_sha256": C.sha256(source_prompt),
        "managed": [f"{folder}/{name}" for folder, pattern in MANAGED
                    for name in sorted(p.name for p in (C.PROFILE / folder).glob(pattern))],
        "dry_run": dry_run,
        "options": {"prompt_context": prompt_context},
        "workspaces": [str(root) for root in active_roots],
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
