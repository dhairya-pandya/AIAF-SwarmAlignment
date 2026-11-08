"""Everything about a run that is fixed before round 0: task, graph, roles, target.

Shared by the ABM and the LLM environment so both see identical instances (paired design)."""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from .config import RunConfig, seed_int
from .task import Task, generate_task
from .topology import adjacency, betweenness, distances, hub_order, make_graph


@dataclass
class World:
    cfg: RunConfig
    task: Task
    G: nx.Graph
    A: np.ndarray             # (N, N) bool adjacency, includes M4 uninformed nodes
    dist: np.ndarray          # (N, N) graph distances
    betweenness: np.ndarray   # (N,)
    N: int                    # all agents
    N_inf: int                # fact-holding positions (honest or attacker)
    attackers: np.ndarray     # positions of compromised agents
    honest: np.ndarray        # (N,) bool: honest and informed (the metric population)
    uninformed: np.ndarray    # (N,) bool: M4 dilution agents
    attacker: np.ndarray      # (N,) bool
    holdings: list[list[int]] # fact ids per agent; empty for attackers and uninformed
    target: int               # attackers' hidden target option (also defined at f=0)


def build_world(cfg: RunConfig, task: Task | None = None) -> World:
    n_inf = cfg.n_agents
    u = int(cfg.module_params.get("M4_u", 2)) if "M4" in cfg.modules else 0
    N = n_inf + u
    task = task or generate_task(seed_int(cfg.seed, "task", n_inf, cfg.n_options),
                                 n_inf, cfg.n_options, cfg.margin)
    topo = cfg.module_params.get("M6_topology", "ring") if "M6" in cfg.modules else cfg.topology
    gseed = seed_int(cfg.seed if cfg.graph_seed is None else cfg.graph_seed, "graph", topo, N)
    G = make_graph(topo, N, gseed)

    k = cfg.n_attackers
    if cfg.placement == "explicit":
        att = np.array(sorted(cfg.attacker_nodes or []), dtype=int)
    elif cfg.placement == "hub":
        att = np.array(sorted(hub_order(G, n_inf, gseed)[:k]), dtype=int)
    else:
        # nested placement: the attackers at f=1/12 are a subset of those at f=3/12
        perm = np.random.default_rng(seed_int(cfg.seed, "placement", n_inf)).permutation(n_inf)
        att = np.array(sorted(perm[:k]), dtype=int)
    assert len(att) == 0 or (att.max() < n_inf and len(set(att.tolist())) == len(att)), att

    attacker = np.zeros(N, dtype=bool)
    attacker[att] = True
    uninformed = np.zeros(N, dtype=bool)
    uninformed[n_inf:] = True
    honest = ~attacker & ~uninformed
    # attackers receive no true facts; honest agents keep the same facts at every f
    holdings = [list(task.holdings[i]) if (i < n_inf and honest[i]) else [] for i in range(N)]

    wrong = [o for o in range(cfg.n_options) if o != task.correct]
    target = int(np.random.default_rng(seed_int(cfg.seed, "target")).choice(wrong))
    return World(cfg, task, G, adjacency(G), distances(G), betweenness(G), N, n_inf, att,
                 honest, uninformed, attacker, holdings, target)
