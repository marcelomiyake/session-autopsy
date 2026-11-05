"""Ports implemented by outer adapters, including future harness integrations."""
from pathlib import Path
from typing import Protocol

from session_autopsy.domain.models import Session


class SessionSourceAdapter(Protocol):
    name: str

    def discover(self, root: Path) -> list[Path]: ...

    def read(self, path: Path) -> Session: ...


class PricingCatalog(Protocol):
    def load(self, offline: bool = False, refresh: bool = False) -> dict: ...


class EvidenceStore(Protocol):
    def save(self, content: str) -> Path: ...


class AnalysisHostAdapter(Protocol):
    def prepare(self, evidence: dict, deep: bool = False) -> dict: ...
