"""Verify the harness upgrade.

Usage:
  python scripts/verify.py              # static checks: files, settings, hook smoke test, prompt patch
  python scripts/verify.py --runtime    # also check hook run log and traces written after the install

Exit code 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from common import (AUTO_COMPACT_WINDOW, BACKUP_ROOT, HOOK_MARKER, HOOK_RUN_LOG, PAYLOAD_DIR, WB_DIR,
                    code_prompt_path, payload_files, read_settings)
from patch_code_prompt import MARKER, check_balanced, tag_sequence

MIN_CALLS_FOR_CONTEXT_CHECK = 10
results: list[tuple[bool, str]] = []


def record(ok: bool, message: str) -> None:
    results.append((ok, message))
    print(f"  [{'PASS' if ok else 'FAIL'}] {message}")


def check_files() -> None:
    for rel in payload_files():
        target = WB_DIR / rel
        same = target.is_file() and target.read_bytes() == (PAYLOAD_DIR / rel).read_bytes()
        record(same, f"installed {rel.as_posix()}" if same else f"missing or different: {target}")


def front_matter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    return parts[1] if text.startswith("---") and len(parts) == 3 else ""


def check_front_matter() -> None:
    for path in sorted((WB_DIR / "agents").glob("*.md")) + sorted((WB_DIR / "skills").glob("*/SKILL.md")):
        meta = front_matter(path)
        ok = re.search(r"^name:\s*\S", meta, re.M) and re.search(r"^description:\s*\S", meta, re.M)
        record(bool(ok), f"front matter name/description: {path.relative_to(WB_DIR).as_posix()}")
    for path in sorted((WB_DIR / "rules").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        ok = not text.startswith("---") or bool(front_matter(path))
        scope = "path-scoped" if "paths:" in front_matter(path) else "always-on"
        record(ok, f"rule parses ({scope}): {path.relative_to(WB_DIR).as_posix()}")


def our_hook_command(settings: dict) -> str | None:
    for group in settings.get("hooks", {}).get("PostToolUse", []):
        for hook in group.get("hooks", []):
            if HOOK_MARKER in hook.get("command", ""):
                return hook["command"]
    return None


def run_hook_via_bash(command: str, file_path: Path) -> subprocess.CompletedProcess:
    """Run the registered hook command the way the engine does; its run log goes next to the probe file."""
    payload = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Edit",
                          "tool_input": {"file_path": str(file_path)}}, ensure_ascii=False)
    env = dict(os.environ, WB_HOOK_LOG=str(file_path.with_suffix(".log")))
    return subprocess.run([shutil.which("bash") or "bash", "-c", command], input=payload.encode("utf-8"),
                          capture_output=True, timeout=60, env=env)


def check_settings_and_hook() -> None:
    settings = read_settings()
    value = settings.get("autoCompactWindow")
    record(value == AUTO_COMPACT_WINDOW, f"settings.autoCompactWindow = {value}")
    command = our_hook_command(settings)
    record(command is not None, "settings.hooks.PostToolUse contains post_edit_check")
    if command is None:
        return
    with tempfile.TemporaryDirectory(prefix="wb-hook-") as tmp:
        bad, good = Path(tmp) / "bad.py", Path(tmp) / "good.py"
        bad.write_text("def f(:\n", encoding="utf-8")
        good.write_text("x = 1\n", encoding="utf-8")
        bad_run, good_run = run_hook_via_bash(command, bad), run_hook_via_bash(command, good)
    stderr = bad_run.stderr.decode("utf-8", "replace")
    record(bad_run.returncode == 2 and "Python" in stderr, f"hook via bash flags a syntax error (exit {bad_run.returncode})")
    record(good_run.returncode == 0, f"hook via bash passes a clean file (exit {good_run.returncode})")


def check_prompt_patch() -> None:
    path = code_prompt_path()
    text = path.read_text(encoding="utf-8")
    record(MARKER in text, f"code-mode prompt is lean v2: {path.parent.name}")
    try:
        check_balanced(tag_sequence(text))
        record(True, "code-mode prompt template tags balanced")
    except ValueError as exc:
        record(False, f"code-mode prompt template tags: {exc}")


def install_time() -> datetime:
    installs = sorted(BACKUP_ROOT.glob("*-install"))
    if not installs:
        raise SystemExit("No install found; run scripts/install.py first.")
    return datetime.strptime(installs[-1].name[:15], "%Y%m%d-%H%M%S")


def hook_runs_since(since: datetime) -> list[list[str]]:
    """Entries of the hook's own run log (ISO time, result, elapsed, path) written after `since`."""
    runs = []
    for log in (WB_DIR / HOOK_RUN_LOG, WB_DIR / (HOOK_RUN_LOG + ".1")):
        if log.is_file():
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                fields = line.split("\t")
                if len(fields) == 4 and datetime.fromisoformat(fields[0]) >= since:
                    runs.append(fields)
    return runs


