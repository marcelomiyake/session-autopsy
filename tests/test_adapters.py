import json
from pathlib import Path
import tempfile
import unittest

from session_autopsy.adapters.claude import ClaudeSource
from session_autopsy.adapters.codex import CodexSource
from session_autopsy.adapters.files import snapshot_rows, text_content, user_prompt


def write_rows(path, rows, suffix=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n" + suffix)
    return path


def claude_usage(identity="m", output=5):
    return {"type": "assistant", "uuid": identity, "timestamp": "2026-11-01T00:00:00Z", "effort": "high",
            "message": {"id": identity, "model": "claude-haiku-5-5", "usage": {
                "input_tokens": 10, "cache_read_input_tokens": 20, "cache_creation_input_tokens": 30,
                "cache_creation": {"ephemeral_5m_input_tokens": 30}, "output_tokens": output}}}


def codex_rows():
    return [{"type": "session_meta", "payload": {"id": "root", "timestamp": "2026-11-01T00:00:00Z", "cwd": "/synthetic", "model_provider": "openai"}},
            {"type": "turn_context", "payload": {"model": "gpt-6-luna", "effort": "medium"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"text": "<environment_context>skip</environment_context>"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"text": "Build a widget"}]}}]


def record(identity, input=100, output=10):
    return {"type": "token_usage_record", "payload": {"thread_id": "root", "response_id": identity,
        "usage": {"input_tokens": input, "cached_input_tokens": 40, "output_tokens": output, "reasoning_output_tokens": 3}}}


def counter(input, output=10):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {"model_context_window": 1000,
        "total_token_usage": {"input_tokens": input, "cached_input_tokens": 0, "output_tokens": output, "reasoning_output_tokens": 0}}}}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_claude_streaming_and_details(self):
        path = self.root / "project/00000000-0000-0000-0000-000000000000.jsonl"
        rows = [{"type": "user", "cwd": "/start", "message": {"content": [{"text": "Do the task"}]}},
                claude_usage(), claude_usage(output=8), {"type": "assistant", "message": {}},
                {"type": "ai-title", "title": "Widget"},
                {"type": "system", "subtype": "compact_boundary", "uuid": "c", "compactMetadata": {"trigger": "auto", "preTokens": 100, "postTokens": 20}},
                {"type": "cost-state", "totalCostUSD": 1, "modelUsage": {"hidden": {"outputTokens": 1}}}]
        write_rows(path, rows, "{incomplete")
        session = ClaudeSource().read(path)
        self.assertEqual(len(session.observations), 1)
        self.assertEqual(session.observations[0].tokens.input, 60)
        self.assertEqual(session.observations[0].tokens.output, 8)
        self.assertEqual(session.prompt, "Do the task")
        self.assertEqual(session.title, "Widget")
        self.assertEqual(session.cwd, "/start")
        self.assertEqual(session.compactions[0]["before"], 100)
        self.assertTrue(session.warnings)
        self.assertEqual(session.reported[0]["recorded_cost_usd"], 1)
        child = write_rows(path.parent / path.stem / "subagents/agent-child.jsonl", [claude_usage("child")])
        self.assertEqual(ClaudeSource().read(child).parent_id, path.stem)
        self.assertEqual(len(ClaudeSource().discover(self.root)), 2)

    def test_invalid_claude_and_helpers(self):
        row = claude_usage();row["message"]["usage"]["input_tokens"] = -100
        session = ClaudeSource().read(write_rows(self.root / "bad.jsonl", [row]))
        self.assertEqual(len(session.observations), 0)
        self.assertIn("invalid usage", session.warnings[0])
        self.assertEqual(text_content("text"), "text")
        self.assertEqual(text_content(42), "")
        self.assertEqual(text_content(["skip", {"content": "text"}, {"text": []}]), "text")
        self.assertFalse(user_prompt("   "))

    def test_codex_response_ledger_and_compaction(self):
        rows = codex_rows() + [record("r1"), counter(100), counter(100)]
        compact = record("compact", 110, 20)["payload"]
        rows.extend([{"type": "compacted", "payload": {"compaction_response_id": "compact", "latest_token_usage_record": compact}},
                     record("compact", 110, 20), {"type": "event_msg", "payload": {"type": "configuration_update", "reasoning": {"effort": "high"}}},
                     {"type": "event_msg", "payload": {"type": "thread_settings_applied", "thread_settings": {"model": "gpt-6.1-sol", "reasoning_effort": "high", "service_tier": "priority"}}}, record("r2")])
        session = CodexSource().read(write_rows(self.root / "rollout-test.jsonl", rows))
        self.assertEqual(len(session.observations), 3)
        self.assertEqual(sum(o.tokens.input for o in session.observations), 310)
        self.assertEqual(session.observations[-1].model, "gpt-6.1-sol")
        self.assertEqual(session.observations[-1].tier, "priority")
        self.assertEqual(session.prompt, "Build a widget")
        self.assertEqual(session.started, "2026-11-01T00:00:00Z")
        self.assertEqual(len(session.compactions), 1)
        self.assertEqual(CodexSource().discover(self.root), [self.root / "rollout-test.jsonl"])

    def test_legacy_resets_child_ownership_and_invalid(self):
        rows = codex_rows() + [counter(100), counter(100), counter(150, 20), counter(20, 2)]
        session = CodexSource().read(write_rows(self.root / "legacy.jsonl", rows))
        self.assertEqual(sum(o.tokens.input for o in session.observations), 170)
        self.assertIn("reset", session.warnings[0])
        rows = codex_rows();rows[0]["payload"].update(parent_thread_id="parent", history_base={"x": 1})
        rows.extend([record("inherited"), record(None), record("bad", -1)])
        rows[-3]["payload"]["thread_id"] = "parent"
        session = CodexSource().read(write_rows(self.root / "child.jsonl", rows))
        self.assertEqual(session.parent_id, "parent")
        self.assertFalse(session.observations)
        self.assertGreaterEqual(len(session.warnings), 3)

    def test_snapshot_ignores_nonobjects(self):
        path = write_rows(self.root / "snap.jsonl", [{"a": 1}, [1]], "bad")
        warnings = []
        self.assertEqual(list(snapshot_rows(path, warnings)), [(1, {"a": 1})])
        self.assertEqual(len(warnings), 1)
        size = path.stat().st_size
        with path.open("a") as stream:stream.write('\n{"after_snapshot":true}\n')
        self.assertEqual(list(snapshot_rows(path, [], size)), [(1, {"a": 1})])

    def test_missing_cumulative_fields_stay_unknown_without_false_reset(self):
        first = {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "output_tokens": 10}}}}
        second = {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 150}}}}
        session = CodexSource().read(write_rows(self.root / "partial.jsonl", codex_rows() + [first, second]))
        self.assertEqual(sum(o.tokens.input for o in session.observations), 150)
        self.assertIsNone(session.observations[-1].tokens.output)
        self.assertIsNone(session.observations[-1].tokens.reasoning)
        self.assertFalse(session.warnings)
