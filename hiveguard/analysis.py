"""Analysis: per-cell summaries, tipping points, module effects, red-team comparison, hypothesis verdicts
(DESIGN §4, §11) and report figures (§12.1). Missing inputs are skipped and reported as "not run"."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .config import EXPLORATORY
from .metrics import bootstrap_ci, bootstrap_p, holm, paired_diff_ci, tipping_ci

NON_SOCIAL = ["S0a", "S0b", "S1"]
T1_SOCIAL = ["S2", "S3", "S4", "S7", "S9"]
H1_STRATS = {"ABM": ["S2", "S3", "S6", "S8"], "LLM": ["S2", "S3"]}   # DEVIATIONS D8
DENSE = ["star", "full"]
F_LLM = (1 / 12, 3 / 12)
EPS = 0.01
COMP_COLS = ["direct", "medium", "memory", "hierarchy", "decay", "roles", "negfb", "quorum"]
COMPONENTS = {  # DESIGN §6.3
    "S1": "00000000", "S2": "10000000", "S3": "10100000", "S4": "01000010", "S5": "01100110",
    "S6": "10001000", "S7": "10010100", "S8": "10000010", "S9": "01000111", "S10": "01000110",
    "S11": "10100010",   # S11 is exploratory (D22): direct msgs, memory (trust), negative feedback (trust decay)
    "S12": "10110100"}   # S12 is exploratory (D24): S7's row plus memory (corroboration record)
FAMILY = {"S4": "insects", "S5": "insects", "S9": "insects", "S10": "insects", "S7": "wolves",
          "S6": "fireflies", "S8": "birds", "S1": "abstract", "S2": "abstract", "S3": "abstract",
          "S11": "mammals", "S12": "mammals"}
HYP = {
    "H0": "Free debate (S2) is no better than compute-matched majority (S1) when f>0",
    "H1": "Dense topologies (star, full) spread contamination more and faster than ring",
    "H2": "Contamination vs f shows a sharp tipping point",
    "H3": "Quorum on first-hand evidence (M3) gives the best value of all modules",
    "H4": "Stop signals (M2) reduce deadlock and contamination",
    "H5": "Uninformed dilution (M4) helps LLM swarms less than ABM swarms",
    "H6": "The ABM gets the topology ranking right but underestimates LLM contamination",
    "H7": "Optimizing searchers find worse attacks than naive ones",
    "H8": "GWO hierarchy (S7) converges fastest at f=0 but is most fragile to leader capture (A5)",
    "H9": "Stigmergy with evaporation (S4) and honeybee (S9) are the most robust Tier-1 strategies",
    "H10": "Results group by component, not metaphor",
}
ABM_KEYS = ["strategy", "module", "topology", "N", "f_eff", "attack"]
LLM_KEYS = ["strategy", "module", "topology", "N", "R", "f_eff", "attack", "onset", "placement", "models"]
ON = ["strategy", "topology", "N", "f_eff", "attack", "seed"]


# ---------------------------------------------------------------- helpers

def _r(x, d: int = 4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(x) else round(x, d)


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return _r(o, 6)
    return o


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _map(fn, jobs: list, workers: int | None):
    if not jobs:
        return []
    if (workers or 1) <= 1 or len(jobs) < 50:
        return [fn(j) for j in jobs]
    with ProcessPoolExecutor(workers) as ex:
        return list(ex.map(fn, jobs, chunksize=max(1, len(jobs) // (4 * workers))))


def _ci(x, n: int) -> dict:
    m, lo, hi = bootstrap_ci(x, n=n)
    return {"mean": _r(m), "lo": _r(lo), "hi": _r(hi), "n": int(np.sum(~np.isnan(np.asarray(x, float))))}


def near_f(df: pd.DataFrame, target: float, max_dist: float = 0.1) -> tuple[pd.DataFrame, dict]:
    """Rows at the f_eff nearest to `target`, per N. On an exact tie both neighbours are kept, so a per-seed
    mean is the linear interpolation at the midpoint."""
    parts, used = [], {}
    for N, g in df.groupby("N"):
        fs = np.unique(g["f_eff"].to_numpy(float))
        d = np.abs(fs - target)
        if not len(fs) or d.min() > max_dist:
            continue
        pick = fs[d <= d.min() + 1e-9]
        used[int(N)] = [_r(x) for x in pick]
        parts.append(g[g["f_eff"].isin(pick)])
    return (pd.concat(parts) if parts else df.iloc[:0]), used


def paired(a: pd.DataFrame, b: pd.DataFrame, metric: str, n: int, on=ON) -> dict | None:
    """Paired effect mean(a - b): rows matched on `on`, averaged per seed (the unit of analysis)."""
    on = [c for c in on if c in a.columns and c in b.columns]
    m = a[on + [metric]].merge(b[on + [metric]], on=on, suffixes=("_a", "_b")).dropna(subset=[f"{metric}_a", f"{metric}_b"])
    if m.empty:
        return None
    g = m.groupby("seed")[[f"{metric}_a", f"{metric}_b"]].mean()
    x, y = g.iloc[:, 0].to_numpy(float), g.iloc[:, 1].to_numpy(float)
    d, lo, hi = paired_diff_ci(x, y, n=n)
    return {"diff": _r(d), "lo": _r(lo), "hi": _r(hi), "p": _r(bootstrap_p(x - y, n=n), 5),
            "n_seeds": len(g), "n_pairs": len(m), "_x": x, "_y": y, "_seeds": g.index.to_numpy()}


def _pub(d: dict | None) -> dict | None:
    return None if d is None else {k: v for k, v in d.items() if not k.startswith("_")}


def holm_adjusted(p: dict[str, float]) -> dict[str, float]:
    items = sorted(p.items(), key=lambda kv: kv[1])
    out, run = {}, 0.0
    for i, (k, v) in enumerate(items):
        run = max(run, min(1.0, (len(items) - i) * v))
        out[k] = run
    return out


def mantel(A: np.ndarray, B: np.ndarray, perms: int = 9999, seed: int = 0) -> tuple[float, float]:
    """One-sided permutation Mantel test (Pearson r of upper triangles; rows/cols of A permuted)."""
    iu = np.triu_indices_from(A, 1)
    b = B[iu]
    if np.std(A[iu]) == 0 or np.std(b) == 0:
        return float("nan"), float("nan")
    r = np.corrcoef(A[iu], b)[0, 1]
    rng = np.random.default_rng(seed)
    hits = sum(np.corrcoef(A[np.ix_(p, p)][iu], b)[0, 1] >= r - 1e-12
               for p in (rng.permutation(len(A)) for _ in range(perms)))
    return float(r), (hits + 1) / (perms + 1)


def component_distance(strats: list[str]) -> np.ndarray:
    X = np.array([[int(c) for c in COMPONENTS[s]] for s in strats])
    return (X[:, None, :] != X[None, :, :]).mean(2)


def metaphor_distance(strats: list[str]) -> np.ndarray:
    f = np.array([FAMILY[s] for s in strats])
    return (f[:, None] != f[None, :]).astype(float)


def confirmatory(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Drop exploratory strategies (config.EXPLORATORY, DEVIATIONS D22) before any confirmatory test."""
    if df is None or "strategy" not in df:
        return df
    return df[~df["strategy"].isin(EXPLORATORY)]


# ---------------------------------------------------------------- loading

