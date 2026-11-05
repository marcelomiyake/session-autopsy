"""Human presentation without loading whole transcripts into the assistant."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json


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


def render(value, format="text"):
    if format == "json":
        return json.dumps(value, indent=2, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(f"{r['number']}. [{r['harness']}] {r['id']} | {r['started']} → {r['updated']}\n   {r['cwd']} | {r['title']}\n   {r['initial_prompt'].replace(chr(10), ' ')}" for r in value) or "No sessions matched."
    if "totals" not in value:
        return json.dumps(value, indent=2, ensure_ascii=False)
    session = value["session"]
    lines = [f"# Session {session['id']} ({session['harness']})", f"Directory: {session['cwd']}",
             f"Started: {session['started']} | Updated: {session['updated']}",
             f"Initial prompt: {session['prompt'][:500]}", "", value["cost_basis"],
             "Totals: " + json.dumps(value["totals"]),
             f"Compactions: {len(value['compactions'])}", f"Prices verified: {value['pricing']['retrieved_at']}",
             value["coverage"], "", "Models and efforts:"]
    lines.extend(json.dumps(m) for m in value["models"])
    lines.append("\nAgents:")
    lines.extend(json.dumps(a) for a in value["agents"])
    lines.append("\nCompaction events:")
    lines.extend(json.dumps(e) for e in value["compactions"])
    lines.append("\nRecorded summaries (not additive):")
    lines.extend(json.dumps(r) for r in value["reported_summaries"])
    lines.extend("Warning: " + w for w in value["warnings"])
    return "\n".join(lines)
