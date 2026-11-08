import json

from hiveguard.config import RunConfig
from hiveguard.export_site import export_site
from hiveguard.run import main
from hiveguard.world import build_world


def _results(path, calibrated=False):
    res = {
        "meta": {"generated": "2026-11-08T00:00:00", "calibrated": calibrated, "inputs": {}, "params": None},
        "not_run": ["H0 (LLM)"],
        "cells": {"ABM": {"columns": ["strategy", "module", "topology", "N", "f_eff", "attack", "n", "acc", "acc_lo",
                                      "acc_hi", "con", "con_lo", "con_hi", "deadlock", "t50"],
                          "rows": [["S2", "none", "full", 12, 0.0, "A2", 5, 0.8, 0.7, 0.9, 0.0, 0.0, 0.0, 0.0, None]]},
                  "LLM": None},
        "tipping": {"ABM": [], "LLM": []}, "modules": {"ABM": {}, "LLM": {}}, "redteam": None,
        "leaderboard": {"ABM": [], "LLM": None}, "proxy_cells": None,
        "hypotheses": [{"id": "H0", "statement": "s", "source": "LLM", "test": "–", "statistic": None, "ci": None,
                        "p": None, "p_holm": None, "holm_reject": None, "verdict": "not run", "note": "no LLM input"}],
        "figures": {"fig1_leaderboard_abm": str(path.parent / "figs" / "fig1_leaderboard_abm.png"),
                    "fig7_abm_vs_llm": "not run: needs matched ABM and LLM cells"},
    }
    path.write_text(json.dumps(res))


def _log(path, cfg: RunConfig, rounds: int, complete: bool = True):
    w = build_world(cfg)
    lines = [json.dumps({"type": "config", "run_id": cfg.run_id, "config": cfg.to_dict(), "target": w.target,
                         "correct": w.task.correct, "attackers": w.attackers.tolist(),
                         "displays": [f"ag-{10 + i}" for i in range(w.N)]})]
    for r in range(rounds):
        for i in range(w.N):
            c = w.target if (w.attacker[i] or r > 0) else w.task.correct
            lines.append(json.dumps({"type": "turn", "round": r, "agent": i, "role": "attacker" if w.attacker[i] else "honest",
                                     "parsed": {"choice": "ABCD"[c], "confidence": 0.9, "message": "x " * 400,
                                                "claims": [{"option": "A", "attribute": "cost", "value": 3, "source": "own"}] * 6},
                                     "choice": int(c), "reverted": False, "error": None, "refusal": False}))
    if complete:
        lines.append('{"type": "result", "metrics": {"acc": 0.0, "con": 1.0, "t50": NaN}}')
    path.write_text("\n".join(lines) + "\n")
    return w


def test_export_site(tmp_path):
    (tmp_path / "figs").mkdir()
    (tmp_path / "figs" / "fig1_leaderboard_abm.png").write_bytes(b"\x89PNG")
    _results(tmp_path / "results.json")
    logs = tmp_path / "logs"
    logs.mkdir()
    cfg = RunConfig(strategy="S2", topology="ring", n_agents=6, f=1 / 6, n_rounds=2, seed=3, backend="llm")
    w = _log(logs / f"{cfg.run_id}.jsonl", cfg, rounds=2)
    _log(logs / "partial.jsonl", RunConfig(strategy="S4", n_agents=6, seed=1), rounds=1, complete=False)
    out = tmp_path / "site"

    m = export_site(str(tmp_path / "results.json"), [str(logs)], None, str(out))
    assert m["calibrated"] is False and m["replays"] == 1 and len(m["skipped_logs"]) == 1

    data = out / "data"
    for f in ("manifest.json", "results.json", "cells.json", "labels.json", "replays/index.json"):
        json.loads((data / f).read_text())          # strict JSON (NaN would fail in JS)
    res = json.loads((data / "results.json").read_text())
    assert "cells" not in res and json.loads((data / "cells.json").read_text())["LLM"] is None
    assert res["figures"]["fig1_leaderboard_abm"] == {"src": "figures/fig1_leaderboard_abm.png"}
    assert res["figures"]["fig7_abm_vs_llm"]["status"].startswith("not run")
    assert (out / "figures" / "fig1_leaderboard_abm.png").exists()

    rp = json.loads((data / "replays" / f"{cfg.run_id}.json").read_text())
    assert rp["n_nodes"] == 6 and len(rp["edges"]) == 6                     # ring
    assert sorted(map(sorted, rp["edges"])) == sorted(map(sorted, w.G.edges()))
    assert rp["attackers"] == w.attackers.tolist() and rp["correct"] == w.task.correct
    assert len(rp["rounds"]) == 2 and rp["metrics"]["t50"] is None
    assert all(0 <= n["x"] <= 1 and 0 <= n["y"] <= 1 for n in rp["nodes"])
    r0, r1 = rp["rounds"]
    assert r0["share_correct"] == 1.0 and r1["share_target"] == 1.0
    assert sum(r0["honest_counts"]) == 6 - len(w.attackers)
    a = r0["agents"][0]
    assert len(a["msg"]) <= 280 and len(a["claims"]) == 4 and a["n_claims"] == 6


def test_cli_site(tmp_path, capsys):
    _results(tmp_path / "results.json", calibrated=True)
    main(["site", "--results", str(tmp_path / "results.json"), "--logs", str(tmp_path / "none"),
          "--out", str(tmp_path / "site")])
    assert "calibrated: 0 replays" in capsys.readouterr().out
    assert json.loads((tmp_path / "site" / "data" / "replays" / "index.json").read_text()) == []
    assert json.loads((tmp_path / "site" / "data" / "manifest.json").read_text())["calibrated"] is True
