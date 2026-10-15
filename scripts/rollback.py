"""Undo installs made by scripts/install.py.

Usage:
  python scripts/rollback.py                 # undo every install that is not rolled back yet, newest first
  python scripts/rollback.py <backup-dir>    # undo only that install (must be the newest pending one)

Order inside one install: settings.json first (removes the hook, so a half-finished rollback can never
leave a hook pointing at a deleted script), then files. Only the keys the install added are reverted.
Files changed after the install are never lost: their current content is kept under
<backup-dir>/modified-after-install/ before anything is restored or removed.
An install is marked ROLLED_BACK only when every step succeeded; re-running continues a partial rollback.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from common import (BACKUP_ROOT, HOOK_MARKER, HOOK_RUN_LOG, WB_DIR, is_workbuddy_running, read_settings, sha256,
                    write_settings)

ROLLED_BACK = "ROLLED_BACK"


def pending_installs() -> list[Path]:
    return sorted(p for p in BACKUP_ROOT.glob("*-install")
                  if (p / "manifest.json").is_file() and not (p / ROLLED_BACK).exists())


def reverted_settings(settings: dict, changes: dict) -> dict:
    reverted = dict(settings)
    compact = changes.get("autoCompactWindow")
    if compact:
        if compact["had"]:
            reverted["autoCompactWindow"] = compact["old"]
        else:
            reverted.pop("autoCompactWindow", None)
    if changes.get("postToolUseHook"):
        hooks = dict(reverted.get("hooks") or {})
        groups = [g for g in hooks.get("PostToolUse") or []
                  if not any(HOOK_MARKER in h.get("command", "") for h in g.get("hooks", []))]
        if groups:
            hooks["PostToolUse"] = groups
        else:
            hooks.pop("PostToolUse", None)
        if hooks:
            reverted["hooks"] = hooks
        else:
            reverted.pop("hooks", None)
    return reverted


def keep_modified(backup: Path, rel: str, move: bool) -> None:
    kept = backup / "modified-after-install" / rel
    kept.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(WB_DIR / rel), kept)
    else:
        shutil.copy2(WB_DIR / rel, kept)
    print(f"  kept      {rel} -> {kept} (modified after install)")


def restore_overwritten(backup: Path, rel: str, installed: str | None) -> None:
    target, original = WB_DIR / rel, backup / "files" / rel
    if target.exists():
        if sha256(target) == sha256(original):
            return  # already restored by an earlier, partial run
        if sha256(target) != installed:
            keep_modified(backup, rel, move=False)
    shutil.copy2(original, target)
    print(f"  restored  {rel}")


def remove_created(backup: Path, rel: str, installed: str | None) -> None:
    target = WB_DIR / rel
    if not target.exists():
        return
    if sha256(target) != installed:
        keep_modified(backup, rel, move=True)
        return
    target.unlink()
    print(f"  removed   {rel}")


def rollback_one(backup: Path) -> list[str]:
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if Path(manifest["wbDir"]) != WB_DIR:
        return [f"{backup.name} targets {manifest['wbDir']}, current config dir is {WB_DIR}"]
    installed = manifest.get("installedSha256", {})
    errors: list[str] = []

    def attempt(label: str, action) -> None:
        try:
            action()
        except Exception as exc:  # collect and continue; ROLLED_BACK is only written on full success
            errors.append(f"{label}: {exc}")

    if manifest["settings"]:
        attempt("settings.json", lambda: write_settings(reverted_settings(read_settings(), manifest["settings"])))
    if "hooks/post_edit_check.py" in manifest["created"]:  # its run log would keep hooks/ from being removed
        for log in (WB_DIR / HOOK_RUN_LOG, WB_DIR / (HOOK_RUN_LOG + ".1")):
            if log.exists():
                attempt(log.name, lambda log=log: shutil.move(str(log), backup / log.name))
    for rel in manifest["overwritten"]:
        attempt(rel, lambda rel=rel: restore_overwritten(backup, rel, installed.get(rel)))
    for rel in manifest["created"]:
        attempt(rel, lambda rel=rel: remove_created(backup, rel, installed.get(rel)))
    for rel in manifest["createdDirs"]:
        directory = WB_DIR / rel
        if directory.is_dir() and not any(directory.iterdir()):
            attempt(rel, directory.rmdir)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("backup_dir", nargs="?", type=Path)
    parser.add_argument("--force", action="store_true", help="roll back even if WorkBuddy is running")
    args = parser.parse_args()

    if is_workbuddy_running() and not args.force:
        print("WorkBuddy is running (or the process check failed) and it rewrites settings.json; "
              "quit it first, or pass --force.")
        return 1

    pending = pending_installs()
    if args.backup_dir:
        if (args.backup_dir / ROLLED_BACK).exists():
            print(f"{args.backup_dir.name} is already rolled back.")
            return 1
        if not pending or pending[-1].resolve() != args.backup_dir.resolve():
            print("Only the newest pending install can be rolled back on its own; run without arguments "
                  "to unwind all pending installs in order.")
            return 1
        targets = [args.backup_dir]
    else:
        targets = list(reversed(pending))
    if not targets:
        print("Nothing to roll back.")
        return 0

    for backup in targets:
        errors = rollback_one(backup)
        if errors:
            print(f"Rollback of {backup.name} incomplete; fix the errors and re-run:")
            for error in errors:
                print(f"  ERROR {error}")
            return 1
        (backup / ROLLED_BACK).write_text("rolled back\n", encoding="utf-8")
        print(f"Rolled back install {backup.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
