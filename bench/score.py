#!/usr/bin/env python3
"""A/B coding benchmark helper for stock WorkBuddy vs the engineering edition.

Subcommands:
  prepare  copy a task's seed into a fresh run workspace and print the prompt
  pids     list recent WorkBuddy CLI traces so a run can be matched to its PID
  score    run the hidden tests on a workspace copy and summarize the traces
  summary  aggregate scored runs from a results JSONL file per task and build

`score` never writes to the workspace: tests run on a temporary copy.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
TASKS_DIR = BENCH_DIR / "tasks"
DEFAULT_TRACES_ROOT = Path(os.environ.get("WB_TRACES_ROOT", r"D:\MovedFromC\.workbuddy-ai\traces"))
DEFAULT_RUNS_ROOT = Path(os.environ.get("WB_BENCH_RUNS", r"D:\wb-bench-runs"))
MAIN_AGENT = "cli"
TITLE_PROMPT_PREFIX = "Generate a concise, sentence-case title"
TEST_TIMEOUT_SECONDS = 300
COPY_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".git", "node_modules", ".venv")
HIDDEN_DIR_NAME = "_bench_hidden"
PROMPT_FOOTER = ("Work only inside the workspace folder above. Do not ask me questions; "
                 "make reasonable assumptions and state them. Finish by running the tests.")
MAX_WORKSPACE_FILES = 5000  # bench seeds are tiny; a huge folder means a wrong --workspace

PROFILE_RE = re.compile(r"<harness_profile>([^<]+)</harness_profile>")
MODEL_RE = re.compile(r"powered by ([A-Za-z0-9][A-Za-z0-9._-]*)")
PROMPT_TOKENS_RE = re.compile(r'prompt_tokens\\*"\s*:\s*(\d+)')


# ---------------------------------------------------------------- traces

def parse_time(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_trace(path):
    """Merge span_start/span_end records of one trace file into span dicts."""
    spans = {}
    trace = {"file": str(path), "trace_id": None, "pid": None, "started_at": None, "ended_at": None,
             "bad_lines": 0, "spans": spans}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                trace["bad_lines"] += 1
                continue
            kind = record.get("type")
            if kind in ("span_start", "span_end"):
                span = record.get("span") or {}
                if span.get("spanId"):
                    spans.setdefault(span["spanId"], {}).update(span)
            elif kind in ("trace_start", "trace_end", "trace_update"):
                info = record.get("trace") or {}
                trace["trace_id"] = info.get("traceId") or trace["trace_id"]
                trace["pid"] = info.get("workerPid", trace["pid"])
                trace["started_at"] = info.get("startedAt") or trace["started_at"]
                trace["ended_at"] = info.get("endedAt") or trace["ended_at"]
    return trace


def owner_agent(span, spans):
    """Return the nearest enclosing agent span, or None."""
    seen = set()
    parent = span.get("parentId")
    while parent and parent not in seen:
        seen.add(parent)
        node = spans.get(parent)
        if node is None:
            return None
        if node.get("type") == "agent":
            return node
        parent = node.get("parentId")
    return None


def root_agents(trace):
    return [s for s in trace["spans"].values() if s.get("type") == "agent" and not s.get("parentId")]


def trace_kind(trace):
    names = {s.get("name") for s in root_agents(trace)}
    if MAIN_AGENT in names:
        return "main"
    if names:
        return "other"
    gens = [s for s in trace["spans"].values() if s.get("type") == "generation"]
    if gens and all(TITLE_PROMPT_PREFIX in str(g.get("toolInput", ""))[:300] for g in gens):
        return "other"
    return "main" if gens else "empty"


def usage_from_output(output):
    """Extract the usage dict of a generation's toolOutput (JSON string or list)."""
    data = output
    if isinstance(output, str):
        try:
            data = json.loads(output)
        except ValueError:
            match = PROMPT_TOKENS_RE.search(output)
            return {"prompt_tokens": int(match.group(1))} if match else None
    chunks = data if isinstance(data, list) else [data]
    usage = None
    for chunk in chunks:
        if isinstance(chunk, dict) and isinstance(chunk.get("usage"), dict):
            if chunk["usage"].get("prompt_tokens") is not None:
                usage = chunk["usage"]
    return usage