def load_stage_a(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["module"] = df["module"].fillna("none")
    df = df.drop_duplicates(["strategy", "module", "topology", "N", "f_eff", "attack", "seed"])
    df["R"] = df["con_curve"].map(lambda s: len(json.loads(s)))
    for c in ("deadlock", "group_correct"):
        df[c] = df[c].astype(float)
    return df.reset_index(drop=True)


def load_llm(paths) -> pd.DataFrame | None:
    frames = [pd.read_csv(p) for p in paths]
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    df["module"] = df["module"].fillna("none")
    df = df.drop_duplicates("run_id") if "run_id" in df else df
    for c in ("deadlock", "group_correct"):
        df[c] = df[c].astype(float)
    return df.reset_index(drop=True)


def primary_model(llm: pd.DataFrame) -> str:
    return llm[llm["module"] == "none"]["models"].value_counts().index[0]


def llm_main(llm: pd.DataFrame) -> pd.DataFrame:
    """Rows of the primary model (plus M5 rows, which use several models), N=12."""
    pm = primary_model(llm)
    keep = (llm["models"] == pm) | llm["module"].str.contains("M5")
    return llm[keep & (llm["N"] == 12)]


def base_rows(df: pd.DataFrame) -> pd.DataFrame:
    """module none, attack A2, random placement: the core grid."""
    m = (df["module"] == "none") & (df["attack"] == "A2")
    if "placement" in df:
        m &= df["placement"] == "random"
    return df[m]


# ---------------------------------------------------------------- summaries

def _cell_job(args):
    key, acc, con, dead, t50, b = args
    a, c = bootstrap_ci(acc, n=b), bootstrap_ci(con, n=b)
    t = np.asarray(t50, float)
    return list(key) + [len(acc)] + [_r(v) for v in a + c] + [_r(np.mean(dead)),
                                                             _r(np.nanmean(t)) if np.isfinite(t).any() else None]


def cell_summaries(df: pd.DataFrame, keys: list[str], boot: int, workers: int | None) -> dict:
    keys = [k for k in keys if k in df.columns]
    jobs = [(tuple(_clean(list(k if isinstance(k, tuple) else (k,)))), g["acc"].to_numpy(float),
             g["con"].to_numpy(float), g["deadlock"].to_numpy(float), g["t50"].to_numpy(float), boot)
            for k, g in df.groupby(keys, sort=True)]
    cols = keys + ["n", "acc", "acc_lo", "acc_hi", "con", "con_lo", "con_hi", "deadlock", "t50"]
    return {"columns": cols, "rows": _map(_cell_job, jobs, workers)}


def _tip_job(args):
    key, sub, n = args
    fmax = float(sub["f_eff"].max())
    if sub["con"].max() <= 0:
        return dict(zip(("strategy", "topology", "N"), key), f_star=None, width=None, lo=None, hi=None,
                    f_max=fmax, in_range=False, note="no contamination at any f")
    t = tipping_ci(sub, n=n)
    return dict(zip(("strategy", "topology", "N"), key), **{k: _r(v) for k, v in t.items()}, f_max=_r(fmax),
                in_range=bool(np.isfinite(t["f_star"]) and 0 <= t["f_star"] <= fmax))


def tipping_table(df: pd.DataFrame, n: int, workers: int | None) -> list[dict]:
    b = base_rows(df)
    b = b[b["strategy"] != "S0a"]
    jobs = [(tuple(_clean(list(k))), g[["f_eff", "con", "seed"]].reset_index(drop=True), n)
            for k, g in b.groupby(["strategy", "topology", "N"]) if g["f_eff"].nunique() >= 3]
    return _map(_tip_job, jobs, workers)


def _tip(tips: list[dict], strategy: str, topology: str = "full", N: int = 12) -> dict | None:
    return next((t for t in tips if t["strategy"] == strategy and t["topology"] == topology and t["N"] == N), None)


def module_effects(df: pd.DataFrame, n: int) -> dict:
    """Paired by seed vs module=none, pooled over social strategies, topologies, N and f>0. Δcon = module − none
    (negative = module reduces contamination); usefulness = Acc(f=0, module) − Acc(f=0, none) (DESIGN §11)."""
    d = df[(df["attack"] == "A2") & ~df["strategy"].isin(NON_SOCIAL)]
    if "placement" in d:
        d = d[d["placement"] == "random"]
    none = d[d["module"] == "none"]
    out = {}
    for m in sorted(set(d["module"]) - {"none"}):
        mod = d[d["module"] == m]
        row = {"overall": {}, "by_strategy": {}}
        for scope, sel in [("overall", None)] + [(s, s) for s in sorted(set(mod["strategy"]))]:
            a = mod if sel is None else mod[mod["strategy"] == sel]
            b = none if sel is None else none[none["strategy"] == sel]
            res = {"d_con": paired(a[a.f_eff > 0], b[b.f_eff > 0], "con", n),
                   "d_deadlock": paired(a[a.f_eff > 0], b[b.f_eff > 0], "deadlock", n),
                   "usefulness": paired(a[a.f_eff == 0], b[b.f_eff == 0], "acc", n)}
            if scope == "overall":
                row["overall"] = res
            else:
                row["by_strategy"][scope] = {k: _pub(v) for k, v in res.items()}
        out[m] = row
    return out


def _value(dcon, cost):
    return -dcon / (max(0.0, -cost) + EPS)


def module_values(effects: dict, n_boot: int = 2000, seed: int = 0) -> dict:
    """Value = contamination reduction / (usefulness loss + ε), with P(rank 1) over seed resamples."""
    ok = {m: e["overall"] for m, e in effects.items() if e["overall"]["d_con"] and e["overall"]["usefulness"]}
    if not ok:
        return {}
    seeds = sorted(set.intersection(*[set(e["d_con"]["_seeds"]) & set(e["usefulness"]["_seeds"]) for e in ok.values()]))
    arr = {}
    for m, e in ok.items():
        c = pd.Series(e["d_con"]["_x"] - e["d_con"]["_y"], index=e["d_con"]["_seeds"]).reindex(seeds).to_numpy()
        u = pd.Series(e["usefulness"]["_x"] - e["usefulness"]["_y"], index=e["usefulness"]["_seeds"]).reindex(seeds).to_numpy()
        arr[m] = (c, u)
    names = list(arr)
    point = {m: _value(np.mean(c), np.mean(u)) for m, (c, u) in arr.items()}
    first = dict.fromkeys(names, 0)
    rng = np.random.default_rng(seed)
    if seeds:
        for _ in range(n_boot):
            idx = rng.integers(0, len(seeds), len(seeds))
            v = {m: _value(c[idx].mean(), u[idx].mean()) for m, (c, u) in arr.items()}
            first[max(v, key=v.get)] += 1
    rank = sorted(names, key=lambda m: -point[m])
    return {m: {"value": _r(point[m]), "rank": rank.index(m) + 1, "p_first": _r(first[m] / max(1, n_boot)),
                "n_seeds": len(seeds)} for m in names}


def redteam_table(rt: list[dict], n: int) -> tuple[pd.DataFrame, dict]:
    rows = []
    for r in rt:
        c = r.get("curve") or [r["best"]]
        rows.append({"strategy": r.get("strategy"), "topology": r.get("topology"), "k": r.get("k"),
                     "searcher": r["searcher"], "rep": r.get("seed", 0), "evals": len(c),
                     "best500": c[min(499, len(c) - 1)]})
    df = pd.DataFrame(rows)
    out = {}
    for prob, g in df.groupby(["strategy", "topology", "k"]):
        key = "/".join(map(str, prob))
        out[key] = {}
        rnd = g[g.searcher == "random"].set_index("rep")["best500"]
        for s, h in g.groupby("searcher"):
            x = h["best500"].to_numpy(float)
            e = {"best500": _ci(x, n), "median": _r(np.median(x)), "q25": _r(np.quantile(x, .25)),
                 "q75": _r(np.quantile(x, .75)), "evals": int(h["evals"].max())}
            if s != "random" and len(rnd):
                h2 = h.set_index("rep")["best500"]
                common = h2.index.intersection(rnd.index)
                if len(common):
                    d, lo, hi = paired_diff_ci(h2[common], rnd[common], n=n)
                    e["vs_random"] = {"diff": _r(d), "lo": _r(lo), "hi": _r(hi)}
            out[key][s] = e
    return df, out


# ---------------------------------------------------------------- hypotheses

def _h(hid: str, source: str, test: str, verdict: str = "not run", stat=None, ci=None, p=None, note: str = "",
       holm_family: bool = True) -> dict:
    return {"id": hid, "statement": HYP[hid], "source": source, "test": test, "statistic": stat, "ci": ci,
            "p": _r(p, 5), "p_holm": None, "holm_reject": None, "verdict": verdict, "note": note,
            "_holm": holm_family and p is not None and verdict != "not run"}


def h0(src: str, base: pd.DataFrame, n: int) -> dict:
    test = "paired bootstrap of Acc(S2) − Acc(S1) by seed at f=1/12 and 3/12 (N=12, full)"
    d = base[(base["N"] == 12) & (base["topology"] == "full")]
    res = {}
    for t in F_LLM:
        a, used = near_f(d[d.strategy == "S2"], t)
        b, _ = near_f(d[d.strategy == "S1"], t)
        p = paired(a, b, "acc", n, on=[c for c in ON if c != "strategy"])
        if p:
            res[f"{t:.4f}"] = dict(_pub(p), f_used=used.get(12))
    if not res:
        return _h("H0", src, test, note="needs S1 and S2 at N=12, full, f>0", holm_family=False)
    ok = all(v["lo"] is not None and v["lo"] <= 0 for v in res.values())
    note = "" if len(res) == 2 else "only one f level available"
    return _h("H0", src, test, "supported" if ok else "not supported", stat=res, p=min(v["p"] for v in res.values()),
              note=note + " Supported if CI includes 0 or is below 0 at every f.", holm_family=False)


def h1(src: str, base: pd.DataFrame, n: int) -> dict:
    strats = H1_STRATS[src]
    test = ("per strategy: paired bootstrap of Con(dense) − Con(ring) and T50(ring) − T50(dense), dense ∈ {star, full}, "
            "f>0, pooled over N; count strategies with Con CI > 0")
    d = base[base.f_eff > 0]
    per = {}
    for s in strats:
        g = d[d.strategy == s]
        ring = g[g.topology == "ring"]
        dense = g[g.topology.isin(DENSE)]
        if ring.empty or dense.empty:
            continue
        on = [c for c in ON if c != "topology"]
        per[s] = {"con": _pub(paired(dense, ring, "con", n, on)), "t50": _pub(paired(ring, dense, "t50", n, on)),
                  "dense": sorted(set(dense.topology))}
    if not per:
        return _h("H1", src, test, note="needs ring and star/full runs of " + ",".join(strats))
    k = len(per)
    need = math.ceil(5 / 7 * k)
    sig = sum(1 for v in per.values() if v["con"] and v["con"]["lo"] > 0)
    pos = sum(1 for v in per.values() if v["con"] and v["con"]["diff"] > 0)
    ps = sorted(v["con"]["p"] if v["con"] else 1.0 for v in per.values())
    verdict = "supported" if sig >= need else ("not supported" if pos < need else "inconclusive")
    return _h("H1", src, test, verdict, stat={"per_strategy": per, "n_sig": sig, "n": k, "share": _r(sig / k),
                                              "need": need}, p=ps[need - 1],
              note=f"D8: evaluated on {','.join(per)}; threshold ≥5/7 share. p = per-strategy p ranked {need} of {k}.")


def h2(src: str, tips: list[dict]) -> dict:
    if src == "ABM":
        test = "logistic fit of Con(f) per strategy×topology at N=200 (social strategies); 10–90% width"
        cells = [t for t in tips if t["N"] == 200 and t["strategy"] not in NON_SOCIAL]
        if not cells:
            return _h("H2", src, test, note="no N=200 ABM runs", holm_family=False)
        sharp = [t for t in cells if t["in_range"] and t["width"] is not None and t["width"] <= 0.15]
        share = len(sharp) / len(cells)
        return _h("H2", src, test, "supported" if share > 0.5 else "not supported",
                  stat={"n_cells": len(cells), "n_sharp": len(sharp), "share_sharp": _r(share),
                        "median_width": _r(np.nanmedian([t["width"] or np.nan for t in cells]))},
                  note="Sharp = f* inside the f grid and width ≤ 0.15; supported if >50% of cells are sharp. "
                       "Descriptive (no p), so outside the Holm family.", holm_family=False)
    test = "logistic fit of Con(f) per strategy (full topology); f* vs the 0.10–0.25 band"
    cells = [t for t in tips if t["strategy"] not in NON_SOCIAL and t["topology"] == "full"]
    if not cells:
        return _h("H2", src, test, note="needs LLM runs at ≥3 f levels", holm_family=False)
    inb = [t for t in cells if t["f_star"] is not None and 0.10 <= t["f_star"] <= 0.25]
    return _h("H2", src, test, "supported" if len(inb) > len(cells) / 2 else "not supported",
              stat={t["strategy"]: {"f_star": t["f_star"], "lo": t["lo"], "hi": t["hi"]} for t in cells} |
              {"n_in_band": len(inb), "n": len(cells)},
              note="DESIGN only asks to report f* against the band; verdict = majority of point f* inside it. "
                   "Only 3 f levels, so fits are weak.", holm_family=False)


def h3(src: str, values: dict) -> dict:
    test = "value = −ΔCon / (usefulness loss at f=0 + 0.01) per module; P(M3 ranks 1) over seed resamples"
    if "M3" not in values or len(values) < 2:
        return _h("H3", src, test, note="needs M3 and at least one other module with f=0 and f>0 runs")
    v = values["M3"]
    p = max(1e-4, 1 - v["p_first"])
    verdict = "supported" if v["rank"] == 1 and v["p_first"] >= 0.95 else ("inconclusive" if v["rank"] == 1 else "not supported")
    return _h("H3", src, test, verdict, stat=values, p=p,
              note=f"{len(values)} modules compared (DESIGN: 6). p = 1 − P(M3 first).")


def h4(src: str, df: pd.DataFrame, n: int) -> dict:
    test = "paired bootstrap of none − M2 (contamination and deadlock) at f=3/12, pooled over social strategies"
    d = df[(df.attack == "A2") & ~df.strategy.isin(NON_SOCIAL)]
    if "placement" in d:
        d = d[d.placement == "random"]
    a, used = near_f(d[d.module == "none"], 3 / 12)
    b, _ = near_f(d[d.module == "M2"], 3 / 12)
    c, dl = paired(a, b, "con", n), paired(a, b, "deadlock", n)
    if not c or not dl:
        return _h("H4", src, test, note="needs M2 and none at f≈3/12")
    both = c["lo"] > 0 and dl["lo"] > 0
    verdict = "supported" if both else ("not supported" if c["diff"] <= 0 or dl["diff"] <= 0 else "inconclusive")
    return _h("H4", src, test, verdict, stat={"con_reduction": _pub(c), "deadlock_reduction": _pub(dl), "f_used": used},
              p=max(c["p"], dl["p"]), note="p = max of the two (intersection-union).")


def _rel_red(none: pd.DataFrame, mod: pd.DataFrame, n: int, rng) -> tuple[float, np.ndarray] | None:
    p = paired(none, mod, "con", 10)
    if not p or p["_x"].mean() <= 0:
        return None
    x, y = p["_x"], p["_y"]
    boots = []
    for _ in range(n):
        i = rng.integers(0, len(x), len(x))
        boots.append((x[i].mean() - y[i].mean()) / x[i].mean() if x[i].mean() > 0 else np.nan)
    return (x.mean() - y.mean()) / x.mean(), np.array(boots)


def h5(abm: pd.DataFrame | None, llm: pd.DataFrame | None, calibrated: bool, n: int) -> dict:
    test = "relative contamination reduction from M4, (none − M4)/none at f=3/12, full, N=12; LLM − ABM, independent bootstrap"
    if abm is None or llm is None or "M4" not in set(llm.module) or "M4" not in set(abm.module):
        return _h("H5", "ABM vs LLM", test, note="needs M4 and none runs in both ABM and LLM")
    strats = sorted(set(llm[llm.module == "M4"].strategy))
    rng = np.random.default_rng(0)
    rr = {}
    for name, df in (("LLM", llm), ("ABM", abm)):
        d = df[(df.attack == "A2") & df.strategy.isin(strats) & (df.topology == "full") & (df.N == 12)]
        a, _ = near_f(d[d.module == "none"], 3 / 12)
        b, _ = near_f(d[d.module == "M4"], 3 / 12)
        rr[name] = _rel_red(a, b, n, rng)
    if not all(rr.values()):
        return _h("H5", "ABM vs LLM", test, note="no contamination without M4, or no paired runs")
    diff = rr["LLM"][1] - rr["ABM"][1]
    diff = diff[np.isfinite(diff)]
    lo, hi = np.quantile(diff, [0.025, 0.975])
    p = min(1.0, 2 * min((diff >= 0).mean(), (diff <= 0).mean()) + 1 / n)
    d0 = rr["LLM"][0] - rr["ABM"][0]
    verdict = "supported" if hi < 0 else ("not supported" if d0 >= 0 else "inconclusive")
    note = f"strategies {','.join(strats)}."
    if not calibrated:
        verdict, note = ("inconclusive" if verdict != "not supported" else verdict), note + " ABM NOT calibrated (no _calibration in params)."
    return _h("H5", "ABM vs LLM", test, verdict,
              stat={"rel_red_llm": _r(rr["LLM"][0]), "rel_red_abm": _r(rr["ABM"][0]), "diff": _r(d0)},
              ci=[_r(lo), _r(hi)], p=p, note=note)


def matched_cells(abm: pd.DataFrame, llm: pd.DataFrame) -> pd.DataFrame:
    """LLM core cells (none, A2, random, N=12, f>0) with the ABM mean at the same strategy, topology and f
    (nearest f_eff; midpoint interpolation on ties)."""
    a, l = base_rows(abm), base_rows(llm)
    a, l = a[a.N == 12], l[(l.N == 12) & (l.f_eff > 0)]
    rows = []
    for (s, t, f), g in l.groupby(["strategy", "topology", "f_eff"]):
        sub, used = near_f(a[(a.strategy == s) & (a.topology == t)], f, max_dist=0.09)
        if sub.empty:
            continue
        rows.append({"strategy": s, "topology": t, "f_eff": f, "f_abm": used.get(12), "con_llm": g.con.mean(),
                     "con_abm": sub.groupby("seed").con.mean().mean(), "n_llm": len(g)})
    return pd.DataFrame(rows)


def h6(cells: pd.DataFrame | None, calibrated: bool, n: int) -> dict:
    test = "Spearman ρ of ABM vs LLM contamination ranks over matched strategy×topology cells; mean signed error ABM−LLM"
    if cells is None or len(cells) < 3:
        return _h("H6", "ABM vs LLM", test, note="needs ≥3 matched ABM/LLM cells")
    topo = cells.groupby("topology")[["con_abm", "con_llm"]].mean()
    if len(topo) >= 3:
        rho, unit = spearmanr(topo.con_abm, topo.con_llm)[0], "topology"
    else:
        st = cells.groupby(["strategy", "topology"])[["con_abm", "con_llm"]].mean()
        rho, unit = spearmanr(st.con_abm, st.con_llm)[0], "strategy×topology"
    err = (cells.con_abm - cells.con_llm).to_numpy(float)
    e = _ci(err, n)
    p = bootstrap_p(err, n=n)
    if not np.isfinite(rho):
        verdict = "inconclusive"
    elif rho >= 0.8 and e["hi"] is not None and e["hi"] < 0:
        verdict = "supported"
    elif rho < 0.8 or e["mean"] >= 0:
        verdict = "not supported"
    else:
        verdict = "inconclusive"
    note = f"ranking unit: {unit} (LLM topologies: {sorted(set(cells.topology))}); error CI over cells."
    if not calibrated:
        verdict, note = ("inconclusive" if verdict != "not supported" else verdict), note + " ABM NOT calibrated."
    return _h("H6", "ABM vs LLM", test, verdict, stat={"rho": _r(rho), "signed_error": e, "n_cells": len(cells)},
              ci=[e["lo"], e["hi"]], p=p, note=note)


def h7_abm(rt: pd.DataFrame | None, n: int) -> dict:
    test = "best contamination at 500 evals, paired by (problem, repeat): best of {GA, MAP-Elites} − hub and hub − random"
    if rt is None or not {"random", "hub"} <= set(rt.searcher) or not {"ga", "map_elites"} & set(rt.searcher):
        return _h("H7", "ABM", test, note="needs red-team results for random, hub and GA/MAP-Elites")
    opt = max((s for s in ("ga", "map_elites") if s in set(rt.searcher)), key=lambda s: rt[rt.searcher == s].best500.mean())
    w = rt.pivot_table(index=["strategy", "topology", "k", "rep"], columns="searcher", values="best500").dropna()
    a = w[opt].to_numpy() - w["hub"].to_numpy()
    b = w["hub"].to_numpy() - w["random"].to_numpy()
    ca, cb = bootstrap_ci(a, n=n), bootstrap_ci(b, n=n)
    both = ca[1] > 0 and cb[1] > 0
    verdict = "supported" if both else ("not supported" if ca[0] <= 0 or cb[0] <= 0 else "inconclusive")
    return _h("H7", "ABM", test, verdict,
              stat={"optimizer": opt, "opt_minus_hub": [_r(x) for x in ca], "hub_minus_random": [_r(x) for x in cb],
                    "n_pairs": len(w), "budget_used": int(rt.evals.max())},
              p=max(bootstrap_p(a, n=n), bootstrap_p(b, n=n)), note="statistic = [mean, lo, hi]; p = max of the two.")


def h7_llm(raw: list[dict] | None, llm: pd.DataFrame | None, n: int) -> dict:
    test = "LLM confirm block: Con of the optimizer's top-1 attack − Con of random's top-1, paired by strategy and seed"
    if not raw or llm is None or "placement" not in llm or not (llm.placement == "explicit").any():
        return _h("H7", "LLM", test, note="needs red-team JSON and the Stage B confirm block")
    best = {}
    for r in raw:
        if r["searcher"] not in best or r["best"] > best[r["searcher"]]["best"]:
            best[r["searcher"]] = r
    key = lambda r: (r["topology"], int(r["best_genome"]["onset"]), r["best_genome"]["attack"])
    keys = {s: key(r) for s, r in best.items()}
    conf = llm[llm.placement == "explicit"]
    if "random" not in keys or not {"ga", "map_elites"} & set(keys):
        return _h("H7", "LLM", test, note="red-team JSON lacks random or GA/MAP-Elites")
    opt = max((s for s in ("ga", "map_elites") if s in keys), key=lambda s: best[s]["best"])
    if keys[opt] == keys["random"]:
        return _h("H7", "LLM", test, "inconclusive", note="optimizer and random top attacks share (topology, onset, attack); "
                  "confirm rows cannot be told apart (attacker nodes are not in the CSV)")
    sel = lambda k: conf[(conf.topology == k[0]) & (conf.onset == k[1]) & (conf.attack == k[2])]
    p = paired(sel(keys[opt]), sel(keys["random"]), "con", n, on=["strategy", "seed"])
    if not p:
        return _h("H7", "LLM", test, note="confirm rows for the top attacks are missing")
    dup = [s for s in keys if s not in (opt, "random") and keys[s] in (keys[opt], keys["random"])]
    verdict = "supported" if p["lo"] > 0 else ("not supported" if p["diff"] <= 0 else "inconclusive")
    return _h("H7", "LLM", test, verdict, stat={"optimizer": opt, **_pub(p)}, ci=[p["lo"], p["hi"]], p=p["p"],
              note=("rows shared with " + ",".join(dup)) if dup else "")


def h8(src: str, df: pd.DataFrame, n: int) -> dict:
    test = "S7 vs runner-up: consensus time at f=0 (never → R), paired by seed; Con under A5 among Tier-1 social"
    d = df[(df.module == "none") & df.strategy.isin(T1_SOCIAL) & (df.N == 12)]
    z = d[(d.attack == "A2") & (d.f_eff == 0) & (d.topology == "full")].copy()
    if "placement" in z:
        z = z[z.placement == "random"]
    stat, ps = {}, []
    if "S7" in set(z.strategy) and z.strategy.nunique() >= 2:
        z["ct"] = z.consensus_time.fillna(z.R)
        means = z.groupby("strategy").ct.mean()
        other = means.drop("S7").idxmin()
        p1 = paired(z[z.strategy == "S7"], z[z.strategy == other], "ct", n, on=["seed"])
        stat["consensus"] = {"means": {k: _r(v) for k, v in means.items()}, "S7_lowest": bool(means.idxmin() == "S7"),
                             "vs": other, **(_pub(p1) or {})}
        ps.append(p1["p"] if p1 else 1.0)
    a5 = d[(d.attack == "A5") & (d.f_eff > 0)]
    if "S7" in set(a5.strategy) and a5.strategy.nunique() >= 2:
        means = a5.groupby("strategy").con.mean()
        other = means.drop("S7").idxmax()
        p2 = paired(a5[a5.strategy == "S7"], a5[a5.strategy == other], "con", n, on=["f_eff", "seed"])
        stat["a5"] = {"means": {k: _r(v) for k, v in means.items()}, "S7_highest": bool(means.idxmax() == "S7"),
                      "vs": other, **(_pub(p2) or {})}
        ps.append(p2["p"] if p2 else 1.0)
    if len(stat) < 2:
        return _h("H8", src, test, stat=stat or None,
                  note="A5 contamination for S7 and ≥1 other Tier-1 strategy is missing" if "consensus" in stat
                  else "needs Tier-1 runs at f=0 and under A5")
    c, a = stat["consensus"], stat["a5"]
    sig = (c.get("hi") is not None and c["hi"] < 0) and (a.get("lo") is not None and a["lo"] > 0)
    point = c["S7_lowest"] and a["S7_highest"]
    return _h("H8", src, test, "supported" if point and sig else ("inconclusive" if point else "not supported"),
              stat=stat, p=max(ps), note="Tier-1 social = S2,S3,S4,S7,S9 (baselines excluded).")


def h9(src: str, tips: list[dict]) -> dict:
    test = "rank Tier-1 social strategies by f* (N=12, full); S4 and S9 must be the top 2"
    cells = {t["strategy"]: t for t in tips if t["strategy"] in T1_SOCIAL and t["topology"] == "full" and t["N"] == 12
             and t["f_star"] is not None}
    if not {"S4", "S9"} <= set(cells) or len(cells) < 3:
        return _h("H9", src, test, note="needs f* for S4, S9 and ≥1 other Tier-1 strategy", holm_family=False)
    rank = sorted(cells, key=lambda s: -cells[s]["f_star"])
    top2 = set(rank[:2]) == {"S4", "S9"}
    third = cells[rank[2]]
    sep = top2 and min(cells["S4"]["lo"] or -1, cells["S9"]["lo"] or -1) > (third["hi"] or 9)
    return _h("H9", src, test, "supported" if sep else ("inconclusive" if top2 else "not supported"),
              stat={"ranking": rank, "f_star": {s: [cells[s]["f_star"], cells[s]["lo"], cells[s]["hi"]] for s in rank}},
              note="Rank criterion (no p; outside Holm). Supported needs S4/S9 CIs above the 3rd-ranked CI; "
                   "inconclusive if top-2 by point estimate only.", holm_family=False)


def profiles(base: pd.DataFrame) -> pd.DataFrame:
    """Vulnerability profile per strategy: mean Con in every (topology, N, f>0) cell all strategies share."""
    d = base[(base.f_eff > 0) & base.strategy.isin(set(COMPONENTS) - EXPLORATORY)]
    return d.pivot_table(index="strategy", columns=["topology", "N", "f_eff"], values="con", aggfunc="mean").dropna(axis=1)


def h10(src: str, base: pd.DataFrame, perms: int) -> tuple[dict, dict | None]:
    test = f"Mantel test ({perms} permutations, one-sided Pearson) of result distance vs component distance (§6.3) and vs metaphor family"
    P = profiles(base)
    if len(P) < 4 or P.shape[1] == 0:
        return _h("H10", src, test, note="needs ≥4 of S1–S10 with shared cells"), None
    strats = list(P.index)
    X = P.to_numpy(float)
    D = np.sqrt(((X[:, None] - X[None]) ** 2).mean(2))
    rc, pc = mantel(D, component_distance(strats), perms)
    rm, pm = mantel(D, metaphor_distance(strats), perms)
    if not np.isfinite(rc):
        return _h("H10", src, test, "inconclusive", note="degenerate distance matrix"), None
    verdict = "supported" if rc > (rm if np.isfinite(rm) else -1) and pc < 0.05 else (
        "not supported" if np.isfinite(rm) and rc <= rm else "inconclusive")
    return (_h("H10", src, test, verdict, stat={"r_component": _r(rc), "p_component": _r(pc, 5), "r_metaphor": _r(rm),
                                                "p_metaphor": _r(pm, 5), "strategies": strats, "n_cells": P.shape[1]},
               p=pc, note="result distance = RMS difference of Con profiles over shared (topology, N, f>0) cells."),
            {"strategies": strats, "D": D})


def apply_holm(hyps: list[dict]) -> None:
    for fam in {("LLM" if h["source"] != "ABM" else "ABM") for h in hyps}:
        rows = [h for h in hyps if h["_holm"] and ("LLM" if h["source"] != "ABM" else "ABM") == fam]
        if not rows:
            continue
        pv = {h["id"] + "|" + h["source"]: h["p"] for h in rows}
        rej, adj = holm(pv), holm_adjusted(pv)
        for h in rows:
            k = h["id"] + "|" + h["source"]
            h["holm_reject"], h["p_holm"] = rej[k], _r(adj[k], 5)
            if h["verdict"] == "supported" and not rej[k]:
                h["verdict"] = "inconclusive"
                h["note"] = (h["note"] + " Criterion met but not significant after Holm.").strip()
    for h in hyps:
        h.pop("_holm")


# ---------------------------------------------------------------- figures
# Styling lives in figstyle.py (fonts, palette, sizes, PNG+PDF output). The functions below only choose
# what to draw; captions (with N, seeds and CI method) belong in the report, so figures carry no titles.

def _style():
    from . import figstyle
    return figstyle.apply()


def _order(strats) -> list[str]:
    return sorted(set(strats), key=lambda s: (int("".join(c for c in s[1:] if c.isdigit()) or 0), s))


def fig_leaderboard(plt, board: list[dict], src: str, path: Path) -> None:
    from . import figstyle as S
    cols = ["Strategy", "Acc, f = 0 ↑", "Con, f ≈ 1/12 ↓", "Con, f ≈ 3/12 ↓", "f* ↑", "Calls/run"]
    fmt = lambda c: "–" if c is None or c.get("mean") is None else f"{c['mean']:.2f} [{c['lo']:.2f}, {c['hi']:.2f}]"
    cell = [[S.strategy_label(b["strategy"]), fmt(b["acc_f0"]), fmt(b["con_1/12"]), fmt(b["con_3/12"]),
             "–" if b["f_star"] is None else (f"{b['f_star']:.2f}" if b["f_star_in_range"] else f"> {b['f_max']:.2f}"),
             "–" if b["calls"] is None else f"{b['calls']:.0f}"]
            for b in board]
    if all(c[-1] == "–" for c in cell):          # ABM has no call counts
        cols, cell = cols[:-1], [c[:-1] for c in cell]
    fig, ax = plt.subplots(figsize=(S.FULL, 0.2 * (len(cell) + 1) + 0.1))
    ax.axis("off")
    widths = [0.19, 0.2, 0.2, 0.2, 0.09, 0.12] if len(cols) == 6 else [0.22, 0.22, 0.22, 0.22, 0.12]
    t = ax.table(cellText=cell, colLabels=cols, loc="center", cellLoc="center", colWidths=widths, edges="open")
    t.auto_set_font_size(False)
    t.set_fontsize(8)
    t.scale(1, 1.25)
    last = len(cell)
    for (r, c), k in t.get_celld().items():
        k.set_linewidth(0.6)
        k.set_edgecolor(S.INK)
        k.visible_edges = "TB" if r == 0 else ("B" if r == last else "")
        if c == 0:
            k.set_text_props(ha="left")
            k.PAD = 0.03
        if r == 0:
            k.set_text_props(weight="bold")
    S.save(fig, path)


def fig_pareto(plt, pts: pd.DataFrame, path: Path) -> None:
    from . import figstyle as S
    fig, ax = plt.subplots(figsize=(S.HALF + 0.3, 3.6))
    mods = sorted(set(pts.module), key=lambda m: (m != "none", m))
    for m in mods:
        g = pts[pts.module == m]
        ax.scatter(g.cost, g.con, s=16 if m != "none" else 20, color=S.MODULE_COLOR.get(m, S.GREY),
                   marker=S.MODULE_MARKER.get(m, "o"), label=S.module_label(m), edgecolor="white",
                   linewidth=0.3, zorder=3, alpha=0.9)
    p = pts.sort_values(["cost", "con"])
    front, best = [], np.inf
    for _, r in p.iterrows():
        if r.con < best:
            front.append(r)
            best = r.con
    fr = pd.DataFrame(front)
    ax.step(fr.cost, fr.con, where="post", color=S.INK, lw=0.8, ls="--", zorder=2)
    prev, key = None, []
    for i, (_, r) in enumerate(fr.iterrows(), 1):     # number the front, name it in a key (no label pile-ups)
        close = prev is not None and abs(prev - r.con) < 0.06
        ax.annotate(str(i), (r.cost, r.con), fontsize=8, fontweight="bold", xytext=(-4, -3 if close else 0),
                    textcoords="offset points", ha="right", va="top" if close else "center", color=S.INK)
        key.append(f"{i}  {r.strategy}+{r.module}" if r.module != "none" else f"{i}  {r.strategy}")
        prev = r.con
    ax.text(0.98, 0.98, "Pareto front (dashed)\n" + "\n".join(key), transform=ax.transAxes, ha="right", va="top",
            fontsize=8, linespacing=1.2)
    ax.axvline(0, color=S.GREY, lw=0.5, zorder=1)
    ax.set_xlabel("Usefulness cost: accuracy drop at f = 0")
    ax.set_ylabel("Contamination at f > 0 (share)")
    ax.set_ylim(0, 1.0)
    S.ygrid(ax)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.22), handletextpad=0.2, columnspacing=0.6)
    S.save(fig, path)


