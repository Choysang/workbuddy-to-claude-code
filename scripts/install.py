"""Install the harness-upgrade payload into the WorkBuddy config dir (~/.workbuddy-ai).

Usage:
  python scripts/install.py --dry-run   # show the plan only
  python scripts/install.py             # back up, copy payload, merge settings.json

Every overwritten file is backed up under backups/<timestamp>-install/ together with a
manifest.json, so scripts/rollback.py can undo the install exactly. Idempotent.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys

from common import (AUTO_COMPACT_WINDOW, PAYLOAD_DIR, PROFILE, SETTINGS_PATH, WB_DIR, has_our_hook, hook_group,
                    is_workbuddy_running, new_backup_dir, payload_files, read_settings, sha256, write_settings)


def plan_files() -> list[tuple[str, str]]:
    actions = []
    for rel in payload_files():
        target = WB_DIR / rel
        if not target.exists():
            actions.append((rel.as_posix(), "create"))
        elif target.read_bytes() == (PAYLOAD_DIR / rel).read_bytes():
            actions.append((rel.as_posix(), "unchanged"))
        else:
            actions.append((rel.as_posix(), "overwrite"))
    return actions


def plan_settings(settings: dict) -> dict:
    if PROFILE == "engineering":
        from engineering import changes
        return {"engineering": changes(settings)} if changes(settings) else {}
    changes: dict = {}
    if settings.get("autoCompactWindow") != AUTO_COMPACT_WINDOW:
        changes["autoCompactWindow"] = {"had": "autoCompactWindow" in settings, "old": settings.get("autoCompactWindow")}
    if not has_our_hook(settings):
        changes["postToolUseHook"] = {"added": True}
    return changes


def merged_settings(settings: dict, changes: dict) -> dict:
    if PROFILE == "engineering":
        from engineering import configured
        return configured(settings)
    merged = dict(settings)
    if "autoCompactWindow" in changes:
        merged["autoCompactWindow"] = AUTO_COMPACT_WINDOW
    if "postToolUseHook" in changes:
        hooks = dict(merged.get("hooks") or {})
        hooks["PostToolUse"] = [*(hooks.get("PostToolUse") or []), hook_group()]
        merged["hooks"] = hooks
    return merged


def missing_parent_dirs(rels: list[str]) -> list[str]:
    created: set[str] = set()
    for rel in rels:
        parent = (WB_DIR / rel).parent
        while parent != WB_DIR and not parent.exists():
            created.add(parent.relative_to(WB_DIR).as_posix())
            parent = parent.parent
    return sorted(created, key=len, reverse=True)  # deepest first, handy for rollback


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="install even if WorkBuddy is running")
    args = parser.parse_args()

    if not args.dry_run and is_workbuddy_running() and not args.force:
        print("WorkBuddy is running and rewrites settings.json; quit it first (or pass --force).")
        return 1

    actions = plan_files()
    settings = read_settings()
    changes = plan_settings(settings)
    for rel, action in actions:
        print(f"  {action:9} {rel}")
    print(f"  settings  {', '.join(changes) if changes else 'unchanged'}")
    if args.dry_run:
        return 0

    todo = [(rel, action) for rel, action in actions if action != "unchanged"]
    if not todo and not changes:
        print("Already installed; nothing to do.")
        return 0

    backup = new_backup_dir("install")
    shutil.copy2(SETTINGS_PATH, backup / "settings.json.orig")
    for rel, action in todo:
        if action == "overwrite":
            saved = backup / "files" / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(WB_DIR / rel, saved)
    manifest = {
        "wbDir": str(WB_DIR),
        "created": [rel for rel, action in todo if action == "create"],
        "overwritten": [rel for rel, action in todo if action == "overwrite"],
        "createdDirs": missing_parent_dirs([rel for rel, action in todo if action == "create"]),
        "installedSha256": {rel: sha256(PAYLOAD_DIR / rel) for rel, _ in todo},
        "settings": changes,
    }
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    for rel, _ in todo:
        target = WB_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PAYLOAD_DIR / rel, target)
    if changes:
        write_settings(merged_settings(settings, changes))

    print(f"Installed. Backup + manifest: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
