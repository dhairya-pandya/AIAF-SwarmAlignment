"""Raster side of the design system (PIL): typesetting with tracking, mosaic tile fields, swarm art, grain.

Used by the social cards (design/post.py), the video cards (video/make_video.py) and the explainer
animations (video/animations.py), so every raster visual is drawn by the same code.
"""
from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import mpl as D
from . import sprites as SP

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_FILES = {
    ("sans", 400): "InstrumentSans-Regular.ttf", ("sans", 500): "InstrumentSans-Medium.ttf",
    ("sans", 600): "InstrumentSans-SemiBold.ttf",
    ("mono", 400): "GeistMono-Regular.ttf", ("mono", 500): "GeistMono-Medium.ttf", ("mono", 600): "GeistMono-SemiBold.ttf",
}


def rgb(h: str, a: int | None = None):
    h = h.lstrip("#")
    t = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    if len(h) == 8:
        t = t + (int(h[6:8], 16),)
    elif a is not None:
        t = t + (a,)
    return t


@lru_cache(maxsize=128)
def font(kind: str = "sans", size: float = 32, weight: int = 400) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / FONT_FILES[(kind, weight)]), int(round(size)))


# ------------------------------------------------------------------ type
def text_w(s: str, f: ImageFont.FreeTypeFont, track: float = 0.0) -> float:
    """Advance width with tracking (``track`` in em, e.g. -0.045 for display, 0.06 for mono labels)."""
    if not s:
        return 0.0
    return f.getlength(s) + track * f.size * (len(s) - 1)


def draw_text(dr: ImageDraw.ImageDraw, xy, s: str, f, fill, track: float = 0.0, anchor: str = "ls") -> float:
    """Draw ``s`` with tracking, keeping kerning (each glyph placed at the kerned advance of its prefix).
    ``anchor`` follows PIL: 'ls' left-baseline, 'lt' left-top (ascender), 'ms' middle-baseline, 'rs' right."""
    x, y = xy
    w = text_w(s, f, track)
    if anchor[0] == "m":
        x -= w / 2
    elif anchor[0] == "r":
        x -= w
    va = anchor[1]
    if track == 0:
        dr.text((x, y), s, font=f, fill=fill, anchor="l" + va)
        return w
    for i, ch in enumerate(s):
        dx = f.getlength(s[:i]) + track * f.size * i
        dr.text((x + dx, y), ch, font=f, fill=fill, anchor="l" + va)
    return w


def wrap(s: str, f, maxw: float, track: float = 0.0) -> list[str]:
    out: list[str] = []
    for para in str(s).split("\n"):
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if cur and text_w(trial, f, track) > maxw:
                out.append(cur)
                cur = word
            else:
                cur = trial
        out.append(cur)
    return out


def caps(dr, xy, s: str, size: float, fill=D.MUTED, weight: int = 400, anchor: str = "ls") -> float:
    """Geist Mono uppercase label with label tracking."""
    return draw_text(dr, xy, str(s).upper(), font("mono", size, weight), rgb(fill) if isinstance(fill, str) else fill,
                     track=0.06, anchor=anchor)


# ------------------------------------------------------------------ tiles
def tile(dr, x: float, y: float, cell: float, color, gap: float = 2) -> None:
    """One hard-cornered tile at grid origin (x, y) with pitch ``cell`` and ``gap`` px between tiles."""
    g = gap / 2
    dr.rectangle([x + g, y + g, x + cell - g - 1, y + cell - g - 1], fill=rgb(color) if isinstance(color, str) else color)


def sprite(dr, name: str, x: float, y: float, cell: float, pal="red", gap: float = 2) -> tuple[int, int]:
    """Draw a sprite with its top-left at (x, y); returns its size in cells."""
    for cx, cy, col in SP.cells(name, pal):
        tile(dr, x + cx * cell, y + cy * cell, cell, col, gap)
    return SP.size(name)


def grain(im: Image.Image, alpha: float = 0.05) -> Image.Image:
    """Subtle monochrome grain over the plate."""
    w, h = im.size
    noise = Image.effect_noise((w, h), 48).convert("L")
    noise = Image.merge("RGB", (noise, noise, noise))
    return Image.blend(im.convert("RGB"), noise, alpha)


def swarm_art(w: int, h: int, cell: int = 16, seed: int = 7, sprites=(), agents: float = 0.05,
              contamination: float = 0.25, bad: int = 4, texture: float = 0.5, bg: str = D.SURFACE,
              avoid=None, gap: int = 2) -> Image.Image:
    """A still of the swarm mosaic: dim texture tiles, sprites drawn in tiles, and agent tiles (lime honest,
    sky informed, vermilion compromised, red-4 misled clustered around the compromised ones).

    sprites: iterable of (name, col, row, scale, palette) in grid cells.
    avoid: optional (x0, y0, x1, y1) pixel box kept free of agents and texture (e.g. behind a headline)."""
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h), rgb(bg))
    dr = ImageDraw.Draw(im)
    cols, rows = w // cell + 1, h // cell + 1
    lit: dict[tuple[int, int], str] = {}
    for name, c0, r0, sc, pal in sprites:
        for cx, cy, col in SP.cells(name, pal):
            for i in range(sc):
                for j in range(sc):
                    lit[(c0 + cx * sc + i, r0 + cy * sc + j)] = col

    def free(c, r):
        if not avoid:
            return True
        x, y = c * cell, r * cell
        return not (avoid[0] <= x <= avoid[2] and avoid[1] <= y <= avoid[3])

    for r in range(rows):
        for c in range(cols):
            if (c, r) in lit:
                tile(dr, c * cell, r * cell, cell, lit[(c, r)], gap)
                continue
            v = rnd.random()
            if v < texture and free(c, r):
                tile(dr, c * cell, r * cell, cell, D.TEX if v < 0.012 else D.OFF, gap)
    n = int(cols * rows * agents)
    bads = []
    for k in range(n):
        for _ in range(20):
            c, r = rnd.randrange(cols), rnd.randrange(rows)
            if (c, r) not in lit and free(c, r):
                break
        else:
            continue
        if k < bad:
            bads.append((c, r))
            tile(dr, c * cell, r * cell, cell, D.VERMILION, gap)
            m = max(2, cell // 4)
            dr.rectangle([c * cell + cell / 2 - m / 2, r * cell + cell / 2 - m / 2, c * cell + cell / 2 + m / 2 - 1,
                          r * cell + cell / 2 + m / 2 - 1], fill=rgb(D.RED_1))
            continue
        near = min((abs(c - a) + abs(r - b) for a, b in bads), default=99)
        if near <= 4 and rnd.random() < contamination * 2.4:
            col = D.RED_4
        else:
            col = D.HUE["sky"] if rnd.random() < 0.28 else D.HUE["lime"]
        tile(dr, c * cell, r * cell, cell, col, gap)
    return im
