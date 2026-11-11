"""Validated official Markdown tables and a last-good, dated local snapshot."""
from datetime import datetime, timezone
from decimal import Decimal
from importlib.resources import files
import hashlib
import json
import re

from session_autopsy.adapters.local import cache_directory, private_write
from session_autopsy.adapters.network import DOCUMENTS, fetch_document


def dollars(cell):
    found = re.search(r"\$([\d,.]+)", cell)
    return str(Decimal(found[1].replace(",", ""))) if found else None


def claude_model(cell):
    found = re.search(r"Claude (Opus|Sonnet|Haiku|Fable|Mythos) (\d+(?:\.\d+)?)", cell)
    return "claude-" + found[1].lower() + "-" + found[2].replace(".", "-") if found else None


def rate(model, provider, tier, context, cells, threshold):
    return {"model": model, "provider": provider, "tier": tier, "context": context,
            "threshold": threshold, **cells}


def parse_openai(body):
    entries = []
    tier = None
    for line in body.splitlines():
        if line.startswith("#"):
            tier = next((t for t in ("ultrafast", "fast", "standard", "batch", "flex") if t in line.lower()), None)
        if not line.startswith("|") or not tier:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        model = re.match(r"(gpt-[\w.-]+|o[134](?:-[\w.-]+)?)", cells[0])
        if not model or len(cells) < 11:
            continue
        for context, start in (("short", 1), ("long", 6)):
            values = [dollars(c) for c in cells[start:start + 5]]
            if values[0] is not None and values[1] is not None:
                entries.append(rate(model[1], "openai", tier, context,
                    dict(zip(("input", "output", "read", "write_30m", "write_12h"), values)), 272000))
    return entries


def parse_claude(body):
    entries = []
    table = False
    last_model = None
    for line in body.splitlines():
        if line.startswith("#"):
            table = False
        if "Base input tokens" in line and "5m cache writes" in line:
            table = True
            continue
        if not table or not line.startswith("|"):
            continue
        parsed = _claude_row(line, last_model)
        if parsed:
            entries.append(parsed)
            last_model = parsed["model"]
    return entries + parse_claude_fast(body, entries)


def parse_claude_fast(body, standard):
    """Fast mode lists only input/output; cache multipliers apply on top, as for standard."""
    base = {e["model"]: e for e in standard if e["context"] == "short"}
    entries = []
    section = False
    for line in body.splitlines():
        if line.startswith("#"):
            section = "fast mode pricing" in line.lower()
        if not section or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        values = [dollars(c) for c in cells[1:3]]
        if len(cells) < 3 or any(v is None for v in values):
            continue
        for name in cells[0].split("/"):
            model = claude_model(name)
            if not model or model not in base:
                continue
            reference = base[model]
            scale = Decimal(values[0]) / Decimal(reference["input"])
            cache = {k: format((Decimal(reference[k]) * scale).normalize(), "f")
                     for k in ("write_5m", "write_1h", "read")}
            entries.append(rate(model, "anthropic", "fast", "short",
                {"input": values[0], **cache, "output": values[1]}, None))
    return entries


def _claude_row(line, last_model):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 6:
        return None
    model = claude_model(cells[0]) or last_model
    values = [dollars(c) for c in cells[1:6]]
    if not model or any(v is None for v in values):
        return None
    long = "over 100" in line or ">100" in line or "> 100" in line
    return rate(model, "anthropic", "standard", "long" if long else "short",
        dict(zip(("input", "write_5m", "write_1h", "read", "output"), values)),
        100000 if model == "claude-haiku-5-5" else None)


def validate_snapshot(data):
    if data.get("schema_version") != 1 or not data.get("retrieved_at"):
        raise ValueError("Invalid pricing snapshot header")
    for entry in data.get("rates", []):
        for key in ("input", "output", "read", "write_5m", "write_1h", "write_30m", "write_12h"):
            value = entry.get(key)
            if value is not None and (not Decimal(value).is_finite() or Decimal(value) < 0):
                raise ValueError("Invalid rate")
    if not data.get("rates"):
        raise ValueError("No verified rates")
    return data


class OfficialPrices:
    def __init__(self, custom=None):
        self.custom = custom
        self.warnings = []

    def load(self, offline=False, refresh=False):
        if self.custom:
            return validate_snapshot(json.loads(self.custom.read_text()))
        cached = cache_directory() / "prices.json"
        baseline = files("session_autopsy").joinpath("data/prices.json")
        try:
            data = validate_snapshot(json.loads((cached if cached.exists() else baseline).read_text()))
        except (ValueError, ArithmeticError):
            self.warnings.append("Invalid cached prices; using bundled verified snapshot")
            data = validate_snapshot(json.loads(baseline.read_text()))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(data["retrieved_at"])
        if not offline and (refresh or age.total_seconds() > 86400):
            try:
                data = self.refresh()
                private_write(cached, json.dumps(data, indent=2))
            except (OSError, ValueError, ArithmeticError) as exc:
                self.warnings.append(f"Pricing refresh failed; last-good snapshot retained: {exc}")
        if (datetime.now(timezone.utc) - datetime.fromisoformat(data["retrieved_at"])).total_seconds() > 86400:
            self.warnings.append("Pricing snapshot is stale; inspect retrieved_at")
        return data

    def refresh(self):
        documents = {name: fetch_document(name) for name in ("anthropic-prices", "openai-prices")}
        anthropic = parse_claude(documents["anthropic-prices"])
        openai = parse_openai(documents["openai-prices"])
        if len(anthropic) < 3 or len(openai) < 3:
            raise ValueError("Official table layout changed or rates are incomplete")
        return validate_snapshot({"schema_version": 1, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "sources": [{"url": DOCUMENTS[k], "sha256": hashlib.sha256(v.encode()).hexdigest()} for k, v in documents.items()],
            "rates": anthropic + openai})