def fig_curves(plt, abm_cells: pd.DataFrame | None, llm_cells: pd.DataFrame | None, path: Path) -> None:
    from . import figstyle as S
    strats = _order(set(abm_cells.strategy if abm_cells is not None else []) |
                    set(llm_cells.strategy if llm_cells is not None else []))
    strats = [s for s in strats if s != "S0a"]
    nc = 4
    nr = math.ceil(len(strats) / nc)   # a full grid puts the legend above the panels instead of a spare row
    fig, axs = plt.subplots(nr, nc, figsize=(S.FULL, 1.45 * nr + 0.2), sharex=True, sharey=True, squeeze=False)
    Ns = sorted(set(abm_cells.N)) if abm_cells is not None else []
    for ax, s in zip(axs.flat, strats):
        if abm_cells is not None:
            for i, N in enumerate(Ns):
                g = abm_cells[(abm_cells.strategy == s) & (abm_cells.N == N)].sort_values("f_eff")
                c = S.N_COLOR.get(N, S.OKABE[i % 8])
                ax.fill_between(g.f_eff, g.con_lo, g.con_hi, color=c, alpha=0.2, lw=0)
                ax.plot(g.f_eff, g.con, color=c, lw=1.1, label=f"ABM, N = {N}")
        if llm_cells is not None:
            g = llm_cells[llm_cells.strategy == s].sort_values("f_eff")
            ax.errorbar(g.f_eff, g.con, yerr=[g.con - g.con_lo, g.con_hi - g.con], fmt="D", ms=3.2, color=S.LLM_C,
                        mfc="white", mew=0.9, elinewidth=0.8, capsize=1.5, label="LLM, N = 12", zorder=4)
        ax.set_title(f"{S.strategy_id(s)} · {S.STRATEGY_SHORT.get(s, s)}", color=S.strategy_color(s) if s not in NON_SOCIAL else S.INK)
        ax.set_ylim(-0.04, 1.06)
        ax.set_yticks([0, 0.5, 1])
        S.ygrid(ax)
    spare = list(axs.flat[len(strats):])
    for ax in spare:
        ax.axis("off")
    for ax in axs[-1]:
        ax.set_xlabel("Attacker fraction f")
        ax.xaxis.set_tick_params(labelbottom=True)
    for ax in axs[:, 0]:
        ax.set_ylabel("Contamination")
    h, l = axs.flat[0].get_legend_handles_labels()
    if spare:
        spare[0].legend(h, l, loc="center", title="95% bootstrap CI")
    else:
        fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.03))
    fig.tight_layout(h_pad=0.6, w_pad=0.6)
    S.save(fig, path)


