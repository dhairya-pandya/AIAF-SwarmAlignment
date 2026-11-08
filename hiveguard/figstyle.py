"""Shared figure style for the report and the analysis figures.

One place for fonts, sizes, the colour-blind-safe palette (Okabe-Ito) and the semantic colours that every
figure reuses, so the same thing has the same colour everywhere:

- correct choice: blue; attackers' target / contamination: vermillion; attackers: black; other: grey;
- strategies: coloured by metaphor family (the H10 grouping);
- modules, searchers and swarm sizes N: fixed colours.

Sizes are print sizes in inches (full column 6.5, half column 3.2), so the font sizes below are the sizes
on paper. Every figure is written as a 300-dpi PNG and a vector PDF with the same stem.
"""
from __future__ import annotations

from pathlib import Path

FULL = 6.5      # single-column text width (in)
HALF = 3.2      # half width (in)
DPI = 300

# Okabe & Ito (2008) colour-blind-safe palette
BLUE, ORANGE, GREEN, VERMILLION = "#0072B2", "#E69F00", "#009E73", "#D55E00"
PURPLE, SKY, YELLOW, BLACK = "#CC79A7", "#56B4E9", "#F0E442", "#000000"
GREY, LIGHT, INK = "#8C8C8C", "#D9D9D9", "#222222"
OKABE = [BLUE, ORANGE, GREEN, VERMILLION, PURPLE, SKY, BLACK, YELLOW]

# semantic colours
CORRECT, TARGET, ATTACKER, OTHER = BLUE, VERMILLION, BLACK, "#C8C8C8"
CON_C, ACC_C = VERMILLION, BLUE          # contamination vs accuracy quantities
LLM_C = BLACK                            # LLM observations (ABM lines are coloured)

FAMILY_COLOR = {"baseline": GREY, "abstract": BLUE, "insects": ORANGE, "wolves": PURPLE,
                "fireflies": GREEN, "birds": SKY}
MODULE_COLOR = {"none": BLACK, "M1": SKY, "M2": GREEN, "M3": ORANGE, "M4": PURPLE, "M5": BLUE, "M6": VERMILLION}
MODULE_MARKER = {"none": "o", "M1": "v", "M2": "s", "M3": "D", "M4": "^", "M5": "P", "M6": "X"}
MODULE_NAME = {"M1": "evaporation", "M2": "stop signals", "M3": "quorum", "M4": "dilution",
               "M5": "model diversity", "M6": "sparse topology"}
MODULE_SHORT = {"M1": "evap.", "M2": "stop", "M3": "quorum", "M4": "dilution", "M5": "diversity",
                "M6": "sparse"}
SEARCHER_COLOR = {"random": GREY, "hub": SKY, "ga": GREEN, "bpso": ORANGE, "map_elites": PURPLE}
SEARCHER_NAME = {"random": "random", "hub": "greedy hub", "ga": "GA", "bpso": "binary PSO", "map_elites": "MAP-Elites"}
N_COLOR = {12: BLUE, 50: ORANGE, 200: GREEN}
TOPO_NAME = {"ring": "ring", "small_world": "small-world", "scale_free": "scale-free", "star": "star", "full": "full"}

# plain names and inspirations (DESIGN §6.2); family = metaphor family used for H10 (analysis.FAMILY)
STRATEGY_NAME = {
    "S0a": "Oracle", "S0b": "Solo", "S1": "Independent + majority", "S2": "Free debate",
    "S3": "Particle swarm (PSO)", "S4": "Ant-colony stigmergy", "S5": "Artificial bee colony",
    "S6": "Firefly attraction", "S7": "Grey-wolf hierarchy", "S8": "Boids", "S9": "Honeybee nest-site",
    "S10": "Response threshold"}
STRATEGY_SHORT = {
    "S0a": "oracle", "S0b": "solo", "S1": "majority", "S2": "debate", "S3": "PSO", "S4": "ACO",
    "S5": "bee colony", "S6": "firefly", "S7": "grey wolf", "S8": "boids", "S9": "honeybee",
    "S10": "resp. threshold"}
INSPIRATION = {
    "S0a": "baseline: all facts", "S0b": "baseline: own facts", "S1": "baseline: voting",
    "S2": "group deliberation", "S3": "flocking, abstracted", "S4": "ant pheromone trails",
    "S5": "honeybee foraging", "S6": "firefly flashing", "S7": "wolf-pack hierarchy",
    "S8": "bird flocking", "S9": "honeybee nest-site choice", "S10": "insect division of labour"}


def family(s: str) -> str:
    from .analysis import FAMILY
    return FAMILY.get(s, "baseline")


def strategy_color(s: str) -> str:
    return FAMILY_COLOR[family(s)]


def strategy_label(s: str) -> str:
    return f"{s} {STRATEGY_SHORT.get(s, '')}".strip()


def module_label(m: str) -> str:
    return "none" if m == "none" else f"{m} {MODULE_NAME.get(m, '')}".strip()


RC = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8.5, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8, "legend.title_fontsize": 8, "figure.titlesize": 9,
    "axes.titleweight": "normal", "axes.titlepad": 4, "axes.labelpad": 2.5,
    "axes.linewidth": 0.6, "axes.edgecolor": INK, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK, "ytick.color": INK, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "xtick.major.pad": 2, "ytick.major.pad": 2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "grid.color": "#E6E6E6", "grid.linewidth": 0.5,
    "lines.linewidth": 1.2, "lines.markersize": 4, "patch.linewidth": 0.5,
    "legend.frameon": False, "legend.handlelength": 1.4, "legend.handletextpad": 0.4,
    "legend.columnspacing": 1.0, "legend.borderaxespad": 0.3, "legend.labelspacing": 0.3,
    "figure.dpi": 150, "savefig.dpi": DPI, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "image.cmap": "cividis",
}


def apply():
    """Set the house style and return pyplot (Agg backend)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update(RC)
    plt.rcParams["axes.prop_cycle"] = matplotlib.cycler(color=OKABE)
    return plt


def save(fig, path: str | Path, pdf: bool = True) -> Path:
    """Write <stem>.png (300 dpi) and <stem>.pdf next to it; closes the figure. Returns the PNG path."""
    import matplotlib.pyplot as plt
    p = Path(path).with_suffix(".png")
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=DPI)
    if pdf:
        fig.savefig(p.with_suffix(".pdf"))
    plt.close(fig)
    return p


def ygrid(ax) -> None:
    """Light horizontal reference grid only."""
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)


def panel_label(ax, s: str, x: float = -0.02, y: float = 1.02) -> None:
    ax.text(x, y, s, transform=ax.transAxes, fontsize=9, fontweight="bold", ha="right", va="bottom")
