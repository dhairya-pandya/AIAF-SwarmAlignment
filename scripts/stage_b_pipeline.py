"""Run the remaining Stage B blocks unattended, in plan order (EXPERIMENT_PLAN.md P2-P5).

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

MODEL = "openrouter:openai/gpt-oss-120b"
SEEDS = 6
PY = [sys.executable, "-u", "-m", "hiveguard.run", "stageB", "--models", MODEL, "--workers", "12",
      "--parallel-runs", "8"]


def run(block: str, out: str, *extra: str) -> None:
    print(f"\n=== {block} -> {out} {' '.join(extra)} [{time.strftime('%H:%M:%S')}]", flush=True)
    subprocess.run(PY + ["--block", block, "--seeds", str(SEEDS), "--out", out, *extra], check=True)


def best_worst(core_csv: str) -> tuple[str, str]:
    df = pd.read_csv(core_csv)
    social = df[df.strategy.isin(["S2", "S3", "S4", "S7", "S9"]) & (df.module == "none")]
    con = social[(social.f - 0.25).abs() < 1e-9].groupby("strategy")["con"].mean()
    acc = social[social.f == 0].groupby("strategy")["acc"].mean()
    rank = pd.DataFrame({"con": con, "acc": acc}).sort_values(["con", "acc"], ascending=[True, False])
    print("selection table (contamination at f=3/12, accuracy at f=0):\n" + rank.to_string(), flush=True)
    return rank.index[0], rank.index[-1]


def main() -> None:
    run("core", "results/stageB_core.csv")
    best, worst = best_worst("results/stageB_core.csv")
    Path("results/stageB_selection.txt").write_text(f"best={best}\nworst={worst}\n")
    print(f"best={best} worst={worst}", flush=True)
    run("modules", "results/stageB_modules.csv", "--strategies", best, worst)
    run("attacks", "results/stageB_attacks.csv", "--strategies", best)
    for f in ["results/redteam_k1.json"]:
        while not Path(f).exists():   # the ABM red-team search may still be running
            time.sleep(30)
    run("confirm", "results/stageB_confirm.csv", "--strategies", worst, best, "--redteam", "results/redteam_k1.json")
    run("tier2", "results/stageB_tier2.csv")
    print(f"\n=== all blocks done [{time.strftime('%H:%M:%S')}]", flush=True)


if __name__ == "__main__":
    main()
