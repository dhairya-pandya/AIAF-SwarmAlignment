"""Build the static results site's data folder (DESIGN §12.2, DEVIATIONS D13).

Reads the results JSON written by `hiveguard analyze`, a set of LLM run logs (JSONL written by env.py) and a
figures folder, and writes:

    <out>/data/manifest.json        what was exported, from where, and whether the numbers are calibrated
    <out>/data/results.json         results JSON minus the per-cell table, figure paths rewritten for the site
    <out>/data/cells.json           per-cell summaries (strategy x module x topology x N x f x attack)
    <out>/data/labels.json          names of strategies, modules, attacks and topologies
    <out>/data/replays/index.json   one entry per exported run
    <out>/data/replays/<id>.json    compact replay: graph, layout, roles, per-round choices and short messages
    <out>/figures/*.png             copied report figures

Nothing is computed here except per-round shares in the replays (counted directly from the logged choices) and
node positions for drawing the graph. Every other number is copied from the inputs."""
from __future__ import annotations

import json
import math
import shutil
import time
from dataclasses import fields
from pathlib import Path

import networkx as nx

from .config import EXPLORATORY, TIER, RunConfig
from .world import build_world

OPTION_IDS = "ABCDEFGHIJ"
BOARD = {"S4", "S5", "S9", "S10"}
BROADCAST = {"S7", "S12"}
SOLO = {"S0a", "S0b", "S1"}

STRATEGIES = {
    "S0a": ("Oracle", "Reference: one agent sees every fact", "abstract"),
    "S0b": ("Solo", "Each agent answers alone from its own facts", "abstract"),
    "S1": ("Majority vote", "Independent answers, group decides by majority (compute-matched)", "abstract"),
    "S2": ("Neighbour debate", "Agents read their neighbours' messages and revise freely", "abstract"),
    "S3": ("Particle swarm (PSO)", "Inertia, personal best and neighbourhood best", "abstract"),
    "S4": ("Ant stigmergy", "No direct messages; a shared board with evaporating pheromone", "insects"),
    "S5": ("Artificial bee colony", "Employed and onlooker bees work claims on a board", "insects"),
    "S6": ("Firefly", "Agents move toward brighter neighbours within distance 2", "fireflies"),
    "S7": ("Wolf-pack hierarchy", "Leader-follower: the top-3 most confident agents broadcast to all", "wolves"),
    "S8": ("Boids", "Alignment and cohesion with a separation push against groupthink", "birds"),
    "S9": ("Honeybee waggle dance", "Scouts dance for options on a board; decision by quorum", "insects"),
    "S10": ("Division of labour", "Proposer-verifier roles taken by response thresholds", "insects"),
    "S11": ("Reciprocity / reputation", "Exploratory: neighbours weighted by trust earned from claims that match "
            "your own facts", "mammals"),
    "S12": ("Elephant matriarch", "Exploratory: leader-follower like S7, but the 3 leaders are the agents whose "
            "first-hand facts were most often independently confirmed last round", "mammals"),
}
MODULES = {
    "none": ("No defence", "Strategy as specified"),
    "M1": ("Evaporation", "Messages and posts lose weight each round; faint ones are hidden"),
    "M2": ("Stop signals", "Claims stopped by 2+ agents are hidden for 2 rounds"),
    "M3": ("Quorum on first-hand evidence", "Switch only when 2+ agents report first-hand support"),
    "M4": ("Uninformed dilution", "Extra agents with no facts who follow the plurality"),
    "M5": ("Model diversity", "Honest agents split across model families"),
    "M6": ("Sparse topology", "Rewire to a ring or small-world graph"),
}
ATTACKS = {
    "A1": ("Confident liar", "Always picks the target with high confidence, no specific claims"),
    "A2": ("Fabricated evidence", "Invents first-hand claims favouring the target"),
    "A3": ("Sleeper", "Honest at first, then switches to fabricated evidence"),
    "A4": ("Sybil", "Posts under several aliases on the board"),
    "A5": ("Leader capture", "Maximises self-reported confidence to become the leader"),
}
TOPOLOGIES = {"ring": "Ring", "small_world": "Small world", "scale_free": "Scale free", "star": "Star",
              "full": "Fully connected"}
MSG_CHARS = 280
CLAIMS_SHOWN = 4


