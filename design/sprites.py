"""Pixel-mosaic animal sprites: the agents of every swarm in this project, drawn as square tiles.

Each sprite is a small grid of characters. A character names a *role*, not a colour:

    .  empty           b  body            d  dark detail (legs, outline, shadow)
    h  highlight       a  accent (glow, stripe, mark)       e  eye

A palette maps roles to colours. ``red`` is the mosaic ramp (the brand art); the state palettes
(``lime``, ``sky``, ``amber``, ...) colour an agent by what it is doing: lime honest/safe, sky correct,
vermilion (``attack``) compromised. Tiles are square with a gap between them, hard corners.

    python -m design.sprites                 # write PNG + SVG sheets to design/out/sprites/
    python -m design.sprites --site site     # also sync site/: sprites.js, tokens.css, fonts/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from . import mpl as _d
except ImportError:  # run as a script
    import importlib.util
    _spec = importlib.util.spec_from_file_location("design_mpl", Path(__file__).with_name("mpl.py"))
    _d = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_d)

# ------------------------------------------------------------------ grids (16 wide unless noted)
SPRITES: dict[str, list[str]] = {
    # ant, side view: abdomen left, thorax, head right with antennae; six legs below
    "ant": [
        "...........d..d.",
        "............dd..",
        "..bbb.......dd..",
        ".bbbbb.....bbbb.",
        "bbhbbbb.bb.bbebb",
        "bbbbbbbbbbbbbbbb",
        "bbbbbb..bb..bbb.",
        ".bbbb..d.dd..d..",
        "......d..d.d..d.",
        ".....d..d...d..d",
    ],
    # honeybee, side view: wings above, striped abdomen, head right
    "bee": [
        ".....hhh.hhh....",
        "....hhhhhhhhh...",
        "....hhhhhhhhh...",
        ".....hhh.hhh....",
        "...addaaddaab...",
        "..aaddaaddaabbb.",
        "daaaddaaddaabbeb",
        "..aaddaaddaabbb.",
        "...addaaddaab...",
        ".....d..d..d....",
        "....d..d..d.....",
    ],
    # wolf head, front: pointed ears, slanted eyes, pale tapering muzzle, dark nose at the tip
    "wolf": [
        "..d..........d..",
        ".dbd........dbd.",
        ".dbbd......dbbd.",
        ".bbbbbbbbbbbbbb.",
        "bbbbbbbbbbbbbbbb",
        "bbhebbbbbbbbehbb",
        "bbbbbbbbbbbbbbbb",
        ".bbbbbhhhhbbbbb.",
        "..bbbhhhhhhbbb..",
        "...bbhhhhhhbb...",
        "....bbhhhhbb....",
        ".....bhddhb.....",
        "......bddb......",
        ".......bb.......",
    ],
    # bird (boid), gliding head-on: swept wings, body, tail
    "bird": [
        "h..............h",
        "hh............hh",
        ".hhb........bhh.",
        "..bbbb....bbbb..",
        "...bbbbbbbbbb...",
        "....bbbeebbb....",
        "......bbbb......",
        "......bddb......",
        ".....dd..dd.....",
    ],
    # firefly: dark body, pale wings, glowing abdomen
    "firefly": [
        ".....d....d.....",
        "......d..d......",
        "......bbbb......",
        "...hh.beeb.hh...",
        "..hhhhbbbbhhhh..",
        "..hhhhbbbbhhhh..",
        "...hhhbbbbhhh...",
        "......bbbb......",
        ".....aaaaaa.....",
        "....aaaaaaaa....",
        "....aaaaaaaa....",
        ".....aaaaaa.....",
        "......aaaa......",
    ],
    # vampire bat, wings spread, ears up, small fangs
    "bat": [
        "......b..b......",
        "......bbbb......",
        "b.....beeb.....b",
        "bb...bbbbbb...bb",
        "bbb.bbbhhbbb.bbb",
        "bbbbbbbbbbbbbbbb",
        "bbdbbbbbbbbbbdbb",
        "bdbbb.bbbb.bbbdb",
        "bb.bb..bb..bb.bb",
        "b..b...hh...b..b",
    ],
    # particle (abstract strategy): a diamond with a bright core and a trail
    "particle": [
        "........b...",
        ".......bab..",
        "......bahab.",
        ".......bab..",
        "....d...b...",
        "............",
        "..d.........",
        "............",
        "d...........",
    ],
    # compromised agent: a tile frame with a cross through it
    "compromised": [
        "dddddddddddd",
        "daa......aad",
        "d.aa....aa.d",
        "d..aa..aa..d",
        "d...aaaa...d",
        "d....aa....d",
        "d...aaaa...d",
        "d..aa..aa..d",
        "d.aa....aa.d",
        "daa......aad",
        "dddddddddddd",
    ],
    # a plain agent tile (honest), for swarms
    "agent": [
        "bbbb",
        "bhbb",
        "bbbb",
        "bbbb",
    ],
}

# strategy id -> sprite (family markers)
STRATEGY_SPRITE = {"S0a": "agent", "S0b": "agent", "S1": "agent", "S2": "agent", "S3": "particle", "S4": "ant",
                   "S5": "bee", "S6": "firefly", "S7": "wolf", "S8": "bird", "S9": "bee", "S10": "ant",
                   "S11": "bat"}
FAMILY_SPRITE = {"baseline": "agent", "abstract": "particle", "insects": "bee", "wolves": "wolf",
                 "fireflies": "firefly", "birds": "bird", "bats": "bat"}


# ------------------------------------------------------------------ palettes
def palette(name: str = "red") -> dict[str, str]:
    """Role -> colour. 'red' = mosaic ramp; 'attack' = compromised (vermilion); else a state hue name."""
    if name == "red":
        return {"b": _d.RED_4, "d": _d.RED_2, "h": _d.BONE, "a": _d.VERMILION, "e": _d.PAPER}
    if name == "attack":
        return {"b": _d.VERMILION, "d": _d.RED_3, "h": _d.PAPER, "a": _d.VERMILION, "e": _d.SURFACE}
    if name == "bone":
        return {"b": _d.BONE, "d": _d.RED_3, "h": _d.PAPER, "a": _d.VERMILION, "e": _d.SURFACE}
    if name == "ink":
        return {"b": _d.INK, "d": _d.SUBTLE, "h": _d.PAPER, "a": _d.VERMILION, "e": _d.SURFACE}
    if name == "dim":
        return {"b": _d.FRAME, "d": _d.FRAME_DIM, "h": _d.SUBTLE, "a": _d.FIELD, "e": _d.SURFACE}
    h, dim = _d.HUE[name], _d.HUE_DIM[name]
    accent = _d.HUE["amber"] if name != "amber" else _d.PAPER
    return {"b": h, "d": dim, "h": _d.PAPER, "a": accent, "e": _d.SURFACE}


def grid(name: str) -> list[str]:
    g = SPRITES[name]
    w = max(len(r) for r in g)
    return [r.ljust(w, ".") for r in g]


def size(name: str) -> tuple[int, int]:
    g = grid(name)
    return len(g[0]), len(g)


def cells(name: str, pal: str | dict = "red"):
    """Yield (col, row, colour) for every lit tile."""
    p = palette(pal) if isinstance(pal, str) else pal
    for y, row in enumerate(grid(name)):
        for x, c in enumerate(row):
            if c != "." and c in p:
                yield x, y, p[c]


# ------------------------------------------------------------------ renderers
def render_png(name: str, path: str | Path, tile: int = 16, gap: int = 2, pal: str | dict = "red",
               bg: str | None = None, pad: int = 0) -> Path:
    """Write the sprite as a PNG: each cell is ``tile`` px with ``gap`` px between tiles (transparent unless bg)."""
    from PIL import Image, ImageDraw
    w, h = size(name)
    W, H = w * tile + 2 * pad, h * tile + 2 * pad
    im = Image.new("RGBA", (W, H), bg or (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    g2 = gap / 2
    for x, y, col in cells(name, pal):
        x0, y0 = pad + x * tile + g2, pad + y * tile + g2
        dr.rectangle([x0, y0, x0 + tile - gap - 1, y0 + tile - gap - 1], fill=col)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p)
    return p


def svg(name: str, pal: str | dict = "red", tile: float = 10, gap: float = 2, title: str | None = None) -> str:
    w, h = size(name)
    rects = "".join(f'<rect x="{x * tile + gap / 2:g}" y="{y * tile + gap / 2:g}" width="{tile - gap:g}" '
                    f'height="{tile - gap:g}" fill="{c}"/>' for x, y, c in cells(name, pal))
    t = f"<title>{title}</title>" if title else ""
    role = 'role="img"' if title else 'aria-hidden="true"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * tile:g} {h * tile:g}" '
            f'shape-rendering="crispEdges" {role}>{t}{rects}</svg>')


def render_svg(name: str, path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(svg(name, **kw))
    return p


def draw(ax, name: str, x: float, y: float, cell: float, pal: str | dict = "red", gap: float = 0.14,
         zorder: float = 3, alpha: float = 1.0, anchor: str = "center"):
    """Draw a sprite on a matplotlib axes in data coordinates. (x, y) is the sprite centre (anchor='center')
    or its top-left corner (anchor='topleft'); ``cell`` is the tile pitch; ``gap`` is a fraction of the cell.
    The axes y axis is assumed to point up. Returns the list of patches."""
    from matplotlib.patches import Rectangle
    w, h = size(name)
    if anchor == "center":
        x0, ytop = x - w * cell / 2, y + h * cell / 2
    else:
        x0, ytop = x, y
    g = cell * gap
    out = []
    for cx, cy, col in cells(name, pal):
        r = Rectangle((x0 + cx * cell + g / 2, ytop - (cy + 1) * cell + g / 2), cell - g, cell - g,
                      facecolor=col, edgecolor="none", linewidth=0, zorder=zorder, alpha=alpha)
        ax.add_patch(r)
        out.append(r)
    return out


def to_js() -> str:
    """The sprite grids as a browser script (window.SI_SPRITES), so the site draws the same art."""
    data = {k: grid(k) for k in SPRITES}
    return ("/* Generated by design/sprites.py: pixel sprites as role grids (b body, d dark, h highlight, "
            "a accent, e eye). Do not edit by hand. */\nwindow.SI_SPRITES = " + json.dumps(data) + ";\n")


def sheet(path: str | Path, pals=("red", "lime", "sky", "attack"), tile: int = 12) -> Path:
    """Contact sheet of every sprite in a few palettes on the dark plate."""
    from PIL import Image
    names = [n for n in SPRITES if n != "agent"]
    cw = max(size(n)[0] for n in names) * tile + 2 * tile
    ch = max(size(n)[1] for n in names) * tile + 2 * tile
    im = Image.new("RGB", (cw * len(names), ch * len(pals)), _d.SURFACE)
    tmp = Path(path).with_suffix(".tmp.png")
    for j, pal in enumerate(pals):
        for i, n in enumerate(names):
            pal_n = "attack" if n == "compromised" else pal
            render_png(n, tmp, tile=tile, gap=2, pal=pal_n)
            sp = Image.open(tmp)
            im.paste(sp, (i * cw + (cw - sp.width) // 2, j * ch + (ch - sp.height) // 2), sp)
    tmp.unlink(missing_ok=True)
    im.save(path)
    return Path(path)


def sync_site(site: str | Path) -> None:
    """Copy the design kit into a static site folder: sprites.js, tokens.css and the web fonts + licences."""
    import shutil
    site = Path(site)
    root = Path(__file__).resolve().parent
    (site / "sprites.js").write_text(to_js())
    shutil.copy2(root / "tokens.css", site / "tokens.css")
    (site / "fonts").mkdir(parents=True, exist_ok=True)
    for f in ["InstrumentSans[wdth,wght].ttf", "GeistMono[wght].ttf", "OFL-InstrumentSans.txt", "OFL-GeistMono.txt"]:
        shutil.copy2(root / "fonts" / f, site / "fonts" / f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out" / "sprites"))
    ap.add_argument("--site", default=None, help="site folder: write <site>/sprites.js")
    a = ap.parse_args()
    out = Path(a.out)
    for n in SPRITES:
        for pal in ("red", "lime", "sky", "attack", "bone"):
            render_png(n, out / f"{n}_{pal}.png", tile=16, gap=2, pal=pal)
            render_svg(n, out / f"{n}_{pal}.svg", pal=pal)
    sheet(out / "sheet.png")
    if a.site:
        sync_site(a.site)
    print(f"wrote sprites to {out}")


if __name__ == "__main__":
    main()
