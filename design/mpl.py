"""Matplotlib side of the project's design system.

Two themes share one typography and one set of colour meanings:

- ``screen``: warm-black plate for the video, the site and social posts;
- ``print``: white page for the PDF report, with the state hues darkened just enough to read on paper.

Colour meanings (identical in both themes):
    contamination / attackers' target / compromised  -> vermilion  (ATTACK)
    accuracy / correct choice                         -> sky        (CORRECT)
    safe / ok / supported                             -> lime       (OK)
    warning / inconclusive / exploratory              -> amber      (WARN)
Every other hue (teal, violet, rose, grey) is categorical only. Charts should still carry a redundant cue
(line style, marker, direct label) so nothing depends on colour alone.

Fonts: Instrument Sans for display and body, Geist Mono for small uppercase labels and tabular numbers.
Both ship in design/fonts (SIL OFL 1.1) and are registered with matplotlib on import of ``register_fonts``.
"""
from __future__ import annotations

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts"
SANS = "Instrument Sans"
MONO = "Geist Mono"
_FALLBACK_SANS = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
_FALLBACK_MONO = ["DejaVu Sans Mono"]

# ------------------------------------------------------------------ raw palette (screen values)
SURFACE, SUNKEN, CARD, RAISED = "#0b0908", "#060504", "#12100e", "#1a1715"
INK, MUTED, SUBTLE, FIELD = "#f2f0ed", "#bab4ad", "#958e87", "#6f6862"
RULE = "#ffffff21"
CHART_GRID = "#2a2522"

RED = ["#33100c", "#5c130e", "#8f150f", "#c4170f", "#e8361c", "#d6b48c", "#f2e9da"]   # mosaic ramp l1..l7
RED_1, RED_2, RED_3, RED_4, VERMILION, BONE, PAPER = RED
TEX = "#2b1411"

HUE = {"lime": "#a6dd62", "sky": "#6fb7ff", "amber": "#ffc95c", "coral": "#ff8a6b", "teal": "#4fd1b8",
       "violet": "#b19bff", "rose": "#ff86b4"}
HUE_DIM = {"lime": "#3a5220", "sky": "#213d5c", "amber": "#5a4319", "coral": "#5a2e24", "teal": "#1c4a42",
           "violet": "#3b3060", "rose": "#5a2640"}
OFF, FRAME, FRAME_DIM = "#1c1916", "#3b3530", "#27231f"

# print variants: same hue families, darker so they hold >=3:1 against white
PRINT_HUE = {"lime": "#51a35e", "sky": "#2f7fd6", "amber": "#c98a00", "coral": "#e0603d", "teal": "#14987f",
             "violet": "#7a5fd6", "rose": "#cf4a86"}
PRINT_VERMILION = "#d9341b"
PRINT_INK, PRINT_MUTED, PRINT_SUBTLE = "#0b0908", "#4f4943", "#7d766f"
PRINT_RULE, PRINT_GRID, PRINT_PAPER = "#d9d4cd", "#ebe7e1", "#ffffff"


class Theme:
    """Resolved colours for one theme. Attribute names are the semantic roles."""

    def __init__(self, name: str):
        self.name = name
        dark = name == "screen"
        h = HUE if dark else PRINT_HUE
        self.bg = SURFACE if dark else PRINT_PAPER
        self.card = CARD if dark else "#f7f4f0"
        self.ink = INK if dark else PRINT_INK
        self.muted = MUTED if dark else PRINT_MUTED
        self.subtle = SUBTLE if dark else PRINT_SUBTLE
        self.rule = "#3b3530" if dark else PRINT_RULE
        self.grid = CHART_GRID if dark else PRINT_GRID
        self.attack = VERMILION if dark else PRINT_VERMILION
        self.correct = h["sky"]
        self.ok = h["lime"]
        self.warn = h["amber"]
        self.teal, self.violet, self.rose, self.coral = h["teal"], h["violet"], h["rose"], h["coral"]
        self.lime, self.sky, self.amber = h["lime"], h["sky"], h["amber"]
        self.grey = "#8c8680" if not dark else "#7d766f"
        self.other = "#cfc9c2" if not dark else "#4a443f"     # 'other option' / neutral fill
        self.hue = dict(h)
        # categorical cycle: meanings first, then categorical-only hues
        self.cycle = [self.correct, self.attack, self.ok, self.warn, self.violet, self.teal, self.ink, self.rose]

    def __repr__(self) -> str:
        return f"Theme({self.name!r})"


SCREEN = Theme("screen")
PRINT = Theme("print")

# ------------------------------------------------------------------ fonts
_registered = False


def register_fonts() -> bool:
    """Add the bundled static TTFs to matplotlib's font manager. Returns True when they were found."""
    global _registered
    if _registered:
        return True
    from matplotlib import font_manager
    files = sorted(FONT_DIR.glob("InstrumentSans-*.ttf")) + sorted(FONT_DIR.glob("GeistMono-*.ttf"))
    for f in files:
        font_manager.fontManager.addfont(str(f))
    _registered = bool(files)
    return _registered


