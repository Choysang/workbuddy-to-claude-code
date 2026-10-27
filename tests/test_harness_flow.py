"""A failed prerequisite must stop later mutation steps."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import harness


class HarnessFlowTest(unittest.TestCase):
    def test_failure_stops_dependent_steps(self):
        with patch.object(harness, "run", side_effect=[0, 7]) as run:
            self.assertEqual(harness.chain([("first.py",), ("second.py",), ("third.py",)]), 7)
        self.assertEqual([call.args[0] for call in run.call_args_list], ["first.py", "second.py"])

    def test_success_runs_all_steps(self):
        with patch.object(harness, "run", return_value=0) as run:
            self.assertEqual(harness.chain([("first.py",), ("second.py",)]), 0)
        self.assertEqual(run.call_count, 2)