def first_message_text(tool_input):
    """Content of the first input message; tolerates the trace writer's truncation."""
    if isinstance(tool_input, list):
        first = tool_input[0] if tool_input else {}
        return str(first.get("content", "")) if isinstance(first, dict) else str(first)
    if not isinstance(tool_input, str):
        return ""
    text = tool_input.lstrip()
    if text.startswith("["):
        try:
            first, _ = json.JSONDecoder().raw_decode(text[1:].lstrip())
            if isinstance(first, dict):
                content = first.get("content", "")
                return content if isinstance(content, str) else json.dumps(content)
        except ValueError:
            pass
    return text


def in_window(trace, since, until):
    start = parse_time(trace["started_at"])
    if start is None:
        return since is None and until is None
    return (since is None or start >= since) and (until is None or start <= until)


def collect_traces(traces_root, pids, since=None, until=None):
    traces = []
    for pid in pids:
        directory = Path(traces_root) / str(pid)
        if not directory.is_dir():
            raise FileNotFoundError(f"no trace directory for PID {pid}: {directory}")
        for path in sorted(directory.glob("trace_*.jsonl")):
            trace = load_trace(path)
            if in_window(trace, since, until):
                traces.append(trace)
    traces.sort(key=lambda t: t["started_at"] or "")
    return traces


def norm_path(text):
    return str(text).replace("\\\\", "/").replace("\\", "/").lower().rstrip("/")


def summarize_traces(traces, workspace=None):
    main_traces = [t for t in traces if trace_kind(t) == "main"]
    main_gens, sub_gens = [], []
    main_tools, sub_tools = collections.Counter(), collections.Counter()
    subagents, agent_tool_calls, agent_tool_errors = [], 0, 0
    wall_ms, incomplete, workspace_hits = 0, 0, 0
    profiles, models = set(), set()
    ws = norm_path(workspace) if workspace else None

    for trace in main_traces:
        spans = trace["spans"]
        roots = [s for s in root_agents(trace) if s.get("name") == MAIN_AGENT]
        starts = [parse_time(s.get("startedAt")) for s in spans.values() if s.get("startedAt")]
        ends = [parse_time(s.get("endedAt")) for s in spans.values() if s.get("endedAt")]
        if roots and roots[0].get("endedAt"):
            wall_ms += int((parse_time(roots[0]["endedAt"]) - parse_time(roots[0]["startedAt"])).total_seconds() * 1000)
        elif starts and ends:
            incomplete += 1
            wall_ms += int((max(ends) - min(starts)).total_seconds() * 1000)
        for span in spans.values():
            kind = span.get("type")
            owner = owner_agent(span, spans)
            is_main = owner is None or (owner.get("name") == MAIN_AGENT and not owner.get("parentId"))
            if kind == "generation":
                (main_gens if is_main else sub_gens).append(span)
            elif kind == "function":
                name = span.get("toolName") or span.get("name")
                (main_tools if is_main else sub_tools)[name] += 1
                if is_main and name == "Agent":
                    agent_tool_calls += 1
                    if span.get("status") == "error" or span.get("error"):
                        agent_tool_errors += 1
                if ws and ws in norm_path(json.dumps(span.get("toolInput", ""), ensure_ascii=False)):
                    workspace_hits += 1
            elif kind == "agent" and span.get("parentId"):
                subagents.append(span.get("agentName") or span.get("name"))

    main_gens.sort(key=lambda s: s.get("startedAt") or "")
    for gen in main_gens:
        head = first_message_text(gen.get("toolInput"))
        profiles.update(PROFILE_RE.findall(head))
        models.update(m.lower() for m in MODEL_RE.findall(head[:500]))

    def token_sum(gens, key):
        total = 0
        for gen in gens:
            usage = usage_from_output(gen.get("toolOutput")) or {}
            value = usage.get(key)
            if key == "cached_tokens":
                value = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
            total += value or 0
        return total

    first_usage = usage_from_output(main_gens[0].get("toolOutput")) if main_gens else None
    return {
        "trace_files": [t["file"] for t in main_traces],
        "turns": len(main_traces),
        "incomplete_traces": incomplete,
        "build": ("engineering" if profiles else "stock") if main_gens else "unknown",
        "harness_profiles": sorted(profiles),
        "models": sorted(models),
        "main_calls": len(main_gens),
        "main_calls_without_usage": sum(1 for g in main_gens if not usage_from_output(g.get("toolOutput"))),
        "first_call_prompt_tokens": first_usage.get("prompt_tokens") if first_usage else None,
        "main_prompt_tokens": token_sum(main_gens, "prompt_tokens"),
        "main_cached_tokens": token_sum(main_gens, "cached_tokens"),
        "main_completion_tokens": token_sum(main_gens, "completion_tokens"),
        "subagent_calls": len(sub_gens),
        "all_prompt_tokens": token_sum(main_gens + sub_gens, "prompt_tokens"),
        "main_tools": dict(sorted(main_tools.items())),
        "subagent_tools": dict(sorted(sub_tools.items())),
        "agent_tool_calls": agent_tool_calls,
        "agent_tool_errors": agent_tool_errors,
        "subagents": sorted(subagents),
        "subagents_dispatched": bool(subagents or agent_tool_calls),
        "wall_seconds": round(wall_ms / 1000, 1),
        "workspace_tool_hits": workspace_hits if ws else None,
    }