def clean(o):
    """Recursively replace NaN/inf with None so the output is strict JSON."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj), separators=(",", ":"), allow_nan=False))


def labels() -> dict:
    return {
        "strategies": {k: {"name": n, "desc": d, "family": fam, "tier": TIER.get(k), "exploratory": k in EXPLORATORY,
                           "comm": "board" if k in BOARD else "broadcast" if k in BROADCAST
                           else "none" if k in SOLO else "graph"}
                       for k, (n, d, fam) in STRATEGIES.items()},
        "modules": {k: {"name": n, "desc": d} for k, (n, d) in MODULES.items()},
        "attacks": {k: {"name": n, "desc": d} for k, (n, d) in ATTACKS.items()},
        "topologies": TOPOLOGIES,
    }


# ---------------------------------------------------------------- figures

def copy_figures(res: dict, fig_dir: str | None, out: Path) -> dict:
    """Copy figures into <out>/figures. Returns {name: {"src": site path} | {"status": "not run: ..."}}."""
    dest = out / "figures"
    dest.mkdir(parents=True, exist_ok=True)
    listed = res.get("figures") or {}
    found: dict[str, Path] = {}
    if fig_dir:
        for p in sorted(Path(fig_dir).glob("*")):
            if p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg", ".webp"):
                found[p.stem] = p
    else:
        for name, v in listed.items():
            if isinstance(v, str) and Path(v).exists():
                found[name] = Path(v)
    figs = {}
    for name, p in found.items():
        shutil.copy2(p, dest / p.name)
        figs[name] = {"src": f"figures/{p.name}"}
    for name, v in listed.items():
        if name not in figs:
            ok = isinstance(v, str) and v.startswith(("not run", "failed"))
            figs[name] = {"status": v if ok else "not exported"}
    return figs


# ---------------------------------------------------------------- replays

def read_log(path: Path) -> dict | None:
    """Parse one run log. Returns None for incomplete logs (no result line) or a different format."""
    head, turns, result = None, [], None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        t = d.get("type")
        if t == "config":
            head = d
        elif t == "turn":
            turns.append(d)
        elif t == "result":
            result = d
    if head is None or result is None or not turns:
        return None
    return {"head": head, "turns": turns, "result": result, "path": path}


def _config(d: dict) -> RunConfig:
    names = {f.name for f in fields(RunConfig)}
    return RunConfig.from_dict({k: v for k, v in d.items() if k in names})


def _layout(G: nx.Graph, topology: str) -> dict[int, tuple[float, float]]:
    n = G.number_of_nodes()
    if n == 0:
        return {}
    if topology in ("ring", "full") or G.number_of_edges() == n * (n - 1) // 2:
        pos = nx.circular_layout(G)
    elif topology == "star":
        pos = nx.shell_layout(G, [[0], list(range(1, n))]) if n > 1 else {0: (0.0, 0.0)}
    else:
        pos = nx.kamada_kawai_layout(G) if n <= 60 else nx.spring_layout(G, seed=0)
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    sx, sy = (max(xs) - min(xs)) or 1.0, (max(ys) - min(ys)) or 1.0
    s = max(sx, sy)
    return {int(k): (round((p[0] - min(xs)) / s + (1 - sx / s) / 2, 4),
                     round((p[1] - min(ys)) / s + (1 - sy / s) / 2, 4)) for k, p in pos.items()}


def _rel(p: Path) -> str:
    """Path relative to the working directory when possible, so no local absolute paths are published."""
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return f"{p.parent.name}/{p.name}"


def _short(s: str, n: int = MSG_CHARS) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def build_replay(log: dict) -> dict:
    head, turns, result = log["head"], log["turns"], log["result"]
    cfg_d = head["config"]
    cfg = _config(cfg_d)
    world = build_world(cfg)
    G = world.G
    N = G.number_of_nodes()
    n_opt = int(cfg_d.get("n_options", 4))
    rounds = sorted({t["round"] for t in turns})
    attackers = [int(a) for a in head.get("attackers", [])]
    uninformed = [i for i in range(N) if bool(world.uninformed[i])]
    honest = [i for i in range(N) if i not in attackers and i not in uninformed]
    correct, target = int(head["correct"]), int(head["target"])
    pos = _layout(G, cfg.module_params.get("M6_topology", "ring") if "M6" in cfg.modules else cfg.topology)
    displays = head.get("displays") or [f"agent {i}" for i in range(N)]

    by_round = {r: {} for r in rounds}
    for t in turns:
        by_round[t["round"]][int(t["agent"])] = t
    out_rounds = []
    for r in rounds:
        row = by_round[r]
        agents = []
        for i in range(N):
            t = row.get(i)
            if t is None:
                agents.append(None)
                continue
            p = t.get("parsed") or {}
            claims = [f"{c.get('option')}.{c.get('attribute')} = {c.get('value')} ({c.get('source')})"
                      for c in (p.get("claims") or [])[:CLAIMS_SHOWN]]
            agents.append({"c": int(t.get("choice", -1)), "role": t.get("role"),
                           "conf": p.get("confidence"), "msg": _short(p.get("message", "")),
                           "claims": claims, "n_claims": len(p.get("claims") or []),
                           "rev": bool(t.get("reverted")), "err": bool(t.get("error")),
                           "refusal": bool(t.get("refusal"))})
        ch = [a["c"] if a else -1 for a in agents]
        hc = [ch[i] for i in honest]
        counts = [sum(1 for i in honest if ch[i] == o) for o in range(n_opt)]
        out_rounds.append({"round": r, "agents": agents, "honest_counts": counts,
                           "honest_abstain": sum(1 for c in hc if c < 0),
                           "share_correct": (sum(1 for c in hc if c == correct) / len(hc)) if hc else None,
                           "share_target": (sum(1 for c in hc if c == target) / len(hc)) if hc else None})

    keep = ("strategy", "topology", "n_agents", "n_rounds", "n_options", "f", "attack", "onset", "placement",
            "modules", "module_params", "seed", "graph_seed", "models", "temperature")
    return {
        "run_id": head.get("run_id") or log["path"].stem,
        "source_file": _rel(log["path"]),
        "config": {k: cfg_d.get(k) for k in keep},
        "f_eff": cfg.f_effective,
        "n_nodes": N,
        "option_ids": list(OPTION_IDS[:n_opt]),
        "correct": correct,
        "target": target,
        "attackers": attackers,
        "uninformed": uninformed,
        "displays": displays,
        "nodes": [{"id": i, "x": pos[i][0], "y": pos[i][1]} for i in range(N)],
        "edges": [[int(u), int(v)] for u, v in G.edges()],
        "rounds": out_rounds,
        "metrics": result.get("metrics", {}),
    }


def _interest(log: dict) -> tuple:
    h, c = log["head"], log["head"]["config"]
    n_rounds = len({t["round"] for t in log["turns"]})
    return (len(h.get("attackers", [])) > 0, n_rounds > 1, c.get("n_agents", 0), log["path"].stat().st_mtime)


def select_logs(sources: list[str], runs: list[str] | None, max_replays: int) -> tuple[list[dict], list[str]]:
    """Collect complete logs. With `runs`, only those ids; otherwise the most informative runs (attackers present,
    several rounds), at most one per (strategy, topology, attack, f, modules) cell before repeating a cell."""
    files: list[Path] = []
    for s in sources:
        p = Path(s)
        if p.is_dir():
            files += sorted(q for q in p.glob("*.jsonl") if not q.name.startswith("_"))
        elif p.is_file():
            files.append(p)
    skipped, logs = [], []
    for f in files:
        if runs and f.stem not in runs:
            continue
        try:
            lg = read_log(f)
        except (json.JSONDecodeError, OSError) as e:
            skipped.append(f"{_rel(f)}: {type(e).__name__}")
            continue
        if lg is None:
            skipped.append(f"{_rel(f)}: incomplete")
            continue
        logs.append(lg)
    if runs:
        order = {r: i for i, r in enumerate(runs)}
        return sorted(logs, key=lambda lg: order.get(lg["path"].stem, 0))[:max_replays], skipped
    logs.sort(key=_interest, reverse=True)
    first, rest, seen = [], [], set()
    for lg in logs:
        c = lg["head"]["config"]
        key = (c.get("strategy"), c.get("topology"), c.get("attack"), c.get("f"), tuple(c.get("modules") or []))
        (rest if key in seen else first).append(lg)
        seen.add(key)
    return (first + rest)[:max_replays], skipped


# ---------------------------------------------------------------- main

def export_site(results: str, logs: list[str] | None = None, figures: str | None = None, out: str = "site",
                runs: list[str] | None = None, max_replays: int = 12) -> dict:
    res = json.loads(Path(results).read_text())
    out_p = Path(out)
    data = out_p / "data"
    for d in (data, out_p / "figures"):
        if d.exists():
            shutil.rmtree(d)
    data.mkdir(parents=True)

    cells = res.pop("cells", None) or {}
    figs = copy_figures(res, figures, out_p)
    res["figures"] = figs
    dump(data / "results.json", res)
    dump(data / "cells.json", cells)
    dump(data / "labels.json", labels())

    chosen, skipped = select_logs(logs or [], runs, max_replays)
    index = []
    for lg in chosen:
        try:
            rp = build_replay(lg)
        except Exception as e:          # one malformed run must not stop the export
            skipped.append(f"{_rel(lg['path'])}: {type(e).__name__}: {e}")
            continue
        dump(data / "replays" / f"{rp['run_id']}.json", rp)
        c = rp["config"]
        index.append({"run_id": rp["run_id"], "file": f"data/replays/{rp['run_id']}.json",
                      "strategy": c["strategy"], "topology": c["topology"], "n_nodes": rp["n_nodes"],
                      "f_eff": rp["f_eff"], "attack": c["attack"], "modules": c["modules"], "seed": c["seed"],
                      "rounds": len(rp["rounds"]), "models": c["models"], "source_dir": str(Path(_rel(lg["path"])).parent)})
    dump(data / "replays" / "index.json", index)

    meta = res.get("meta") or {}
    manifest = {
        "exported": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results_file": _rel(Path(results)),
        "calibrated": bool(meta.get("calibrated")),
        "results_generated": meta.get("generated"),
        "inputs": meta.get("inputs"),
        "params": meta.get("params"),
        "llm_primary_model": meta.get("llm_primary_model"),
        "abm_rows": meta.get("abm_rows"),
        "llm_rows": meta.get("llm_rows"),
        "cells": {k: (len(v["rows"]) if v else None) for k, v in cells.items()},
        "replays": len(index),
        "log_sources": [_rel(Path(s)) for s in (logs or [])],
        "skipped_logs": skipped,
        "figures": sorted(k for k, v in figs.items() if "src" in v),
    }
    dump(data / "manifest.json", manifest)
    return manifest
