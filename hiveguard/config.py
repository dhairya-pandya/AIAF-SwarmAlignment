"""Run configuration, seeding and YAML IO (DESIGN §5.6)."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

STRATEGIES = ["S0a", "S0b", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11"]
TIER = {"S0a": 1, "S0b": 1, "S1": 1, "S2": 1, "S3": 1, "S4": 1, "S7": 1, "S9": 1,
        "S5": 2, "S6": 2, "S8": 2, "S10": 3}   # S11 has no tier (exploratory)
# Added after the pre-registration (DEVIATIONS D22): reported in cells, leaderboards and figures, marked
# exploratory, and excluded from every confirmatory hypothesis test (H0-H10).
EXPLORATORY = {"S11"}
MODULES = ["M1", "M2", "M3", "M4", "M5", "M6"]
ATTACKS = ["A1", "A2", "A3", "A4", "A5"]
TOPOLOGIES = ["ring", "small_world", "scale_free", "star", "full"]
PLACEMENTS = ["random", "hub", "explicit"]

# Sleeper (A3) behaves honestly for rounds < onset; the others attack from round 0.
DEFAULT_ONSET = {"A1": 0, "A2": 0, "A3": 3, "A4": 0, "A5": 0}


def seed_int(*parts) -> int:
    """Stable 32-bit seed derived from any tuple of parts (independent of PYTHONHASHSEED)."""
    h = hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


@dataclass
class RunConfig:
    strategy: str = "S2"
    topology: str = "full"
    n_agents: int = 12              # informed agents (fact-holding positions), excludes M4 extras
    n_rounds: int = 6
    n_options: int = 4
    f: float = 0.0                  # attacker fraction; k = nearest integer to f*N, halves round up
    attack: str = "A2"
    onset: int | None = None        # None -> DEFAULT_ONSET[attack]
    placement: str = "random"
    attacker_nodes: list[int] | None = None   # used when placement == "explicit"
    modules: list[str] = field(default_factory=list)
    module_params: dict = field(default_factory=dict)
    seed: int = 0
    graph_seed: int | None = None   # None -> seed; red-team search fixes the graph
    backend: str = "abm"            # abm | llm
    models: list[str] = field(default_factory=lambda: ["mock:mock"])
    temperature: float = 0.7
    margin: tuple[float, float] = (4.0, 16.0)   # best-minus-second score gap (difficulty knob)
    prompt_variant: int = 0

    def __post_init__(self):
        assert self.strategy in STRATEGIES, self.strategy
        assert self.topology in TOPOLOGIES, self.topology
        assert self.attack in ATTACKS, self.attack
        assert self.placement in PLACEMENTS, self.placement
        for m in self.modules:
            assert m in MODULES, m
        self.margin = tuple(self.margin)

    @property
    def n_attackers(self) -> int:
        if self.placement == "explicit":
            return len(self.attacker_nodes or [])
        return int(math.floor(self.f * self.n_agents + 0.5))

    @property
    def f_effective(self) -> float:
        return self.n_attackers / self.n_agents

    @property
    def effective_onset(self) -> int:
        return DEFAULT_ONSET[self.attack] if self.onset is None else self.onset

    def to_dict(self) -> dict:
        d = asdict(self)
        d["margin"] = list(self.margin)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RunConfig":
        return cls(**d)

    @property
    def run_id(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    def save_yaml(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=True))

    @classmethod
    def load_yaml(cls, path: str | Path) -> "RunConfig":
        return cls.from_dict(yaml.safe_load(Path(path).read_text()))
