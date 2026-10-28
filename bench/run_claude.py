#!/usr/bin/env python3
"""Run a bench task through stock Claude Code on DeepSeek, then score it like a WorkBuddy run.

Same task seed, first message, hidden tests and result fields as `score.py`, so
`score.py summary` puts the `claude-code` rows next to `stock` and `eng`.

Claude Code runs headless (`claude -p`) with an empty config dir: no user CLAUDE.md,
hooks, plugins or MCP servers, i.e. the vendor harness as shipped. The model is reached
through DeepSeek's Anthropic-compatible endpoint; `deepseek-flash` is served by
DeepSeek-V4.1-Flash. The key is read from DEEPSEEK_API_KEY and never written anywhere.

  python bench/run_claude.py t01_bugfix --run 1 --append bench/results/results.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import score as S

BUILD = "claude-code"
DEFAULT_BASE_URL = "https://api.deepseek.com/anthropic"
DEFAULT_MODEL = "deepseek-flash"
TIMEOUT_SECONDS = 20 * 60  # same ceiling as the WorkBuddy protocol


def claude_env(key, base_url, model, config_dir):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_"))}
    env.update({
        "ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_AUTH_TOKEN": key, "ANTHROPIC_MODEL": model,
        # Every tier, including subagents and background calls, uses the same model.
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model, "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model, "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_CONFIG_DIR": str(config_dir), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def summarize_stream(lines):
    """Turn `--output-format stream-json` events into score.py's summary fields."""
    calls, order, tools, sub_tools = {}, [], {}, {}
    subagents, models, result = [], set(), {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "result":
            result = event
        if kind != "assistant":
            continue
        message = event.get("message") or {}
        if message.get("model") == "<synthetic>":
            continue  # local error text such as "Failed to authenticate", not a model call
        is_main = not event.get("parent_tool_use_id")
        if message.get("model"):
            models.add(message["model"].lower())
        usage = message.get("usage") or {}
        key = message.get("id") or f"anon-{len(order)}"
        if key not in calls:
            order.append(key)
        # Streaming repeats a message once per content block; the last usage is the final one.
        calls[key] = {"main": is_main, "usage": usage}
        for block in message.get("content") or []:
            if block.get("type") != "tool_use":
                continue
            name = block.get("name")
            target = tools if is_main else sub_tools
            target[name] = target.get(name, 0) + 1
            if is_main and name in ("Agent", "Task"):
                subagents.append((block.get("input") or {}).get("subagent_type") or "general-purpose")

    def prompt_tokens(usage):
        return sum(usage.get(k) or 0 for k in
                   ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))

    main = [calls[k]["usage"] for k in order if calls[k]["main"]]
    sub = [calls[k]["usage"] for k in order if not calls[k]["main"]]
    return {
        "turns": 1, "incomplete_traces": 0 if result else 1, "build": BUILD,
        "harness_profiles": [], "models": sorted(models),
        "main_calls": len(main),
        "main_calls_without_usage": sum(1 for u in main if not u),
        "first_call_prompt_tokens": prompt_tokens(main[0]) if main else None,
        "main_prompt_tokens": sum(prompt_tokens(u) for u in main),
        "main_cached_tokens": sum(u.get("cache_read_input_tokens") or 0 for u in main),
        "main_completion_tokens": sum(u.get("output_tokens") or 0 for u in main),
        "subagent_calls": len(sub),
        "all_prompt_tokens": sum(prompt_tokens(u) for u in main + sub),
        "main_tools": dict(sorted(tools.items())), "subagent_tools": dict(sorted(sub_tools.items())),
        "agent_tool_calls": len(subagents), "agent_tool_errors": 0,
        "subagents": sorted(subagents), "subagents_dispatched": bool(subagents),
        "wall_seconds": round((result.get("duration_ms") or 0) / 1000, 1),
        "workspace_tool_hits": None,
        "cost_usd_reported": result.get("total_cost_usd"),
        "is_error": (not result or bool(result.get("is_error"))
                     or result.get("terminal_reason") == "api_error"),
    }


def run(args):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("set DEEPSEEK_API_KEY in the environment first")
    claude = shutil.which(args.claude)
    if not claude:
        raise FileNotFoundError(f"Claude Code CLI not found: {args.claude}")
    workspace, message = S.prepare_workspace(args.task, BUILD, args.run, args.runs_root)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="cc-bench-config-") as config_dir:
        cmd = [claude, "-p", message, "--output-format", "stream-json", "--verbose",
               "--model", args.model, "--dangerously-skip-permissions"]
        try:
            proc = subprocess.run(cmd, cwd=workspace, env=claude_env(key, args.base_url, args.model, config_dir),
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=TIMEOUT_SECONDS)
            stdout, timed_out = proc.stdout, False
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            stdout = partial.decode("utf-8", "replace") if isinstance(partial, bytes) else partial
            timed_out = True
    (Path(workspace).parent / f"{Path(workspace).name}.stream.jsonl").write_text(stdout, encoding="utf-8")
    summary = summarize_stream(stdout.splitlines())
    hidden, visible = S.score_tests(workspace, args.task)
    warnings = []
    if summary["main_calls"] == 0:
        warnings.append("no model call recorded; check the key, endpoint and model name")
    if summary["is_error"] and not timed_out:
        warnings.append("Claude Code reported an error; see the .stream.jsonl next to the workspace")
    if timed_out:
        warnings.append(f"timeout after {TIMEOUT_SECONDS}s")
    result = {"task": args.task, "workspace": str(Path(workspace).resolve()), "pids": [],
              "label": args.label or ("timeout" if timed_out else None), "started_at": started,
              "hidden": hidden, "visible": visible, **summary, "warnings": warnings}
    if args.append:
        Path(args.append).parent.mkdir(parents=True, exist_ok=True)
        with open(args.append, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(S.format_result(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task")
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--claude", default="claude", help="Claude Code executable")
    parser.add_argument("--runs-root", default=S.DEFAULT_RUNS_ROOT)
    parser.add_argument("--label")
    parser.add_argument("--append", help="append the result as one JSON line to this file")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
