import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from session_autopsy import cli
from session_autopsy.adapters.hosts import NativeAnalysisHost
from session_autopsy.adapters.picker import choose, _screen, _interactive
from session_autopsy.adapters.presentation import local_time, render, session_rows
from session_autopsy.application.advisory import prepare_analysis
from session_autopsy.application.ports import SessionSourceAdapter, AnalysisHostAdapter, EvidenceStore, PricingCatalog
from session_autopsy.application.sessions import SessionService, filtered_sessions
from session_autopsy.domain.accounting import build_report
from session_autopsy.domain.models import Session
from tests.test_accounting import catalog, observation
from tests.test_adapters import write_rows, claude_usage, codex_rows, record


class FutureSource:
    name = "future"

    def discover(self, root):
        return [root / "future"]

    def read(self, path):
        return Session(self.name, "root", str(path), agent_id="root", observations=[observation()])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {"XDG_CACHE_HOME": self.temp.name});env.start();self.addCleanup(env.stop)
        self.s = FutureSource().read(self.root / "future")
        self.s.started = "2026-11-01T12:00:00Z";self.s.updated = self.s.started
        self.s.cwd = "/demo";self.s.prompt = "Build a widget"

    def test_third_harness_contract_selection_and_family(self):
        service = SessionService([(FutureSource(), self.root)])
        sessions, warnings = service.discover()
        self.assertFalse(warnings)
        self.assertEqual(service.select(sessions, "latest").harness, "future")
        self.assertEqual(service.select(sessions, "roo").id, "root")
        self.assertEqual(service.select(sessions, sessions[0].path).id, "root")
        for selected in (None, "missing"):
            with self.assertRaises(ValueError):service.select(sessions, selected)
        with self.assertRaises(ValueError):service.select([], "latest")
        with self.assertRaises(ValueError):service.select(sessions * 2, "root")
        child = Session("future", "root", "child", parent_id="root", agent_id="child")
        grandchild = Session("future", "root", "grand", parent_id="child", agent_id="grand")
        report, family = service.report(sessions + [child, grandchild], sessions[0], catalog())
        self.assertEqual(len(family), 3)
        self.assertEqual(report["totals"]["requests"], 1)
        source = MagicMock();source.discover.return_value = [self.root / "bad"];source.read.side_effect = OSError("denied")
        self.assertTrue(SessionService([(source, self.root)]).discover()[1])

    def test_filters_and_presentation(self):
        for kwargs in ({"harness": "future"}, {"since": "2026-11-01"}, {"until": "2026-11-02"}, {"cwd": "demo"}, {"query": "widget"}):
            self.assertEqual(filtered_sessions([self.s], **kwargs), [self.s])
        self.assertFalse(filtered_sessions([self.s], query="absent"))
        rows = session_rows([self.s], "UTC")
        self.assertIn("+00:00", rows[0]["started"])
        self.assertIn("root", render(rows))
        self.assertEqual(json.loads(render(rows, "json"))[0]["id"], "root")
        self.assertIn("No sessions", render([]))
        self.assertEqual(local_time("invalid"), "invalid")
        self.assertIn("root", render(build_report([self.s], catalog()), "markdown"))
        self.assertIn("selected", render({"selected": "root"}))

    def test_bounded_packet_and_policy(self):
        report = build_report([self.s], catalog())
        self.s.excerpts = [{"characters": 50000, "text": "x" * 50000}]
        report["most_expensive_requests"] *= 300
        packet = prepare_analysis(report, [self.s], "improve", "claude", budget=4000)
        self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False)), 4000)
        self.assertEqual(packet["policy"]["model"], "claude-haiku-5-5")
        self.assertEqual(len(report["most_expensive_requests"]), 300)
        self.assertEqual(NativeAnalysisHost("codex").prepare({})["policy"]["model"], "gpt-6-luna")
        for budget in (1, 40000):
            with self.assertRaises(ValueError):prepare_analysis(report, [], "improve", "codex", budget=budget)
        report["coverage"] = "x" * 10000
        with self.assertRaises(ValueError):prepare_analysis(report, [], "improve", "codex", budget=4000)

    def test_picker_fallback(self):
        rows = session_rows([self.s])
        with patch("sys.stdin.isatty", return_value=False), patch("builtins.input", return_value="1"), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(choose(rows), self.s.path)
        with self.assertRaises(ValueError):choose([])
        with patch("sys.stdin.isatty", return_value=False), patch("builtins.input", return_value="99"), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(ValueError):choose(rows)
        with patch("sys.stdin.isatty", return_value=False), patch("builtins.input", side_effect=EOFError), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(ValueError):choose(rows)

    def test_picker_navigation(self):
        curses = MagicMock();curses.KEY_UP = 1;curses.KEY_DOWN = 2;curses.KEY_BACKSPACE = 3
        screen = MagicMock();screen.getmaxyx.return_value = (20, 120)
        screen.get_wch.side_effect = [2, 1, "w", 3, "\n"]
        self.assertEqual(_screen(screen, session_rows([self.s]), curses), self.s.path)
        screen.get_wch.side_effect = ["\x1b"]
        rows = session_rows([self.s])
        with self.assertRaises(ValueError):_screen(screen, rows, curses)
        with patch.dict("sys.modules", {"curses": None}):
            self.assertIsNone(_interactive([]))
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), patch("session_autopsy.adapters.picker._interactive", return_value="chosen"):
            self.assertEqual(choose(session_rows([self.s])), "chosen")

    def invoke(self, command):
        args = cli.parser().parse_args(command + ["--claude-root", str(self.root / "claude"), "--codex-root", str(self.root / "codex"), "--offline"])
        return cli.run(args)

    def test_cli_end_to_end(self):
        sid = "00000000-0000-0000-0000-000000000000"
        path = write_rows(self.root / "claude/project" / (sid + ".jsonl"), [claude_usage()])
        write_rows(self.root / "codex/rollout-demo.jsonl", codex_rows() + [record("response")])
        self.assertEqual(len(self.invoke(["list"])), 2)
        self.assertEqual(self.invoke(["tokens", str(path)])["totals"]["requests"], 1)
        self.assertEqual(self.invoke(["improve", str(path), "--host", "codex", "--deep"])["analysis_request"]["policy"]["model"], "gpt-6.1-sol")
        with patch("session_autopsy.cli.choose", return_value=str(path)):
            self.assertEqual(self.invoke(["pick"])["selected"], str(path))
            self.assertEqual(self.invoke(["tokens"])["session"]["id"], sid)
        with patch.dict(os.environ, {"CLAUDE_SESSION_ID": sid}):
            self.assertEqual(self.invoke(["tokens", "current"])["session"]["id"], sid)
        for command in (["list", "--limit", "0"], ["improve", str(path)], ["tokens", "absent"]):
            with self.assertRaises(ValueError):self.invoke(command)
        self.assertTrue(self.invoke(["prices"])["rates"])
        with self.assertRaises(ValueError):self.invoke(["tokens", "latest", "--cwd", "not-a-matching-directory"])

    def test_main_output_errors_and_install(self):
        with patch("session_autopsy.cli.run", return_value={"ok": True}), patch("sys.stdout", new_callable=io.StringIO) as stream:
            self.assertEqual(cli.main(["list"]), 0)
            self.assertIn("true", stream.getvalue())
        output = self.root / "reports/report.json"
        with patch("session_autopsy.cli.run", return_value=[]), patch("session_autopsy.adapters.local.Path.cwd", return_value=self.root):
            self.assertEqual(cli.main(["list", "--output", "report.json"]), 0)
        self.assertTrue(output.exists())
        with patch("session_autopsy.cli.run", side_effect=ValueError("invalid")), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(cli.main(["list"]), 2)
        with self.assertRaises(ValueError):cli.install(None)
        with patch("session_autopsy.cli.Path.home", return_value=self.root):
            self.assertEqual(len(cli.install("both")["installed"]), 2)
            self.assertEqual(len(cli.install("both")["installed"]), 2)
        self.assertTrue((self.root / ".claude/skills/session-autopsy/SKILL.md").exists())
        self.assertTrue((self.root / ".agents/skills/session-autopsy/scripts/autopsy.py").exists())
        conflict = self.root / "other/.claude/skills/session-autopsy";conflict.mkdir(parents=True)
        with patch("session_autopsy.cli.Path.home", return_value=self.root / "other"):
            with self.assertRaises(ValueError):cli.install("claude")
