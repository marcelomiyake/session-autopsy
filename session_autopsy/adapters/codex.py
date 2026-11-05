"""Codex response ledger with a cumulative-counter fallback for older rollouts."""
from pathlib import Path

from session_autopsy.domain.models import EvidenceRef, Session, Tokens, UsageObservation
from session_autopsy.adapters.files import remember_excerpt, remember_time, snapshot_rows, text_content, user_prompt

FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")


def codex_tokens(usage):
    return Tokens(usage.get("input_tokens"), usage.get("cached_input_tokens", 0),
                  usage.get("cache_write_input_tokens", 0), usage.get("output_tokens"),
                  usage.get("reasoning_output_tokens"))


def source_parent(meta):
    source = meta.get("source") or {}
    nested = source.get("subagent", {}) if isinstance(source, dict) else {}
    spawn = nested.get("thread_spawn", {}) if isinstance(nested, dict) else {}
    return meta.get("parent_thread_id") or spawn.get("parent_thread_id")


class CodexSource:
    name = "codex"

    def discover(self, root: Path):
        return sorted(root.rglob("rollout-*.jsonl"))

    def read(self, path: Path):
        session = Session(self.name, path.stem, str(path), snapshot_bytes=path.stat().st_size,
                          capabilities={"usage": True, "effort": True, "compactions": True})
        state = {"model": None, "effort": None, "provider": "unknown", "tier": "standard", "previous": None}
        ledger, fallback = {}, []
        for line, row in snapshot_rows(path, session.warnings):
            remember_time(session, row.get("timestamp", ""))
            payload = row.get("payload") or {}
            kind = row.get("type")
            self._context(session, state, kind, payload)
            self._content(session, kind, payload, line)
            self._usage(session, state, ledger, fallback, kind, payload, line, row.get("timestamp", ""))
        session.observations = list(ledger.values()) if ledger else fallback
        if session.parent_id and not ledger:
            session.warnings.append("Legacy child counters may include inherited usage; attribution is incomplete")
        return session

    def _context(self, session, state, kind, payload):
        if kind == "session_meta":
            session.id = payload.get("id", session.id)
            session.started = payload.get("timestamp", session.started)
            session.agent_id = session.id
            session.cwd = payload.get("cwd", "")
            session.parent_id = source_parent(payload)
            state["provider"] = payload.get("model_provider", "unknown")
            if payload.get("history_base"):
                session.warnings.append("Referenced historical base is not loaded; report covers records present in this file")
        settings = payload if kind == "turn_context" else {}
        if payload.get("type") == "thread_settings_applied":
            settings = payload.get("thread_settings", {})
        for target, keys in {"model": ("model",), "effort": ("effort", "reasoning_effort"),
                             "tier": ("service_tier",)}.items():
            for key in keys:
                if settings.get(key) is not None:
                    state[target] = settings[key]
        if payload.get("type") == "configuration_update":
            state["effort"] = (payload.get("reasoning") or {}).get("effort", state["effort"])

    def _content(self, session, kind, payload, line):
        if kind == "response_item":
            text = text_content(payload.get("content")) or payload.get("output", "")
            if isinstance(text, str):
                if payload.get("role") == "user" and not session.prompt and user_prompt(text):
                    session.prompt = text[:4000]
                remember_excerpt(session, text, payload.get("type", "message"), line)
        elif kind == "compacted":
            session.compactions.append({"id": payload.get("compaction_response_id", payload.get("window_id", f"{session.path}:{line}")),
                "agent_id": session.agent_id, "trigger": "unknown", "before": None, "after": None,
                "evidence": {"path": session.path, "line": line}})

    def _usage(self, session, state, ledger, fallback, kind, payload, line, timestamp):
        if kind == "token_usage_record":
            self._record(session, state, ledger, payload, line, timestamp)
        elif kind == "compacted":
            record = payload.get("latest_token_usage_record")
            if record:
                self._record(session, state, ledger, record, line, timestamp, True)
        elif payload.get("type") == "token_count" and payload.get("info"):
            info = payload["info"]
            total = info.get("total_token_usage")
            if total:
                self._cumulative(session, state, fallback, total, line, timestamp)
                session.reported[:] = [{"source": "token_count", "usage": total,
                                        "context_window": info.get("model_context_window")}]

    def _record(self, session, state, ledger, payload, line, timestamp, compaction=False):
        if payload.get("thread_id", session.id) != session.id:
            return
        identity = payload.get("response_id")
        if not identity:
            session.warnings.append(f"{session.path}:{line}: response identity missing")
            return
        observation = self._observation(session, state, payload.get("usage", {}), line, timestamp, identity, compaction)
        if observation:
            prior = ledger.get(observation.identity)
            if prior and prior.compaction and not observation.compaction:
                return
            ledger[observation.identity] = observation

    def _cumulative(self, session, state, fallback, total, line, timestamp):
        previous = state["previous"]
        state["previous"] = total
        if total == previous:
            return
        reset = previous is not None and any(total.get(k, 0) < previous.get(k, 0) for k in FIELDS)
        if reset:
            session.warnings.append(f"{session.path}:{line}: cumulative counter reset")
        baseline = {} if previous is None or reset else previous
        delta = {k: total.get(k, 0) - baseline.get(k, 0) for k in FIELDS}
        observation = self._observation(session, state, delta, line, timestamp, f"legacy:{session.id}:{line}")
        if observation:
            fallback.append(observation)

    def _observation(self, session, state, usage, line, timestamp, identity, compaction=False):
        try:
            return UsageObservation(f"{state['provider']}:{identity}", session.agent_id, state["provider"],
                state["model"], state["effort"], timestamp, codex_tokens(usage), EvidenceRef(session.path, line),
                tier=state["tier"], compaction=compaction,
                assumptions=("Service tier is the recorded preference; standard assumed if unavailable",))
        except (TypeError, ValueError) as exc:
            session.warnings.append(f"{session.path}:{line}: invalid usage: {exc}")
            return None
