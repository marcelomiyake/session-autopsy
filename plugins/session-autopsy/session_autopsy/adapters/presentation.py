"""Human presentation without loading whole transcripts into the assistant."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json

UNKNOWN = "unknown"
TOKEN_COLUMNS = (("input", "Input"), ("uncached", "Uncached"), ("cache_read", "Cache read"),
                 ("cache_write", "Cache write"), ("output", "Output"), ("reasoning", "Reasoning"))


def local_time(timestamp, timezone=None):
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo(timezone) if timezone else None).isoformat(timespec="seconds")
    except ValueError:
        return timestamp
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown timezone; use an IANA name such as America/Sao_Paulo") from exc


def session_rows(sessions, timezone=None):
    return [{"number": i, "harness": s.harness, "id": s.agent_id,
             "started": local_time(s.started, timezone), "updated": local_time(s.updated, timezone),
             "cwd": s.cwd, "title": s.title, "initial_prompt": s.prompt[:200], "path": s.path}
            for i, s in enumerate(sessions, 1)]


def render(value, format="text", timezone=None):
    if format == "json":
        return json.dumps(value, indent=2, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(f"{r['number']}. [{r['harness']}] {r['id']} | {r['started']} → {r['updated']}\n   {r['cwd']} | {r['title']}\n   {r['initial_prompt'].replace(chr(10), ' ')}" for r in value) or "No sessions matched."
    if "totals" in value:
        return "\n".join(report_lines(value, format == "markdown", timezone))
    if all(not isinstance(v, (dict, list)) for v in value.values()):
        return "\n".join(f"{key.replace('_', ' ')}: {count(item)}" for key, item in value.items())
    return json.dumps(value, indent=2, ensure_ascii=False)


def count(value):
    if value is None:
        return UNKNOWN
    if isinstance(value, bool):
        return str(value).lower()
    return f"{value:,}" if type(value) in (int, float) else str(value)


def money(amount):
    try:
        value = Decimal(str(amount))
    except InvalidOperation:
        return str(amount)
    if 0 < abs(value) < Decimal("0.0001"):
        return "<$0.0001"
    return f"${value.quantize(Decimal('0.01') if abs(value) >= 1 else Decimal('0.0001')):,}"


def cost(estimate):
    if not estimate:
        return "unpriced"
    low, high = money(estimate.get("low")), money(estimate.get("high"))
    return low if low == high else f"{low}–{high}"


def summary_cost(summary):
    """Unpriced requests make a total a lower bound, never a zero."""
    if summary["unpriced_requests"] and summary["unpriced_requests"] < summary["requests"]:
        return "≥" + money(summary["priced_subtotal_usd"]["low"])
    return cost(summary["estimated_cost_usd"])


def table(headers, rows, markdown, labels=1):
    """Align a table; the first `labels` columns are text, the rest are numbers."""
    if markdown:
        rule = ["---" if i < labels else "---:" for i in range(len(headers))]
        return ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in (headers, rule, *rows)]
    widths = [max(len(cell) for cell in column) for column in zip(headers, *rows)]
    def line(row):
        return "  ".join(c.ljust(w) if i < labels else c.rjust(w) for i, (c, w) in enumerate(zip(row, widths))).rstrip()
    return [line(headers), line(["-" * w for w in widths]), *(line(row) for row in rows)]


def heading(text, markdown):
    return ["", f"## {text}"] if markdown else ["", text, "=" * len(text)]


def fields(pairs, markdown):
    pairs = [(label, value) for label, value in pairs if value not in (None, "")]
    if markdown:
        return [f"- **{label}:** {value}" for label, value in pairs]
    width = max((len(label) for label, _ in pairs), default=0)
    return [f"{label + ':':<{width + 1}} {value}" for label, value in pairs]


def bullets(items, markdown):
    return [("- " if markdown else "  • ") + item for item in items]


def describe(value):
    """Flatten an untrusted recorded summary into one readable phrase."""
    if isinstance(value, dict):
        return ", ".join(f"{key.replace('_', ' ')} {describe(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "; ".join(describe(item) for item in value)
    return count(value)


def report_lines(value, markdown, timezone=None):
    session, totals = value["session"], value["totals"]
    title = f"Session {session['id']} ({session['harness']})"
    lines = [f"# {title}" if markdown else title]
    lines += fields((("Title", session.get("title")), ("Directory", session.get("cwd")),
                     ("Started", local_time(session.get("started") or "", timezone)),
                     ("Updated", local_time(session.get("updated") or "", timezone)),
                     ("Initial prompt", " ".join(session.get("prompt", "").split())[:500])), markdown)
    lines += heading("Summary", markdown) + fields(summary_pairs(value, timezone), markdown)
    lines += heading("Usage by model", markdown) + usage_table(value["models"], totals, markdown)
    lines += heading("Agents", markdown) + agent_table(value["agents"], markdown)
    if value["compactions"]:
        lines += heading("Compactions", markdown) + compaction_table(value["compactions"], markdown, timezone)
    if value["reported_summaries"]:
        lines += heading("Recorded summaries (not additive)", markdown)
        lines += bullets([describe(summary) for summary in value["reported_summaries"]], markdown)
    if value["reconciliation"]:
        lines += heading("Summary reconciliation", markdown) + reconciliation_table(value["reconciliation"], markdown)
    notes = [value["cost_basis"], value["coverage"], *("Warning: " + w for w in value["warnings"])]
    return lines + heading("Notes", markdown) + bullets(notes, markdown)


def summary_pairs(value, timezone=None):
    totals = value["totals"]
    estimate = cost(totals["estimated_cost_usd"])
    unpriced = totals["unpriced_requests"]
    if unpriced:
        estimate = f"incomplete: {cost(totals['priced_subtotal_usd'])} priced, {unpriced} unpriced request{'s' * (unpriced != 1)}"
    return (("Requests", count(totals["requests"])), ("Estimated API cost", estimate),
            ("Compactions", count(len(value["compactions"]))),
            ("Prices verified", local_time(value["pricing"].get("retrieved_at") or UNKNOWN, timezone)))


def token_cells(tokens):
    return [count(tokens.get(key)) for key, _ in TOKEN_COLUMNS]


def usage_table(models, totals, markdown):
    headers = ["Model", "Effort", "Requests", *(label for _, label in TOKEN_COLUMNS), "Est. cost"]
    rows = [[m["model"] or UNKNOWN, m["effort"] or UNKNOWN, count(m["requests"]), *token_cells(m["tokens"]),
             summary_cost(m)] for m in models]
    rows.append(["Total", "", count(totals["requests"]), *token_cells(totals["tokens"]), summary_cost(totals)])
    return table(headers, rows, markdown, labels=2)


def agent_table(agents, markdown):
    parents = {agent["id"]: agent.get("parent_id") for agent in agents}
    def depth(agent_id, seen=()):
        parent = parents.get(agent_id)
        return 0 if parent not in parents or agent_id in seen else 1 + depth(parent, (*seen, agent_id))
    headers = ["Agent", "Requests", "Compactions", "Peak input", "Input", "Output", "Est. cost"]
    rows = [["  " * depth(a["id"]) + ("↳ " if depth(a["id"]) else "") + a["id"], count(a["requests"]),
             count(a["compactions"]), count(a["peak_request_input"]), count(a["tokens"].get("input")),
             count(a["tokens"].get("output")), summary_cost(a)] for a in agents]
    return table(headers, rows, markdown)


def compaction_table(events, markdown, timezone=None):
    headers = ["Time", "Agent", "Trigger", "Before", "After", "Evidence line"]
    rows = [[local_time(e.get("timestamp") or UNKNOWN, timezone), e.get("agent_id") or UNKNOWN, e.get("trigger") or UNKNOWN,
             count(e.get("before")), count(e.get("after")), count((e.get("evidence") or {}).get("line"))] for e in events]
    return table(headers, rows, markdown, labels=3)


def reconciliation_table(differences, markdown):
    headers = ["Model", "Counter", "Recorded", "Observed", "Difference"]
    rows = []
    for item in differences:
        model = item["model"] + (" (summary only)" if item.get("summary_only_model") else "")
        for key, delta in item["difference"].items():
            rows.append([model, key.replace("_", " "), count(item["reported_tokens"].get(key)),
                         count(item["observed_tokens"].get(key)), f"{delta:+,}"])
    notes = sorted({item["note"] for item in differences})
    return table(headers, rows, markdown, labels=2) + [""] + bullets(notes, markdown)