# ------------------------------------------------------------------ colormaps
def mosaic_cmap(theme: Theme | str = "print", reverse: bool = False):
    """Sequential map along the mosaic red ramp, monotone in lightness (safe for colour-vision deficiency).
    Print runs paper -> red-1 (light = low); screen runs red-1 -> paper (bright = high on the dark plate)."""
    from matplotlib.colors import LinearSegmentedColormap
    t = theme if isinstance(theme, Theme) else (SCREEN if theme == "screen" else PRINT)
    stops = ["#fbf7f1", PAPER, BONE, VERMILION, RED_3, RED_1] if t.name == "print" else \
        ["#1a0b09", RED_1, RED_3, VERMILION, BONE, PAPER]
    if reverse:
        stops = stops[::-1]
    return LinearSegmentedColormap.from_list(f"mosaic_{t.name}{'_r' if reverse else ''}", stops, N=256)


def _register_cmaps() -> None:
    import matplotlib
    for t in (SCREEN, PRINT):
        for rev in (False, True):
            cm = mosaic_cmap(t, rev)
            try:
                matplotlib.colormaps.register(cm, name=cm.name)
            except ValueError:
                pass


# ------------------------------------------------------------------ rcParams
def rc(theme: Theme | str = "print", base: float = 8.0) -> dict:
    """rcParams for a theme. ``base`` is the body size in points (8 for print columns, larger for screen)."""
    t = theme if isinstance(theme, Theme) else (SCREEN if theme == "screen" else PRINT)
    have = register_fonts()
    sans = ([SANS] if have else []) + _FALLBACK_SANS
    mono = ([MONO] if have else []) + _FALLBACK_MONO
    return {
        # a family list (not "sans-serif") lets matplotlib fall back per glyph, e.g. Greek letters -> DejaVu Sans
        "font.family": [sans[0], "DejaVu Sans"], "font.sans-serif": sans, "font.monospace": mono,
        "font.size": base, "axes.titlesize": base + 0.5, "axes.labelsize": base + 0.5,
        "xtick.labelsize": base, "ytick.labelsize": base, "legend.fontsize": base, "legend.title_fontsize": base,
        "figure.titlesize": base + 1, "axes.titleweight": "semibold", "axes.titlepad": 4, "axes.labelpad": 2.5,
        "axes.titlelocation": "left",
        "figure.facecolor": t.bg, "axes.facecolor": t.bg, "savefig.facecolor": t.bg, "savefig.edgecolor": t.bg,
        "axes.linewidth": 0.6, "axes.edgecolor": t.muted if t.name == "screen" else t.ink,
        "axes.labelcolor": t.ink, "text.color": t.ink, "xtick.color": t.muted if t.name == "screen" else t.ink,
        "ytick.color": t.muted if t.name == "screen" else t.ink,
        "xtick.labelcolor": t.ink, "ytick.labelcolor": t.ink,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.major.pad": 2, "ytick.major.pad": 2,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": False, "grid.color": t.grid, "grid.linewidth": 0.5,
        "lines.linewidth": 1.3, "lines.markersize": 4, "lines.solid_capstyle": "butt",
        "patch.linewidth": 0.5, "patch.edgecolor": t.ink,
        "legend.frameon": False, "legend.handlelength": 1.6, "legend.handletextpad": 0.4,
        "legend.columnspacing": 1.0, "legend.borderaxespad": 0.3, "legend.labelspacing": 0.3,
        "legend.labelcolor": t.ink,
        "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.03,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "image.cmap": f"mosaic_{t.name}",
        "axes.prop_cycle": __import__("matplotlib").cycler(color=t.cycle),
    }


def apply(theme: Theme | str = "print", base: float = 8.0):
    """Select the Agg backend, register fonts and colormaps, set the theme. Returns pyplot."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import logging
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # silence weight-fallback notes
    register_fonts()
    _register_cmaps()
    plt.rcParams.update(rc(theme, base))
    return plt


def theme(name: str = "print") -> Theme:
    return SCREEN if name == "screen" else PRINT


# ------------------------------------------------------------------ helpers
def label(ax_or_fig, x, y, s: str, size: float = 7.5, color: str | None = None, transform=None, **kw):
    """Small uppercase Geist Mono label (the house caption style)."""
    import matplotlib.pyplot as plt
    kw.setdefault("ha", "left")
    kw.setdefault("va", "baseline")
    color = color or plt.rcParams["axes.labelcolor"]
    fam = plt.rcParams["font.monospace"]
    tr = transform if transform is not None else getattr(ax_or_fig, "transAxes", None) or ax_or_fig.transFigure
    return ax_or_fig.text(x, y, str(s).upper(), fontsize=size, color=color, family=fam, transform=tr,
                          parse_math=False, **kw)


def mono_ticks(ax) -> None:
    """Tick labels in Geist Mono (tabular numbers)."""
    import matplotlib.pyplot as plt
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_family(plt.rcParams["font.monospace"])


def tile(ax, x, y, w, h, color, gap: float = 0.0, **kw):
    """A hard-cornered square tile (data coordinates), optionally inset by ``gap`` on every side."""
    from matplotlib.patches import Rectangle
    r = Rectangle((x + gap, y + gap), w - 2 * gap, h - 2 * gap, facecolor=color, edgecolor="none",
                  linewidth=0, **kw)
    ax.add_patch(r)
    return r
