"""Shared figure style for the report and the analysis figures.

The look comes from the project's design system (design/mpl.py, light "print" theme): Instrument Sans for
text, Geist Mono for small labels, hard corners, and colour spent only where it carries meaning. One place
for sizes and the semantic colours every figure reuses, so the same thing has the same colour everywhere:

- contamination / attackers' target: vermilion; accuracy / correct choice: sky blue;
  safe / ok: lime; warning: amber; compromised agents: ink (near black) squares; other: warm grey;
- strategies: coloured by metaphor family (the H10 grouping);
- modules, searchers and swarm sizes N: fixed colours, each paired with a fixed marker or line style.

The state hues are the print variants (darker than the screen ones) so they hold contrast on white;
vermilion vs sky stays distinguishable under deuteranopia, protanopia and tritanopia, and every
pairing that could fail (vermilion vs lime) is always backed by a marker or line-style cue.

Sizes are print sizes in inches (full column 6.5, half column 3.2), so the font sizes below are the sizes
on paper (8 pt minimum). Every figure is written as a 300-dpi PNG and a vector PDF with the same stem.
If design/ is not importable the module falls back to the same colours with system fonts.
"""
from __future__ import annotations

import sys
from pathlib import Path

FULL = 6.5      # single-column text width (in)
HALF = 3.2      # half width (in)
DPI = 300

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
try:
    from design import mpl as _D
except Exception:  # pragma: no cover - design kit missing
    _D = None

# print-theme palette (design/mpl.py PRINT); literal values kept here so the module works without design/
VERMILLION = "#d9341b"                       # attack / contamination
BLUE = SKY = "#2f7fd6"                       # accuracy / correct
GREEN = LIME = "#51a35e"                     # safe / ok (CVD-checked against vermilion and amber)
ORANGE = AMBER = "#c98a00"                   # warning
PURPLE = VIOLET = "#7a5fd6"
TEAL, ROSE = "#14987f", "#cf4a86"
BLACK = INK = "#0b0908"
YELLOW = AMBER
GREY, LIGHT = "#8c8680", "#e3ded8"
MUTED = "#4f4943"                            # secondary text
PAPER = "#ffffff"
CARD = "#f5f2ee"                             # light panel fill
OFF = "#ece8e3"                              # unlit tile
OKABE = [BLUE, VERMILLION, GREEN, ORANGE, PURPLE, TEAL, BLACK, ROSE]   # categorical cycle (name kept for callers)

# semantic colours
CORRECT, TARGET, ATTACKER, OTHER = BLUE, VERMILLION, INK, "#cfc9c2"
CON_C, ACC_C = VERMILLION, BLUE          # contamination vs accuracy quantities
LLM_C = BLACK                            # LLM observations (ABM lines are coloured)

FAMILY_COLOR = {"baseline": GREY, "abstract": TEAL, "insects": AMBER, "wolves": VIOLET,
                "fireflies": LIME, "birds": ROSE, "bats": "#a0522d"}
MODULE_COLOR = {"none": BLACK, "M1": TEAL, "M2": LIME, "M3": AMBER, "M4": VIOLET, "M5": BLUE, "M6": ROSE}
MODULE_MARKER = {"none": "o", "M1": "v", "M2": "s", "M3": "D", "M4": "^", "M5": "P", "M6": "X"}
MODULE_NAME = {"M1": "evaporation", "M2": "stop signals", "M3": "quorum", "M4": "dilution",
               "M5": "model diversity", "M6": "sparse topology"}
MODULE_SHORT = {"M1": "evap.", "M2": "stop", "M3": "quorum", "M4": "dilution", "M5": "diversity",
                "M6": "sparse"}
SEARCHER_COLOR = {"random": GREY, "hub": TEAL, "ga": LIME, "bpso": AMBER, "map_elites": VIOLET}
SEARCHER_NAME = {"random": "random", "hub": "greedy hub", "ga": "GA", "bpso": "binary PSO", "map_elites": "MAP-Elites"}
N_COLOR = {12: VIOLET, 50: AMBER, 200: TEAL}
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


def _rc() -> dict:
    if _D is not None:
        rc = _D.rc("print", base=8.0)
        rc.pop("axes.titlelocation", None)       # figures place their own titles
        rc.update({"axes.titleweight": "semibold", "axes.edgecolor": INK, "savefig.pad_inches": 0.02,
                   "image.cmap": "cividis"})
        return rc
    return {
        "font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8.5, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "legend.fontsize": 8, "legend.title_fontsize": 8, "figure.titlesize": 9,
        "axes.linewidth": 0.6, "axes.edgecolor": INK, "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
        "grid.color": LIGHT, "grid.linewidth": 0.5, "legend.frameon": False,
        "savefig.dpi": DPI, "savefig.bbox": "tight", "savefig.pad_inches": 0.02, "pdf.fonttype": 42,
        "ps.fonttype": 42, "svg.fonttype": "none", "image.cmap": "cividis"}


RC = _rc()
MONO = list(RC.get("font.monospace", ["DejaVu Sans Mono"]))


def apply():
    """Set the house style and return pyplot (Agg backend)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import logging
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    if _D is not None:
        _D.register_fonts()
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
    ax.text(x, y, s, transform=ax.transAxes, fontsize=9, fontweight="semibold", ha="right", va="bottom")


def caps(ax, x, y, s: str, size: float = 8, color: str = MUTED, **kw):
    """Small uppercase Geist Mono label in axes coordinates (the design system's caption style)."""
    kw.setdefault("transform", ax.transAxes)
    return ax.text(x, y, str(s).upper(), fontsize=size, color=color, family=MONO, parse_math=False, **kw)
