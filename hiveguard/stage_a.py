"""Stage A: the ABM screen over the full grid (DESIGN §10.2)."""
from __future__ import annotations

import itertools
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from .abm import ABMParams, run_abm
from .config import MODULES, STRATEGIES, TOPOLOGIES, RunConfig
from .search import SEARCHERS, Problem, run_search

F_GRID = ["0", "1/N", 0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
N_GRID = [12, 50, 200]


def _f(f, N):
    if f == "0":
        return 0.0
    if f == "1/N":
        return 1.0 / N
    return float(f)


def grid(strategies=STRATEGIES, modules=MODULES, topologies=TOPOLOGIES, f_grid=F_GRID,
         n_grid=N_GRID, seeds=30, attack="A2"):
    for s, m, t, f, N, seed in itertools.product(strategies, [None] + list(modules), topologies,
                                                 f_grid, n_grid, range(seeds)):
        yield RunConfig(strategy=s, modules=[m] if m else [], topology=t, f=_f(f, N), n_agents=N,
                        seed=seed, attack=attack)


def _row(args):
    cfg, pdict = args
    m = run_abm(cfg, ABMParams(**pdict))
    return {
        "strategy": cfg.strategy, "module": cfg.modules[0] if cfg.modules else "none",
        "topology": cfg.topology, "N": cfg.n_agents, "f": cfg.f, "f_eff": cfg.f_effective,
        "k": cfg.n_attackers, "attack": cfg.attack, "seed": cfg.seed,
        "acc": m["acc"], "con": m["con"], "group_correct": m["group_correct"],
        "deadlock": m["deadlock"], "consensus_time": m["consensus_time"], "t50": m["t50"],
        "con_curve": json.dumps([round(x, 4) for x in m["con_curve"]]),
    }


def run_stage_a(out: str | Path, params: ABMParams, workers: int | None = None, **grid_kw) -> pd.DataFrame:
    cfgs = list(grid(**grid_kw))
    pdict = params.to_dict()
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    with ProcessPoolExecutor(workers) as ex:
        rows = list(ex.map(_row, [(c, pdict) for c in cfgs], chunksize=256))
    df = pd.DataFrame(rows)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


def _search_job(args):
    strategy, topology, k, name, rep, budget, pdict = args
    prob = Problem(RunConfig(strategy=strategy, topology=topology), k=k, params=ABMParams(**pdict))
    r = run_search(prob, name, budget=budget, seed=rep)
    g = r["best_genome"]
    r["best_genome"] = {"nodes": list(g.nodes), "onset": g.onset, "attack": g.attack}
    r.update(strategy=strategy, topology=topology, k=k)
    return r


def run_red_team(out: str | Path, params: ABMParams, strategies=("S2",), topologies=("scale_free",),
                 k: int = 3, budget: int = 500, repeats: int = 10, workers: int | None = None) -> list[dict]:
    jobs = [(s, t, k, name, rep, budget, params.to_dict())
            for s in strategies for t in topologies for name in SEARCHERS for rep in range(repeats)]
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_search_job, jobs))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res))
    return res
