from dataclasses import replace
import unittest

from session_autopsy.domain.accounting import build_report, request_cost, resolve_rate, summarize
from session_autopsy.domain.models import EvidenceRef, Session, Tokens, UsageObservation


def catalog():
    entries = []
    for context, multiplier in (("short", 1), ("long", 2)):
        entries.append({"model": "test", "provider": "openai", "tier": "standard", "context": context,
            "threshold": 100, "input": str(multiplier), "output": "10", "read": "0.1", "write_30m": "1.25", "write_12h": "2.5"})
    return {"schema_version": 1, "retrieved_at": "2026-11-05T00:00:00+00:00", "rates": entries}


def observation(**kwargs):
    base = UsageObservation("id", "root", "openai", "test", "medium", "now", Tokens(100, 40, 20, 10, 3), EvidenceRef("log", 1))
    return replace(base, **kwargs)


class AccountingTests(unittest.TestCase):
    def test_disjoint_prices_and_ttl_bounds(self):
        price = request_cost(observation(), catalog())
        self.assertEqual(price, {"low": "0.000169", "high": "0.000194"})
        priced = request_cost(observation(writes={"ttl_30m_tokens": 20}), catalog())
        self.assertEqual(priced["low"], priced["high"])
        self.assertEqual(request_cost(observation(geography="us"), catalog())["low"], "0.0001859")

    def test_boundaries_unknowns_and_bad_breakdown(self):
        self.assertEqual(resolve_rate(observation(tokens=Tokens(101, 0, 0, 1)), catalog())["context"], "long")
        for obs in (observation(model="unknown"), observation(tokens=Tokens()), observation(writes={"bad": 21}), observation(writes={"bad": 20})):
            self.assertIsNone(request_cost(obs, catalog()))
        data = catalog();data["rates"][0]["read"] = None
        self.assertIsNone(request_cost(observation(), data))
        data = catalog();data["rates"][0]["write_30m"] = None;data["rates"][0]["write_12h"] = None
        self.assertIsNone(request_cost(observation(), data))
        self.assertIsNone(summarize([], catalog())["estimated_cost_usd"])

    def test_deduplication_and_reconciliation_are_not_additive(self):
        root = Session("fake", "root", "log", agent_id="root", observations=[observation()], reported=[{"cost": 999}])
        child = Session("fake", "child", "child", agent_id="child", parent_id="root", observations=[observation(), observation(identity="child", agent_id="child", model="unknown")])
        event = {"id": "compaction"};root.compactions = [event];child.compactions = [event]
        report = build_report([root, child], catalog())
        self.assertEqual(report["totals"]["requests"], 2)
        self.assertIsNone(report["totals"]["estimated_cost_usd"])
        self.assertEqual(report["totals"]["unpriced_requests"], 1)
        self.assertEqual(len(report["compactions"]), 1)
        self.assertEqual(report["reported_summaries"], [{"cost": 999}])

    def test_summary_only_models_are_visible_without_adding_counters(self):
        session = Session("fake", "root", "log", agent_id="root", observations=[observation()],
            reported=[{"model_provider": "openai", "models": {"test": {"input": 120}, "background": {"input": 10}}}])
        report = build_report([session], catalog())
        self.assertEqual(report["totals"]["tokens"]["input"], 100)
        self.assertEqual(report["reconciliation"][0]["difference"]["input"], 20)
        self.assertTrue(report["reconciliation"][1]["summary_only_model"])
