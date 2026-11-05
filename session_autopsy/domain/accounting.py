"""Pure request accounting and pricing; no harness schemas or external effects."""
from dataclasses import asdict
from decimal import Decimal
import re

MILLION = Decimal(1000000)
WRITE_KEYS = {"ephemeral_5m_input_tokens": "write_5m", "ephemeral_1h_input_tokens": "write_1h",
              "ttl_30m_tokens": "write_30m", "ttl_12h_tokens": "write_12h"}


def resolve_rate(observation, catalog):
    model = observation.model or ""
    aliases = catalog.get("aliases", {})
    model = aliases.get(model, model)
    if observation.model_provider == "anthropic":
        model = re.sub(r"-\d{8}$", "", model)
    tier = {"default": "standard", "auto": "standard", "priority": "fast"}.get(observation.tier, observation.tier)
    candidates = [r for r in catalog["rates"] if r["model"] == model
                  and r["provider"] == observation.model_provider and r["tier"] == tier]
    for entry in candidates:
        long = entry.get("threshold") is not None and observation.tokens.input is not None and observation.tokens.input > entry["threshold"]
        if entry["context"] == ("long" if long else "short"):
            return entry
    return None


def request_cost(observation, catalog):
    entry = resolve_rate(observation, catalog)
    tokens = observation.tokens
    if entry is None or tokens.uncached is None or tokens.output is None:
        return None
    if tokens.cache_read and entry.get("read") is None:
        return None
    base = Decimal(tokens.uncached) * Decimal(entry["input"]) + Decimal(tokens.output) * Decimal(entry["output"])
    base += Decimal(tokens.cache_read) * Decimal(entry.get("read") or 0)
    known_writes = sum(observation.writes.values())
    if known_writes > tokens.cache_write:
        return None
    for key, count in observation.writes.items():
        price = entry.get(WRITE_KEYS.get(key, key))
        if count and price is None:
            return None
        base += count * Decimal(price or 0)
    unknown = tokens.cache_write - known_writes
    prices = [Decimal(value) for key, value in entry.items() if key.startswith("write_") and value is not None]
    if unknown and not prices:
        return None
    low = base + unknown * min(prices, default=Decimal(0))
    high = base + unknown * max(prices, default=Decimal(0))
    multiplier = Decimal("1.1") if observation.geography in ("us", "us-only") else Decimal(1)
    return {"low": str(low * multiplier / MILLION), "high": str(high * multiplier / MILLION)}


def sum_tokens(observations):
    result = {}
    for field in ("input", "cache_read", "cache_write", "output", "reasoning", "uncached"):
        values = [getattr(o.tokens, field) for o in observations]
        result[field] = sum(values) if values and all(v is not None for v in values) else None
    return result


def summarize(observations, catalog):
    costs = [request_cost(o, catalog) for o in observations]
    known = [cost for cost in costs if cost is not None]
    subtotal = {k: str(sum((Decimal(cost[k]) for cost in known), Decimal(0))) for k in ("low", "high")}
    return {"requests": len(observations), "tokens": sum_tokens(observations),
            "estimated_cost_usd": subtotal if observations and len(known) == len(costs) else None,
            "priced_subtotal_usd": subtotal, "unpriced_requests": len(costs) - len(known)}


def build_report(sessions, catalog):
    unique = {}
    compactions = {}
    for session in sessions:
        for observation in session.observations:
            unique[observation.identity] = observation
        for event in session.compactions:
            compactions[event["id"]] = event
    observations = list(unique.values())
    groups = {}
    for observation in observations:
        key = (observation.model_provider, observation.model, observation.effort)
        groups.setdefault(key, []).append(observation)
    models = [{"provider": k[0], "model": k[1], "effort": k[2], **summarize(v, catalog)} for k, v in groups.items()]
    agents = [{"id": s.agent_id, "parent_id": s.parent_id, "path": s.path,
               "compactions": sum(e.get("agent_id") == s.agent_id for e in compactions.values()),
               "peak_request_input": max((o.tokens.input or 0 for o in observations if o.agent_id == s.agent_id), default=None),
               **summarize([o for o in observations if o.agent_id == s.agent_id], catalog)} for s in sessions]
    requests = [{**asdict(o), "cost_usd": request_cost(o, catalog)} for o in observations]
    requests.sort(key=lambda r: Decimal((r["cost_usd"] or {}).get("high", "0")), reverse=True)
    root = sessions[0]
    return {"schema_version": 1, "session": {k: getattr(root, k) for k in ("harness", "id", "started", "updated", "cwd", "prompt", "title")},
        "snapshot": [{"path": s.path, "bytes": s.snapshot_bytes} for s in sessions],
        "totals": summarize(observations, catalog), "models": models, "agents": agents,
        "compactions": list(compactions.values()), "most_expensive_requests": requests[:20],
        "reported_summaries": [r for s in sessions for r in s.reported],
        "reconciliation": reconcile(sessions, observations),
        "warnings": [w for s in sessions for w in s.warnings],
        "pricing": {k: catalog.get(k) for k in ("retrieved_at", "sources")},
        "cost_basis": "Estimated at current API rates; recorded summaries are reconciliation evidence, never additive",
        "coverage": "Observed requests only; summaries may contain additional unattributed/background usage"}


def reconcile(sessions, observations):
    differences = []
    for session in sessions:
        for summary in session.reported:
            for model, reported in summary.get("models", {}).items():
                owned = [o for o in observations if o.model == model and o.model_provider == summary.get("model_provider")]
                measured = sum_tokens(owned)
                delta = {k: v - (measured.get(k) or 0) for k, v in reported.items() if type(v) is int}
                differences.append({"provider": summary.get("model_provider"), "model": model,
                    "summary_only_model": not owned, "reported_tokens": reported,
                    "observed_tokens": measured, "difference": delta,
                    "note": "Counter scope/timing may differ; differences are not additive usage or estimated charges"})
    return differences
