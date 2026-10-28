"""Claude Code stream-json is reduced to the same fields score.py records for WorkBuddy."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
import run_claude as R  # noqa: E402


def assistant(msg_id, usage, blocks=(), parent=None, model="deepseek-flash"):
    return json.dumps({"type": "assistant", "parent_tool_use_id": parent,
                       "message": {"id": msg_id, "model": model, "usage": usage, "content": list(blocks)}})


class StreamSummaryTest(unittest.TestCase):
    def test_counts_calls_tokens_tools_and_subagents(self):
        tool = {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}
        agent = {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "Explore"}}
        lines = [
            json.dumps({"type": "system", "subtype": "init"}),
            # Two events for the same message (one per content block) are one model call.
            assistant("m1", {"input_tokens": 5000, "cache_read_input_tokens": 0, "output_tokens": 10}),
            assistant("m1", {"input_tokens": 5000, "cache_read_input_tokens": 0, "output_tokens": 40}, [tool]),
            assistant("m2", {"input_tokens": 200, "cache_read_input_tokens": 5100,
                             "cache_creation_input_tokens": 300, "output_tokens": 20}, [agent]),
            assistant("s1", {"input_tokens": 3000, "output_tokens": 5},
                      [{"type": "tool_use", "name": "Grep", "input": {}}], parent="toolu_1"),
            "not json",
            json.dumps({"type": "result", "subtype": "success", "duration_ms": 61234, "is_error": False,
                        "total_cost_usd": 0.01}),
        ]
        s = R.summarize_stream(lines)
        self.assertEqual(s["main_calls"], 2)
        self.assertEqual(s["first_call_prompt_tokens"], 5000)
        self.assertEqual(s["main_prompt_tokens"], 10600)
        self.assertEqual(s["main_cached_tokens"], 5100)
        self.assertEqual(s["main_completion_tokens"], 60)
        self.assertEqual(s["subagent_calls"], 1)
        self.assertEqual(s["all_prompt_tokens"], 13600)
        self.assertEqual(s["main_tools"], {"Agent": 1, "Bash": 1})
        self.assertEqual(s["subagent_tools"], {"Grep": 1})
        self.assertEqual(s["subagents"], ["Explore"])
        self.assertEqual(s["wall_seconds"], 61.2)
        self.assertFalse(s["is_error"])
        self.assertEqual(s["build"], "claude-code")

    def test_local_auth_error_is_not_a_model_call(self):
        # Shape captured from a real `claude -p` run whose credentials were missing.
        lines = [
            assistant("x", {"input_tokens": 0, "output_tokens": 0},
                      [{"type": "text", "text": "Failed to authenticate"}], model="<synthetic>"),
            json.dumps({"type": "result", "subtype": "success", "is_error": False,
                        "terminal_reason": "api_error", "duration_ms": 388}),
        ]
        s = R.summarize_stream(lines)
        self.assertEqual(s["main_calls"], 0)
        self.assertIsNone(s["first_call_prompt_tokens"])
        self.assertTrue(s["is_error"])

    def test_isolated_environment_uses_one_model_everywhere(self):
        env = R.claude_env("k", R.DEFAULT_BASE_URL, "deepseek-flash", Path("cfg"))
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.deepseek.com/anthropic")
        for name in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                     "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"):
            self.assertEqual(env[name], "deepseek-flash")
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], "cfg")

    def test_missing_key_is_reported_before_any_workspace_is_created(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(R.main(["t01_bugfix", "--run", "999", "--runs-root", "Z:/never"]), 2)


if __name__ == "__main__":
    unittest.main()
