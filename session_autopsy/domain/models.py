"""Common language shared through the published adapter contract."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tokens:
    """Input includes reads/writes; reasoning is a subset of output."""

    input: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    output: int | None = None
    reasoning: int | None = None

    def __post_init__(self):
        values = (self.input, self.cache_read, self.cache_write, self.output, self.reasoning)
        if any(v is not None and (type(v) is not int or v < 0) for v in values):
            raise ValueError("Token counts must be nonnegative integers or unknown")
        if self.uncached is not None and self.uncached < 0:
            raise ValueError("Cache categories exceed total input")
        if self.reasoning is not None and self.output is not None and self.reasoning > self.output:
            raise ValueError("Reasoning exceeds output")

    @property
    def uncached(self):
        if any(v is None for v in (self.input, self.cache_read, self.cache_write)):
            return None
        return self.input - self.cache_read - self.cache_write


@dataclass(frozen=True)
class EvidenceRef:
    path: str
    line: int


@dataclass(frozen=True)
class UsageObservation:
    identity: str
    agent_id: str
    model_provider: str
    model: str | None
    effort: str | None
    timestamp: str
    tokens: Tokens
    evidence: EvidenceRef
    writes: dict[str, int] = field(default_factory=dict)
    tier: str = "standard"
    geography: str = "global"
    compaction: bool = False
    assumptions: tuple[str, ...] = ()


@dataclass
class Session:
    harness: str
    id: str
    path: str
    started: str = ""
    updated: str = ""
    cwd: str = ""
    prompt: str = ""
    title: str = ""
    parent_id: str | None = None
    agent_id: str = ""
    observations: list[UsageObservation] = field(default_factory=list)
    compactions: list[dict] = field(default_factory=list)
    excerpts: list[dict] = field(default_factory=list)
    reported: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)
    snapshot_bytes: int = 0
