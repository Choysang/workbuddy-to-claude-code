"""Replace WorkBuddy's code-mode system prompt with the lean coding prompt (v2, see lean_prompt.py).

Usage:
  python scripts/patch_code_prompt.py status
  python scripts/patch_code_prompt.py diff      # preview, changes nothing
  python scripts/patch_code_prompt.py apply
  python scripts/patch_code_prompt.py rollback [--force]

Edits only the runtime copy in the plugin cache (~/.workbuddy-ai/plugins/cache/...), never the
signed install dir. The lean prompt is always built from the ORIGINAL template: if the cache copy
carries an older patch, the original is taken from that patch's backup.
A WorkBuddy update installs a new plugin version dir; re-run `apply` after updates.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

from common import BACKUP_ROOT, code_prompt_path, new_backup_dir, sha256, sha256_bytes
from lean_prompt import build

MARKER = "{# harness-upgrade:v2 #}"
ANY_MARKER = "{# harness-upgrade:"
NL = "\r\n"
TAG_PATTERN = re.compile(r"\{%-?\s*(\w+)")
INCLUDE_PATTERN = re.compile(r'\{%-?\s*include\s+"([^"]+)"')
BLOCK_OPENERS = {"if", "for", "block", "macro", "raw", "filter", "call"}


def tag_sequence(text: str) -> list[str]:
    return TAG_PATTERN.findall(text)


def check_balanced(tags: list[str]) -> None:
    stack: list[str] = []
    for tag in tags:
        if tag in BLOCK_OPENERS:
            stack.append(tag)
        elif tag in ("elif", "else"):
            if not stack or stack[-1] not in ("if", "for"):
                raise ValueError(f"dangling {tag}")
        elif tag.startswith("end"):
            if not stack or stack[-1] != tag[3:]:
                raise ValueError(f"unbalanced {tag}")
            stack.pop()
    if stack:
        raise ValueError(f"unclosed blocks: {stack}")


def validate(original: str, patched: str) -> None:
    try:
        check_balanced(tag_sequence(patched))
    except ValueError as exc:
        raise SystemExit(f"Generated template is unbalanced ({exc}); not patching.")
    unknown = set(INCLUDE_PATTERN.findall(patched)) - set(INCLUDE_PATTERN.findall(original))
    if unknown:
        raise SystemExit(f"Generated template includes unknown fragments {unknown}; not patching.")
    for mode in ("ask", "plan", "expert", "quick", "craft"):
        if f"interactionmode-{mode}/fragments/interaction.md" not in patched:
            raise SystemExit(f"Tool list include for {mode} mode missing; not patching.")


def prompt_backups(path: Path) -> list[tuple[Path, dict]]:
    found = []
    for backup in sorted(BACKUP_ROOT.glob("*-prompt")):
        meta_file = backup / "meta.json"
        if meta_file.is_file():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta["path"] == str(path):
                found.append((backup, meta))
    return found


def original_text(path: Path) -> str:
    current = path.read_bytes()
    if ANY_MARKER.encode() not in current:
        return current.decode("utf-8")
    for backup, meta in reversed(prompt_backups(path)):
        if meta["patchedSha256"] == sha256_bytes(current):
            return (backup / "prompt.tpl").read_bytes().decode("utf-8")
    raise SystemExit("prompt.tpl carries an unknown patch and no matching backup; roll back manually.")


def status(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    print(f"path     {path}")
    print(f"symlink  {path.is_symlink()}")
    print(f"sha256   {sha256(path)}")
    print(f"patched  {'v2' if MARKER in text else ('older' if ANY_MARKER in text else 'no')}")
    print(f"chars    {len(text)}")
    return 0


def diff(path: Path) -> int:
    original = original_text(path)
    patched = build(original, MARKER)
    validate(original, patched)
    before = [line + "\n" for line in original.split(NL)]
    after = [line + "\n" for line in patched.split(NL)]
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # template has CJK; Windows console is GBK
    sys.stdout.writelines(difflib.unified_diff(before, after, "prompt.tpl (original)", "prompt.tpl (lean)", n=0))
    print(f"\n{len(original)} -> {len(patched)} chars")
    return 0


def apply(path: Path) -> int:
    if path.is_symlink():
        raise SystemExit("prompt.tpl is a symlink into the install dir; refusing to patch through it.")
    if MARKER in path.read_text(encoding="utf-8"):
        print("Already patched (v2).")
        return 0
    original = original_text(path)
    patched = build(original, MARKER)
    validate(original, patched)
    original_bytes, patched_bytes = original.encode("utf-8"), patched.encode("utf-8")
    backup = new_backup_dir("prompt")
    (backup / "prompt.tpl").write_bytes(original_bytes)
    meta = {"path": str(path), "originalSha256": sha256_bytes(original_bytes),
            "patchedSha256": sha256_bytes(patched_bytes)}
    (backup / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp = path.with_suffix(".tpl.harness-tmp")
    tmp.write_bytes(patched_bytes)
    os.replace(tmp, path)
    print(f"Patched {path}\n  {len(original)} -> {len(patched)} chars; backup: {backup}")
    return 0


def rollback(path: Path, force: bool) -> int:
    backups = prompt_backups(path)
    if not backups:
        raise SystemExit(f"No prompt backup found for {path}")
    backup, meta = backups[-1]
    current = sha256(path)
    if current == meta["originalSha256"]:
        print("prompt.tpl is already the original; nothing to roll back.")
        return 0
    if current != meta["patchedSha256"] and not force:
        raise SystemExit("Current prompt.tpl differs from the patched version (updated by WorkBuddy?). "
                         "Use --force to restore the backup anyway.")
    tmp = path.with_suffix(".tpl.harness-tmp")
    tmp.write_bytes((backup / "prompt.tpl").read_bytes())
    os.replace(tmp, path)
    if sha256(path) != meta["originalSha256"]:
        raise SystemExit("Restore verification failed: sha256 mismatch.")
    print(f"Restored original prompt.tpl (sha256 {meta['originalSha256'][:12]}) from {backup}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["status", "diff", "apply", "rollback"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    path = code_prompt_path()
    return {"status": lambda: status(path), "diff": lambda: diff(path), "apply": lambda: apply(path),
            "rollback": lambda: rollback(path, args.force)}[args.action]()


if __name__ == "__main__":
    sys.exit(main())