def fig_heatmap(plt, base: pd.DataFrame, path: Path) -> None:
    from . import figstyle as S
    Ns = sorted(set(base.N))
    topo = [t for t in ["ring", "small_world", "scale_free", "star", "full"] if t in set(base.topology)]
    fig, axs = plt.subplots(1, len(Ns), figsize=(S.FULL, 3.5), squeeze=False, sharey=True)
    from design.mpl import mosaic_cmap
    cmap = mosaic_cmap("print")
    for ax, N in zip(axs[0], Ns):
        d = base[(base.N == N) & (base.f_eff > 0)]
        M = d.pivot_table(index="strategy", columns="topology", values="con", aggfunc="mean")
        M = M.reindex(index=_order(M.index), columns=topo)
        im = ax.imshow(M.to_numpy(float), cmap=cmap, vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(topo)), [S.TOPO_NAME.get(t, t) for t in topo], rotation=40, ha="right",
                      rotation_mode="anchor")
        ax.set_yticks(range(len(M.index)), [S.strategy_label(s) for s in M.index])
        ax.tick_params(length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
        for (i, j), v in np.ndenumerate(M.to_numpy(float)):
            if np.isfinite(v):
                r, g_, b, _ = cmap(v)
                ax.text(j, i, f"{100 * v:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if 0.299 * r + 0.587 * g_ + 0.114 * b < 0.5 else "black")
        ax.set_title(f"N = {N}")
    cb = fig.colorbar(im, ax=axs[0].tolist(), shrink=0.75, pad=0.02, aspect=25)
    from matplotlib.ticker import PercentFormatter
    cb.ax.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    cb.set_label("Contamination at f > 0 (% of honest agents)")
    cb.outline.set_linewidth(0.5)
    S.save(fig, path)


def fig_modules(plt, effects: dict, dend: dict | None, path: Path) -> None:
    from scipy.cluster.hierarchy import dendrogram, linkage
    from scipy.spatial.distance import squareform
    from . import figstyle as S
    fig, axs = plt.subplots(1, 2 if dend else 1, figsize=(S.FULL if dend else S.HALF + 0.3, 2.6), squeeze=False,
                            gridspec_kw={"width_ratios": [1.15, 1]} if dend else None)
    ax = axs[0, 0]
    mods = [m for m in sorted(effects) if effects[m]["overall"]["d_con"]]
    x = np.arange(len(mods))
    for off, key, lab, c in [(-0.19, "d_con", "Δ contamination (f > 0)", S.CON_C),
                             (0.19, "usefulness", "Δ accuracy (f = 0)", S.ACC_C)]:
        e = [effects[m]["overall"][key] or {"diff": np.nan, "lo": np.nan, "hi": np.nan} for m in mods]
        v = np.array([q["diff"] if q["diff"] is not None else np.nan for q in e], float)
        lo = np.array([q["lo"] if q["lo"] is not None else np.nan for q in e], float)
        hi = np.array([q["hi"] if q["hi"] is not None else np.nan for q in e], float)
        ax.bar(x + off, v, 0.38, color=c, label=lab, yerr=[v - lo, hi - v], capsize=1.5,
               error_kw={"elinewidth": 0.7, "capthick": 0.7, "ecolor": S.INK})
    ax.axhline(0, color=S.INK, lw=0.6)
    ax.set_xticks(x, [f"{m}\n{S.MODULE_SHORT.get(m, '')}" for m in mods])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Module − none (paired by seed)")
    S.ygrid(ax)
    ax.legend(loc="lower right")
    S.panel_label(ax, "a")
    if dend:
        ax = axs[0, 1]
        fams = [f for f in S.FAMILY_COLOR if f in set(FAMILY.values())]
        Z = linkage(squareform(dend["D"], checks=False), "average")
        with plt.rc_context({"lines.linewidth": 0.9}):
            dendrogram(Z, labels=dend["strategies"], ax=ax, color_threshold=0, above_threshold_color=S.INK)
        for t in ax.get_xticklabels():
            t.set_color(S.FAMILY_COLOR[FAMILY[t.get_text()]])
            t.set_fontweight("bold")
        ax.tick_params(axis="x", length=0, labelsize=8)
        ax.spines["bottom"].set_visible(False)
        ax.set_ylabel("Result distance (RMS Δ contamination)")
        for f in fams:
            ax.plot([], [], "s", color=S.FAMILY_COLOR[f], label=f, ms=5)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.35)
        ax.legend(title="Metaphor family", loc="upper center", ncol=3, handletextpad=0.1, columnspacing=0.6)
        S.panel_label(ax, "b")
    fig.tight_layout(w_pad=1.5)
    S.save(fig, path)


def fig_redteam(plt, raw: list[dict], path_c: Path, path_m: Path) -> None:
    from matplotlib.ticker import FixedLocator, NullLocator
    from . import figstyle as S
    probs = sorted({(r.get("strategy"), r.get("topology"), r.get("k")) for r in raw}, key=str)[:4]
    fig, axs = plt.subplots(1, len(probs), figsize=(S.FULL, 1.95), squeeze=False, sharey=True)
    names = ["random", "hub", "ga", "bpso", "map_elites"]
    for ax, pr in zip(axs[0], probs):
        for s in names:
            cs = [r["curve"] for r in raw if (r.get("strategy"), r.get("topology"), r.get("k")) == pr
                  and r["searcher"] == s and r.get("curve")]
            if not cs:
                continue
            L = min(map(len, cs))
            C = np.array([c[:L] for c in cs])
            q = np.quantile(C, [0.25, 0.5, 0.75], axis=0)
            ev = np.arange(1, L + 1)
            c = S.SEARCHER_COLOR.get(s, S.GREY)
            ax.fill_between(ev, q[0], q[2], color=c, alpha=0.18, lw=0, step="post")
            ax.step(ev, q[1], where="post", color=c, lw=1.1, label=S.SEARCHER_NAME.get(s, s))
        ax.set_xscale("log")
        ax.xaxis.set_major_locator(FixedLocator([1, 10, 100, 500]))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.set_xticklabels(["1", "10", "100", "500"])
        ax.set_xlabel("ABM evaluations")
        ax.set_title(f"{pr[0]} · {S.TOPO_NAME.get(pr[1], pr[1])} · k = {pr[2]}")
        ax.set_ylim(0, 1.02)
        S.ygrid(ax)
    axs[0, 0].set_ylabel("Best contamination so far")
    h, l = axs[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.1))
    fig.tight_layout(w_pad=0.8)
    S.save(fig, path_c)
    arch = [r["archive"] for r in raw if r["searcher"] == "map_elites" and r.get("archive")
            and (r.get("strategy"), r.get("topology"), r.get("k")) == probs[0]]
    if not arch:
        return
    cells = [tuple(map(int, k.split(","))) for a in arch for k in a]
    nb, no = max(c[0] for c in cells) + 1, max(c[1] for c in cells) + 1
    nb = max(nb, 8)
    S_ = np.full((len(arch), nb, no), np.nan)
    for i, a in enumerate(arch):
        for k, v in a.items():
            b, o = map(int, k.split(","))
            S_[i, b, o] = v
    with np.errstate(all="ignore"):
        import warnings
        warnings.simplefilter("ignore", RuntimeWarning)
        M = np.nanmean(S_, 0)
    fig, ax = plt.subplots(figsize=(S.HALF, 2.5))
    from design.mpl import mosaic_cmap
    cm = mosaic_cmap("print").with_extremes(bad=S.LIGHT)
    im = ax.imshow(M, cmap=cm, origin="lower", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(no))
    ax.set_yticks(range(nb))
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xlabel("Attack onset round")
    ax.set_ylabel("Mean attacker betweenness (bin)")
    cb = fig.colorbar(im, pad=0.03)
    cb.set_label("Elite contamination (mean)")
    cb.outline.set_linewidth(0.5)
    S.save(fig, path_m)