# ---------------------------------------------------------------- tests

def run_pytest(cwd, args, name):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    junit = Path(cwd).parent / f"junit_{name}.xml"
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}", *args]
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TEST_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"passed": False, "tests": 0, "failures": 0, "errors": 1, "returncode": None,
                "tail": f"timeout after {TEST_TIMEOUT_SECONDS}s"}
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if junit.exists():
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        for suite in suites:
            for key in counts:
                counts[key] += int(suite.get(key, 0))
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
    # pytest exit code 5 means "no tests collected".
    return {"passed": proc.returncode == 0, "returncode": proc.returncode, **counts, "tail": tail}


def task_dir(task):
    path = TASKS_DIR / task
    if not (path / "hidden").is_dir():
        raise FileNotFoundError(f"unknown task {task!r}; expected {path / 'hidden'}")
    return path


def infer_task(workspace):
    name = Path(workspace).resolve().name
    for candidate in sorted(p.name for p in TASKS_DIR.iterdir() if p.is_dir()):
        if name == candidate or name.startswith(candidate + "-"):
            return candidate
    raise ValueError(f"cannot infer task from workspace name {name!r}; pass --task")


def score_tests(workspace, task):
    """Copy the workspace, add the hidden suite, run both suites on the copy."""
    workspace = Path(workspace)
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace not found: {workspace}")
    count = 0
    for _, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".git", "node_modules", ".venv")]
        count += len(files)
        if count > MAX_WORKSPACE_FILES:
            raise ValueError(f"workspace has more than {MAX_WORKSPACE_FILES} files; is {workspace} a bench run folder?")
    with tempfile.TemporaryDirectory(prefix="wb-bench-") as tmp:
        copy = Path(tmp) / "ws"
        shutil.copytree(workspace, copy, ignore=COPY_IGNORE)
        if (copy / HIDDEN_DIR_NAME).exists():
            raise ValueError(f"workspace already contains {HIDDEN_DIR_NAME}/")
        shutil.copytree(task_dir(task) / "hidden", copy / HIDDEN_DIR_NAME, ignore=COPY_IGNORE)
        hidden = run_pytest(copy, [HIDDEN_DIR_NAME], "hidden")
        visible = run_pytest(copy, [f"--ignore={HIDDEN_DIR_NAME}"], "visible")
    return hidden, visible


# ---------------------------------------------------------------- commands

