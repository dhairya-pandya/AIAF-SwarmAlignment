"""Red-team searchers over attack configurations (DESIGN §9).

Genome: (attacker node set of size k, onset round, attack type). Fitness: mean final contamination
over `n_seeds` ABM seeds on a fixed graph. Every searcher uses the ask/tell interface."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .abm import ABMParams, run_abm
from .config import ATTACKS, RunConfig
from .world import build_world


@dataclass(frozen=True)
class Genome:
    nodes: tuple[int, ...]
    onset: int
    attack: str


class Problem:
    def __init__(self, base: RunConfig, k: int, n_seeds: int = 5, params: ABMParams | None = None,
                 graph_seed: int = 0):
        self.base = replace(base, graph_seed=graph_seed, placement="explicit")
        self.k, self.n_seeds, self.params = k, n_seeds, params
        w = build_world(replace(self.base, attacker_nodes=list(range(k))))
        self.N = w.N_inf
        self.R = base.n_rounds
        self.bc = w.betweenness[: self.N]
        self.hubs = [int(i) for i in np.argsort(-self.bc, kind="stable")]
        self.cache: dict[Genome, float] = {}
        self.evals = 0

    def fitness(self, g: Genome) -> float:
        if g not in self.cache:
            cons = [run_abm(replace(self.base, attacker_nodes=list(g.nodes), onset=g.onset,
                                    attack=g.attack, seed=s), self.params)["con"]
                    for s in range(self.n_seeds)]
            self.cache[g] = float(np.mean(cons))
        self.evals += 1          # repeated genomes still spend budget
        return self.cache[g]

    def random(self, rng) -> Genome:
        return Genome(tuple(sorted(rng.choice(self.N, self.k, replace=False).tolist())),
                      int(rng.integers(0, self.R)), str(rng.choice(ATTACKS)))

    def mutate(self, g: Genome, rng, rate: float = 0.1) -> Genome:
        nodes = set(g.nodes)
        for n in list(nodes):
            if rng.random() < rate:
                free = [i for i in range(self.N) if i not in nodes]
                if free:
                    nodes.remove(n)
                    nodes.add(int(rng.choice(free)))
        onset = int(rng.integers(0, self.R)) if rng.random() < rate else g.onset
        attack = str(rng.choice(ATTACKS)) if rng.random() < rate else g.attack
        out = Genome(tuple(sorted(nodes)), onset, attack)
        if out == g:  # force at least one change so mutation explores
            return self.mutate(g, rng, rate=max(rate, 0.5))
        return out

    def descriptor(self, g: Genome, bins: int = 8) -> tuple[int, int]:
        mx = self.bc.max() if self.bc.max() > 0 else 1.0
        b = min(int(np.mean(self.bc[list(g.nodes)]) / mx * bins), bins - 1)
        return b, g.onset


class Searcher:
    name = ""

    def __init__(self, prob: Problem, seed: int):
        self.prob, self.rng = prob, np.random.default_rng(seed)

    def ask(self) -> Genome:
        raise NotImplementedError

    def tell(self, g: Genome, fit: float) -> None:
        pass


class RandomSearch(Searcher):
    name = "random"

    def ask(self):
        return self.prob.random(self.rng)


class HubSearch(Searcher):
    """Greedy hub: top-k betweenness nodes over every onset x attack, then local swaps near hubs."""
    name = "hub"

    def __init__(self, prob, seed):
        super().__init__(prob, seed)
        hubs = tuple(sorted(prob.hubs[: prob.k]))
        self.queue = [Genome(hubs, o, a) for o in range(prob.R) for a in ATTACKS]
        self.rng.shuffle(self.queue)
        self.best: tuple[float, Genome] | None = None

    def ask(self):
        if self.queue:
            return self.queue.pop()
        g = self.best[1]
        nodes = list(g.nodes)
        nxt = [h for h in self.prob.hubs if h not in nodes]
        i = int(self.rng.integers(len(nodes)))
        rank = min(int(self.rng.geometric(0.4)) - 1, len(nxt) - 1)
        nodes[i] = nxt[rank]
        return Genome(tuple(sorted(nodes)), g.onset, g.attack)

    def tell(self, g, fit):
        if self.best is None or fit > self.best[0]:
            self.best = (fit, g)


class GA(Searcher):
    """Pop 20, binary tournament, uniform crossover, mutation rate 0.1."""
    name = "ga"

    def __init__(self, prob, seed, pop: int = 20, rate: float = 0.1):
        super().__init__(prob, seed)
        self.size, self.rate = pop, rate
        self.pending = [prob.random(self.rng) for _ in range(pop)]
        self.pop: list[tuple[float, Genome]] = []
        self.children: list[tuple[float, Genome]] = []

    def _tour(self):
        a, b = self.rng.choice(len(self.pop), 2, replace=False)
        return max(self.pop[a], self.pop[b], key=lambda t: t[0])[1]

    def _cross(self, a: Genome, b: Genome) -> Genome:
        pool = list(set(a.nodes) | set(b.nodes))
        shared = list(set(a.nodes) & set(b.nodes))
        rest = [n for n in pool if n not in shared]
        self.rng.shuffle(rest)
        nodes = tuple(sorted(shared + rest[: self.prob.k - len(shared)]))
        return Genome(nodes, a.onset if self.rng.random() < 0.5 else b.onset,
                      a.attack if self.rng.random() < 0.5 else b.attack)

    def ask(self):
        if self.pending:
            return self.pending.pop()
        return self.prob.mutate(self._cross(self._tour(), self._tour()), self.rng, self.rate)

    def tell(self, g, fit):
        if len(self.pop) < self.size:
            self.pop.append((fit, g))
            return
        self.children.append((fit, g))
        if len(self.children) == self.size:   # generational replacement with elitism of 1
            elite = max(self.pop, key=lambda t: t[0])
            self.pop = sorted(self.children, key=lambda t: -t[0])[: self.size - 1] + [elite]
            self.children = []


class BinaryPSO(Searcher):
    """Binary PSO over node bits (repaired to exactly k) plus categorical PSO over onset and attack."""
    name = "bpso"

    def __init__(self, prob, seed, particles: int = 20, w: float = 0.7, c1: float = 1.5,
                 c2: float = 1.5, vmax: float = 4.0):
        super().__init__(prob, seed)
        self.P, self.w, self.c1, self.c2, self.vmax = particles, w, c1, c2, vmax
        dim = prob.N + prob.R + len(ATTACKS)
        self.x = np.zeros((particles, dim))
        self.v = self.rng.uniform(-1, 1, (particles, dim))
        for i in range(particles):
            self.x[i] = self._encode(prob.random(self.rng))
        self.pbest = self.x.copy()
        self.pfit = np.full(particles, -np.inf)
        self.gbest, self.gfit = self.x[0].copy(), -np.inf
        self.i = 0
        self.started = False

    def _encode(self, g: Genome) -> np.ndarray:
        N, R = self.prob.N, self.prob.R
        x = np.zeros(N + R + len(ATTACKS))
        x[list(g.nodes)] = 1
        x[N + g.onset] = 1
        x[N + R + ATTACKS.index(g.attack)] = 1
        return x

    def _decode(self, v: np.ndarray) -> np.ndarray:
        N, R, k = self.prob.N, self.prob.R, self.prob.k
        prob = 1 / (1 + np.exp(-v))
        x = np.zeros_like(v)
        bits = self.rng.random(N) < prob[:N]
        # repair to exactly k nodes, keeping sampled ones by probability
        score = prob[:N] + bits * 10 + self.rng.uniform(0, 1e-6, N)
        x[np.argsort(-score)[:k]] = 1
        p_on = prob[N:N + R] / prob[N:N + R].sum()
        x[N + self.rng.choice(R, p=p_on)] = 1
        p_at = prob[N + R:] / prob[N + R:].sum()
        x[N + R + self.rng.choice(len(ATTACKS), p=p_at)] = 1
        return x

    def _genome(self, x) -> Genome:
        N, R = self.prob.N, self.prob.R
        return Genome(tuple(int(i) for i in np.flatnonzero(x[:N])), int(np.argmax(x[N:N + R])),
                      ATTACKS[int(np.argmax(x[N + R:]))])

    def ask(self):
        i = self.i
        if self.started:
            r1, r2 = self.rng.random(self.v.shape[1]), self.rng.random(self.v.shape[1])
            self.v[i] = np.clip(self.w * self.v[i] + self.c1 * r1 * (self.pbest[i] - self.x[i])
                                + self.c2 * r2 * (self.gbest - self.x[i]), -self.vmax, self.vmax)
            self.x[i] = self._decode(self.v[i])
        return self._genome(self.x[i])

    def tell(self, g, fit):
        i = self.i
        if fit > self.pfit[i]:
            self.pfit[i], self.pbest[i] = fit, self.x[i].copy()
        if fit > self.gfit:
            self.gfit, self.gbest = fit, self.x[i].copy()
        self.i = (i + 1) % self.P
        if self.i == 0:
            self.started = True


class MapElites(Searcher):
    """MAP-Elites over (mean attacker betweenness bin x onset round) on an 8 x R grid."""
    name = "map_elites"

    def __init__(self, prob, seed, init: int = 20):
        super().__init__(prob, seed)
        self.n_init = init
        self.archive: dict[tuple[int, int], tuple[float, Genome]] = {}
        self.told = 0

    def ask(self):
        if self.told < self.n_init or not self.archive:
            return self.prob.random(self.rng)
        keys = list(self.archive)
        parent = self.archive[keys[int(self.rng.integers(len(keys)))]][1]
        return self.prob.mutate(parent, self.rng, 0.2)

    def tell(self, g, fit):
        self.told += 1
        d = self.prob.descriptor(g)
        if d not in self.archive or fit > self.archive[d][0]:
            self.archive[d] = (fit, g)


SEARCHERS = {c.name: c for c in [RandomSearch, HubSearch, GA, BinaryPSO, MapElites]}


def run_search(prob: Problem, name: str, budget: int = 500, seed: int = 0) -> dict:
    s = SEARCHERS[name](prob, seed)
    best, best_g, curve = -1.0, None, []
    while prob.evals < budget:
        g = s.ask()
        fit = prob.fitness(g)
        s.tell(g, fit)
        if fit > best:
            best, best_g = fit, g
        curve.append(best)
    out = {"searcher": name, "seed": seed, "best": best, "best_genome": best_g, "curve": curve}
    if isinstance(s, MapElites):
        out["archive"] = {f"{k[0]},{k[1]}": v[0] for k, v in s.archive.items()}
    return out
