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

    result = C.restore_backup(root, cfg, dry_run=dry_run)
    if not dry_run:
        state = C.state_dir(cfg) / "state.json"
        if state.is_file():
            state.unlink()
    return {"backup": str(root), "dry_run": dry_run, **result}