def cmd_prepare(args):
    source = task_dir(args.task) / "seed"
    target = Path(args.runs_root) / f"{args.task}-{args.build}-r{args.run}"
    if target.exists():
        raise ValueError(f"refusing to reuse existing workspace {target}; pick another --run or delete it")
    shutil.copytree(source, target, ignore=COPY_IGNORE)
    prompt = (task_dir(args.task) / "prompt.md").read_text(encoding="utf-8").strip()
    print(f"workspace: {target}\n")
    print("---- paste everything between the lines as the first and only message ----")
    print(f"Workspace: {target.as_posix()}\n\n{prompt}\n\n{PROMPT_FOOTER}")
    print("---- end ----")
    return 0


def cmd_pids(args):
    root = Path(args.traces_root)
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=args.minutes)
    rows = []
    for directory in root.iterdir():
        if not directory.is_dir() or not directory.name.isdigit():
            continue
        if dt.datetime.fromtimestamp(directory.stat().st_mtime, dt.timezone.utc) < since:
            continue
        for path in directory.glob("trace_*.jsonl"):
            trace = load_trace(path)
            start = parse_time(trace["started_at"])
            if start is None or start < since or trace_kind(trace) != "main":
                continue
            summary = summarize_traces([trace], args.workspace)
            rows.append((trace["started_at"], directory.name, summary))
    for started, pid, s in sorted(rows):
        hits = "" if s["workspace_tool_hits"] is None else f" ws_hits={s['workspace_tool_hits']}"
        cached = (f"{100 * s['main_cached_tokens'] / s['main_prompt_tokens']:.0f}%"
                  if s["main_prompt_tokens"] else "-")
        # first= is the context already carried into this turn; a large value means a long
        # conversation, not harness overhead.
        print(f"{started[:19]}  pid={pid:<6} build={s['build']:<11} model={','.join(s['models']) or '?'} "
              f"calls={s['main_calls']} first={s['first_call_prompt_tokens']} "
              f"total={s['all_prompt_tokens']} cached={cached}{hits}")
    if not rows:
        print(f"no main-agent traces started in the last {args.minutes} minutes under {root}")
    return 0


def cmd_score(args):
    task = args.task or infer_task(args.workspace)
    since = parse_time(args.since) if args.since else None
    until = parse_time(args.until) if args.until else None
    traces = collect_traces(args.traces_root, args.pid, since, until)
    summary = summarize_traces(traces, args.workspace)
    hidden, visible = score_tests(args.workspace, task)
    result = {"task": task, "workspace": str(Path(args.workspace).resolve()), "pids": args.pid,
              "label": args.label, "hidden": hidden, "visible": visible, **summary}
    warnings = []
    if summary["turns"] == 0:
        warnings.append("no main-agent trace found for the given PID(s)/window")
    if summary["workspace_tool_hits"] == 0:
        warnings.append("no tool call mentions the workspace path; check the PID")
    if len(summary["models"]) > 1:
        warnings.append(f"mixed models {summary['models']}")
    if summary["turns"] > 1:
        warnings.append(f"{summary['turns']} user turns; the protocol expects exactly one")
    result["warnings"] = warnings
    if args.append:
        with open(args.append, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({k: v for k, v in result.items() if k != "trace_files"}, ensure_ascii=False) + "\n")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_result(result))
    return 0


