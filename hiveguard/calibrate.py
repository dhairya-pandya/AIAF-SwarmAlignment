"""Calibrate the ABM's deference kappa and confidence sensitivity lambda on pilot LLM runs, then freeze
them (DESIGN §6.1, §10.1). The frozen file is what Stage A and the H6 predictions use."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .abm import ABMParams, run_abm
from .config import RunConfig

KAPPAS = np.round(np.linspace(0.05, 0.95, 19), 3)
LAMS = [0.0, 0.5, 1.0, 2.0, 3.0, 4.0]


def _abm_cells(cells: pd.DataFrame, params: ABMParams, seeds: int) -> pd.DataFrame:
    rows = []
    for _, c in cells.iterrows():
        res = [run_abm(RunConfig(strategy=c.strategy, n_agents=int(c.N), n_rounds=int(c.R), f=float(c.f),
                                 topology=c.topology, attack=c.attack, seed=s), params) for s in range(seeds)]
        rows.append({"acc_abm": np.mean([r["acc"] for r in res]), "con_abm": np.mean([r["con"] for r in res]),
                     "curve_abm": np.mean([r["con_curve"] for r in res], 0)})
    return pd.DataFrame(rows, index=cells.index)


def calibrate(pilot_csv: str, out: str, seeds: int = 30, model: str | None = None) -> dict:
    df = pd.read_csv(pilot_csv)
    if model:
        df = df[df["models"] == model]
    keys = ["strategy", "N", "R", "f", "topology", "attack"]
    cells = df.groupby(keys).agg(acc=("acc", "mean"), con=("con", "mean"),
                                 curve=("con_curve", lambda s: np.mean([json.loads(x) for x in s], 0))).reset_index()
    best = None
    for k in KAPPAS:
        for lam in LAMS:
            p = ABMParams(kappa=float(k), lam=float(lam))
            pred = _abm_cells(cells, p, seeds)
            curve_err = np.mean([np.mean((a - b) ** 2) for a, b in zip(cells["curve"], pred["curve_abm"])])
            loss = float(np.mean((cells["acc"] - pred["acc_abm"]) ** 2)
                         + np.mean((cells["con"] - pred["con_abm"]) ** 2) + curve_err)
            if best is None or loss < best[0]:
                best = (loss, p)
    loss, p = best
    d = p.to_dict()
    d.update(_calibration={"loss": loss, "pilot": pilot_csv, "model": model, "n_cells": len(cells),
                           "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(d, indent=2))
    print(f"kappa={p.kappa} lambda={p.lam} loss={loss:.4f} -> {out} (frozen)")
    return d
