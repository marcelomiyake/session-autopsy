"""Human report formats stay readable tables while JSON stays the machine contract."""
import json
import unittest

from session_autopsy.adapters.presentation import cost, count, describe, local_time, money, render
from session_autopsy.domain.accounting import build_report
from session_autopsy.domain.models import Session
from tests.test_accounting import catalog, observation


def family():
    root = Session("future", "root", "log", agent_id="root", started="2026-11-01T12:00:00Z",
                   updated="2026-11-01T12:30:00Z", cwd="/demo", prompt="Build\na widget", title="Widget",
                   observations=[observation(), observation(identity="unpriced", model="unknown", effort=None)],
                   compactions=[{"id": "c", "agent_id": "root", "timestamp": "2026-11-01T12:10:00Z",
                                 "trigger": "auto", "before": 1000, "after": 200, "evidence": {"line": 7}}],
                   reported=[{"source": "cost-state", "model_provider": "openai", "recorded_cost_usd": 1.5,
                              "models": {"test": {"input": 150, "output": None}}}],
                   warnings=["partial log"])
    child = Session("future", "root", "child", parent_id="root", agent_id="child",
                    observations=[observation(identity="child", agent_id="child")])
    return build_report([root, child], catalog())


class PresentationTests(unittest.TestCase):
    def test_text_report_uses_aligned_tables_without_json(self):
        text = render(family(), "text", "UTC")
        self.assertNotIn("{", text)
        self.assertIn("Initial prompt: Build a widget", text)
        self.assertIn("Started:        2026-11-01T12:00:00+00:00", text)
        self.assertRegex(text, r"Model\s+Effort\s+Requests\s+Input")
        self.assertIn("incomplete: ", text)
        self.assertIn("1 unpriced request\n", text)
        self.assertRegex(text, r"Total\s+3\s+300.*≥\$0\.0003")
        self.assertRegex(text, r"unknown\s+unknown\s+1\s.*unpriced")
        self.assertIn("  ↳ child", text)
        self.assertRegex(text, r"auto\s+1,000\s+200\s+7")
        self.assertIn("cost-state", text)
        self.assertRegex(text, r"test\s+input\s+150\s+200\s+-50")
        self.assertIn("Warning: partial log", text)

    def test_markdown_report_uses_pipe_tables(self):
        text = render(family(), "markdown")
        self.assertTrue(text.startswith("# Session root (future)"))
        self.assertIn("## Usage by model", text)
        self.assertIn("| --- | --- | ---: |", text)
        self.assertIn("- **Title:** Widget", text)

    def test_json_and_other_values(self):
        report = family()
        self.assertEqual(json.loads(render(report, "json"))["session"]["id"], "root")
        self.assertEqual(render({"selected": "/a/b"}), "selected: /a/b")
        self.assertEqual(json.loads(render({"policy": {"model": "m"}}))["policy"]["model"], "m")

    def test_numbers_costs_and_summaries(self):
        self.assertEqual((count(None), count(1234), count("n/a"), count(False)), ("unknown", "1,234", "n/a", "false"))
        self.assertEqual((money("0.00001"), money("0.26551"), money("1234.5"), money("bad")),
                         ("<$0.0001", "$0.2655", "$1,234.50", "bad"))
        self.assertEqual((cost(None), cost({"low": "1", "high": "2.5"})), ("unpriced", "$1.00–$2.50"))
        with self.assertRaises(ValueError):
            local_time("2026-11-01T00:00:00Z", "Not/AZone")
        self.assertEqual(describe({"usage": {"input_tokens": 5}, "items": [1, None]}), "usage input tokens 5, items 1; unknown")


if __name__ == "__main__":
    unittest.main()
