"""Product-level tuning for a lean coding agent on deepseek-v4.1-flash.

Usage:
  python scripts/tune.py --dry-run
  python scripts/tune.py               # apply (backs up every touched file first)
  python scripts/tune.py --rollback    # restore the values recorded by the latest apply

Changes:
  (customPrompt is left alone: WorkBuddy restores it from the cloud and strips the copy from SOUL.md)
  app/app-config.json  personalization.toneStyle    -> ""   (drops the injected office "professional" tone block)
  models.json          custom gpt-5.6-sol: maxInputTokens/maxOutputTokens 32/32 -> 1000000/128000
                       (the built-in values for that model; 32 meant 32 tokens, not 32K)
  settings.json        enabledPlugins: disable plugins with no recorded use that only add tools/skills/MCP
                       servers to every session (payments, stock experts, finance data, marketplace
                       skill search, duplicate document and browser plugins)
Only the listed keys are written; rollback restores each key's old value (or removes it if it was absent).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from common import BACKUP_ROOT, SETTINGS_PATH, WB_DIR, is_workbuddy_running, new_backup_dir

APP_CONFIG = WB_DIR / "app" / "app-config.json"
MODELS = WB_DIR / "models.json"
CUSTOM_MODEL_ID = "gpt-5.6-sol"
UNUSED_PLUGINS = (
    "weixinpay@workbuddy-builtin",
    "a-share-analysis@cb_teams_marketplace",
    "finance-data@cb_teams_marketplace",
    "find-skills@codebuddy-plugins-official",
    "document-skills@cb_teams_marketplace",
    "playwright-cli@codebuddy-plugins-official",
)
MISSING = "__missing__"


def planned_edits() -> list[tuple[Path, list, object]]:
    edits: list[tuple[Path, list, object]] = [
        (APP_CONFIG, ["personalization", "toneStyle"], ""),
    ]
    models = json.loads(MODELS.read_text(encoding="utf-8")) if MODELS.is_file() else []
    for index, model in enumerate(models):
        if model.get("id") == CUSTOM_MODEL_ID:
            edits += [(MODELS, [index, "maxInputTokens"], 1_000_000), (MODELS, [index, "maxOutputTokens"], 128_000)]
    edits += [(SETTINGS_PATH, ["enabledPlugins", name], False) for name in UNUSED_PLUGINS]
    return edits


def get(doc, path: list):
    for key in path:
        if isinstance(doc, list):
            if not isinstance(key, int) or key >= len(doc):
                return MISSING
            doc = doc[key]
        elif isinstance(doc, dict) and key in doc:
            doc = doc[key]
        else:
            return MISSING
    return doc


def put(doc, path: list, value) -> None:
    for key in path[:-1]:
        doc = doc[key]
    if value == MISSING:
        doc.pop(path[-1], None)
    else:
        doc[path[-1]] = value


def write_json(path: Path, doc) -> None:
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + ".harness-tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def apply(dry_run: bool) -> int:
    docs: dict[Path, object] = {}
    changes = []
    for file, path, value in planned_edits():
        doc = docs.setdefault(file, json.loads(file.read_text(encoding="utf-8")))
        old = get(doc, path)
        if old != value:
            changes.append({"file": str(file), "path": path, "old": old, "new": value})
            print(f"  {file.name}: {'.'.join(map(str, path))}: {str(old)[:40]!r} -> {value!r}")
    if not changes or dry_run:
        print("nothing to do" if not changes else "dry run, nothing written")
        return 0
    backup = new_backup_dir("tune")
    for file in {Path(c["file"]) for c in changes}:
        (backup / file.name).write_bytes(file.read_bytes())
    (backup / "changes.json").write_text(json.dumps(changes, indent=2, ensure_ascii=False), encoding="utf-8")
    for change in changes:
        put(docs[Path(change["file"])], change["path"], change["new"])
    for file in {Path(c["file"]) for c in changes}:
        write_json(file, docs[file])
    print(f"Applied {len(changes)} changes; backup: {backup}")
    return 0


def rollback() -> int:
    backups = sorted(p for p in BACKUP_ROOT.glob("*-tune") if not (p / "ROLLED_BACK").exists())
    if not backups:
        print("Nothing to roll back.")
        return 0
    backup = backups[-1]
    changes = json.loads((backup / "changes.json").read_text(encoding="utf-8"))
    docs: dict[Path, object] = {}
    for change in changes:
        file = Path(change["file"])
        doc = docs.setdefault(file, json.loads(file.read_text(encoding="utf-8")))
        put(doc, change["path"], change["old"])
    for file, doc in docs.items():
        write_json(file, doc)
    (backup / "ROLLED_BACK").write_text("rolled back\n", encoding="utf-8")
    print(f"Restored {len(changes)} values from {backup}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if is_workbuddy_running() and not args.force and not args.dry_run:
        print("WorkBuddy is running (or the process check failed); quit it first, or pass --force.")
        return 1
    return rollback() if args.rollback else apply(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
