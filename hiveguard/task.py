"""Hidden-profile best-of-n task generator (DESIGN §5.1)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ATTRIBUTES = ["durability", "efficiency", "comfort", "safety", "capacity", "upkeep"]
OPTION_IDS = "ABCDEFGH"
_SYLLABLES = ["ka", "lo", "mi", "ra", "ven", "dor", "sil", "tu", "ber", "nax",
              "qua", "zel", "pim", "oro", "fen", "gal", "tre", "vy", "mon", "sha"]
NEUTRAL = 5  # unknown attribute values are treated as average


@dataclass(frozen=True)
class Fact:
    fid: int
    option: int
    attribute: int
    value: int


@dataclass
class Task:
    seed: int
    option_names: list[str]
    attributes: list[str]
    weights: np.ndarray          # (A,) public integer weights
    values: np.ndarray           # (n, A) true attribute values 0..10
    facts: list[Fact]
    holdings: list[list[int]]    # fact ids per position (attackers' facts are dropped by World)
    m: int                       # copies of each fact
    correct: int
    margin: float
    local_correct_share: float

    @property
    def n_options(self) -> int:
        return self.values.shape[0]

    def option_id(self, o: int) -> str:
        return OPTION_IDS[o]

    def option_index(self, oid: str) -> int | None:
        oid = (oid or "").strip().upper()[:1]
        i = OPTION_IDS.find(oid)
        return i if 0 <= i < self.n_options else None

    def scores(self) -> np.ndarray:
        return self.values @ self.weights

    def partial_scores(self, fact_ids) -> np.ndarray:
        """Weighted deviation from NEUTRAL using only the given facts.

        argmax of the pooled deviation equals argmax of scores(), because the shift is equal for
        every option."""
        s = np.zeros(self.n_options)
        for fid in fact_ids:
            f = self.facts[fid]
            s[f.option] += self.weights[f.attribute] * (f.value - NEUTRAL)
        return s

    def points(self, attribute: str, value: int) -> str:
        """' (+6 pts)': weight x (value - 5), shown next to every fact and claim (DEVIATIONS D17)."""
        a = attribute.strip().lower()
        if a not in self.attributes:
            return ""
        p = int(self.weights[self.attributes.index(a)] * (value - NEUTRAL))
        return f" ({p:+d} pts)"

    def fact_text(self, fid: int) -> str:
        f = self.facts[fid]
        a = self.attributes[f.attribute]
        return f"{self.option_id(f.option)}.{a} = {f.value}{self.points(a, f.value)}"


def _option_names(rng: np.random.Generator, n: int) -> list[str]:
    names: set[str] = set()
    while len(names) < n:
        k = rng.integers(2, 4)
        names.add("".join(rng.choice(_SYLLABLES, size=k)).capitalize())
    # sort first: set iteration order depends on PYTHONHASHSEED, which made names differ across processes
    return sorted(sorted(names), key=lambda s: rng.random())


def _assign(rng: np.random.Generator, n_facts: int, n_pos: int, m: int) -> list[list[int]]:
    """Give each fact to m distinct positions, keeping per-position counts balanced."""
    holdings: list[list[int]] = [[] for _ in range(n_pos)]
    copies = [fid for fid in range(n_facts) for _ in range(m)]
    rng.shuffle(copies)
    for fid in copies:
        load = np.array([len(h) if fid not in h else 10**9 for h in holdings], dtype=float)
        load += rng.random(n_pos) * 0.5           # random tie-break
        holdings[int(np.argmin(load))].append(fid)
    return holdings


def auto_m(n_pos: int, n_facts: int, facts_per_agent: int = 4) -> int:
    """m=2 at N=12 (the pre-registered value); grows with N so every agent holds ~4 facts."""
    return max(2, min(n_pos, round(facts_per_agent * n_pos / n_facts)))


def generate_task(seed: int, n_positions: int, n_options: int = 4,
                  margin: tuple[float, float] = (4.0, 16.0), max_local: float = 0.4,
                  m: int | None = None, max_tries: int = 5000) -> Task:
    """Rejection-sample a hidden-profile instance.

    Accepts an instance when the best-minus-second score gap lies in `margin` and fewer than
    `max_local` of positions would pick the correct option from their private facts alone."""
    rng = np.random.default_rng(seed)
    n_attr = len(ATTRIBUTES)
    n_facts = n_options * n_attr
    m = m or auto_m(n_positions, n_facts)
    names = _option_names(rng, n_options)
    for _ in range(max_tries):
        weights = rng.integers(1, 6, size=n_attr)
        values = rng.integers(0, 11, size=(n_options, n_attr))
        s = values @ weights
        order = np.argsort(-s)
        gap = float(s[order[0]] - s[order[1]])
        if not (margin[0] <= gap <= margin[1]):
            continue
        correct = int(order[0])
        facts = [Fact(o * n_attr + a, o, a, int(values[o, a]))
                 for o in range(n_options) for a in range(n_attr)]
        holdings = _assign(rng, n_facts, n_positions, m)
        task = Task(seed, names, list(ATTRIBUTES), weights, values, facts, holdings, m,
                    correct, gap, 0.0)
        hits = []
        for h in holdings:
            p = task.partial_scores(h)
            top = np.flatnonzero(p == p.max())
            hits.append(len(h) > 0 and len(top) == 1 and top[0] == correct)
        task.local_correct_share = float(np.mean(hits))
        if task.local_correct_share < max_local:
            return task
    raise RuntimeError(f"no hidden-profile instance found for seed={seed} after {max_tries} tries")
