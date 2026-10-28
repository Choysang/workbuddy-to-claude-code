"""bench/score.py: trace summaries, hidden-test scoring and the task suite itself."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[1] / "bench"
sys.path.insert(0, str(BENCH))
import score  # noqa: E402

FIXTURES = BENCH / "fixtures" / "traces"
ENG_PID, STOCK_PID = "18504", "12660"


def summarize(pid, **kwargs):
    return score.summarize_traces(score.collect_traces(FIXTURES, [pid]), **kwargs)


def snapshot(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir",
                                       p.stat().st_mtime_ns)
            for p in sorted(Path(root).rglob("*"))}


def write_trace(directory, records):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "trace_synthetic.jsonl"
    path.write_text("".join(r if isinstance(r, str) else json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def span(kind, span_id, parent=None, name=None, start="2026-10-28T00:00:00Z", end="2026-10-28T00:00:01Z", **extra):
    body = {"spanId": span_id, "parentId": parent, "type": kind, "name": name or kind,
            "startedAt": start, "endedAt": end, **extra}
    return {"type": "span_end" if end else "span_start", "span": body}


class FixtureTraceTest(unittest.TestCase):
    """Expected values were checked against the unminimized traces with grep."""

    def test_engineering_run_with_subagents(self):
        s = summarize(ENG_PID)
        self.assertEqual(s["build"], "engineering")
        self.assertEqual(s["harness_profiles"], ["workbuddy-engineering-v4"])
        self.assertEqual(s["models"], ["deepseek-v4.1-flash"])
        self.assertEqual(s["turns"], 1)
        self.assertEqual(s["main_calls"], 9)
        self.assertEqual(s["first_call_prompt_tokens"], 24392)
        self.assertEqual(s["main_prompt_tokens"], 299852)
        self.assertEqual(s["subagent_calls"], 11)
        self.assertEqual(s["all_prompt_tokens"], 408657)
        self.assertEqual(s["main_tools"], {"Agent": 5, "Bash": 4, "Edit": 1, "Read": 1, "Skill": 3,
                                           "ToolSearch": 4, "Write": 2})
        self.assertEqual(s["subagent_tools"], {"Bash": 5, "Glob": 1, "Read": 6, "Write": 1})
        self.assertTrue(s["subagents_dispatched"])
        self.assertEqual(s["subagents"], ["explorer", "test-author", "verifier"])
        self.assertEqual((s["agent_tool_calls"], s["agent_tool_errors"]), (5, 2))
        self.assertEqual(s["wall_seconds"], 143.4)

    def test_stock_run_without_subagents(self):
        s = summarize(STOCK_PID)
        self.assertEqual(s["build"], "stock")
        self.assertEqual(s["harness_profiles"], [])
        self.assertEqual(s["main_calls"], 11)
        self.assertEqual(s["first_call_prompt_tokens"], 39556)
        self.assertEqual(s["main_prompt_tokens"], 521015)
        self.assertFalse(s["subagents_dispatched"])
        self.assertEqual(s["subagent_calls"], 0)

    def test_title_generator_trace_is_not_counted(self):
        traces = score.collect_traces(FIXTURES, [ENG_PID])
        self.assertEqual(sorted(score.trace_kind(t) for t in traces), ["main", "other"])

    def test_workspace_hits_use_tool_inputs(self):
        self.assertEqual(summarize(ENG_PID, workspace="D:\\bench\\ws")["workspace_tool_hits"], 33)
        self.assertEqual(summarize(ENG_PID, workspace="D:/elsewhere")["workspace_tool_hits"], 0)

    def test_missing_pid_directory_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            score.collect_traces(FIXTURES, ["999999"])


class ParsingTest(unittest.TestCase):
    def test_usage_from_json_string(self):
        out = json.dumps([{"id": "x"}, {"usage": {"prompt_tokens": 7, "completion_tokens": 1}}])
        self.assertEqual(score.usage_from_output(out)["prompt_tokens"], 7)

    def test_usage_from_truncated_string(self):
        self.assertEqual(score.usage_from_output('[{"usage":{\\"prompt_tokens\\": 123, "comp'),
                         {"prompt_tokens": 123})

    def test_usage_missing(self):
        for value in (None, "", "garbage", json.dumps([{"choices": []}])):
            self.assertIsNone(score.usage_from_output(value))

    def test_first_message_survives_truncated_array(self):
        text = '[' + json.dumps({"content": "powered by m-1 <harness_profile>p</harness_profile>"}) + ',{"conte'
        self.assertIn("<harness_profile>p</harness_profile>", score.first_message_text(text))

    def test_profile_only_in_later_messages_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool_input = json.dumps([{"content": "powered by m"}, {"content": "<harness_profile>x</harness_profile>"}])
            write_trace(Path(tmp) / "1", [
                span("agent", "a", name="cli"),
                span("generation", "g", parent="a", toolInput=tool_input, toolOutput=None),
            ])
            s = score.summarize_traces(score.collect_traces(tmp, ["1"]))
        self.assertEqual(s["build"], "stock")
        self.assertEqual(s["main_calls_without_usage"], 1)
        self.assertIsNone(s["first_call_prompt_tokens"])

    def test_incomplete_trace_and_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_trace(Path(tmp) / "2", [
                {"type": "trace_start", "trace": {"traceId": "t", "startedAt": "2026-10-28T00:00:00Z"}},
                span("agent", "a", name="cli", end=None, agentName="cli"),
                "{not json\n",
                span("generation", "g", parent="a", start="2026-10-28T00:00:00Z", end="2026-10-28T00:00:30Z",
                     toolOutput=json.dumps([{"usage": {"prompt_tokens": 5}}])),
                span("function", "f", parent="a", name="Bash", toolName="Bash", toolInput={"command": "ls"}),
            ])
            traces = score.collect_traces(tmp, ["2"])
            s = score.summarize_traces(traces)
        self.assertEqual(traces[0]["bad_lines"], 1)
        self.assertEqual(s["incomplete_traces"], 1)
        self.assertEqual(s["wall_seconds"], 30.0)
        self.assertEqual(s["main_tools"], {"Bash": 1})
        self.assertEqual(s["first_call_prompt_tokens"], 5)

    def test_time_window_filters_traces(self):
        traces_since = score.collect_traces(FIXTURES, [ENG_PID], since=score.parse_time("2030-01-01T00:00:00Z"))
        self.assertEqual(traces_since, [])


class HiddenTestScoringTest(unittest.TestCase):
    def test_every_task_seed_fails_and_reference_passes(self):
        tasks = sorted(p.name for p in (BENCH / "tasks").iterdir() if p.is_dir())
        self.assertGreaterEqual(len(tasks), 5)
        for task in tasks:
            with self.subTest(task=task), tempfile.TemporaryDirectory() as tmp:
                seed = Path(tmp) / "seed"
                shutil.copytree(BENCH / "tasks" / task / "seed", seed)
                hidden, _ = score.score_tests(seed, task)
                self.assertFalse(hidden["passed"], f"{task}: hidden suite already passes on the seed")
                solved = Path(tmp) / "solved"
                shutil.copytree(seed, solved)
                shutil.copytree(BENCH / "tasks" / task / "reference", solved, dirs_exist_ok=True)
                hidden, visible = score.score_tests(solved, task)
                self.assertTrue(hidden["passed"], f"{task}: {hidden['tail']}")
                self.assertTrue(visible["passed"], f"{task}: {visible['tail']}")

    def test_scoring_does_not_modify_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "t04_build_repair-eng-r1"
            shutil.copytree(BENCH / "tasks" / "t04_build_repair" / "seed", ws)
            before = snapshot(ws)
            score.score_tests(ws, "t04_build_repair")
            self.assertEqual(snapshot(ws), before)

    def test_task_inferred_from_workspace_name(self):
        self.assertEqual(score.infer_task("D:/runs/t02_feature-stock-r3"), "t02_feature")
        with self.assertRaises(ValueError):
            score.infer_task("D:/runs/whatever")


class CommandTest(unittest.TestCase):
    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = score.main(argv)
        return code, out.getvalue()

    def test_prepare_score_append_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = self.run_main(["prepare", "t06_semver", "--build", "eng", "--run", "1", "--runs-root", tmp])
            ws = Path(tmp) / "t06_semver-eng-r1"
            self.assertEqual(code, 0)
            self.assertIn(f"Workspace: {ws.as_posix()}", text)
            self.assertIn(score.PROMPT_FOOTER, text)
            self.assertTrue((ws / "semver.py").exists())
            self.assertFalse((ws / "_bench_hidden").exists())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(self.run_main(["prepare", "t06_semver", "--build", "eng", "--run", "1",
                                                   "--runs-root", tmp])[0], 0)

            results = Path(tmp) / "results.jsonl"
            code, text = self.run_main(["score", "--workspace", str(ws), "--pid", ENG_PID, "--traces-root",
                                        str(FIXTURES), "--append", str(results)])
            self.assertEqual(code, 0)
            self.assertIn("hidden      FAIL", text)
            self.assertIn("main calls  9", text)
            self.assertIn("first=24392", text)
            self.assertIn("dispatched=True", text)
            self.assertIn("no tool call mentions the workspace path", text)
            row = json.loads(results.read_text(encoding="utf-8"))
            self.assertEqual((row["task"], row["build"], row["hidden"]["passed"]), ("t06_semver", "engineering", False))

            code, text = self.run_main(["summary", str(results)])
            self.assertEqual(code, 0)
            self.assertIn("overall engineering: 0/1", text)


if __name__ == "__main__":
    unittest.main()