def format_result(r):
    def tests(t):
        state = "PASS" if t["passed"] else ("NO TESTS" if t["returncode"] == 5 else "FAIL")
        return f"{state} ({t['tests'] - t['failures'] - t['errors'] - t.get('skipped', 0)}/{t['tests']} passed)"
    tools = ", ".join(f"{k}={v}" for k, v in r["main_tools"].items()) or "-"
    sub_tools = ", ".join(f"{k}={v}" for k, v in r["subagent_tools"].items()) or "-"
    lines = [
        f"task        {r['task']}  ({r['workspace']})",
        f"build       {r['build']} {r['harness_profiles'] or ''}  model={','.join(r['models']) or '?'}  pids={r['pids']}",
        f"hidden      {tests(r['hidden'])}",
        f"visible     {tests(r['visible'])}",
        f"main calls  {r['main_calls']}  (without usage: {r['main_calls_without_usage']}, turns: {r['turns']})",
        f"tokens      first={r['first_call_prompt_tokens']}  main_total={r['main_prompt_tokens']}  "
        f"main_cached={r['main_cached_tokens']}  all_agents_total={r['all_prompt_tokens']}",
        f"tools       {tools}",
        f"subagents   dispatched={r['subagents_dispatched']}  agents={r['subagents'] or '-'}  "
        f"Agent calls={r['agent_tool_calls']} (errors {r['agent_tool_errors']})  calls={r['subagent_calls']}  tools: {sub_tools}",
        f"workspace   tool calls mentioning it: {r['workspace_tool_hits']}",
        f"wall        {r['wall_seconds']} s" + (f"  ({r['incomplete_traces']} trace(s) without end)" if r["incomplete_traces"] else ""),
    ]
    if not r["hidden"]["passed"]:
        lines.append("hidden test tail:\n  " + r["hidden"]["tail"].replace("\n", "\n  "))
    lines += [f"WARNING     {w}" for w in r["warnings"]]
    return "\n".join(lines)


def cmd_summary(args):
    groups = collections.defaultdict(list)
    with open(args.results, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                groups[(row["task"], row["build"])].append(row)

    def med(rows, key):
        values = [r[key] for r in rows if r.get(key) is not None]
        return statistics.median(values) if values else None

    header = f"{'task':<18}{'build':<13}{'runs':>5}{'pass':>7}{'calls':>8}{'first_tok':>11}{'main_tok':>11}{'wall_s':>9}{'subagent':>10}"
    print(header)
    for (task, build), rows in sorted(groups.items()):
        passed = sum(1 for r in rows if r["hidden"]["passed"])
        sub = sum(1 for r in rows if r["subagents_dispatched"])
        print(f"{task:<18}{build:<13}{len(rows):>5}{passed:>4}/{len(rows):<2}{med(rows, 'main_calls')!s:>8}"
              f"{med(rows, 'first_call_prompt_tokens')!s:>11}{med(rows, 'main_prompt_tokens')!s:>11}"
              f"{med(rows, 'wall_seconds')!s:>9}{sub:>7}/{len(rows):<2}")
    totals = collections.defaultdict(lambda: [0, 0])
    for (task, build), rows in groups.items():
        totals[build][0] += sum(1 for r in rows if r["hidden"]["passed"])
        totals[build][1] += len(rows)
    for build, (passed, runs) in sorted(totals.items()):
        print(f"overall {build}: {passed}/{runs} hidden suites passed")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="create a fresh run workspace from a task seed")
    prepare.add_argument("task")
    prepare.add_argument("--build", required=True, choices=["stock", "eng"])
    prepare.add_argument("--run", required=True, type=int)
    prepare.add_argument("--runs-root", default=DEFAULT_RUNS_ROOT)
    prepare.set_defaults(func=cmd_prepare)

    pids = sub.add_parser("pids", help="list recent main-agent traces")
    pids.add_argument("--minutes", type=int, default=120)
    pids.add_argument("--workspace", help="count tool calls that mention this path")
    pids.add_argument("--traces-root", default=DEFAULT_TRACES_ROOT)
    pids.set_defaults(func=cmd_pids)

    score = sub.add_parser("score", help="score one run")
    score.add_argument("--workspace", required=True)
    score.add_argument("--pid", required=True, action="append", help="WorkBuddy CLI PID; repeat for several")
    score.add_argument("--task", help="task id; inferred from the workspace folder name by default")
    score.add_argument("--since", help="ignore traces that started before this ISO time")
    score.add_argument("--until", help="ignore traces that started after this ISO time")
    score.add_argument("--label", help="free-form note stored with the result")
    score.add_argument("--traces-root", default=DEFAULT_TRACES_ROOT)
    score.add_argument("--append", help="append the result as one JSON line to this file")
    score.add_argument("--json", action="store_true")
    score.set_defaults(func=cmd_score)

    summary = sub.add_parser("summary", help="aggregate a results JSONL file")
    summary.add_argument("results")
    summary.set_defaults(func=cmd_summary)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
