#!/usr/bin/env python3
"""Run bench tasks unattended through WorkBuddy's own one-off automations.

`enqueue` prepares fresh workspaces and inserts `once` automations into the running
app's database (the scheduler picks up new rows within a minute). The model is set per
automation, so free models can be compared without touching the UI. Whichever WorkBuddy
build is running executes the queue; `score.py` reads the real build from the trace.

`collect` scores every finished run: traces are matched by the run's time window and by
tool calls that mention its workspace, so overlapping runs do not mix.

  python bench/queue_runs.py enqueue --tasks t07_bughunt,t02_feature --models deepseek-v4.1-flash,hy3 \
      --runs 1-3 --label eng --gap 15
  python bench/queue_runs.py status
  python bench/queue_runs.py collect --append bench/results/results.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import score as S

DB = Path(os.environ.get("WB_DB", r"D:\MovedFromC\.workbuddy-ai\workbuddy.db"))
QUEUE = S.BENCH_DIR / "results" / "queue.jsonl"
NAME_PREFIX = "bench "
# A normal run finishes within a second of its last span; compacted runs measured 190 s+.
TRACE_GAP_S = 30


def connect(readonly=False):
    if readonly:
        return sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    return sqlite3.connect(DB, timeout=30)


def parse_runs(text):
    start, _, end = text.partition("-")
    return range(int(start), int(end or start) + 1)


def load_queue():
    if not QUEUE.exists():
        return []
    return [json.loads(line) for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_enqueue(args):
    tasks, models = args.tasks.split(","), args.models.split(",")
    at = dt.datetime.now().replace(second=0, microsecond=0) + dt.timedelta(minutes=args.start_in)
    with connect() as db:
        owner = db.execute("select owner_user_id from automations where owner_user_id is not null "
                           "order by updated_at desc limit 1").fetchone()
        if not owner:
            raise ValueError("no existing automation to copy the owner id from; create one in the UI first")
        QUEUE.parent.mkdir(parents=True, exist_ok=True)
        # Interleave models inside each run so time-of-day load hits both equally.
        for run in parse_runs(args.runs):
            for task in tasks:
                for model in models:
                    build = f"{args.label}-{model}"
                    workspace, message = S.prepare_workspace(task, build, run, args.runs_root)
                    aid, now = str(uuid.uuid4()), int(time.time() * 1000)
                    db.execute(
                        "insert into automations(id,name,prompt,status,schedule_type,cwds,rrule,scheduled_at,"
                        "next_run_at,model_id,model_is_thinking,skills_json,push_to_wechat,push_to_wecom_bot,"
                        "owner_user_id,owner_status,connector_ids_json,created_at,updated_at,workspace_scope) "
                        "values(?,?,?,'ACTIVE','once',?,'',?,?,?,0,'[]',0,0,?,'confirmed','[]',?,?,'workspace')",
                        (aid, f"{NAME_PREFIX}{task} {build} r{run}", message, json.dumps([str(workspace)]),
                         at.strftime("%Y-%m-%dT%H:%M"), int(at.timestamp() * 1000), model, owner[0], now, now))
                    entry = {"automation_id": aid, "task": task, "model": model, "label": args.label,
                             "run": run, "workspace": str(workspace), "scheduled_at": at.isoformat()}
                    with open(QUEUE, "a", encoding="utf-8") as handle:
                        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    print(f"{at:%H:%M}  {task:<14} {model:<22} r{run}  {workspace}")
                    at += dt.timedelta(minutes=args.gap)
    return 0


def run_rows(db, automation_id):
    return db.execute("select status,runs_json,result_success,failure_code from automation_runs "
                      "where automation_id=? order by created_at", (automation_id,)).fetchall()


def cmd_status(args):
    with connect(readonly=True) as db:
        for entry in load_queue():
            rows = run_rows(db, entry["automation_id"])
            state = rows[-1][0] if rows else "WAITING"
            print(f"{entry['scheduled_at'][11:16]}  {state:<12} {entry['task']:<14} {entry['model']:<22} "
                  f"{entry['label']} r{entry['run']}" + ("  scored" if entry.get("scored") else ""))
    return 0


def traces_for(workspace, started_ms, finished_ms, traces_root):
    """Main-agent traces that ran inside the window and touched this workspace."""
    since = dt.datetime.fromtimestamp(started_ms / 1000 - 60, dt.timezone.utc)
    until = dt.datetime.fromtimestamp(finished_ms / 1000 + 60, dt.timezone.utc)
    picked, pids = [], set()
    for directory in Path(traces_root).iterdir():
        if not directory.is_dir() or not directory.name.isdigit():
            continue
        if dt.datetime.fromtimestamp(directory.stat().st_mtime, dt.timezone.utc) < since:
            continue
        for path in directory.glob("trace_*.jsonl"):
            trace = S.load_trace(path)
            if not S.in_window(trace, since, until) or S.trace_kind(trace) != "main":
                continue
            if S.summarize_traces([trace], workspace)["workspace_tool_hits"]:
                picked.append(trace)
                pids.add(directory.name)
    return picked, sorted(pids)


def cmd_collect(args):
    entries = load_queue()
    with connect(readonly=True) as db:
        for entry in entries:
            if entry.get("scored"):
                continue
            rows = run_rows(db, entry["automation_id"])
            if not rows or rows[-1][0] == "IN_PROGRESS":
                continue
            runs = json.loads(rows[-1][1] or "[]")
            started = min(r.get("startedAt") for r in runs if r.get("startedAt"))
            finished = max(r.get("finishedAt") or r.get("startedAt") for r in runs)
            traces, pids = traces_for(entry["workspace"], started, finished, args.traces_root)
            summary = S.summarize_traces(traces, entry["workspace"])
            hidden, visible = S.score_tests(entry["workspace"], entry["task"])
            warnings = [] if traces else ["no main-agent trace touched the workspace"]
            last = S.last_activity(traces)
            if last is not None and finished / 1000 - last.timestamp() > TRACE_GAP_S:
                warnings.append(f"trace stops {finished / 1000 - last.timestamp():.0f} s before the run finished "
                                "(context compaction ends the engine trace); calls and tokens undercount")
            if rows[-1][0] != "ACCEPTED" or not rows[-1][2]:
                warnings.append(f"automation ended as {rows[-1][0]} ({rows[-1][3] or 'no failure code'})")
            result = {"task": entry["task"], "workspace": entry["workspace"], "pids": pids,
                      "label": f"{entry['label']} automation", "hidden": hidden, "visible": visible,
                      **{k: v for k, v in summary.items() if k != "trace_files"}, "warnings": warnings}
            print(S.format_result(result) + "\n")
            if args.append:
                Path(args.append).parent.mkdir(parents=True, exist_ok=True)
                with open(args.append, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            entry["scored"] = True
    QUEUE.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--tasks", required=True)
    enqueue.add_argument("--models", required=True)
    enqueue.add_argument("--runs", required=True, help="run numbers, e.g. 1-3")
    enqueue.add_argument("--label", required=True, help="the build you expect to be running: stock or eng")
    enqueue.add_argument("--gap", type=int, default=15, help="minutes between scheduled runs")
    enqueue.add_argument("--start-in", type=int, default=2, help="minutes until the first run")
    enqueue.add_argument("--runs-root", default=S.DEFAULT_RUNS_ROOT)
    enqueue.set_defaults(func=cmd_enqueue)
    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)
    collect = sub.add_parser("collect")
    collect.add_argument("--append")
    collect.add_argument("--traces-root", default=S.DEFAULT_TRACES_ROOT)
    collect.set_defaults(func=cmd_collect)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
