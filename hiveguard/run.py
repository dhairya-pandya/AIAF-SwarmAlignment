"""CLI: abm / stageA / search / pilot / calibrate / stageB / replay / analyze / site / paperfigs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .abm import ABMParams, run_abm
from .config import RunConfig


def load_params(path: str | None) -> ABMParams:
    if not path:
        return ABMParams()
    d = json.loads(Path(path).read_text())
    return ABMParams(**{k: v for k, v in d.items() if k in ABMParams.__dataclass_fields__})


def _cfg_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--strategy", default="S2")
    p.add_argument("--topology", default="full")
    p.add_argument("--n-agents", type=int, default=12)
    p.add_argument("--f", type=float, default=0.0)
    p.add_argument("--attack", default="A2")
    p.add_argument("--onset", type=int, default=None)
    p.add_argument("--placement", default="random")
    p.add_argument("--modules", nargs="*", default=[])
    p.add_argument("--seed", type=int, default=0)


def _cfg(a) -> RunConfig:
    return RunConfig(strategy=a.strategy, topology=a.topology, n_agents=a.n_agents, f=a.f,
                     attack=a.attack, onset=a.onset, placement=a.placement, modules=a.modules,
                     seed=a.seed)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser("hiveguard")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("abm", help="one ABM run")
    _cfg_args(p)
    p.add_argument("--params")

    p = sub.add_parser("stageA", help="ABM screen over the full grid")
    p.add_argument("--out", default="results/stageA.csv")
    p.add_argument("--params")
    p.add_argument("--seeds", type=int, default=30)
    p.add_argument("--quick", action="store_true", help="N=12 only, 5 seeds")
    p.add_argument("--strategies", nargs="+", help="subset of strategies (default: all)")
    p.add_argument("--workers", type=int)

    p = sub.add_parser("search", help="red-team searchers on the ABM")
    p.add_argument("--out", default="results/redteam.json")
    p.add_argument("--params")
    p.add_argument("--strategies", nargs="+", default=["S2"])
    p.add_argument("--topologies", nargs="+", default=["scale_free"])
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--budget", type=int, default=500)
    p.add_argument("--repeats", type=int, default=10)
    p.add_argument("--workers", type=int)

    for name in ("llm", "pilot", "stageB"):
        p = sub.add_parser(name)
        if name == "llm":
            _cfg_args(p)
        else:
            p.add_argument("--block", default="core",
                           help="core | tier2 | modules | attacks | confirm (stageB only)")
            p.add_argument("--strategies", nargs="+", help="modules/attacks/confirm: best (and worst) Tier-1")
            p.add_argument("--redteam", help="confirm: results/redteam.json")
        p.add_argument("--models", nargs="+", default=["mock:mock"])
        p.add_argument("--logs", default="logs")
        p.add_argument("--out", default=f"results/{name}.csv")
        p.add_argument("--cache", default=".cache/llm.sqlite")
        p.add_argument("--seeds", type=int, default=3)
        p.add_argument("--workers", type=int, default=8)
        p.add_argument("--parallel-runs", type=int, default=1, help="runs executed concurrently")

    p = sub.add_parser("calibrate", help="fit kappa, lambda to pilot runs and freeze them")
    p.add_argument("--pilot", default="results/pilot.csv")
    p.add_argument("--out", default="results/abm_params.json")

    p = sub.add_parser("replay", help="re-run a logged LLM run from the cache and compare bytes")
    p.add_argument("run_id")
    p.add_argument("--logs", default="logs")
    p.add_argument("--cache", default=".cache/llm.sqlite")

    p = sub.add_parser("analyze", help="figures, hypothesis verdicts and results JSON (missing inputs are skipped)")
    p.add_argument("--stageA", default="results/stageA.csv")
    p.add_argument("--redteam", default="results/redteam_k1.json")
    p.add_argument("--llm", nargs="*", default=sorted(str(x) for x in Path("results").glob("stageB_*.csv")),
                   help="Stage B CSV(s) (default: every results/stageB_*.csv)")
    p.add_argument("--pilot", default="results/pilot.csv")
    p.add_argument("--params", default="results/abm_params.json")
    p.add_argument("--out", default="results/results.json")
    p.add_argument("--figures", default="figures")
    p.add_argument("--boot", type=int, default=2000, help="bootstrap resamples for per-cell CIs")
    p.add_argument("--tip-boot", type=int, default=500, help="bootstrap resamples for f* CIs")
    p.add_argument("--hyp-boot", type=int, default=10_000, help="bootstrap resamples for hypothesis tests")
    p.add_argument("--perms", type=int, default=9999, help="Mantel permutations (H10)")
    p.add_argument("--workers", type=int)

    p = sub.add_parser("site", help="build site/data (results, cells, replays) and copy figures for the results page")
    p.add_argument("--results", default="results/results.json")
    p.add_argument("--logs", nargs="*", default=["logs", "results/oracle_logs"], help="run log files or folders")
    p.add_argument("--runs", nargs="*", help="run ids to replay (default: the most informative runs)")
    p.add_argument("--max-replays", type=int, default=12)
    p.add_argument("--figures", help="figures folder (default: the paths listed in the results JSON)")
    p.add_argument("--out", default="site")

    p = sub.add_parser("paperfigs", help="report-only figures: method overview, component matrix, ABM cascade")
    p.add_argument("--out", default="figures/paper")
    p.add_argument("--params", help="ABM params JSON for the cascade (default: current ABMParams defaults)")

    a = ap.parse_args(argv)

    if a.cmd == "abm":
        m = run_abm(_cfg(a), load_params(a.params))
        m.pop("choices")
        print(json.dumps(m, indent=2))
    elif a.cmd == "stageA":
        from .stage_a import run_stage_a
        kw = dict(seeds=a.seeds)
        if a.strategies:
            kw["strategies"] = a.strategies
        if a.quick:
            kw.update(n_grid=[12], seeds=5)
        df = run_stage_a(a.out, load_params(a.params), workers=a.workers, **kw)
        print(f"{len(df)} runs -> {a.out}")
    elif a.cmd == "search":
        from .stage_a import run_red_team
        res = run_red_team(a.out, load_params(a.params), a.strategies, a.topologies, a.k,
                           a.budget, a.repeats, a.workers)
        print(f"{len(res)} searches -> {a.out}")
    elif a.cmd in ("llm", "pilot", "stageB"):
        from . import llm_runs
        llm_runs.dispatch(a, _cfg(a) if a.cmd == "llm" else None)
    elif a.cmd == "calibrate":
        from .calibrate import calibrate
        calibrate(a.pilot, a.out)
    elif a.cmd == "analyze":
        from .analysis import analyze, summary_table
        res = analyze(a.stageA, a.redteam, a.llm, a.pilot, a.params, a.out, a.figures, a.boot, a.tip_boot,
                      a.hyp_boot, a.perms, a.workers)
        print(summary_table(res))
        print(f"-> {a.out}, figures in {a.figures}/")
    elif a.cmd == "site":
        from .export_site import export_site
        m = export_site(a.results, a.logs, a.figures, a.out, a.runs, a.max_replays)
        print(f"{'calibrated' if m['calibrated'] else 'UNCALIBRATED (exploratory)'}: {m['replays']} replays, "
              f"{len(m['figures'])} figures, {len(m['skipped_logs'])} logs skipped -> {a.out}/data")
    elif a.cmd == "paperfigs":
        from .paper_figures import make_all
        res = make_all(a.out, load_params(a.params) if a.params else None)
        c = res["cascade"]
        print(f"cascade: {c['n_attackers']} attackers, Con by round {c['con_by_round']}")
        print(f"-> {a.out}/ (PNG 300 dpi + PDF)")
    elif a.cmd == "replay":
        from .env import replay
        ok = replay(a.run_id, a.logs, a.cache)
        print("replay identical" if ok else "replay DIFFERS")
        raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
