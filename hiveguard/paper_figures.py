"""Report-only figures that do not depend on experiment results (DESIGN §5–§9):

- fig0_overview:           method overview (task -> swarm under attack -> strategy -> modules -> metrics,
                           plus the red-team loop on the ABM twin and the LLM transfer check);
- fig_strategy_components: the strategy taxonomy and component matrix used for H10;
- fig_cascade_abm:         one ABM run drawn round by round on its graph (illustration only).

Every data-bearing element is computed from the code: the task glyph is a real generated instance, the
graphs come from topology.py, the component matrix from analysis.COMPONENTS, and the cascade from ABMSim.
The only schematic element is the tipping-point sketch in fig0, which is labelled as such.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import figstyle as S
from .abm import ABMParams, ABMSim
from .analysis import COMP_COLS, COMPONENTS, FAMILY
from .config import RunConfig
from .world import build_world

CASCADE = dict(strategy="S2", topology="small_world", n_agents=50, f=0.1, attack="A2", seed=0)


# ---------------------------------------------------------------- helpers

def _box(ax, x, y, w, h, title=None, fc=S.PAPER, ec=S.INK, lw=0.7, title_color=S.INK, r=0.0):
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}" if r else "square,pad=0", fc=fc, ec=ec, lw=lw,
                                zorder=1))
    if title:
        ax.text(x + 0.08, y + h - 0.08, title, ha="left", va="top", fontsize=8.5, fontweight="semibold",
                color=title_color, zorder=3)


def _arrow(ax, p, q, color=S.INK, lw=0.9, style="-|>", rad=0.0, ms=7, ls="-"):
    from matplotlib.patches import FancyArrowPatch
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=ms, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0, zorder=4))


def _draw_graph(ax, G, pos, colors, attackers, node_size=14, edge_lw=0.35, att_marker="s"):
    for u, v in G.edges():
        ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]], color=S.LIGHT, lw=edge_lw, zorder=1)
    nodes = np.arange(G.number_of_nodes())
    hon = [i for i in nodes if i not in set(attackers)]
    P = np.array([pos[i] for i in nodes])
    ax.scatter(P[hon, 0], P[hon, 1], s=node_size, c=[colors[i] for i in hon], edgecolors=S.PAPER, linewidths=0.3,
               zorder=2)
    if len(attackers):
        A = P[list(attackers)]
        ax.scatter(A[:, 0], A[:, 1], s=node_size * 1.15, c=S.ATTACKER, marker=att_marker, edgecolors=S.PAPER,
                   linewidths=0.3, zorder=3)


def _circle_pos(n, r=1.0, phase=np.pi / 2):
    a = phase - 2 * np.pi * np.arange(n) / n
    return {i: (r * np.cos(a[i]), r * np.sin(a[i])) for i in range(n)}


# ---------------------------------------------------------------- Fig. 0: overview

def _polyarrow(ax, pts, color=S.INK, lw=0.9, ls="-", ms=6):
    """Polyline with an arrow head on the last segment."""
    xs, ys = zip(*pts[:-1])
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=4, solid_capstyle="butt")
    _arrow(ax, pts[-2], pts[-1], color=color, lw=lw, ms=ms)


def fig_overview(plt, path: Path) -> None:
    W, H = S.FULL, 3.45
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    # top row: five stages
    widths, gap, top_y, bh = [1.16, 1.16, 1.36, 1.30, 1.02], 0.12, 1.42, 1.98
    xs = [0.01 + sum(widths[:i]) + gap * i for i in range(5)]
    titles = ["1  Hidden profile", "2  Swarm + attack", "3  Coordination", "4  Defences", "5  Metrics"]
    for x, w, t in zip(xs, widths, titles):
        _box(ax, x, top_y, w, bh, t)
    for i in range(4):
        _arrow(ax, (xs[i] + widths[i] + 0.01, top_y + bh / 2), (xs[i + 1] - 0.01, top_y + bh / 2), ms=6)
    row = lambda k: top_y + 1.30 - k * 0.165       # list rows shared by boxes 3 and 4

    # 1: a real task instance (seed 0, N=12): one agent's private view vs the pooled view
    world = build_world(RunConfig(seed=0))
    task = world.task
    agent = next(i for i in range(world.N) if world.holdings[i]
                 and int(np.argmax(task.partial_scores(world.holdings[i]))) != task.correct)
    views = [("one agent's facts", task.partial_scores(world.holdings[agent])),
             (f"all {len(task.facts)} facts pooled", task.partial_scores(range(len(task.facts))))]
    x0, w0 = xs[0], widths[0]
    for j, (lab, sc) in enumerate(views):
        yb = top_y + 1.17 - j * 0.66
        ia = fig.add_axes([(x0 + 0.22) / W, yb / H, (w0 - 0.44) / W, 0.36 / H])
        best = int(np.argmax(sc))
        ia.bar(range(len(sc)), sc - sc.min() + 0.15 * (np.ptp(sc) or 1), width=0.7,
               color=[S.CORRECT if o == task.correct else S.OTHER for o in range(len(sc))],
               edgecolor=[S.INK if o == best else "none" for o in range(len(sc))], linewidth=0.9)
        ia.set_xticks(range(len(sc)), [task.option_id(o) for o in range(len(sc))])
        ia.set_yticks([])
        ia.tick_params(length=0, pad=1)
        for sp in ("left", "top", "right"):
            ia.spines[sp].set_visible(False)
        ia.spines["bottom"].set_linewidth(0.5)
        ia.set_title(lab, fontsize=8, pad=1.5)
    ax.text(x0 + 0.08, top_y + 0.06, "outlined: best guess\nblue: correct option", fontsize=8, va="bottom")

    # 2: a real N=12 small-world instance with f = 3/12 compromised agents
    x1, w1 = xs[1], widths[1]
    sw = build_world(RunConfig(topology="small_world", f=3 / 12, seed=0))
    pos = _circle_pos(sw.N, r=0.30)
    pos = {k: (x1 + w1 / 2 + v[0], top_y + 1.33 + v[1]) for k, v in pos.items()}
    _draw_graph(ax, sw.G, pos, {i: S.CORRECT for i in range(sw.N)}, list(sw.attackers), node_size=20, edge_lw=0.5)
    ax.scatter([x1 + 0.12], [top_y + 0.905], s=14, marker="s", c=S.ATTACKER, zorder=3)
    ax.text(x1 + 0.2, top_y + 0.96, "compromised\n(fraction f):", fontsize=8, va="top")
    for k, s in enumerate(["A1 confident liar", "A2 fake evidence", "A3 sleeper", "A4 sybil", "A5 max confidence"]):
        ax.text(x1 + 0.08, top_y + 0.66 - k * 0.12, s, fontsize=8, va="top")

    # 3: strategy families (metaphor families of H10)
    x2, w2 = xs[2], widths[2]
    ax.text(x2 + 0.08, top_y + bh - 0.27, "LLM agents + ABM twin", fontsize=8, va="top")
    fam_lines = [("baseline", "base", "S0a S0b"), ("abstract", "abstract", "S1 S2 S3"),
                 ("insects", "insects", "S4 S5 S9 S10"), ("wolves", "wolves", "S7"),
                 ("fireflies", "fireflies", "S6"), ("birds", "birds", "S8")]
    for k, (f, lab, members) in enumerate(fam_lines):
        y = row(k)
        ax.scatter([x2 + 0.13], [y - 0.05], s=16, marker="s", c=S.FAMILY_COLOR[f], zorder=3, linewidths=0)
        ax.text(x2 + 0.21, y, lab, fontsize=8, va="top")
        ax.text(x2 + w2 - 0.07, y, members, fontsize=8, va="top", ha="right")
    ax.text(x2 + 0.08, top_y + 0.06, "5 topologies: ring …\nfully connected", fontsize=8, va="bottom")

    # 4: modules
    x3, w3 = xs[3], widths[3]
    ax.text(x3 + 0.08, top_y + bh - 0.27, "add-on negative\nfeedback", fontsize=8, va="top")
    for k, m in enumerate(["M1", "M2", "M3", "M4", "M5", "M6"]):
        y = row(k)
        ax.scatter([x3 + 0.13], [y - 0.05], s=16, marker=S.MODULE_MARKER[m], c=S.MODULE_COLOR[m], zorder=3,
                   linewidths=0)
        ax.text(x3 + 0.21, y, f"{m} {S.MODULE_NAME[m]}", fontsize=8, va="top")
    ax.text(x3 + 0.08, top_y + 0.06, "cost = accuracy\nlost at f = 0", fontsize=8, va="bottom")

    # 5: metrics with a schematic tipping curve
    x4, w4 = xs[4], widths[4]
    ia = fig.add_axes([(x4 + 0.2) / W, (top_y + 1.0) / H, (w4 - 0.3) / W, 0.55 / H])
    fx = np.linspace(0, 0.4, 100)
    ia.plot(fx, 1 / (1 + np.exp(-(fx - 0.18) / 0.03)), color=S.CON_C, lw=1.1)
    ia.axvline(0.18, color=S.GREY, lw=0.6, ls="--")
    ia.axhline(0.5, color=S.GREY, lw=0.6, ls=":")
    ia.text(0.195, 0.02, "f*", fontsize=8)
    ia.set_xticks([])
    ia.set_yticks([])
    ia.set_xlabel("f", fontsize=8, labelpad=1)
    ia.set_ylabel("Con", fontsize=8, labelpad=1)
    ia.set_title("SCHEMATIC", fontsize=8, color=S.MUTED, family=S.MONO, fontweight="normal", pad=1)
    for sp in ("top", "right"):
        ia.spines[sp].set_visible(False)
    for k, (a, b) in enumerate([("Acc", "correct"), ("Con", "on target"), ("f*", "tipping"), ("T50", "speed")]):
        y = top_y + 0.66 - k * 0.15
        ax.text(x4 + 0.08, y, a, fontsize=8, va="top", fontweight="semibold", color=S.CON_C if a == "Con" else S.INK)
        ax.text(x4 + 0.40, y, b, fontsize=8, va="top")

    # bottom row: red-team loop on the ABM twin -> transfer check on the LLM swarm
    by, bh2 = 0.01, 1.14
    rx, rw = 0.01, 4.08
    _box(ax, rx, by, rw, bh2, "Red team: worst-case attacks searched on the ABM twin", fc=S.CARD, ec=S.GREY)
    iw, ih, iy = 1.2, 0.70, by + 0.205
    items = [(rx + 0.1, "searcher", "random, greedy hub,\nGA, binary PSO,\nMAP-Elites"),
             (rx + 0.1 + iw + 0.14, "proposes attack", "attacker nodes ×\nonset round ×\nattack A1–A5"),
             (rx + 0.1 + 2 * (iw + 0.14), "ABM twin scores it", "fitness = mean Con\nover 5 seeds;\nκ, λ fit on LLM pilot")]
    for k, (x, t, d) in enumerate(items):
        _box(ax, x, iy, iw, ih, None, fc=S.PAPER, ec=S.INK, lw=0.6)
        ax.text(x + iw / 2, iy + ih - 0.05, t, fontsize=8, fontweight="semibold", ha="center", va="top")
        ax.text(x + iw / 2, iy + ih - 0.20, d, fontsize=8, ha="center", va="top", linespacing=1.05)
        if k < 2:
            _arrow(ax, (x + iw + 0.01, iy + ih / 2), (items[k + 1][0] - 0.01, iy + ih / 2), ms=6)
    fy = by + 0.115
    _polyarrow(ax, [(items[2][0] + iw / 2, iy), (items[2][0] + iw / 2, fy), (items[0][0] + iw / 2, fy),
                    (items[0][0] + iw / 2, iy - 0.005)], color=S.GREY)
    ax.text((items[0][0] + items[2][0] + iw) / 2, fy, " next proposal (500 evaluations × 10 repeats) ",
            fontsize=8, ha="center", va="center", color=S.MUTED, zorder=6,
            bbox=dict(fc=S.CARD, ec="none", pad=0.5))

    tx = rx + rw + 0.14
    tw = W - tx - 0.01
    _box(ax, tx, by, tw, bh2, "Transfer check")
    ax.text(tx + 0.08, by + bh2 - 0.28, "top attack of each\nsearcher re-run on\nthe LLM swarm (most\n"
            "and least robust\nstrategy, 6 seeds)", fontsize=8, va="top", linespacing=1.05)
    _arrow(ax, (rx + rw + 0.01, by + bh2 / 2), (tx - 0.01, by + bh2 / 2), ms=6)
    # LLM confirmation results feed back to the swarm stage (dashed): route through the gap between rows
    gy = (by + bh2 + top_y) / 2
    _polyarrow(ax, [(tx + tw / 2, by + bh2), (tx + tw / 2, gy), (xs[1] + w1 / 2, gy), (xs[1] + w1 / 2, top_y - 0.005)],
               ls=(0, (3, 2)), lw=0.8)
    S.save(fig, path)


# ---------------------------------------------------------------- strategy taxonomy / component matrix

COMP_LABEL = {"direct": "Direct messages", "medium": "Shared medium", "memory": "Memory",
              "hierarchy": "Hierarchy", "decay": "Distance decay", "roles": "Roles",
              "negfb": "Negative feedback", "quorum": "Quorum"}
# kind of negative feedback, from DESIGN §6.3 (the code stores the binary flag only)
NEGFB_KIND = {"S4": "evaporation", "S5": "abandon", "S8": "separation", "S9": "decay+stop", "S10": "verify",
              "S11": "trust decay"}
FAMILY_ORDER = ["baseline", "abstract", "insects", "wolves", "fireflies", "birds", "mammals"]
INSP_SHORT = {"S0a": "upper bound", "S0b": "lower bound", "S1": "voting", "S2": "deliberation",
              "S3": "flocking, abstracted", "S4": "ant pheromone trails", "S5": "bee foraging",
              "S6": "firefly flashing", "S7": "wolf-pack ranks", "S8": "bird flocking", "S9": "bee nest-site choice",
              "S10": "insect task roles", "S11": "vampire-bat sharing"}


def strategy_rows() -> list[tuple[str, str]]:
    """(strategy, family) in display order: baselines first, then H10 metaphor families."""
    rows = [("S0a", "baseline"), ("S0b", "baseline")]
    for fam in FAMILY_ORDER[1:]:
        members = [s for s in COMPONENTS if FAMILY[s] == fam]
        rows += [(s, fam) for s in sorted(members, key=lambda s: int(s[1:]))]
    return rows


def fig_components(plt, path: Path) -> None:
    from matplotlib.patches import Rectangle
    rows = strategy_rows()
    nR = len(rows)
    rh, head = 0.215, 0.98
    W = S.FULL
    H = head + nR * rh + 0.02
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    x_bar, x_fam, x_id, x_name, x_insp = 0.01, 0.09, 0.67, 0.98, 2.27
    cws = [0.74 if c == "negfb" else 0.33 for c in COMP_COLS]
    x_grid = W - 0.01 - sum(cws)
    cx = [x_grid + sum(cws[:j]) for j in range(len(cws))]
    hy = head - 0.05
    for x, t in [(x_fam, "Family"), (x_id, "ID"), (x_name, "Strategy"), (x_insp, "Inspiration")]:
        ax.text(x, hy, t, fontsize=8, fontweight="semibold", va="bottom")
    for j, c in enumerate(COMP_COLS):
        ax.text(cx[j] + cws[j] / 2, hy, COMP_LABEL[c], fontsize=8, fontweight="semibold", ha="center", va="bottom",
                rotation=90)
    ax.plot([0.01, W - 0.01], [head, head], color=S.INK, lw=0.6)
    y, prev = head, None
    spans: dict[str, list[float]] = {}
    for s, fam in rows:
        if prev is not None and fam != prev:
            ax.plot([x_fam, W - 0.01], [y, y], color=S.LIGHT, lw=0.5)
        prev = fam
        spans.setdefault(fam, [y, y])[1] = y + rh
        cy = y + rh / 2
        if spans[fam][0] == y:
            ax.text(x_fam, cy, fam, fontsize=8, va="center", color=S.FAMILY_COLOR[fam], fontweight="semibold")
        ax.text(x_id, cy, S.strategy_id(s), fontsize=8, va="center", family=S.MONO)
        ax.text(x_name, cy, S.STRATEGY_NAME[s], fontsize=8, va="center")
        ax.text(x_insp, cy, INSP_SHORT[s], fontsize=8, va="center", color=S.MUTED)
        code = COMPONENTS.get(s)
        for j, c in enumerate(COMP_COLS):
            x, cw = cx[j], cws[j]
            if code is None:      # S0a/S0b are not in the H10 component matrix
                ax.add_patch(Rectangle((x + 0.025, y + 0.025), cw - 0.05, rh - 0.05, fc=S.PAPER, ec=S.LIGHT,
                                       lw=0.5, hatch="/////", zorder=1))
                continue
            on = code[j] == "1"
            ax.add_patch(Rectangle((x + 0.025, y + 0.025), cw - 0.05, rh - 0.05, fc=S.INK if on else S.OFF,
                                   ec="none", zorder=1))
            if on and c == "negfb" and s in NEGFB_KIND:
                ax.text(x + cw / 2, cy, NEGFB_KIND[s], fontsize=8, ha="center", va="center", color=S.PAPER)
        y += rh
    for fam, (y0, y1) in spans.items():
        ax.add_patch(Rectangle((x_bar, y0 + 0.025), 0.04, y1 - y0 - 0.05, fc=S.FAMILY_COLOR[fam], ec="none"))
    ax.plot([0.01, W - 0.01], [y, y], color=S.INK, lw=0.6)
    S.save(fig, path)


# ---------------------------------------------------------------- example contamination cascade (ABM)

def cascade_data(params: ABMParams | None = None, **over) -> dict:
    cfg = RunConfig(**{**CASCADE, **over})
    sim = ABMSim(cfg, params or ABMParams())
    m = sim.run()
    w = sim.world
    return {"cfg": cfg, "world": w, "choices": m["choices"], "metrics": m}


def fig_cascade(plt, path: Path, params: ABMParams | None = None, **over) -> dict:
    from matplotlib.lines import Line2D
    d = cascade_data(params, **over)
    w, ch, cfg = d["world"], d["choices"], d["cfg"]
    R, N = ch.shape
    hon = w.honest
    pos = _circle_pos(N)
    acc = [(ch[r][hon] == w.task.correct).mean() for r in range(R)]
    con = [(ch[r][hon] == w.target).mean() for r in range(R)]

    fig = plt.figure(figsize=(S.FULL, 2.95))
    gs = fig.add_gridspec(1, R, wspace=0.02, left=0.085, right=0.995, top=0.88, bottom=0.42)
    for r in range(R):
        ax = fig.add_subplot(gs[0, r])
        cols = {i: (S.CORRECT if ch[r, i] == w.task.correct else S.TARGET if ch[r, i] == w.target else S.OTHER)
                for i in range(N)}
        _draw_graph(ax, w.G, pos, cols, list(w.attackers), node_size=9, edge_lw=0.3)
        ax.set_aspect("equal")
        ax.set_xlim(-1.08, 1.08)
        ax.set_ylim(-1.08, 1.08)
        ax.axis("off")
        ax.set_title(f"ROUND {r}", fontsize=8, pad=1, family=S.MONO, fontweight="normal")
        ax.text(0.5, -0.06, f"Con = {con[r]:.2f}", transform=ax.transAxes, fontsize=8, ha="center", va="top",
                color=S.TARGET)
    # line plot narrower than the graph row, so its legend sits outside the data area and never covers a line
    gl = fig.add_gridspec(1, 1, left=0.085, right=0.72, top=0.25, bottom=0.115)
    ax = fig.add_subplot(gl[0, 0])
    rr = np.arange(R)
    ax.plot(rr, acc, "-o", color=S.CORRECT, ms=3.5, label="correct option (Acc)")
    ax.plot(rr, con, "--s", color=S.TARGET, ms=3.5, label="attackers' target (Con)")
    ax.set_xticks(rr, [str(r) for r in rr])
    ax.set_xlim(-0.3, R - 0.7)
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.5, 1])
    ax.set_xlabel("Round")
    ax.set_ylabel("Share of\nhonest agents")
    fig.text(0.085, 0.31, f"ABM illustration, not LLM data: {cfg.strategy} {S.STRATEGY_NAME[cfg.strategy].lower()}, "
             f"{S.TOPO_NAME[cfg.topology]}, N = {cfg.n_agents}, f = {cfg.f:g} ({len(w.attackers)} attackers), "
             f"{cfg.attack}, seed {cfg.seed}", ha="left", va="bottom", fontsize=8, color=S.MUTED)
    S.ygrid(ax)
    h = [Line2D([], [], ls="", marker="o", ms=4, color=S.CORRECT, label="honest: correct option"),
         Line2D([], [], ls="", marker="o", ms=4, color=S.TARGET, label="honest: attackers' target"),
         Line2D([], [], ls="", marker="o", ms=4, color=S.OTHER, label="honest: other option"),
         Line2D([], [], ls="", marker="s", ms=4, color=S.ATTACKER, label="compromised (A2)")]
    fig.legend(handles=h, loc="upper center", ncol=4, bbox_to_anchor=(0.54, 1.0), handletextpad=0.1)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=1)
    S.save(fig, path)
    m = d["metrics"]
    return {"config": cfg.to_dict(), "n_attackers": int(len(w.attackers)), "honest": int(hon.sum()),
            "acc_by_round": [round(float(a), 4) for a in acc], "con_by_round": [round(float(c), 4) for c in con],
            "final": {k: _jsonable(v) for k, v in m.items() if k != "choices"}}


def _jsonable(v):
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, float, np.integer, np.floating)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_jsonable(x) for x in v]
    return v


# ---------------------------------------------------------------- driver

def make_all(out: str = "figures/paper", params: ABMParams | None = None) -> dict:
    import json
    plt = S.apply()
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    res = {}
    fig_overview(plt, o / "fig0_overview.png")
    res["fig0_overview"] = str(o / "fig0_overview.png")
    fig_components(plt, o / "fig_strategy_components.png")
    res["fig_strategy_components"] = str(o / "fig_strategy_components.png")
    res["fig_cascade_abm"] = str(o / "fig_cascade_abm.png")
    res["cascade"] = fig_cascade(plt, o / "fig_cascade_abm.png", params)
    res["cascade"]["abm_params"] = (params or ABMParams()).to_dict()
    (o / "paper_figures.json").write_text(json.dumps(res, indent=1, default=str))
    return res
