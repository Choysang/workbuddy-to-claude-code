#!/usr/bin/env python3
"""Copy a WorkBuddy trace file into a minimized, secret-free test fixture.

Keeps span ids, parents, names, types, timings and status. Replaces every
payload with the few facts score.py reads: the model line and harness
profile tag of generation input, the usage block of generation output, and
`subagent_type` of Agent tool input. Tool input becomes a placeholder path
so workspace matching can still be tested.

    python bench/make_fixture.py <trace.jsonl> <out.jsonl> [--workspace-placeholder D:/bench/ws]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402

KEEP_SPAN_KEYS = ("traceId", "spanId", "parentId", "name", "type", "agentName", "toolName",
                  "startedAt", "endedAt", "duration", "status")


def minimize_generation_input(value):
    head = score.first_message_text(value)
    if score.TITLE_PROMPT_PREFIX in head[:300]:
        content = score.TITLE_PROMPT_PREFIX
    else:
        models = score.MODEL_RE.findall(head[:500])
        content = f"This conversation is powered by {models[0]}\n\n" if models else ""
        content += "".join(f"<harness_profile>{p}</harness_profile>" for p in score.PROFILE_RE.findall(head))
    return json.dumps([{"content": content, "role": "system"}])


def minimize_generation_output(value):
    usage = score.usage_from_output(value)
    if not usage:
        return None
    keep = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens") if k in usage}
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cached is not None:
        keep["prompt_tokens_details"] = {"cached_tokens": cached}
    return json.dumps([{"usage": keep}])


def minimize_span(span, placeholder):
    out = {k: span[k] for k in KEEP_SPAN_KEYS if k in span}
    if span.get("error"):
        out["error"] = "redacted"
    if span.get("type") == "generation":
        if "toolInput" in span:
            out["toolInput"] = minimize_generation_input(span["toolInput"])
        if "toolOutput" in span:
            out["toolOutput"] = minimize_generation_output(span["toolOutput"])
    elif span.get("type") == "function" and "toolInput" in span:
        tool_input = {"path": placeholder}
        if isinstance(span["toolInput"], dict) and "subagent_type" in span["toolInput"]:
            tool_input["subagent_type"] = span["toolInput"]["subagent_type"]
        out["toolInput"] = tool_input
    return out


def minimize(source, target, placeholder):
    lines = []
    with open(source, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            kind = record.get("type")
            if kind in ("span_start", "span_end"):
                lines.append({"type": kind, "span": minimize_span(record["span"], placeholder)})
            elif kind in ("trace_start", "trace_end", "trace_update"):
                info = record.get("trace") or {}
                lines.append({"type": kind, "trace": {k: info.get(k) for k in
                                                      ("traceId", "workerPid", "startedAt", "endedAt", "status")}})
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        for item in lines:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--workspace-placeholder", default="D:/bench/ws")
    args = parser.parse_args()
    print(f"wrote {minimize(args.source, args.target, args.workspace_placeholder)} records to {args.target}")


if __name__ == "__main__":
    main()