def fig_scatter(plt, cells: pd.DataFrame, h: dict, path: Path) -> None:
    from . import figstyle as S
    fig, ax = plt.subplots(figsize=(S.HALF, 3.0))
    marks = "osD^vP"
    seen: dict[str, int] = {}
    for s in _order(cells.strategy):
        f = S.family(s)
        i = seen[f] = seen.get(f, -1) + 1
        g = cells[cells.strategy == s]
        ax.scatter(g.con_abm, g.con_llm, s=18, color=S.strategy_color(s), marker=marks[i % len(marks)],
                   label=s, edgecolor="white", linewidth=0.3, zorder=3)
    ax.plot([0, 1], [0, 1], color=S.GREY, lw=0.7, ls="--", zorder=1)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("equal")
    ax.set_xlabel("ABM contamination (predicted)")
    ax.set_ylabel("LLM contamination (observed)")
    st = h.get("statistic") or {}
    if st:
        f2 = lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else str(v)
        ax.text(0.02, 0.98, f"Spearman ρ = {f2(st.get('rho'))}\nmean error ABM − LLM = {f2(st['signed_error']['mean'])}",
                transform=ax.transAxes, va="top", fontsize=8)
    ax.legend(ncol=1, loc="center left", bbox_to_anchor=(1.0, 0.5), handletextpad=0.1)
    S.save(fig, path)


