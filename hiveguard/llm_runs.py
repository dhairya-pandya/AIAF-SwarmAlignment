"""Pilot and Stage B blocks for LLM runs (DESIGN §10.1, §10.3). Results append to a CSV and resume."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from .abm import STRATEGY_CLASSES
from .config import ATTACKS, RunConfig
from .env import run_llm
from .llm import LLMClient

TIER1 = ["S0b", "S1", "S2", "S3", "S4", "S7", "S9"]
TIER2 = ["S5", "S6", "S8"]
F_LLM = [0.0, 1 / 12, 3 / 12]


def _topo_free(strategy: str) -> bool:
    return not STRATEGY_CLASSES[strategy].topology


def block_configs(block: str, models: list[str], seeds: int, strategies=None, redteam=None) -> list[RunConfig]:
    base = dict(backend="llm", models=models)
    out: list[RunConfig] = []
    if block == "pilot":
        for s in ["S2", "S4"]:
            for f in [0.0, 1 / 6]:
                for seed in range(seeds):
                    out.append(RunConfig(strategy=s, n_agents=6, n_rounds=3, f=f, seed=seed, **base))
    elif block == "core":
        for s in TIER1:
            # topology-free strategies give identical runs on ring and full (DEVIATIONS D8)
            for t in (["full"] if _topo_free(s) or s in ("S0b", "S1") else ["ring", "full"]):
                for f in F_LLM:
                    for seed in range(seeds):
                        out.append(RunConfig(strategy=s, topology=t, f=f, seed=seed, **base))
        out += [RunConfig(strategy="S0a", seed=seed, **base) for seed in range(seeds)]
    elif block == "tier2":
        out = [RunConfig(strategy=s, f=f, seed=seed, **base) for s in TIER2 for f in F_LLM for seed in range(seeds)]
    elif block == "modules":
        assert strategies, "--strategies BEST WORST required"
        for s in strategies:
            for m in ["M1", "M2", "M3", "M4"]:
                for f in [0.0, 3 / 12]:   # f=0 measures usefulness cost
                    out += [RunConfig(strategy=s, f=f, modules=[m], seed=seed, **base) for seed in range(seeds)]
        if len(models) > 1:
            out += [RunConfig(strategy=strategies[0], f=f, modules=["M5"], seed=seed, **base)
                    for f in [0.0, 3 / 12] for seed in range(seeds)]
    elif block == "attacks":
        assert strategies, "--strategies BEST required"
        out = [RunConfig(strategy=strategies[0], f=1 / 12, attack=a, seed=seed, **base)
               for a in ATTACKS for seed in range(seeds)]
    elif block == "confirm":
        assert strategies and redteam, "--strategies MOST LEAST and --redteam results/redteam.json required"
        res = json.loads(Path(redteam).read_text())
        best = {}
        for r in res:
            if r["searcher"] not in best or r["best"] > best[r["searcher"]]["best"]:
                best[r["searcher"]] = r
        for name, r in sorted(best.items()):
            g = r["best_genome"]
            for s in strategies:
                out += [RunConfig(strategy=s, topology=r["topology"], placement="explicit", attacker_nodes=g["nodes"],
                                  onset=g["onset"], attack=g["attack"], graph_seed=0, seed=seed, **base)
                        for seed in range(seeds)]
    else:
        raise ValueError(block)
    return out


def _row(cfg: RunConfig, m: dict, secs: float) -> dict:
    return {"run_id": cfg.run_id, "strategy": cfg.strategy, "topology": cfg.topology, "N": cfg.n_agents,
            "R": cfg.n_rounds, "f": cfg.f, "f_eff": cfg.f_effective, "attack": cfg.attack,
            "onset": cfg.effective_onset, "placement": cfg.placement,
            "module": "+".join(cfg.modules) or "none", "models": "|".join(cfg.models), "seed": cfg.seed,
            "acc": m["acc"], "con": m["con"], "group_correct": m["group_correct"], "deadlock": m["deadlock"],
            "consensus_time": m["consensus_time"], "t50": m["t50"], "valid_rate": m["valid_rate"],
            "refusal_rate": m["refusal_rate"], "revert_rate": m["revert_rate"], "calls": m["calls"],
            "seconds": round(secs, 2), "acc_curve": json.dumps(m["acc_curve"]),
            "con_curve": json.dumps(m["con_curve"])}


def run_block(cfgs: list[RunConfig], out: str, cache: str, logs: str, workers: int) -> pd.DataFrame:
    client = LLMClient(cache)
    path = Path(out)
    done = set(pd.read_csv(path)["run_id"]) if path.exists() else set()
    todo = [c for c in cfgs if c.run_id not in done]
    print(f"{len(cfgs)} runs in block, {len(todo)} to do, ~{sum(c.n_agents * c.n_rounds for c in todo)} calls")
    for k, cfg in enumerate(todo):
        t = time.time()
        m = run_llm(cfg, client, logs, workers)
        row = _row(cfg, m, time.time() - t)
        pd.DataFrame([row]).to_csv(path, mode="a", header=not path.exists(), index=False)
        print(f"[{k + 1}/{len(todo)}] {cfg.strategy} {cfg.topology} f={cfg.f:.3f} {cfg.attack} "
              f"{row['module']} seed={cfg.seed}: acc={m['acc']:.2f} con={m['con']:.2f} "
              f"valid={m['valid_rate']:.2f} {row['seconds']}s  stats={client.stats}", flush=True)
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def pilot_report(df: pd.DataFrame) -> None:
    print("\nPilot go criteria (DESIGN §10.1):")
    for model, g in df.groupby("models"):
        valid = g["valid_rate"].mean()
        refusal = g["refusal_rate"].mean()
        s2 = g[(g.strategy == "S2") & (g.f == 0)]["acc"].mean()
        rpm = g["calls"].sum() / max(g["seconds"].sum(), 1e-9) * 60
        print(f"  {model}: valid={valid:.3f} (>=0.98 {'OK' if valid >= 0.98 else 'FAIL'}), "
              f"S2 acc@f=0={s2:.2f} (0.6-0.9 {'OK' if 0.6 <= s2 <= 0.9 else 'TUNE MARGIN'}), "
              f"refusal={refusal:.3f} (<0.02 {'OK' if refusal < 0.02 else 'FAIL'}), throughput={rpm:.0f} calls/min")


def dispatch(a, cfg: RunConfig | None) -> None:
    if a.cmd == "llm":
        cfg.backend, cfg.models = "llm", a.models
        m = run_llm(cfg, LLMClient(a.cache), a.logs, a.workers)
        m.pop("choices")
        print(json.dumps(m, indent=2))
        return
    if a.cmd == "pilot":
        frames = []
        for spec in a.models:    # one model per provider, each run separately
            cfgs = block_configs("pilot", [spec], a.seeds)
            frames.append(run_block(cfgs, a.out, a.cache, a.logs, a.workers))
        pilot_report(pd.read_csv(a.out))
        return
    cfgs = block_configs(a.block, a.models, a.seeds, getattr(a, "strategies", None), getattr(a, "redteam", None))
    run_block(cfgs, a.out, a.cache, a.logs, a.workers)
