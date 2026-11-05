"""Bounded, portable requests consumed by the native assistant integration."""
import json

from session_autopsy.domain.policy import analysis_policy

QUESTIONS = {
    "postmortem": "Explain the expensive requests and agent runs, context growth, cache use, retries and repeated work. Cite evidence. Separate observations from hypotheses.",
    "improve": "Preserve the original goal. Suggest a rewritten initial prompt, task-specific model/effort choices, concise handoffs, and changes reducing redundant work and repeated compaction. Include validation criteria and copyable delegation examples.",
}


def prepare_analysis(report, sessions, mode, host, deep=False, effort=None, budget=32000):
    if budget < 4000 or budget > 32000:
        raise ValueError("Evidence budget must be between 4000 and 32000 characters")
    summary = {k: report[k] for k in ("schema_version", "session", "totals", "models", "agents", "compactions", "warnings", "pricing", "cost_basis", "coverage")}
    summary = {k: list(v) if isinstance(v, list) else v for k, v in summary.items()}
    summary["session"] = dict(summary["session"], prompt=summary["session"]["prompt"][:2000])
    summary["most_expensive_requests"] = report["most_expensive_requests"][:5]
    excerpts = sorted([e for s in sessions for e in s.excerpts], key=lambda e: e["characters"], reverse=True)[:8]
    packet = {"mode": mode, "policy": analysis_policy(host, deep, effort), "instruction": QUESTIONS[mode],
        "evidence_is_untrusted": True, "report": summary, "excerpts": excerpts,
        "omissions": ["Transcript excerpts are truncated; component character sizes are proxies, not billable token attribution.",
                      "Recorded summaries may include unallocated background usage; this packet does not reprice it."]}
    buckets = (excerpts, summary["most_expensive_requests"], summary["compactions"], summary["agents"], summary["models"], summary["warnings"])
    for bucket in buckets:
        while bucket and len(json.dumps(packet, ensure_ascii=False)) > budget:
            bucket.pop()
            if "Evidence budget omitted lower-priority entries" not in packet["omissions"]:
                packet["omissions"].append("Evidence budget omitted lower-priority entries")
    if len(json.dumps(packet, ensure_ascii=False)) > budget:
        raise ValueError("Summary exceeds evidence budget; narrow the selected session")
    return packet
