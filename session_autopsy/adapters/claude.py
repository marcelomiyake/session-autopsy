"""Anti-corruption layer for Claude Code's append-only JSONL format."""
from pathlib import Path
import re

from session_autopsy.domain.models import EvidenceRef, Session, Tokens, UsageObservation
from session_autopsy.adapters.files import remember_excerpt, remember_time, snapshot_rows, text_content, user_prompt

SESSION_NAME = re.compile(r"[0-9a-f-]{36}\.jsonl$")


def claude_tokens(usage):
    fresh = usage.get("input_tokens")
    read = usage.get("cache_read_input_tokens", 0)
    write = usage.get("cache_creation_input_tokens", 0)
    total = None if fresh is None else fresh + read + write
    return Tokens(total, read, write, usage.get("output_tokens"),
                  (usage.get("output_tokens_details") or {}).get("thinking_tokens"))


class ClaudeSource:
    name = "claude"

    def discover(self, root: Path):
        roots = [p for p in root.glob("*/*.jsonl") if SESSION_NAME.fullmatch(p.name)]
        return sorted(roots + list(root.glob("*/*/subagents/agent-*.jsonl")))

    def read(self, path: Path):
        child = path.parent.name == "subagents"
        sid = path.parent.parent.name if child else path.stem
        session = Session(self.name, sid, str(path), parent_id=sid if child else None,
                          agent_id=path.stem if child else sid, snapshot_bytes=path.stat().st_size,
                          capabilities={"usage": True, "effort": True, "compactions": True})
        latest = {}
        for line, row in snapshot_rows(path, session.warnings):
            remember_time(session, row.get("timestamp", ""))
            session.cwd = session.cwd or row.get("cwd", "")
            self._metadata(session, row, line)
            if row.get("type") == "assistant":
                self._assistant(session, row, line, latest)
        session.observations = list(latest.values())
        return session

    def _metadata(self, session, row, line):
        kind = row.get("type")
        if kind == "user" and not row.get("isMeta"):
            message = row.get("message") or {}
            text = text_content(message.get("content"))
            if not session.prompt and user_prompt(text):
                session.prompt = text[:4000]
            remember_excerpt(session, text, "user/tool result", line)
        elif kind == "ai-title":
            session.title = row.get("title", "")
        elif kind == "system" and row.get("subtype") == "compact_boundary":
            meta = row.get("compactMetadata") or {}
            session.compactions.append({"id": row.get("uuid", f"{session.path}:{line}"),
                "agent_id": session.agent_id, "timestamp": row.get("timestamp"),
                "trigger": meta.get("trigger", "unknown"), "before": meta.get("preTokens"),
                "after": meta.get("postTokens"), "evidence": {"path": session.path, "line": line}})
        elif kind == "cost-state":
            session.reported[:] = [{"source": "cost-state", "timestamp": row.get("timestamp"),
                "recorded_cost_usd": row.get("totalCostUSD"), "models": row.get("modelUsage", {})}]

    def _assistant(self, session, row, line, latest):
        message = row.get("message") or {}
        usage = message.get("usage")
        remember_excerpt(session, text_content(message.get("content")), "assistant", line)
        if not usage:
            return
        try:
            tokens = claude_tokens(usage)
            identity = f"anthropic:{row.get('requestId', '')}:{message.get('id', row.get('uuid', line))}"
            creation = usage.get("cache_creation") or {}
            writes = {k: creation[k] for k in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens") if k in creation}
            latest[identity] = UsageObservation(identity, session.agent_id, "anthropic", message.get("model"),
                row.get("effort", row.get("perTurnEffort")), row.get("timestamp", ""), tokens,
                EvidenceRef(session.path, line), writes, usage.get("speed", "standard"),
                usage.get("inference_geo", "global"))
        except (TypeError, ValueError) as exc:
            session.warnings.append(f"{session.path}:{line}: invalid usage: {exc}")
