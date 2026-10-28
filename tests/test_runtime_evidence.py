"""Do not count a quoted template or model output as loaded system instructions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify


class SystemInputEvidenceTest(unittest.TestCase):
    def test_accepts_system_message_in_truncated_trace_array(self):
        first = json.dumps({"role": "system", "content": verify.MARKER})
        self.assertTrue(verify._has_profile_system_input("[" + first + ',{"role":"user","content":"truncated'))

    def test_rejects_tool_and_user_quotes(self):
        for role in ("tool", "user", "assistant"):
            self.assertFalse(verify._has_profile_system_input(json.dumps([{"role": role, "content": verify.MARKER}])))

    def test_unknown_or_incomplete_system_message_is_not_evidence(self):
        for value in ("garbage", '[{"role":"system","content":"' + verify.MARKER, {}, None):
            self.assertFalse(verify._has_profile_system_input(value))

    def test_jsonl_requires_completed_generation_system_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace_example.jsonl"
            message = [{"role": "system", "content": verify.MARKER}]
            span = {"type": "generation", "toolInput": message}
            path.write_text(json.dumps({"type": "span_start", "span": span}) + "\n", encoding="utf-8")
            self.assertFalse(verify._trace_has_profile(path))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"type": "span_end", "span": span}) + '\n{"incomplete":')
            self.assertTrue(verify._trace_has_profile(path))

    def test_memory_continuation_lines_stay_scoped_to_their_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "logs/day/harness__example.log"
            log.parent.mkdir(parents=True)
            log.write_text("[time] [pid=19] [MemoryLoader]  Loaded 1 memory rules:\n"
                           "  [user] [always] C:/example/CODEBUDDY.md\n"
                           "[time] [pid=20] [MemoryLoader]  Loaded 0 memory rules:\n", encoding="utf-8")
            own = {name: state for name, state, _ in verify.runtime_checks(root, pid=19)}
            other = {name: state for name, state, _ in verify.runtime_checks(root, pid=20)}
            self.assertEqual(own["记忆包含 CODEBUDDY.md"], verify.PASS)
            self.assertEqual(other["记忆包含 CODEBUDDY.md"], verify.FAIL)

    def test_engine_argv_and_connected_mcp_are_the_evidence(self):
        """Judge the tools and MCP servers the engine actually received, latest line per pid."""
        import common as C
        good = json.dumps(["--tools", "stale", "--model", "m", "--tools", C.CODE_TOOLS])
        bad = json.dumps(["--tools", "A2ACancelTask,Agent"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older, newer = root / "logs/a/zzz__1.log", root / "logs/b/aaa__2.log"
            older.parent.mkdir(parents=True)
            newer.parent.mkdir(parents=True)
            # The later timestamp lives in the alphabetically earlier file.
            older.write_text(f"[2026/10/28 09:00:00.000] [Info] [pid=7] [CliDispatcher]  [Prewarm] activated pid=7 v → args={bad}\n"
                             "[2026/10/28 09:00:01.000] [Info] [pid=7] [MCP][buildMcpServers] connected servers=[context7,weixinpay] (count=2)\n",
                             encoding="utf-8")
            newer.write_text(f"[2026/10/28 10:00:00.000] [Info] [pid=7] [CliDispatcher]  [Prewarm] activated pid=7 v → args={good}\n"
                             "[2026/10/28 10:00:01.000] [Info] [pid=7] [MCP][buildMcpServers] connected servers=[context7] (count=1)\n"
                             f"[2026/10/28 11:00:00.000] [Info] [pid=8] [CliDispatcher]  [Prewarm] activated pid=8 v → args={bad}\n"
                             "[2026/10/28 11:00:01.000] [Info] [pid=8] [MCP][buildMcpServers] connected servers=[context7,sheetagent] (count=2)\n",
                             encoding="utf-8")
            own = {name: state for name, state, _ in verify.runtime_checks(root, pid=7)}
            other = {name: state for name, state, _ in verify.runtime_checks(root, pid=8)}
            self.assertEqual(own["引擎实际工具清单"], verify.PASS)
            self.assertEqual(own["生态 MCP 未启动"], verify.PASS)
            self.assertEqual(other["引擎实际工具清单"], verify.FAIL)
            self.assertEqual(other["生态 MCP 未启动"], verify.FAIL)
            self.assertIsNone(verify._launch_args([], None))
            cold = root / "logs/c/ws__3.log"
            cold.parent.mkdir(parents=True)
            cold.write_text(f"[2026/10/28 12:00:00.000] [Info] [pid=9] [CliDispatcher]  [Dispatch] entry opts: sessionId=x "
                            f"mcpConfig={{\"a\":1}} allowedTools=[\"x\"] port=0 argv={good}\n", encoding="utf-8")
            self.assertEqual(verify._arg_value(verify._launch_args([cold], 9), "--tools"), C.CODE_TOOLS)