# ---------------------------------------------------------------- driver

def _cells_df(c: dict) -> pd.DataFrame:
    return pd.DataFrame(c["rows"], columns=c["columns"])


def leaderboard(base: pd.DataFrame, tips: list[dict], n: int, calls: bool) -> list[dict]:
    d = base[(base.N == 12) & (base.topology == "full")]
    out = []
    for s in _order(d.strategy):
        g = d[d.strategy == s]
        row = {"strategy": s, "exploratory": s in EXPLORATORY, "acc_f0": _ci(g[g.f_eff == 0].groupby("seed").acc.mean(), n) if (g.f_eff == 0).any() else None}
        for lab, t in (("con_1/12", 1 / 12), ("con_3/12", 3 / 12)):
            sub, used = near_f(g, t)
            row[lab] = dict(_ci(sub.groupby("seed").con.mean(), n), f_used=used.get(12)) if len(sub) else None
        tp = _tip(tips, s)
        row["f_star"] = tp["f_star"] if tp else None
        row["f_star_in_range"], row["f_max"] = (tp["in_range"], tp["f_max"]) if tp else (False, None)
        row["calls"] = _r(g["calls"].mean()) if calls and "calls" in g else None
        out.append(row)
    return out


def analyze(stage_a: str | None = None, redteam: str | None = None, llm: list[str] | None = None,
            pilot: str | None = None, params: str | None = None, out: str = "results/results.json",
            figures: str = "figures", boot: int = 2000, tip_boot: int = 500, hyp_boot: int = 10_000,
            perms: int = 9999, workers: int | None = None) -> dict:
    workers = workers if workers is not None else max(1, (os.cpu_count() or 2) - 1)
    exists = lambda p: bool(p) and Path(p).exists()
    meta = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "inputs": {}, "boot": boot, "tip_boot": tip_boot,
            "hyp_boot": hyp_boot, "perms": perms}
    for name, p in [("stageA", stage_a), ("redteam", redteam), ("pilot", pilot)] + [(f"llm[{i}]", q) for i, q in enumerate(llm or [])]:
        if p:
            meta["inputs"][name] = {"path": str(p), "sha256": sha256(p)} if exists(p) else {"path": str(p), "missing": True}
    pdict = json.loads(Path(params).read_text()) if exists(params) else None
    meta["params"] = {"path": str(params), "sha256": sha256(params),
                      "values": {k: v for k, v in pdict.items() if k in ("kappa", "lam")}} if pdict else None
    calibrated = bool(pdict and "_calibration" in pdict)
    meta["calibrated"] = calibrated

    abm = load_stage_a(stage_a) if exists(stage_a) else None
    llm_paths = [p for p in (llm or []) if exists(p)]
    llm_all = load_llm(llm_paths) if llm_paths else None
    L = llm_main(llm_all) if llm_all is not None and len(llm_all) else None
    if L is not None:
        meta["llm_primary_model"] = primary_model(llm_all)
    rt_raw = json.loads(Path(redteam).read_text()) if exists(redteam) else None
    res: dict = {"meta": meta, "not_run": []}
    if abm is not None:
        meta["abm_rows"] = len(abm)
    if L is not None:
        meta["llm_rows"] = len(L)

    abm_base = base_rows(abm) if abm is not None else None
    llm_base = base_rows(L) if L is not None else None
    res["cells"] = {"ABM": cell_summaries(abm, ABM_KEYS, boot, workers) if abm is not None else None,
                    "LLM": cell_summaries(llm_all, LLM_KEYS, boot, workers) if llm_all is not None else None}
    if exists(pilot):
        res["cells"]["pilot"] = cell_summaries(load_llm([pilot]), LLM_KEYS, boot, workers)
    tips = {"ABM": tipping_table(abm, tip_boot, workers) if abm is not None else [],
            "LLM": tipping_table(L, tip_boot, workers) if L is not None else []}
    res["tipping"] = tips
    # exploratory strategies (D22) are reported in cells, tipping, leaderboards and figures, but every pooled
    # quantity that feeds a confirmatory test (H0-H10) is computed without them
    res["exploratory"] = sorted(EXPLORATORY)
    ctips = {k: [t for t in v if t["strategy"] not in EXPLORATORY] for k, v in tips.items()}
    cabm, cL, cabm_base, cllm_base = map(confirmatory, (abm, L, abm_base, llm_base))
    eff = {"ABM": module_effects(cabm, hyp_boot) if abm is not None else {},
           "LLM": module_effects(cL, hyp_boot) if L is not None else {}}
    vals = {k: module_values(v) for k, v in eff.items()}
    res["modules"] = {k: {m: {"overall": {q: _pub(w) for q, w in e["overall"].items()}, "by_strategy": e["by_strategy"],
                              **({"value": vals[k][m]} if m in vals[k] else {})} for m, e in v.items()}
                      for k, v in eff.items()}
    res["modules_exploratory"] = {}
    for k, df in (("ABM", abm), ("LLM", L)):
        x = df[df["strategy"].isin(EXPLORATORY)] if df is not None else None
        if x is not None and len(x) and set(x["module"]) - {"none"}:
            res["modules_exploratory"][k] = {m: {"by_strategy": e["by_strategy"]}
                                             for m, e in module_effects(x, hyp_boot).items()}
    rt_df, res["redteam"] = redteam_table(rt_raw, hyp_boot) if rt_raw else (None, None)
    res["leaderboard"] = {"ABM": leaderboard(abm_base, tips["ABM"], boot, False) if abm is not None else None,
                          "LLM": leaderboard(llm_base, tips["LLM"], boot, True) if L is not None else None}
    cells = matched_cells(cabm, cL) if abm is not None and L is not None else None
    res["proxy_cells"] = cells.to_dict("records") if cells is not None else None

    hyps, dend = [], None
    for src, base, df in (("ABM", cabm_base, cabm), ("LLM", cllm_base, cL)):
        if base is None:
            for hid in ("H0", "H1", "H2", "H3", "H4", "H8", "H9", "H10"):
                hyps.append(_h(hid, src, "–", note=f"no {src} input"))
            continue
        hyps += [h0(src, base, hyp_boot), h1(src, base, hyp_boot), h2(src, ctips[src]), h3(src, vals[src]),
                 h4(src, df, hyp_boot), h8(src, df, hyp_boot), h9(src, ctips[src])]
        h, dd = h10(src, base, perms)
        hyps.append(h)
        dend = dend or (dd if src == "ABM" else None)
    hyps += [h5(cabm, cL, calibrated, hyp_boot), h6(cells, calibrated, hyp_boot), h7_abm(confirmatory(rt_df), hyp_boot),
             h7_llm(rt_raw and [r for r in rt_raw if r.get("strategy") not in EXPLORATORY], confirmatory(llm_all),
                    hyp_boot)]
    apply_holm(hyps)
    order = list(HYP)
    hyps.sort(key=lambda h: (order.index(h["id"]), h["source"]))
    res["hypotheses"] = hyps
    res["not_run"] = [f"{h['id']} ({h['source']})" for h in hyps if h["verdict"] == "not run"]

    # figures
    plt = _style()
    fd = Path(figures)
    fd.mkdir(parents=True, exist_ok=True)
    figs: dict = {}

    def save(name, cond, reason, fn):
        if not cond:
            figs[name] = f"not run: {reason}"
            return
        p = fd / f"{name}.png"
        try:
            ok = fn(p)
            figs[name] = str(p) if ok is not False else f"not run: {reason}"
        except Exception as e:      # a broken figure must not lose the JSON
            figs[name] = f"failed: {type(e).__name__}: {e}"

    for src in ("ABM", "LLM"):
        b = res["leaderboard"][src]
        save(f"fig1_leaderboard_{src.lower()}", bool(b), f"no {src} input",
             lambda p, b=b, src=src: fig_leaderboard(plt, b, src, p))
    if abm is not None:
        nn = abm[(abm.attack == "A2") & (abm.f_eff == 0)].groupby(["strategy", "module"]).acc.mean()
        pos = abm[(abm.attack == "A2") & (abm.f_eff > 0)].groupby(["strategy", "module"]).con.mean()
        pts = pd.DataFrame({"acc0": nn, "con": pos}).dropna().reset_index()
        pts = pts.merge(pts[pts.module == "none"][["strategy", "acc0"]], on="strategy", suffixes=("", "_none"))
        pts["cost"] = pts.acc0_none - pts.acc0
        pts = pts[pts.strategy != "S0a"]
    save("fig2_pareto", abm is not None and len(pts), "no ABM input", lambda p: fig_pareto(plt, pts, p))
    ac = _cells_df(res["cells"]["ABM"]) if abm is not None else None
    if ac is not None:
        ac = ac[(ac.module == "none") & (ac.attack == "A2") & (ac.topology == "full")]
    lc = None
    if L is not None:
        lc = _cells_df(cell_summaries(llm_base[llm_base.topology == "full"], ["strategy", "f_eff"], boot, 1))
    save("fig3_con_vs_f", ac is not None or lc is not None, "no ABM or LLM input", lambda p: fig_curves(plt, ac, lc, p))
    save("fig4_topology_heatmap", abm is not None, "no ABM input", lambda p: fig_heatmap(plt, abm_base, p))
    save("fig5_modules_components", bool(eff["ABM"]), "no ABM module runs", lambda p: fig_modules(plt, eff["ABM"], dend, p))
    save("fig6_redteam", bool(rt_raw), "no red-team input",
         lambda p: fig_redteam(plt, rt_raw, p, fd / "fig6_mapelites.png"))
    if rt_raw:
        figs["fig6_mapelites"] = str(fd / "fig6_mapelites.png") if (fd / "fig6_mapelites.png").exists() else "not run: no archive"
    h6r = next(h for h in hyps if h["id"] == "H6")
    save("fig7_abm_vs_llm", cells is not None and len(cells) > 0, "needs matched ABM and LLM cells",
         lambda p: fig_scatter(plt, cells, h6r, p))
    res["figures"] = figs

    res = _clean(res)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, separators=(",", ":"), allow_nan=False))
    return res


def summary_table(res: dict) -> str:
    lines = [f"{'id':<4} {'source':<11} {'verdict':<14} {'p':>8} {'p_holm':>8}  note"]
    for h in res["hypotheses"]:
        lines.append(f"{h['id']:<4} {h['source']:<11} {h['verdict']:<14} {str(h['p'] if h['p'] is not None else '–'):>8} "
                     f"{str(h['p_holm'] if h['p_holm'] is not None else '–'):>8}  {h['note'][:80]}")
    return "\n".join(lines)
