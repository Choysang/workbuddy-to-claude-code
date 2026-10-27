#!/usr/bin/env python
"""WorkBuddy harness upgrade: unified entry point.

Dispatches to the focused scripts in this directory so the whole
upgrade / re-patch / verify flow is one command per scenario.

Usage:
  python harness.py setup [--dry-run]       # ONE-SHOT: install + all patches + verify
  python harness.py install [--dry-run]     # install payload only
  python harness.py post-update             # re-apply after WorkBuddy auto-update
  python harness.py verify [--runtime]      # static checks, optional runtime trace check
  python harness.py status                  # patch status only
  python harness.py rollback [backup_dir]   # restore from a backup
  python harness.py skills-audit            # report on ~/.workbuddy-ai/skills vs payload

All child scripts refuse to run while WorkBuddy is running; quit it first.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from common import PROFILE

SCRIPTS = Path(__file__).resolve().parent


def run(script: str, *args: str) -> int:
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    print(f"\n>>> {script} {' '.join(args)}".rstrip())
    return subprocess.call(cmd)


def chain(steps) -> int:
    for step in steps:
        rc = run(*step)
        if rc != 0:
            print(f"\nFAILED step: {step[0]}; remaining steps not run")
            return rc
    return 0


def cmd_install(a: argparse.Namespace) -> int:
    extra = ["--dry-run"] if a.dry_run else []
    return run("install.py", *extra)


def cmd_setup(a: argparse.Namespace) -> int:
    """One-shot first-time setup: install + all patches + verify."""
    if a.dry_run:
        steps = [("install.py", "--dry-run")]
    else:
        steps = [
            ("install.py",),
            ("patch_code_prompt.py", "apply"),
            ("patch_tools.py", "apply"),
            *(([("tune.py",), ("extras.py",)]) if PROFILE == "legacy" else []),
            ("verify.py",),
        ]
    rc = chain(steps)
    if rc == 0 and not a.dry_run:
        print("\nSetup complete. Next (manual, see docs/MANUAL-STEPS.md):")
        print("  1. quit WorkBuddy if it is running, then reopen")
        print("  2. confirm the selected model and required MCP connections")
        print("  3. run the acceptance task, then: python harness.py verify --runtime")
    return rc


def cmd_post_update(a: argparse.Namespace) -> int:
    """Re-apply everything an update can reset. Order matters:
    prompt/tools patches land in the new plugin cache dir first,
    then tune (toneStyle / plugins), then extras (MCP/hooks/memory),
    finally verify."""
    rc = chain([
        ("install.py",),
        ("patch_code_prompt.py", "apply"),
        ("patch_tools.py", "apply"),
        *(([("tune.py",), ("extras.py",)]) if PROFILE == "legacy" else []),
        ("verify.py",),
    ])
    if rc != 0:
        return rc
    print("\nAll steps OK. Next (manual, see docs/MANUAL-STEPS.md):")
    print("  1. confirm toneStyle / plugin toggles if WorkBuddy reset them")
    print("  2. start WorkBuddy, run the acceptance task")
    print("  3. python harness.py verify --runtime")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    extra = ["--runtime"] if a.runtime else []
    return run("verify.py", *extra)


def cmd_status(a: argparse.Namespace) -> int:
    rc1 = run("patch_code_prompt.py", "status")
    rc2 = run("patch_tools.py", "status")
    return rc1 or rc2


def cmd_rollback(a: argparse.Namespace) -> int:
    args = [str(a.backup_dir)] if a.backup_dir else []
    return run("rollback.py", *args)


def cmd_skills_audit(a: argparse.Namespace) -> int:
    """Report-only: list skills in ~/.workbuddy-ai/skills, flag ones that look
    auto-sunk (one-off task names) or sensitive. Never deletes anything."""
    import os

    skills_dir = Path(os.environ.get("CODEBUDDY_CONFIG_DIR", Path.home() / ".workbuddy-ai")) / "skills"
    payload_dir = SCRIPTS.parent / "payload" / "skills"
    if not skills_dir.is_dir():
        print(f"no skills dir: {skills_dir}")
        return 1
    installed = {p.name for p in payload_dir.iterdir() if p.is_dir()} if payload_dir.is_dir() else set()
    suspicious_kw = ("token", "chrome", "recycle", "winrm", "deploy", "recovery")
    rows = []
    for p in sorted(skills_dir.iterdir()):
        if not p.is_dir() or p.name.startswith("_"):
            continue
        origin = "payload" if p.name in installed else "other"
        flag = ""
        low = p.name.lower()
        if any(k in low for k in suspicious_kw):
            flag = "SENSITIVE-NAME"
        elif origin == "other" and "-" in p.name and len(p.name) > 20:
            flag = "check-if-auto-sunk"
        rows.append((p.name, origin, flag))
    width = max((len(r[0]) for r in rows), default=10)
    print(f"{skills_dir}\n")
    for name, origin, flag in rows:
        print(f"  {name:<{width}}  {origin:<8}  {flag}")
    print(f"\n{len(rows)} skills. To archive a one-off skill, move its folder to")
    print(f"  {SCRIPTS.parent / 'backups'}{os.sep}<date>-auto-skills")
    print("never delete outright.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("setup", help="ONE command: install + patches + tune + extras + verify")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_setup)

    p = sub.add_parser("install", help="first-time install from payload/")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_install)

    p = sub.add_parser("post-update", help="re-apply after a WorkBuddy auto-update")
    p.set_defaults(fn=cmd_post_update)

    p = sub.add_parser("verify", help="static checks")
    p.add_argument("--runtime", action="store_true")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("status", help="patch status")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("rollback", help="restore from backup")
    p.add_argument("backup_dir", nargs="?", type=Path)
    p.set_defaults(fn=cmd_rollback)

    p = sub.add_parser("skills-audit", help="report skills, flag suspicious ones")
    p.set_defaults(fn=cmd_skills_audit)

    a = parser.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
