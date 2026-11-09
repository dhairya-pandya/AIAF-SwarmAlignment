import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hiveguard.analysis import (COMPONENTS, HYP, analyze, component_distance, holm_adjusted, mantel,
                                metaphor_distance, near_f)

QUICK = Path(__file__).parents[1] / "results" / "stageA_quick_precal.csv"
VERDICTS = {"supported", "not supported", "inconclusive", "not run"}
FSTAR = {"S0a": 9, "S0b": 9, "S1": 9, "S2": 0.05, "S3": 0.08, "S4": 0.3, "S5": 0.2, "S6": 0.06, "S7": 0.04,
         "S8": 0.07, "S9": 0.28, "S10": 0.1, "S11": 0.5, "S12": 0.45}
MOD = {"none": (1.0, 0.0), "M2": (0.7, 0.05), "M3": (0.3, 0.01), "M4": (0.9, 0.0)}
FAST = dict(boot=50, tip_boot=5, hyp_boot=300, perms=199, workers=1)


def _con(s, f, topo, rng):
    c = 1 / (1 + np.exp(-(f - FSTAR[s]) / 0.02)) if s != "S0a" else 0.0
    if s in ("S2", "S3", "S6", "S8") and topo != "ring" and f > 0:
        c += 0.2
    return float(np.clip(c * 0.8 + rng.normal(0, 0.03), 0, 1))


def _stage_a(path, rng):
    rows = []
    for s in FSTAR:
        for m, (mul, cost) in MOD.items():
            for t in ("ring", "full", "star"):
                for f in (0, 1 / 12, 2 / 12, 3 / 12, 4 / 12):
                    for seed in range(8):
                        con = _con(s, f, t, rng) * mul
                        rows.append(dict(strategy=s, module=m, topology=t, N=12, f=f, f_eff=f, k=round(f * 12),
                                         attack="A2", seed=seed, acc=max(0, 0.8 - 0.6 * con - cost + rng.normal(0, .02)),
                                         con=con, group_correct=con < .5, deadlock=bool(rng.random() < mul * .4),
                                         consensus_time=(1 if s == "S7" else 3) if f == 0 else np.nan,
                                         t50=(1 if t != "ring" else 3) if con > 0 else np.nan,
                                         con_curve=json.dumps([con * r / 5 for r in range(6)])))
    for s in ("S2", "S3", "S4", "S7", "S9"):
        for seed in range(8):
            con = (0.95 if s == "S7" else 0.4) + rng.normal(0, .02)
            rows.append(dict(strategy=s, module="none", topology="full", N=12, f=1 / 12, f_eff=1 / 12, k=1,
                             attack="A5", seed=seed, acc=0.3, con=con, group_correct=False, deadlock=False,
                             consensus_time=2, t50=1, con_curve=json.dumps([con] * 6)))
    pd.DataFrame(rows).to_csv(path, index=False)


def _llm(path, rng):
    rows = []

    def add(s, t, f, seed, module="none", placement="random", attack="A2", onset=0, con=None):
        con = _con(s, f, t, rng) * MOD.get(module, (1, 0))[0] * 1.1 if con is None else con
        rows.append(dict(run_id=f"r{len(rows)}", strategy=s, topology=t, N=12, R=6, f=f, f_eff=f, attack=attack,
                         onset=onset, placement=placement, module=module, models="m:a", seed=seed,
                         acc=0.7 - 0.5 * con, con=min(con, 1), group_correct=True, deadlock=False, consensus_time=2,
                         t50=1, valid_rate=1, refusal_rate=0, revert_rate=0, calls=72, seconds=1,
                         acc_curve="[]", con_curve=json.dumps([con] * 6)))
    for s in ("S0b", "S1", "S2", "S3", "S4", "S7", "S9"):
        for t in (["ring", "full"] if s in ("S2", "S3") else ["full"]):
            for f in (0, 1 / 12, 3 / 12):
                for seed in range(3):
                    add(s, t, f, seed)
    for m in ("M1", "M2", "M3", "M4"):
        for f in (0, 3 / 12):
            for seed in range(3):
                add("S2", "full", f, seed, module=m)
    for seed in range(3):
        add("S2", "scale_free", 0, seed, placement="explicit", attack="A2", onset=0, con=0.9)
        add("S2", "scale_free", 0, seed, placement="explicit", attack="A1", onset=2, con=0.3)
    pd.DataFrame(rows).to_csv(path, index=False)


