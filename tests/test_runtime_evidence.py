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
