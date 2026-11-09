"""GitHub README banner in the design system: logo mark, title, finding, the cast, and a contained swarm.

    python -m design.banner            # -> design/out/banner.png (1600x400) and banner_dark@2x.png (3200x800)

Everything is drawn at a scale factor ``k`` (1 or 2) so the @2x file is a crisp re-render, not an upscale.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

from . import mosaic as M
from . import mpl as D

OUT = Path(__file__).resolve().parent / "out"
W, H = 1600, 400

TITLE = "Swarm Immunity"
SUBTITLE = "How nature's collectives inspire defences for agentic AI"
FINDING = ("Leaderless evidence-sharing beats leader hierarchies:", "8%", " vs ", "70%", " contamination")
AUTHOR = "Dhairya Pandya · IIITDM Jabalpur"
KICKER = "Apart × AIAF Swarm Alignment Hackathon · 2026"
CAST = ["ant", "bee", "wolf", "bird", "firefly", "bat", "elephant"]
# the cast is drawn neutral: colour is reserved for meaning (the field on the right)
CAST_PAL = {"b": D.MUTED, "d": D.FIELD, "h": D.INK, "a": D.BONE, "e": D.SURFACE}

# logo mark: (x, y, colour) in the 24-unit space of design/out/logo_mark.svg (4-unit tiles, 5-unit pitch)
_L, _S, _W, _V = D.HUE["lime"], D.HUE["sky"], D.INK, D.VERMILION
LOGO = [(5, 0, _S), (10, 0, _L), (15, 0, _L),
        (2.5, 5, _L), (7.5, 5, _W), (12.5, 5, _W), (17.5, 5, _L),
        (0, 10, _L), (5, 10, _W), (10, 10, _V), (15, 10, _W), (20, 10, _S),
        (2.5, 15, _L), (7.5, 15, _W), (12.5, 15, _W), (17.5, 15, _L),
        (5, 20, _L), (10, 20, _L), (15, 20, _S)]


def logo(dr, x0: float, y0: float, unit: float) -> float:
    """The honeycomb mark as hard square tiles, same geometry as logo_mark.svg (4-unit tiles on a 5-unit
    pitch, half-offset rows). ``unit`` is px per svg unit. Returns the side length."""
    t = round(4 * unit)
    for ux, uy, col in LOGO:
        x, y = round(x0 + ux * unit), round(y0 + uy * unit)
        dr.rectangle([x, y, x + t - 1, y + t - 1], fill=M.rgb(col))
    return 24 * unit


def field(dr, x0: int, y0: int, x1: int, y1: int, cell: int, gap: float, seed: int = 5, keep=None) -> None:
    """Swarm mosaic between x0..x1: texture and agents fade in from the left edge; a few compromised
    (vermilion) clusters, each fully ringed by honest (lime) tiles, i.e. contained."""
    rnd = random.Random(seed)
    cols, rows = (x1 - x0) // cell, (y1 - y0) // cell
    ox = x1 - cols * cell                       # flush to the right edge
    oy = y0 + ((y1 - y0) - rows * cell) // 2
    fade = max(1, int(cols * 0.42))

    def ok(c, r):
        if not keep:
            return True
        x, y = ox + c * cell, oy + r * cell
        return not (x + cell > keep[0] and x < keep[2] and y + cell > keep[1] and y < keep[3])

    # contained clusters: (col, row, shape) in cells relative to the field; shapes are core offsets
    cores = [(cols - 21, 4, [(0, 0), (1, 0), (0, 1)]),
             (cols - 9, 8, [(0, 0), (1, 0), (1, 1), (2, 1)]),
             (cols - 17, 15, [(0, 0)])]
    lit: dict[tuple[int, int], str] = {}
    for c0, r0, shape in cores:
        core = {(c0 + a, r0 + b) for a, b in shape}
        for c, r in core:
            for dc in (-1, 0, 1):
                for dr_ in (-1, 0, 1):
                    n = (c + dc, r + dr_)
                    if n not in core:
                        lit[n] = D.HUE["lime"]
        for n in core:
            lit[n] = D.VERMILION
    for r in range(rows):
        for c in range(cols):
            if not ok(c, r):
                continue
            x, y = ox + c * cell, oy + r * cell
            if (c, r) in lit:
                col = lit[(c, r)]
                M.tile(dr, x, y, cell, col, gap)
                if col == D.VERMILION:          # the compromised mark: a dark core, as in mosaic.swarm_art
                    m = max(2, cell // 4)
                    dr.rectangle([x + cell / 2 - m / 2, y + cell / 2 - m / 2, x + cell / 2 + m / 2 - 1,
                                  y + cell / 2 + m / 2 - 1], fill=M.rgb(D.RED_1))
                continue
            near = min(max(abs(c - a), abs(r - b)) for a, b in lit)
            dens = min(1.0, c / fade)
            v = rnd.random()
            if near <= 1:
                continue                         # breathing room around each ring keeps it legible
            if v < 0.055 * dens:
                col = D.HUE["sky"] if rnd.random() < 0.35 else D.HUE["lime"]
                M.tile(dr, x, y, cell, col, gap)
            elif v < 0.5 * dens ** 1.4:
                M.tile(dr, x, y, cell, D.OFF, gap)


def banner(k: int, path: Path) -> Path:
    w, h = W * k, H * k
    im = Image.new("RGB", (w, h), M.rgb(D.SURFACE))
    dr = ImageDraw.Draw(im)
    gap = 2 * k
    pad = 56 * k

    # right: the contained swarm (kept clear of the bottom-right label)
    f_cap = M.font("mono", 18 * k, 400)
    kick_w = M.text_w(KICKER.upper(), f_cap, 0.06)
    base = h - pad
    keep = (w - pad - kick_w - 18 * k, base - 34 * k, w, h)
    field(dr, int(w * 0.66), 0, w, h, 16 * k, gap, keep=keep)

    # left: the mark
    unit = 8.8 * k
    side = 24 * unit
    lx, ly = pad, (h - side) / 2
    logo(dr, lx, ly, unit)

    # copy column
    x = round(lx + side + 56 * k)
    M.caps(dr, (x, pad + 16 * k), AUTHOR, 18 * k, fill=D.INK)
    f_title = M.font("sans", 76 * k, 600)
    y = pad + 16 * k + 82 * k
    M.draw_text(dr, (x, y), TITLE, f_title, M.rgb(D.INK), track=-0.045)
    f_sub = M.font("sans", 28 * k, 500)
    y += 46 * k
    M.draw_text(dr, (x, y), SUBTITLE, f_sub, M.rgb(D.MUTED), track=-0.015)
    # finding: two lines on a vermilion rule; 8% in lime (safe), 70% in vermilion (contaminated)
    f_find = M.font("sans", 22 * k, 600)
    y += 46 * k
    lh = 29 * k
    dr.rectangle([x, y - 19 * k, x + 4 * k - 1, y - 19 * k + lh + 24 * k], fill=M.rgb(D.VERMILION))
    tx = x + 18 * k
    M.draw_text(dr, (tx, y), FINDING[0], f_find, M.rgb(D.INK), track=-0.01)
    cx = tx
    for part, col in zip(FINDING[1:], [D.HUE["lime"], D.INK, D.VERMILION, D.INK]):
        cx += M.draw_text(dr, (cx, y + lh), part, f_find, M.rgb(col), track=-0.01)

    # bottom row: the cast, bottom-aligned on the baseline; the event label at the far right
    cs = 4 * k
    cx = x
    for name in CAST:
        sw, sh = M.SP.size(name)
        M.sprite(dr, name, cx, base - sh * cs, cs, CAST_PAL, gap=k)
        cx += sw * cs + 18 * k
    M.caps(dr, (w - pad, base), KICKER, 18 * k, fill=D.MUTED, anchor="rs")

    im = M.grain(im, 0.035)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    o = Path(a.out)
    for k, name in [(1, "banner.png"), (2, "banner_dark@2x.png")]:
        print(f"wrote {banner(k, o / name)}")


if __name__ == "__main__":
    main()
