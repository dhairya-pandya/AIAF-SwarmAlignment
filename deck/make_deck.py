"""Short presentation deck (PDF) in the project design system, built from the video's slide renderer.

    python deck/make_deck.py   ->  deck/SwarmImmunity_slides.pdf (16:9, 9 slides)
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "video"))
import make_video as V  # noqa: E402
from design import mpl as D  # noqa: E402

OUT = ROOT / "deck"
BUILD = OUT / "build"
W, H = V.BASE_W, V.BASE_H
V.SUB_ZONE = 0.06   # no subtitles on slides: use more of the frame
V.SCENE_SPRITE.update({"title": "bee", "closing": "elephant", "takeaways": "bee", "earned": "elephant"})


def leaders_chart(path: Path) -> None:
    """Contamination with 3 of 12 agents compromised, leaderless vs led designs (pooled seeds, 95% CI)."""
    rows = [  # label, contamination, lo, hi, kind   (from the report's Table 1)
        ("Leaderless debate, everyone sees all evidence", 0.06, 0.00, 0.15, "safe"),
        ("Ant stigmergy (shared board)", 0.17, 0.09, 0.26, "safe"),
        ("Honeybee dance + quorum", 0.24, 0.11, 0.37, "safe"),
        ("Elephant matriarch: leaders by verified knowledge", 0.31, 0.07, 0.56, "mid"),
        ("Wolf pack + honeybee quorum", 0.36, 0.20, 0.54, "mid"),
        ("Wolf pack: leaders by self-reported confidence", 0.67, 0.50, 0.83, "bad"),
    ]
    D.apply("print", base=13)
    col = {"safe": D.PRINT.lime if hasattr(D.PRINT, "lime") else "#51a35e", "mid": "#c98a1a", "bad": D.VERMILION}
    fig, ax = plt.subplots(figsize=(12, 5.2))
    ys = range(len(rows))[::-1]
    for y, (lab, v, lo, hi, k) in zip(ys, rows):
        ax.barh(y, v, color=col[k], height=0.62)
        ax.errorbar(v, y, xerr=[[v - lo], [hi - v]], fmt="none", ecolor="#0b0908", elinewidth=1.4, capsize=4)
        ax.text(hi + 0.015, y, f"{v:.0%}", va="center", fontsize=14, fontweight="semibold")
    ax.set_yticks(list(ys), [r[0] for r in rows], fontsize=14)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Honest agents misled (contamination), 3 of 12 agents compromised", fontsize=13)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.axvline(0.18, color="#958e87", lw=1, ls="--")
    ax.text(0.185, len(rows) - 0.45, "chance floor", fontsize=11, color="#6b645e")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


SLIDES = [
    dict(id="title", type="title", kicker="Apart × AIAF Swarm Alignment Hackathon · 2026",
         title="Swarm Immunity", subtitle="How nature's collectives inspire defences for agentic AI",
         author="Dhairya Pandya", affiliation="IIITDM Jabalpur"),
    dict(id="problem", type="bullets", kicker="The problem",
         heading="A few compromised agents can mislead a whole swarm",
         bullets=["LLM agents increasingly work in groups: they debate, share boards and follow leaders",
                  "One compromised minority can feed the group false information",
                  "The honest majority's own coordination rules then spread it",
                  "Contamination = share of honest agents misled. Which designs resist it?"]),
    dict(id="idea", type="bullets", kicker="Approach",
         heading="Borrow nature's coordination and its immune-like defences",
         bullets=["13 coordination designs from ants, honeybees, wolves, birds, fireflies, vampire bats and elephants",
                  "6 bio-inspired defences: evaporation, stop signals, quorum, dilution, diversity, sparse wiring",
                  "A hidden-profile task: nobody can answer alone, so agents must pool facts",
                  "Pre-registered hypotheses, with key effects re-tested on fresh seeds"]),
    dict(id="method", type="image", heading="Experiments",
         image=str((ROOT / "figures/paper/fig0_overview.png").relative_to(ROOT)),
         caption="483 LLM swarm runs (gpt-oss-120b, 12 agents) · 327,600 agent-based twin runs · 5 attacks · "
                 "5 topologies · red-team search for worst-case attacks · every run replays byte-for-byte"),
    dict(id="leaders", type="image", heading="Finding 1: leaderless evidence-sharing is safest",
         image="deck/build/leaders_chart.png",
         caption="Leaderless debate vs wolf pack: −0.62 [−0.81, −0.41], confirmed on fresh seeds (p < 0.001). "
                 "Bars: pooled seeds, 95% CI."),
    dict(id="earned", type="bullets", kicker="Finding 2",
         heading="Leadership is safe only when it is earned",
         bullets=["Leaders elected by self-reported confidence are captured: attackers claim confidence and lead",
                  "Honeybee quorum (switch only on corroborated first-hand evidence) halves capture, at no accuracy cost (confirmed)",
                  "Elephant-style leaders, chosen by knowledge others confirm, cut capture from 70% to 31%",
                  "Pheromone-style evaporation backfires: it penalises honest agents who update"]),
    dict(id="transfer", type="image", heading="Finding 3: classical swarm theory does not transfer",
         image=str((ROOT / "figures/fig7_abm_vs_llm.png").relative_to(ROOT)),
         bullets=["The calibrated swarm model overestimated LLM contamination by 35 points",
                  "It could not rank which conditions were safer (rank correlation about zero)",
                  "Dense networks protect reasoning agents: they check evidence instead of averaging opinions"]),
    dict(id="takeaways", type="bullets", kicker="For people building agent swarms",
         heading="Route evidence to everyone; make authority earned",
         bullets=["Prefer leaderless designs that share first-hand evidence with every agent",
                  "Never elect leaders by self-reported confidence; use verified knowledge",
                  "Add a corroboration quorum before agents change their minds",
                  "Test defences on the real agents: simulations mis-rank the risk"]),
    dict(id="closing", type="title", kicker="Report, code, logs and replay viewer",
         title="github.com/dhairya-pandya/AIAF-SwarmAlignment",
         subtitle="Interactive results: swarm-immunity.vercel.app", author="Dhairya Pandya",
         affiliation="IIITDM Jabalpur · Apart × AIAF Swarm Alignment Hackathon 2026"),
]


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    leaders_chart(BUILD / "leaders_chart.png")
    pages = []
    for k, s in enumerate(SLIDES):
        out = BUILD / f"{k:02d}_{s['id']}.png"
        {"title": V.render_title, "bullets": V.render_bullets, "image": V.render_image}[s["type"]](s, W, H, out)
        pages.append(Image.open(out).convert("RGB"))
    pdf = OUT / "SwarmImmunity_slides.pdf"
    pages[0].save(pdf, save_all=True, append_images=pages[1:], resolution=150.0,
                  title="Swarm Immunity: How Nature's Collectives Inspire Defences for Agentic AI", author="Dhairya Pandya")
    print(f"{len(pages)} slides -> {pdf} ({pdf.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