def _redteam(path, rng):
    level = {"random": 0.3, "hub": 0.5, "ga": 0.8, "bpso": 0.6, "map_elites": 0.75}
    out = []
    for s, lv in level.items():
        for rep in range(4):
            curve = list(np.maximum.accumulate(np.linspace(0.1, lv, 60) + rng.normal(0, .01, 60)))
            g = {"nodes": [0, 1, 2], "onset": 0, "attack": "A2"} if s == "ga" else {"nodes": [3, 4, 5], "onset": 2, "attack": "A1"}
            r = dict(searcher=s, seed=rep, best=curve[-1], best_genome=g, curve=curve, strategy="S2",
                     topology="scale_free", k=3)
            if s == "map_elites":
                r["archive"] = {f"{b},{o}": float(rng.random()) for b in range(8) for o in range(6)}
            out.append(r)
    Path(path).write_text(json.dumps(out))


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    d = tmp_path_factory.mktemp("an")
    rng = np.random.default_rng(0)
    _stage_a(d / "a.csv", rng)
    _llm(d / "b.csv", rng)
    _redteam(d / "rt.json", rng)
    (d / "p.json").write_text(json.dumps({"kappa": 0.4, "lam": 1.0, "_calibration": {"loss": 0.1}}))
    res = analyze(str(d / "a.csv"), str(d / "rt.json"), [str(d / "b.csv")], None, str(d / "p.json"),
                  str(d / "res.json"), str(d / "fig"), **FAST)
    return d, res


def test_mantel_and_distances():
    rng = np.random.default_rng(1)
    X = rng.random((8, 3))
    A = np.sqrt(((X[:, None] - X[None]) ** 2).sum(2))
    r, p = mantel(A, A, perms=199)
    assert r == pytest.approx(1) and p <= 0.01
    C = component_distance(list(COMPONENTS))
    assert C.shape == (len(COMPONENTS),) * 2 and np.allclose(C, C.T) and C[0, 1] == 1 / 8
    M = metaphor_distance(["S4", "S9", "S7"])
    assert M[0, 1] == 0 and M[0, 2] == 1


