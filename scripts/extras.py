"""Claude Code parity extras: MCP servers, Claude Code hooks, auto memory, thinking effort.

Usage:
  python scripts/extras.py --dry-run
  python scripts/extras.py             # apply (backs up settings.json and mcp.json first)
  python scripts/extras.py --rollback  # restore values recorded by the latest apply

settings.json
  reasoningEffort "high", alwaysThinkingEnabled true      (Claude Code: effortLevel high, thinking on)
  memory.autoMemoryEnabled / typedMemory true              (Claude Code typed auto memory)
  env: CODEBUDDY_DISABLE_AUTO_MEMORY=0, CODEBUDDY_MEMORY_ENABLED / CODEBUDDY_TYPED_MEMORY_ENABLED=true
  hooks: caveman SessionStart + UserPromptSubmit (same scripts Claude Code runs);
         RTK PreToolUse(Bash) rewrite through hooks/rtk_rewrite.sh (absolute rtk path, sandbox-safe)
mcp.json
  context7, agentmemory, headroom copied from ~/.claude.json; npx launched through node directly
  because cmd.exe is blocked in WorkBuddy sessions. codegraph / node_repl are skipped: their binaries
  do not exist on this machine (they also fail in Claude Code).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from common import BACKUP_ROOT, SETTINGS_PATH, WB_DIR, is_workbuddy_running, new_backup_dir

MCP_PATH = WB_DIR / "mcp.json"
CLAUDE_JSON = Path.home() / ".claude.json"
NODE = Path("D:/Program Files/nodejs/node.exe")
NPX_CLI = Path("D:/Program Files/nodejs/node_modules/npm/bin/npx-cli.js")
CAVEMAN_ROOT = Path.home() / ".claude/plugins/cache/caveman/caveman/2.7.0"
RTK_SCRIPT = WB_DIR / "hooks" / "rtk_rewrite.sh"
MARKER = "harness-extra"
MISSING = "__missing__"


def rtk_path() -> str | None:
    found = shutil.which("rtk")
    return Path(found).as_posix() if found else None


def caveman_hook(script: str) -> dict:
    root = CAVEMAN_ROOT.as_posix()
    return {"type": "command", "timeout": 30,
            "command": f'# {MARKER}\nexport CLAUDE_PLUGIN_ROOT="{root}"; [ -f "$CLAUDE_PLUGIN_ROOT/src/hooks/{script}" ] '
                       f'|| exit 0; node "$CLAUDE_PLUGIN_ROOT/src/hooks/{script}"'}


def rtk_script(rtk: str) -> str:
    return (f'#!/bin/bash\n# {MARKER}: RTK PreToolUse rewrite with an absolute rtk path (sandbox PATH lacks rtk)\n'
            f'RTK="{rtk}"\n[ -x "$RTK" ] || exit 0\n'
            'out=$("$RTK" hook claude 2>/dev/null) || exit 0\n'
            f'printf %s "${{out//\\"command\\":\\"rtk /\\"command\\":\\"\\\\\\"$RTK\\\\\\" }}"\n')


def planned_hooks() -> dict[str, list]:
    plan = {"SessionStart": [{"matcher": "startup|resume", "hooks": [caveman_hook("caveman-activate.js")]}],
            "UserPromptSubmit": [{"hooks": [caveman_hook("caveman-mode-tracker.js")]}]}
    if rtk_path():
        plan["PreToolUse"] = [{"matcher": "Bash", "hooks": [
            {"type": "command", "timeout": 15, "command": f'# {MARKER}\nbash "{RTK_SCRIPT.as_posix()}"'}]}]
    return plan


def planned_mcp() -> dict:
    claude = json.loads(CLAUDE_JSON.read_text(encoding="utf-8")).get("mcpServers", {})
    servers = {}
    for name, package in (("context7", "@upstash/context7-mcp@latest"), ("agentmemory", "@agentmemory/mcp")):
        if name in claude:
            servers[name] = {"type": "stdio", "command": NODE.as_posix(),
                             "args": [NPX_CLI.as_posix(), "-y", package], "env": claude[name].get("env", {})}
    headroom = claude.get("headroom", {})
    if headroom and Path(headroom.get("command", "")).exists():
        servers["headroom"] = {"type": "stdio", "command": headroom["command"], "args": headroom.get("args", []),
                               "env": headroom.get("env", {})}
    return servers


SETTINGS_EDITS = [
    (["reasoningEffort"], "high"),
    (["alwaysThinkingEnabled"], True),
    (["memory", "autoMemoryEnabled"], True),
    (["memory", "typedMemory"], True),
    (["env", "CODEBUDDY_DISABLE_AUTO_MEMORY"], "0"),
    (["env", "CODEBUDDY_MEMORY_ENABLED"], "true"),
    (["env", "CODEBUDDY_TYPED_MEMORY_ENABLED"], "true"),
]


def get(doc: dict, path: list):
    for key in path:
        if not isinstance(doc, dict) or key not in doc:
            return MISSING
        doc = doc[key]
    return doc


def put(doc: dict, path: list, value) -> None:
    for key in path[:-1]:
        doc = doc.setdefault(key, {})
    if value == MISSING:
        doc.pop(path[-1], None)
    else:
        doc[path[-1]] = value


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def save(path: Path, doc) -> None:
    tmp = path.with_suffix(path.suffix + ".harness-tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def without_our_hooks(hooks: dict) -> dict:
    cleaned = {}
    for event, groups in hooks.items():
        kept = [g for g in groups if not any(MARKER in h.get("command", "") for h in g.get("hooks", []))]
        if kept:
            cleaned[event] = kept
    return cleaned


def apply(dry_run: bool) -> int:
    settings, mcp = load(SETTINGS_PATH, {}), load(MCP_PATH, {"mcpServers": {}})
    changes = [{"path": p, "old": get(settings, p), "new": v} for p, v in SETTINGS_EDITS if get(settings, p) != v]
    servers = {k: v for k, v in planned_mcp().items() if mcp.get("mcpServers", {}).get(k) != v}
    hooks = planned_hooks()
    for c in changes:
        print(f"  settings {'.'.join(c['path'])}: {c['old']!r} -> {c['new']!r}")
    print(f"  hooks    {', '.join(f'{e}({len(g)})' for e, g in hooks.items())} (replacing earlier {MARKER} hooks)")
    print(f"  mcp      add/update: {', '.join(servers) or 'none'}")
    if dry_run:
        return 0
    backup = new_backup_dir("extras")
    shutil.copy2(SETTINGS_PATH, backup / "settings.json")
    if MCP_PATH.is_file():
        shutil.copy2(MCP_PATH, backup / "mcp.json")
    old_servers = {k: mcp.get("mcpServers", {}).get(k, MISSING) for k in servers}
    meta = {"settings": changes, "mcpOld": old_servers, "mcpExisted": MCP_PATH.is_file(),
            "rtkScriptExisted": RTK_SCRIPT.is_file()}
    (backup / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    for c in changes:
        put(settings, c["path"], c["new"])
    merged = without_our_hooks(settings.get("hooks") or {})
    for event, groups in hooks.items():
        merged[event] = [*merged.get(event, []), *groups]
    settings["hooks"] = merged
    save(SETTINGS_PATH, settings)
    mcp.setdefault("mcpServers", {}).update(servers)
    save(MCP_PATH, mcp)
    if "PreToolUse" in hooks:
        RTK_SCRIPT.write_text(rtk_script(rtk_path()), encoding="utf-8", newline="\n")
    print(f"Applied; backup: {backup}")
    return 0


def rollback() -> int:
    backups = sorted(p for p in BACKUP_ROOT.glob("*-extras") if not (p / "ROLLED_BACK").exists())
    if not backups:
        print("Nothing to roll back.")
        return 0
    backup = backups[-1]
    meta = json.loads((backup / "meta.json").read_text(encoding="utf-8"))
    settings = load(SETTINGS_PATH, {})
    hooks = without_our_hooks(settings.get("hooks") or {})
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    for c in meta["settings"]:
        put(settings, c["path"], c["old"])
    for parent in ("memory", "env"):
        if settings.get(parent) == {}:
            settings.pop(parent)
    save(SETTINGS_PATH, settings)
    if meta["mcpExisted"]:
        mcp = load(MCP_PATH, {"mcpServers": {}})
        for name, old in meta["mcpOld"].items():
            put(mcp, ["mcpServers", name], old)
        save(MCP_PATH, mcp)
    elif MCP_PATH.is_file():
        MCP_PATH.unlink()
    if not meta["rtkScriptExisted"] and RTK_SCRIPT.is_file():
        RTK_SCRIPT.unlink()
    (backup / "ROLLED_BACK").write_text("rolled back\n", encoding="utf-8")
    print(f"Rolled back {backup.name}")
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
