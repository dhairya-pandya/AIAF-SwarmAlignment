"""Exploratory S12 (elephant matriarch) on LLM swarms, DEVIATIONS D24. Not confirmatory.

Runs S12 at f=3/12 on confirmation seeds 6-17 (paired with confirmation arm a, the S7 hierarchy) and at f=0 on seeds
0-5 (paired with the Study 1 core S7 and S2 runs) -> results/s12_llm.csv; summary -> results/s12_llm.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hiveguard.config import RunConfig  # noqa: E402
from hiveguard.llm_runs import run_block  # noqa: E402

MODEL = "openrouter:openai/gpt-oss-120b"
OUT = "results/s12_llm.csv"


def paired(a: pd.Series, b: pd.Series) -> dict:
    d = (a - b).dropna().to_numpy()
    m = d[np.random.default_rng(0).integers(0, len(d), (10_000, len(d)))].mean(1)
    return {"diff": round(float(d.mean()), 3), "lo": round(float(np.percentile(m, 2.5)), 3),
            "hi": round(float(np.percentile(m, 97.5)), 3), "n": int(len(d))}


def main() -> None:
    cfgs = [RunConfig(strategy="S12", f=3 / 12, seed=s, backend="llm", models=[MODEL]) for s in range(6, 18)]
    cfgs += [RunConfig(strategy="S12", f=0.0, seed=s, backend="llm", models=[MODEL]) for s in range(6)]
    run_block(cfgs, OUT, ".cache/llm.sqlite", "logs", 12, 12)
    s12 = pd.read_csv(OUT)
    s2 = pd.read_csv("results/confirmation.csv")
    core = pd.read_csv("results/stageB_core.csv")
    att, clean = s12[s12.f > 0].set_index("seed"), s12[s12.f == 0].set_index("seed")
    s7a = s2[(s2.strategy == "S7") & (s2.module == "none")].set_index("seed")
    s2f = s2[(s2.strategy == "S2") & (s2.topology == "full") & (s2.module == "none")].set_index("seed")
    s7c = core[(core.strategy == "S7") & (core.f == 0)].set_index("seed")
    s2c = core[(core.strategy == "S2") & (core.topology == "full") & (core.f == 0)].set_index("seed")
    out = {"S12_con_f3_12": round(att.con.mean(), 3), "S12_acc_f3_12": round(att.acc.mean(), 3),
           "S12_acc_f0": round(clean.acc.mean(), 3),
           "con_S12_minus_S7": paired(att.con, s7a.con), "con_S12_minus_S2full": paired(att.con, s2f.con),
           "acc_f0_S12_minus_S7": paired(clean.acc, s7c.acc), "acc_f0_S12_minus_S2full": paired(clean.acc, s2c.acc)}
    Path("results/s12_llm.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