def test_near_f_tie_and_holm():
    df = pd.DataFrame({"N": 12, "f_eff": [0, 1 / 12, 2 / 12, 4 / 12], "seed": 0})
    sub, used = near_f(df, 3 / 12)
    assert sorted(sub.f_eff) == [2 / 12, 4 / 12] and len(used[12]) == 2
    assert near_f(df, 1 / 12)[1][12] == [round(1 / 12, 4)]
    adj = holm_adjusted({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}


def test_synthetic_end_to_end(synth):
    d, res = synth
    strict = json.loads((d / "res.json").read_text())       # strict JSON, no NaN
    assert strict["meta"]["calibrated"] is True and strict["meta"]["inputs"]["stageA"]["sha256"]
    H = {(h["id"], h["source"]): h for h in res["hypotheses"]}
    assert {h["id"] for h in res["hypotheses"]} == set(HYP)
    assert all(h["verdict"] in VERDICTS for h in res["hypotheses"])
    assert H[("H1", "ABM")]["verdict"] == "supported"
    assert H[("H3", "ABM")]["statistic"]["M3"]["rank"] == 1
    assert H[("H8", "ABM")]["verdict"] != "not run"
    assert H[("H9", "ABM")]["statistic"]["ranking"][:2] in (["S4", "S9"], ["S9", "S4"])
    assert H[("H7", "ABM")]["verdict"] == "supported"
    assert H[("H7", "LLM")]["statistic"]["diff"] > 0
    assert H[("H2", "ABM")]["verdict"] == "not run"           # no N=200
    assert H[("H0", "LLM")]["verdict"] != "not run" and H[("H0", "LLM")]["holm_reject"] is None
    assert H[("H6", "ABM vs LLM")]["verdict"] != "not run" and H[("H5", "ABM vs LLM")]["verdict"] != "not run"
    assert H[("H10", "ABM")]["statistic"]["strategies"]
    assert "S11" not in H[("H10", "ABM")]["statistic"]["strategies"]       # exploratory (D22)
    assert "S12" not in H[("H10", "ABM")]["statistic"]["strategies"]       # exploratory (D24)
    lb = {b["strategy"]: b for b in res["leaderboard"]["ABM"]}
    assert lb["S11"]["exploratory"] and lb["S12"]["exploratory"] and not lb["S2"]["exploratory"]
    assert all(h["p_holm"] is not None for h in res["hypotheses"] if h["holm_reject"] is not None)
    m3 = res["modules"]["ABM"]["M3"]["overall"]
    assert m3["d_con"]["hi"] < 0 and "usefulness" in m3
    assert res["redteam"]["S2/scale_free/3"]["ga"]["vs_random"]["lo"] > 0
    for name, p in res["figures"].items():
        assert not p.startswith("failed"), (name, p)
    assert len(list((d / "fig").glob("*.png"))) >= 9


def test_exploratory_excluded_from_hypotheses(synth, tmp_path):
    d, res = synth
    df = pd.read_csv(d / "a.csv")
    df[~df.strategy.isin(["S11", "S12"])].to_csv(tmp_path / "a.csv", index=False)
    res2 = analyze(str(tmp_path / "a.csv"), str(d / "rt.json"), [str(d / "b.csv")], None, str(d / "p.json"),
                   str(tmp_path / "res.json"), str(tmp_path / "fig"), **FAST)
    key = lambda r: {(h["id"], h["source"]): (h["verdict"], h["p"], h["p_holm"]) for h in r["hypotheses"]}
    assert key(res) == key(res2)
    assert not {"S11", "S12"} & {b["strategy"] for b in res2["leaderboard"]["ABM"]}


def test_missing_inputs(tmp_path):
    res = analyze(None, str(tmp_path / "nope.json"), [], None, None, str(tmp_path / "r.json"), str(tmp_path / "f"), **FAST)
    assert {h["verdict"] for h in res["hypotheses"]} == {"not run"}
    assert res["meta"]["inputs"]["redteam"]["missing"] and res["meta"]["calibrated"] is False
    assert all(v.startswith("not run") for v in res["figures"].values())


@pytest.mark.skipif(not QUICK.exists(), reason="quick Stage A CSV absent")
def test_quick_stage_a(tmp_path):
    df = pd.read_csv(QUICK)
    df = df[df.strategy.isin(["S1", "S2", "S3", "S4", "S9"]) & df.module.isin(["none", "M2", "M3"])
            & df.topology.isin(["ring", "full"])]
    df.to_csv(tmp_path / "q.csv", index=False)
    res = analyze(str(tmp_path / "q.csv"), None, [], None, None, str(tmp_path / "r.json"), str(tmp_path / "f"), **FAST)
    H = {(h["id"], h["source"]): h for h in res["hypotheses"]}
    assert H[("H0", "ABM")]["verdict"] != "not run"
    assert H[("H2", "ABM")]["verdict"] == "not run"
    assert H[("H1", "ABM")]["statistic"]["n"] == 2          # only S2, S3 of the D8 set present
    assert res["tipping"]["ABM"] and res["cells"]["ABM"]["rows"]
