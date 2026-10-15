"""Trim the tool lists of WorkBuddy's interaction modes to a coding tool set.

Usage:
  python scripts/patch_tools.py status
  python scripts/patch_tools.py apply
  python scripts/patch_tools.py rollback

Edits the `tools:` front matter of fragments/interaction.md for the craft (Agent), plan and expert
modes in the plugin cache. Removed: Visualizer widgets, automations, image/video generation and site
deployment. Added: NotebookEdit (Claude Code parity). Every edited file is backed up first.
These fragments are shared by all welcome modes; re-run `apply` after a WorkBuddy update.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from common import BACKUP_ROOT, INSTALLED_PLUGINS_PATH, new_backup_dir, sha256, sha256_bytes

MODES = ("craft", "plan", "expert")
REMOVE = {"widget_guidelines", "show_widget", "automation_update", "Defer(ImageGen)", "Defer(VideoGen)",
          "Defer(workbuddy_sites_deploy)", "Defer(workbuddy_cloud_service)"}
ADD = ("NotebookEdit",)


def fragment_paths() -> list[Path]:
    registry = json.loads(INSTALLED_PLUGINS_PATH.read_text(encoding="utf-8"))["plugins"]
    paths = []
    for mode in MODES:
        entries = registry.get(f"interactionmode-{mode}@workbuddy-builtin") or []
        if entries:
            paths.append(Path(entries[0]["installPath"]) / "fragments" / "interaction.md")
    return paths


def trimmed(text: str) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    if lines[0] != "---" or "---" not in lines[1:]:
        raise SystemExit("interaction.md has no front matter; template changed, not patching.")
    end = lines.index("---", 1)
    try:
        start = lines.index("tools:", 1)
    except ValueError:
        raise SystemExit("interaction.md has no tools list; not patching.")
    tools = [l for l in lines[start + 1:end] if l.startswith("  - ")]
    kept = [l for l in tools if l[4:].strip() not in REMOVE]
    names = {l[4:].strip() for l in kept}
    kept += [f"  - {name}" for name in ADD if name not in names and f"Defer({name})" not in names]
    return newline.join(lines[:start + 1] + kept + lines[start + 1 + len(tools):])


def status() -> int:
    for path in fragment_paths():
        text = path.read_text(encoding="utf-8")
        left = [t for t in REMOVE if f"  - {t}" in text]
        print(f"{path.parent.parent.parent.name}: {'trimmed' if not left else 'original'} (sha {sha256(path)[:12]})")
    return 0


def apply() -> int:
    targets = []
    for path in fragment_paths():
        original = path.read_bytes()
        patched = trimmed(original.decode("utf-8")).encode("utf-8")
        if patched != original:
            targets.append((path, original, patched))
    if not targets:
        print("Already trimmed.")
        return 0
    backup = new_backup_dir("tools")
    meta = []
    for index, (path, original, patched) in enumerate(targets):
        (backup / f"{index}.md").write_bytes(original)
        meta.append({"path": str(path), "backup": f"{index}.md", "originalSha256": sha256_bytes(original),
                     "patchedSha256": sha256_bytes(patched)})
    (backup / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    for path, _, patched in targets:
        tmp = path.with_suffix(".md.harness-tmp")
        tmp.write_bytes(patched)
        os.replace(tmp, path)
        print(f"  trimmed {path.parent.parent.parent.name}")
    print(f"Backup: {backup}")
    return 0


def rollback() -> int:
    backups = sorted(p for p in BACKUP_ROOT.glob("*-tools") if not (p / "ROLLED_BACK").exists())
    if not backups:
        print("Nothing to roll back.")
        return 0
    backup = backups[-1]
    for entry in json.loads((backup / "meta.json").read_text(encoding="utf-8")):
        path = Path(entry["path"])
        if path.exists() and sha256(path) == entry["patchedSha256"]:
            path.write_bytes((backup / entry["backup"]).read_bytes())
            print(f"  restored {path.parent.parent.parent.name}")
        else:
            print(f"  skipped {path} (changed since patch or missing)")
    (backup / "ROLLED_BACK").write_text("rolled back\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["status", "apply", "rollback"])
    return {"status": status, "apply": apply, "rollback": rollback}[parser.parse_args().action]()


if __name__ == "__main__":
    sys.exit(main())
