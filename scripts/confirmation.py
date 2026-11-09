"""Confirmation set (docs/CONFIRMATION_PREREG.md): run the 60 confirmatory LLM runs on fresh seeds, then the pre-registered tests.

    python scripts/confirmation.py run       # LLM runs -> results/confirmation.csv (resumable; stops before $9.85 spend)
    python scripts/confirmation.py analyze   # tests C1-C3 -> results/confirmation.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hiveguard.config import RunConfig  # noqa: E402

MODEL = "openrouter:openai/gpt-oss-120b"
SEEDS = range(6, 18)
OUT = "results/confirmation.csv"
BUDGET_STOP = 9.85
ARMS = {"a": ("S7", "full", []), "b": ("S7", "full", ["M3"]), "c": ("S2", "full", []),
        "d": ("S2", "ring", []), "e": ("S2", "ring", ["M3"])}
TESTS = {"C1": ("b", "a"), "C2": ("c", "a"), "C3": ("e", "d")}   # contrast = first - second, predicted < 0


def configs() -> list[RunConfig]:
    return [RunConfig(strategy=s, topology=t, f=3 / 12, modules=m, seed=seed, backend="llm", models=[MODEL])
            for s, t, m in ARMS.values() for seed in SEEDS]


def spend() -> float:
    import os
    import urllib.request
    req = urllib.request.Request("https://openrouter.ai/api/v1/credits",
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
    return float(json.load(urllib.request.urlopen(req, timeout=30))["data"]["total_usage"])


def run() -> None:
    from hiveguard.llm_runs import run_block
    cfgs = configs()
    # in batches so the budget guard is checked between them
    for k in range(0, len(cfgs), 12):
        used = spend()
        print(f"spend ${used:.2f}", flush=True)
        if used > BUDGET_STOP:
            raise SystemExit(f"budget guard: ${used:.2f} > ${BUDGET_STOP}")
        run_block(cfgs[k:k + 12], OUT, ".cache/llm.sqlite", "logs", 12, 12)


def arm_of(row) -> str:
    for name, (s, t, m) in ARMS.items():
        if row.strategy == s and row.topology == t and row.module == ("+".join(m) or "none"):
            return name
    return "?"


def paired(df: pd.DataFrame, x: str, y: str, boot: int = 10_000) -> dict:
    a = df[df.arm == x].set_index("seed").con
    b = df[df.arm == y].set_index("seed").con
    d = (a - b).dropna().to_numpy()
    rng = np.random.default_rng(0)
    means = d[rng.integers(0, len(d), (boot, len(d)))].mean(1)
    return {"diff": round(float(d.mean()), 4), "lo": round(float(np.percentile(means, 2.5)), 4),
            "hi": round(float(np.percentile(means, 97.5)), 4), "p_one_sided": round(float((means >= 0).mean()), 4),
            "n_pairs": int(len(d))}


def analyze() -> dict:
    df = pd.read_csv(OUT)
    df["arm"] = df.apply(arm_of, axis=1)
    res = {h: paired(df, x, y) for h, (x, y) in TESTS.items()}
    order = sorted(res, key=lambda h: res[h]["p_one_sided"])
    running = 0.0
    for rank, h in enumerate(order):                    # Holm step-down, adjusted p kept monotone
        running = max(running, min(1.0, (len(order) - rank) * res[h]["p_one_sided"]))
        res[h]["p_holm"] = round(running, 4)
    for h, r in res.items():
        if r["p_holm"] < 0.05 and r["diff"] < 0:
            r["verdict"] = "supported"
        elif r["diff"] > 0 or r["lo"] > 0:
            r["verdict"] = "not supported"
        else:
            r["verdict"] = "inconclusive"
    arms = df.groupby("arm").agg(con=("con", "mean"), acc=("acc", "mean"), n=("seed", "count")).round(3)
    out = {"tests": res, "arms": arms.reset_index().to_dict("records"), "seeds": list(SEEDS),
           "prereg": "docs/CONFIRMATION_PREREG.md"}
    Path("results/confirmation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    {"run": run, "analyze": analyze}[sys.argv[1]]()