def memory_loader_lines(since: datetime) -> list[str]:
    """[MemoryLoader] lines from WorkBuddy's text logs. Informational: WorkBuddy prunes these logs."""
    patterns = ("*.log", "20*/*.log", "20*/sdk/conversations/*.log*")
    files = {f for p in patterns for f in glob.glob(str(WB_DIR / "logs" / p))}
    lines = []
    for log in files:
        if datetime.fromtimestamp(Path(log).stat().st_mtime) < since:
            continue
        with open(log, encoding="utf-8", errors="replace") as handle:
            lines += [line.strip() for line in handle if "MemoryLoader" in line and "memory rules" in line]
    return lines


def check_runtime(since: datetime) -> None:
    print(f"  runtime evidence since {since:%Y-%m-%d %H:%M:%S}")
    runs = hook_runs_since(since)
    results_count = {kind: sum(1 for r in runs if r[1] == kind) for kind in ("ok", "problem", "skip", "error")}
    record(bool(runs), f"hook ran in WorkBuddy sessions: {len(runs)} runs {results_count}")
    loader = memory_loader_lines(since)
    if loader:
        print(f"  info: {len(loader)} MemoryLoader log lines; mentions CODEBUDDY.md: "
              f"{any('CODEBUDDY.md' in l for l in loader)}; 'No memory rules loaded': "
              f"{sum('No memory rules loaded' in l for l in loader)}")
    else:
        print("  info: no MemoryLoader log lines (WorkBuddy prunes its text logs); relying on traces")

    prompts, engineering, protocol = [], 0, 0
    for trace in glob.glob(str(WB_DIR / "traces" / "*" / "trace_*.json")):
        if datetime.fromtimestamp(Path(trace).stat().st_mtime) < since:
            continue
        spans = json.loads(Path(trace).read_text(encoding="utf-8")).get("spans", [])
        for span in spans:
            if span.get("type") != "generation":
                continue
            prompt_in, output = span.get("toolInput") or "", span.get("toolOutput") or ""
            engineering += "<engineering>" in prompt_in
            protocol += "workbuddy-protocol.md" in prompt_in
            match = re.search(r'"prompt_tokens":(\d+)', output)
            if match:
                prompts.append(int(match.group(1)))
    record(engineering > 0, f"system prompt is the lean coding prompt ({engineering} calls)")
    record(protocol > 0, f"requests carry rules/workbuddy-protocol.md ({protocol} calls)")
    if len(prompts) >= MIN_CALLS_FOR_CONTEXT_CHECK:
        prompts.sort()
        p90 = prompts[int(len(prompts) * 0.9)]
        record(p90 <= AUTO_COMPACT_WINDOW, f"context stays bounded: {len(prompts)} calls, prompt tokens "
                                           f"p50={int(statistics.median(prompts))} p90={p90} max={prompts[-1]}")
    elif prompts:
        print(f"  info: only {len(prompts)} model calls so far; prompt tokens max={max(prompts)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime", action="store_true", help="also check logs/traces after install")
    args = parser.parse_args()
    print("static checks")
    check_files()
    check_front_matter()
    check_settings_and_hook()
    check_prompt_patch()
    if args.runtime:
        print("runtime checks")
        check_runtime(install_time())
    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
