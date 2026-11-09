"""Replay every logged Stage B and pilot run from the committed cache and record whether each log is
byte-identical. Writes results/replay_check.csv."""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hiveguard.env import replay  # noqa: E402


def check(rid: str) -> tuple[str, str]:
    try:
        return rid, "identical" if replay(rid) else "differs"
    except Exception as e:  # cache miss or missing log
        return rid, f"error: {type(e).__name__}"


def main() -> None:
    files = sorted(Path("results").glob("stageB_*.csv")) + [Path(p) for p in ("results/pilot.csv", "results/confirmation.csv", "results/s12_llm.csv")]
    ids = sorted({r for f in files for r in pd.read_csv(f).run_id})
    with ProcessPoolExecutor(8) as ex:
        rows = list(ex.map(check, ids))
    df = pd.DataFrame(rows, columns=["run_id", "replay"])
    df.to_csv("results/replay_check.csv", index=False)
    print(df.replay.value_counts().to_string())


if __name__ == "__main__":
    main()
