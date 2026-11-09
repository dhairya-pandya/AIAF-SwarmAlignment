"""Run the remaining Stage B blocks unattended, in plan order (docs/EXPERIMENT_PLAN.md P2-P5).

The best and worst Tier-1 strategies are picked by a fixed rule, written here before the core block is
analysed. The rule uses the social Tier-1 strategies (S2, S3, S4, S7, S9), ranks them by mean contamination
at f = 3/12 in the core block, and breaks ties by mean accuracy at f = 0.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run from anywhere: import hiveguard from the repo

MODEL = "openrouter:openai/gpt-oss-120b"
M5_MODELS = [MODEL, "openrouter:minimax/minimax-m3.1-flash", "openrouter:qwen/qwen3.6-35b-a3b"]
SEEDS = 6
PY = [sys.executable, "-u", "-m", "hiveguard.run", "stageB", "--models", MODEL, "--workers", "12",
      "--parallel-runs", "8"]


BUDGET_STOP = 9.3   # USD; stop before a block when the key's spend passes this (credit is $10)


def spend() -> float:
    import json
    import os
    import urllib.request
    req = urllib.request.Request("https://openrouter.ai/api/v1/credits",
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
    return float(json.load(urllib.request.urlopen(req, timeout=30))["data"]["total_usage"])


def run(block: str, out: str, *extra: str, seeds: int = SEEDS) -> None:
    used = spend()
    print(f"\n=== {block} -> {out} {' '.join(extra)} seeds={seeds} spend=${used:.2f} "
          f"[{time.strftime('%H:%M:%S')}]", flush=True)
    if used > BUDGET_STOP:
        raise SystemExit(f"budget guard: spend ${used:.2f} > ${BUDGET_STOP}; stopping before {block}")
    subprocess.run(PY + ["--block", block, "--seeds", str(seeds), "--out", out, *extra], check=True)


def best_worst(core_csv: str) -> tuple[str, str]:
    df = pd.read_csv(core_csv)
    social = df[df.strategy.isin(["S2", "S3", "S4", "S7", "S9"]) & (df.module == "none")]
    con = social[(social.f - 0.25).abs() < 1e-9].groupby("strategy")["con"].mean()
    acc = social[social.f == 0].groupby("strategy")["acc"].mean()
    rank = pd.DataFrame({"con": con, "acc": acc}).sort_values(["con", "acc"], ascending=[True, False])
    print("selection table (contamination at f=3/12, accuracy at f=0):\n" + rank.to_string(), flush=True)
    return rank.index[0], rank.index[-1]


def run_m5(best: str, worst: str) -> None:
    if spend() > BUDGET_STOP:
        raise SystemExit("budget guard before M5")
    """M5: honest agents split across three model families; compared with the single-model core runs."""
    from hiveguard.config import RunConfig
    from hiveguard.llm_runs import run_block
    print(f"\n=== M5 diversity [{time.strftime('%H:%M:%S')}]", flush=True)
    cfgs = [RunConfig(strategy=s, f=f, modules=["M5"], seed=seed, backend="llm", models=M5_MODELS)
            for s in (best, worst) for f in (0.0, 3 / 12) for seed in range(SEEDS)]
    run_block(cfgs, "results/stageB_m5.csv", ".cache/llm.sqlite", "logs", 12, 8)


def main() -> None:
    run("core", "results/stageB_core.csv")
    best, worst = best_worst("results/stageB_core.csv")
    Path("results/stageB_selection.txt").write_text(f"best={best}\nworst={worst}\n")
    print(f"best={best} worst={worst}", flush=True)
    run("modules", "results/stageB_modules.csv", "--strategies", best, worst)
    run_m5(best, worst)
    run("attacks", "results/stageB_attacks.csv", "--strategies", best)
    for f in ["results/redteam_k1.json"]:
        while not Path(f).exists():   # the ABM red-team search may still be running
            time.sleep(30)
    run("confirm", "results/stageB_confirm.csv", "--strategies", worst, best, "--redteam", "results/redteam_k1.json")
    run("tier2", "results/stageB_tier2.csv", seeds=3)   # optional block, cut to 3 seeds for budget (D20)
    print(f"\n=== all blocks done [{time.strftime('%H:%M:%S')}]", flush=True)


if __name__ == "__main__":
    main()
