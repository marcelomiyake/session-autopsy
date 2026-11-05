"""The approved analysis roster is execution policy, not a log filter."""

MODELS = {
    "claude": {False: "claude-haiku-5-5", True: "claude-sonnet-5-5"},
    "codex": {False: "gpt-6-luna", True: "gpt-6.1-sol"},
}


def analysis_policy(host: str, deep: bool = False, effort: str | None = None):
    if host not in MODELS:
        raise ValueError("No approved analysis host; choose claude or codex")
    level = effort or ("high" if deep else "medium")
    if level not in ("medium", "high"):
        raise ValueError("Approved analysis efforts are medium and high")
    return {"host": host, "model": MODELS[host][deep], "effort": level,
            "fresh_context": True, "automatic_escalation": False,
            "tools": "none; use only supplied evidence"}
