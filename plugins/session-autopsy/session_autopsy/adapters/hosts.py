"""Native host handoff only; this adapter never makes inference requests."""
from session_autopsy.domain.policy import analysis_policy


class NativeAnalysisHost:
    def __init__(self, name):
        self.name = name

    def prepare(self, evidence, deep=False):
        return {"policy": analysis_policy(self.name, deep), "evidence": evidence,
                "delivery": "Use a native fresh-context worker on this provider; no API client or fallback"}
