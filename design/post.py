"""Social cards in the design system: a 1600x900 (landscape) and a 1080x1350 (portrait) PNG.

    python -m design.post                                  # -> design/out/post_1600x900.png, post_1080x1350.png
    python -m design.post --finding "Stop signals cut contamination by 31 points"

The finding line stays a placeholder until the results are final.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from . import mosaic as M
from . import mpl as D

OUT = Path(__file__).resolve().parent / "out"
TITLE = "Swarm Immunity"
SUBTITLE = "How nature's collectives inspire defences for agentic AI"
AUTHOR = "Dhairya Pandya · IIITDM Jabalpur"
REPO = "github.com/dhairya-pandya/AIAF-SwarmAlignment"
KICKER = "Apart × AIAF Swarm Alignment Hackathon · 2026"
CAST = ["ant", "bee", "wolf", "bird", "firefly", "bat"]


def card(w: int, h: int, finding: str, path: Path) -> Path:
    portrait = h > w
    s = w / 1600 if not portrait else w / 1080          # type scale
    cell = 16 if not portrait else 15
    pad = int(72 * s) if not portrait else 64
    # the art: a swarm field with one large sprite (wolf, the pack leader that can be captured) and the cast
    cols, rows = w // cell + 1, h // cell + 1
    if portrait:
        sc = 3
        sw, sh = 16 * sc, 14 * sc
        big = ("wolf", (cols - sw) // 2, max(2, (int(rows * 0.5) - sh) // 2), sc, "red")
    else:
        sc = 2
        sw, sh = 16 * sc, 14 * sc
        half = cols // 2
        big = ("wolf", half + (cols - half - sw) // 2, (rows - sh) // 2, sc, "red")
    im = M.swarm_art(w, h, cell=cell, seed=11, sprites=[big], agents=0.06, contamination=0.3, bad=5, texture=0.45,
                     avoid=None)
    dr = ImageDraw.Draw(im, "RGBA")
    # copy panel: a solid plate where the type sits, so the field never fights the headline
    if portrait:
        y0 = int(h * 0.50)
        dr.rectangle([0, y0, w, h], fill=M.rgb(D.SURFACE))
        dr.line([0, y0, w, y0], fill=M.rgb(D.FRAME), width=1)
        x, top = pad, y0 + 40
    else:
        x0 = int(w * 0.50)
        dr.rectangle([0, 0, x0, h], fill=M.rgb(D.SURFACE))
        dr.line([x0, 0, x0, h], fill=M.rgb(D.FRAME), width=1)
        x, top = pad, pad + 8
    maxw = (w - 2 * pad) if portrait else (int(w * 0.50) - 2 * pad)

    M.caps(dr, (x, top + 14 * s), KICKER, 17 * s, fill=D.BONE)
    f_title = M.font("sans", 112 * s if not portrait else 96, 600)
    y = top + 30 * s + f_title.size * 0.95
    for line in ["Swarm", "Immunity"]:
        M.draw_text(dr, (x, y), line, f_title, M.rgb(D.INK), track=-0.045)
        y += f_title.size * 0.9
    f_sub = M.font("sans", 34 * s if not portrait else 34, 500)
    y += 10 * s
    for line in M.wrap(SUBTITLE, f_sub, maxw, -0.02):
        M.draw_text(dr, (x, y), line, f_sub, M.rgb(D.MUTED), track=-0.02)
        y += f_sub.size * 1.12
    # finding: the one line that matters, on a vermilion rule
    y += 34 * s
    f_find = M.font("sans", 36 * s if not portrait else 36, 600)
    flines = M.wrap(finding, f_find, maxw - 22, -0.02)
    bar_h = len(flines) * f_find.size * 1.15
    dr.rectangle([x, y - f_find.size * 0.85, x + 5, y - f_find.size * 0.85 + bar_h], fill=M.rgb(D.VERMILION))
    for line in flines:
        M.draw_text(dr, (x + 22, y), line, f_find, M.rgb(D.INK), track=-0.02)
        y += f_find.size * 1.15
    # cast strip + footer
    foot = h - pad
    cs = max(4, int(5 * s)) if not portrait else 5
    cx = x
    cast_y = foot - (100 if not portrait else 70) * s - 16 * cs
    for name in CAST:
        cw, ch = M.sprite(dr, name, cx, cast_y + (16 - M.SP.size(name)[1]) * cs, cs, "red", gap=1)
        cx += cw * cs + 18 * s
    M.sprite(dr, "compromised", cx + 6 * s, cast_y + 4 * cs, cs, "attack", gap=1)
    if portrait:
        dr.line([x, foot - 40, x + maxw, foot - 40], fill=M.rgb(D.FRAME), width=1)
        M.caps(dr, (x, foot), AUTHOR, 17, fill=D.INK)
        M.caps(dr, (x + maxw, foot), REPO, 17, fill=D.MUTED, anchor="rs")
    else:       # stacked: the half-width panel is too narrow for both on one line
        dr.line([x, foot - 66 * s, x + maxw, foot - 66 * s], fill=M.rgb(D.FRAME), width=1)
        M.caps(dr, (x, foot - 28 * s), AUTHOR, 17 * s, fill=D.INK)
        M.caps(dr, (x, foot), REPO, 17 * s, fill=D.MUTED)
    im = M.grain(im, 0.035)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--finding", default="[FINDING TBD]")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    o = Path(a.out)
    for w, h in [(1600, 900), (1080, 1350)]:
        p = card(w, h, a.finding, o / f"post_{w}x{h}.png")
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
