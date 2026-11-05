import unittest

from session_autopsy.domain.models import EvidenceRef, Session, Tokens, UsageObservation
from session_autopsy.domain.policy import analysis_policy


class DomainTests(unittest.TestCase):
    def test_disjoint_accounting(self):
        tokens = Tokens(100, 40, 20, 30, 10)
        self.assertEqual(tokens.uncached, 40)
        self.assertIsNone(Tokens().uncached)

    def test_invalid_counts(self):
        for args in ((-1,), (1.5,), (True,), (2, 3, 0), (2, 3), (2, None, 3), (1, 0, 0, 1, 2)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Tokens(*args)

    def test_observation_and_session(self):
        usage = UsageObservation("request", "main", "vendor", None, None, "", Tokens(), EvidenceRef("x", 1))
        session = Session("future", "id", "x", observations=[usage])
        self.assertEqual(session.observations[0].evidence.line, 1)

    def test_allowlist_and_escalation(self):
        self.assertEqual(analysis_policy("claude")["model"], "claude-haiku-5-5")
        self.assertEqual(analysis_policy("codex")["model"], "gpt-6-luna")
        self.assertEqual(analysis_policy("claude", True)["model"], "claude-sonnet-5-5")
        self.assertEqual(analysis_policy("codex", True)["model"], "gpt-6.1-sol")
        self.assertEqual(analysis_policy("codex", effort="high")["effort"], "high")
        for host, effort in (("unknown", None), ("codex", "max")):
            with self.assertRaises(ValueError):
                analysis_policy(host, effort=effort)
