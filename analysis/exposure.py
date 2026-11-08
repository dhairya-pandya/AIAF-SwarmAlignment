"""Exploratory mechanism analysis (not pre-registered): what an honest LLM agent saw versus whether it adopted
the attackers' target. Reads the per-run JSONL logs of the Stage B core block.

For each honest turn in a social round we count the claim lines visible in its prompt, the share written by
compromised agents, and whether a visible first-hand claim from an honest agent contradicts a visible attacker
claim (same option and attribute, different value)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CLAIM = re.compile(r"\[(ag-\d+)-r\d+-\d+\] ([A-D])\.(\w+) = (\d+)")


def turns(run_ids, log_dir="logs"):
    for rid in run_ids:
        p = Path(log_dir) / f"{rid}.jsonl"
        if not p.exists():
            continue
        lines = [json.loads(x) for x in p.open()]
        h = lines[0]
        cfg = h["config"]
        disp = h["displays"]
        bad = {disp[i] for i in h["attackers"]}
        tgt = "ABCD"[h["target"]]
        for t in lines[1:]:
            if t.get("type") != "turn" or t["role"] != "honest" or t["round"] == 0:
                continue
            seen = CLAIM.findall(t["prompt"])
            att = [(o, a, v) for who, o, a, v in seen if who in bad]
            hon = {(o, a): v for who, o, a, v in seen if who not in bad}
            contra = any((o, a) in hon and hon[(o, a)] != v for o, a, v in att)
            yield {"run_id": rid, "strategy": cfg["strategy"], "topology": cfg["topology"], "f": cfg["f"],
                   "round": t["round"], "n_claims": len(seen), "att_share": len(att) / max(len(seen), 1),
                   "contradicted": contra, "chose_target": (t.get("parsed") or {}).get("choice") == tgt}


def main(core="results/stageB_core.csv", out="results/exposure.csv"):
    core = pd.read_csv(core)
    ids = core[core.strategy.isin(["S2", "S3"]) & (core.f > 0) & (core.module == "none")].run_id
    df = pd.DataFrame(turns(ids))
    df.to_csv(out, index=False)
    print(f"{len(df)} honest social turns from {df.run_id.nunique()} runs -> {out}")
    print("\nby topology:")
    print(df.groupby(["strategy", "topology"]).agg(claims=("n_claims", "mean"), att_share=("att_share", "mean"),
                                                   contradicted=("contradicted", "mean"),
                                                   adopt_target=("chose_target", "mean")).round(3).to_string())
    df["share_bin"] = pd.cut(df.att_share, [-0.01, 0, 0.1, 0.25, 0.5, 1.0])
    print("\nadoption of target by attacker share of visible claims:")
    print(df.groupby("share_bin", observed=True).chose_target.agg(["mean", "count"]).round(3).to_string())
    print("\nadoption when an attacker claim is visibly contradicted (att_share > 0):")
    print(df[df.att_share > 0].groupby("contradicted").chose_target.agg(["mean", "count"]).round(3).to_string())


if __name__ == "__main__":
    main(*sys.argv[1:])
