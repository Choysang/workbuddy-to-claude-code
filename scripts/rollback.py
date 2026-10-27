"""Restore the configuration directory from a harness backup."""

from __future__ import annotations

from pathlib import Path

import common as C


def pick_backup(cfg: Path, backup: Path | None = None) -> Path | None:
    """Resolve which snapshot to restore.

    `initial_backup` (recorded by the first apply) is the only snapshot that
    actually predates the harness: after apply → apply, the newest backup only
    describes the state the first apply produced.
    """
    if backup is not None:
        return Path(backup)
    state = C.read_json(C.state_dir(cfg) / "state.json", default={}) or {}
    for key in ("initial_backup", "backup"):
        value = state.get(key)
        if value and (Path(value) / "manifest.json").is_file():
            return Path(value)
    return C.latest_backup(cfg)


def rollback(cfg: Path | None = None, backup: Path | None = None,
             dry_run: bool = False) -> dict:
    cfg = Path(cfg or C.config_dir())
    root = pick_backup(cfg, backup)
    if root is None or not (root / "manifest.json").is_file():
        raise SystemExit("没有可用的备份，无法回滚")

    roots = [root]
    if backup is None:
        history = C.list_backups(cfg)
        if root in history:
            roots = list(reversed(history[history.index(root):]))
    def replay(preview: bool, keep: set[str]) -> dict:
        result = {"changed": [], "kept": [], "missing": []}
        protected = set(keep)
        # Preview only the files mentioned in snapshots; never copy the config
        # tree or write a target, including an absolute manifest path.
        virtual: dict[str, bytes | None] | None = {} if preview else None
        for snapshot in roots:
            part = C.restore_backup(snapshot, cfg, dry_run=preview, protected=protected, virtual=virtual)
            for key in result:
                result[key].extend(part[key])
            protected.update(part["kept"])
        return {key: list(dict.fromkeys(value)) for key, value in result.items()}

    planned = replay(True, set())
    dependencies: set[str] = set()
    if "settings.json" in (*planned["kept"], *planned["missing"]):
        # A user-edited settings file may still register our hooks. Keep the
        # small script set with it instead of leaving dangling blocking hooks.
        dependencies = {f"hooks/{name}" for name in (*C.HOOK_SCRIPTS, *C.OPTIONAL_HOOKS, "_hooklib.py")}
    result = replay(dry_run, dependencies)
    if not dry_run and not result["missing"]:
        state = C.state_dir(cfg) / "state.json"
        if state.is_file():
            state.unlink()
    return {"backup": str(root), "dry_run": dry_run, **result}
