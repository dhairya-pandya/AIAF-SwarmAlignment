#!/usr/bin/env python3
"""Render the narrated project video from a YAML scene script.

    python video/make_video.py                      # full render -> video/swarm_immunity.mp4
    python video/make_video.py --subtitles          # burn subtitles into the picture
    python video/make_video.py --preview            # first 3 scenes, 960x540, fast encode
    python video/make_video.py --allow-tbd          # keep placeholder scenes (missing images / TBD narration)

Scene types (see video/script.yaml): title, bullets, image, clip.
Narration is spoken with macOS `say`; scene length = narration length + `padding` seconds.
A sidecar .srt is always written next to the MP4 and also muxed as a soft subtitle track.

Frames are drawn with PIL in the project's design system (design/: tokens, fonts, sprites, mosaic art).
Scene changes are a stepped tile wipe (8 steps) or hard cuts (--no-xfade); figure zooms move in steps.

Requires: ffmpeg/ffprobe on PATH, macOS `say`, Pillow, PyYAML.
"""
from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import yaml  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from design import mosaic as M  # noqa: E402
from design import mpl as D  # noqa: E402

# Design system colours (design/mpl.py): warm-black plate, ink type, vermilion accents, colour only for state
PLATE = D.SURFACE
INK = D.INK
MUTED = D.MUTED
SUBTLE = D.SUBTLE
ACCENT = D.VERMILION
BONE = D.BONE

BASE_W, BASE_H = 1920, 1080
SUB_ZONE = 0.155  # bottom fraction of the frame kept free for subtitles
AUDIO_SR = 48000

# section sprite per scene id (override with `sprite:` in the script); compromised = the threat glyph
SCENE_SPRITE = {"title": "wolf", "problem": "compromised", "idea": "bee", "defences": "ant", "reproducibility": "particle",
                "closing": "bird", "howitworks": "firefly"}
# stepped tile wipe between scenes (xfade custom expression): tiles flip from scene A to B in 8 steps,
# sweeping left to right with a hashed jitter per tile
TILE_WIPE = ("if(lt(floor(X*32/W)/32*0.72+mod(floor(X*32/W)*7+floor(Y*18/H)*13+floor(X*32/W)*floor(Y*18/H)*3\\,17)/17*0.28"
             "\\,floor((1-P)*8)/8)\\,B\\,A)")


# --------------------------------------------------------------------------- utils
def run(cmd: list[str], quiet: bool = True) -> None:
    res = subprocess.run(cmd, capture_output=quiet, text=True)
    if res.returncode != 0:
        sys.stderr.write(" ".join(map(str, cmd)) + "\n")
        if quiet:
            sys.stderr.write(res.stderr[-4000:] + "\n")
        raise SystemExit(f"command failed: {cmd[0]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class Canvas:
    """A 16:9 PIL frame. Sizes are given at 1920x1080 and scale with resolution; positions are pixels at 1080p."""

    def __init__(self, w: int, h: int, bg: str | None):
        self.w, self.h = w, h
        self.k = w / BASE_W
        self.im = Image.new("RGBA", (w, h), (0, 0, 0, 0) if bg is None else M.rgb(bg, 255))
        self.dr = ImageDraw.Draw(self.im, "RGBA")

    def f(self, size: float, weight: int = 400, kind: str = "sans"):
        return M.font(kind, size * self.k, weight)

    def text(self, x, y, s, size, color, weight=400, kind="sans", track=0.0, anchor="ls"):
        return M.draw_text(self.dr, (x * self.k, y * self.k), s, self.f(size, weight, kind),
                           M.rgb(color) if isinstance(color, str) else color, track, anchor) / self.k

    def caps(self, x, y, s, size, color=MUTED, weight=400, anchor="ls"):
        return self.text(x, y, str(s).upper(), size, color, weight, "mono", 0.06, anchor)

    def width(self, s, size, weight=400, track=0.0, kind="sans"):
        return M.text_w(s, self.f(size, weight, kind), track) / self.k

    def wrap(self, s, size, maxw, weight=400, track=0.0, kind="sans"):
        return M.wrap(s, self.f(size, weight, kind), maxw * self.k, track)

    def rect(self, x0, y0, x1, y1, color):
        X0, Y0 = x0 * self.k, y0 * self.k
        X1, Y1 = max(X0, x1 * self.k - 1), max(Y0, y1 * self.k - 1)     # at least 1 px at small scales
        self.dr.rectangle([X0, Y0, X1, Y1], fill=M.rgb(color) if isinstance(color, str) else color)

    def sprite(self, name, x, y, cell, pal="red"):
        M.sprite(self.dr, name, x * self.k, y * self.k, cell * self.k, pal, gap=max(1, round(2 * self.k)))

    def paste(self, img: Image.Image, x, y):
        self.im.paste(img, (int(x * self.k), int(y * self.k)), img if img.mode == "RGBA" else None)

    def save(self, path: Path, grain: bool = True) -> None:
        im = self.im
        if grain and im.getextrema()[3][0] == 255:     # opaque frame: add the plate grain
            im = M.grain(im, 0.03)
        im.save(path)


def draw_lines(c: Canvas, x, y, lines, size, color, weight=400, spacing=1.25, track=0.0, anchor="ls"):
    """Baseline-anchored lines going down from the first baseline y; returns the baseline after the last line."""
    for ln in lines:
        c.text(x, y, ln, size, color, weight, track=track, anchor=anchor)
        y += size * spacing
    return y


def scene_sprite(scene: dict) -> str | None:
    return scene.get("sprite", SCENE_SPRITE.get(scene.get("id", "")))


def art_panel(c: Canvas, x0: float, sprite: str | None, seed: int = 7, cell: int = 16) -> None:
    """The mosaic field on the right of a card, with the scene sprite drawn in tiles (scale 2)."""
    w, h = int((BASE_W - x0) * c.k), c.h
    cols, rows = int(w / (cell * c.k)) + 1, int(h / (cell * c.k)) + 1
    sprites = []
    if sprite:
        sw, sh = M.SP.size(sprite)
        sc = 2
        pal = "attack" if sprite == "compromised" else "red"
        sprites = [(sprite, max(0, (cols - sw * sc) // 2), max(1, int(rows * 0.42) - sh * sc // 2), sc, pal)]
    art = M.swarm_art(w, h, cell=max(4, round(cell * c.k)), seed=seed, sprites=sprites, agents=0.05,
                      contamination=0.25, bad=3, texture=0.45, gap=max(1, round(2 * c.k)))
    c.paste(art.convert("RGBA"), x0, 0)
    c.rect(x0, 0, x0 + 1, BASE_H, D.FRAME)


# --------------------------------------------------------------------------- frame renderers
def render_title(scene: dict, w: int, h: int, out: Path) -> None:
    c = Canvas(w, h, PLATE)
    split = 1100
    art_panel(c, split, scene_sprite(scene), seed=sum(map(ord, str(scene.get("id", "")))) % 97)
    x, maxw = 120, split - 220
    tsize = float(scene.get("title_size", 132))
    while tsize > 40 and max(c.width(wd, tsize, 600, -0.045) for wd in str(scene.get("title", "x")).split()) > maxw:
        tsize -= 4  # shrink until the longest unbreakable word (e.g. a URL) fits
    title_lines = c.wrap(scene.get("title", ""), tsize, maxw, 600, -0.045)
    sub_lines = c.wrap(scene.get("subtitle", ""), 40, maxw, 500, -0.02) if scene.get("subtitle") else []
    aff_lines = c.wrap(scene.get("affiliation", ""), 24, maxw) if scene.get("affiliation") else []
    total = (len(title_lines) * tsize * 0.92 + 30 + len(sub_lines) * 40 * 1.12 + 70 + 34 + len(aff_lines) * 30)
    y = (BASE_H * (1 - SUB_ZONE)) / 2 - total / 2 + tsize * 0.8
    if scene.get("kicker"):
        c.caps(x, y - tsize * 0.8 - 34, scene["kicker"], 20, BONE)
    y = draw_lines(c, x, y, title_lines, tsize, INK, 600, spacing=0.92, track=-0.045)
    y += 30 - tsize * 0.92 + 40
    y = draw_lines(c, x, y, sub_lines, 40, MUTED, 500, spacing=1.12, track=-0.02)
    y += 50
    c.rect(x, y - 24, x + 10, y - 14, ACCENT)
    if scene.get("author"):
        c.caps(x + 24, y - 14, scene["author"], 22, INK, 500)
    y += 34
    draw_lines(c, x, y, aff_lines, 24, SUBTLE, spacing=1.25)
    c.save(out)


def render_bullets(scene: dict, w: int, h: int, out: Path) -> None:
    c = Canvas(w, h, PLATE)
    sp = scene_sprite(scene)
    x, y = 120, 150
    if scene.get("kicker"):
        c.rect(x, y - 16, x + 10, y - 6, ACCENT)
        c.caps(x + 22, y - 6, scene["kicker"], 20, BONE)
    if sp:   # the section's sprite, small, top right
        sw, sh = M.SP.size(sp)
        cell = 7
        c.sprite(sp, BASE_W - 120 - sw * cell, y - 40, cell, "attack" if sp == "compromised" else "red")
    y += 78
    y = draw_lines(c, x, y, c.wrap(scene.get("heading", ""), 60, 1450, 600, -0.035), 60, INK, 600, spacing=1.04,
                   track=-0.035)
    y += 40
    bullets = list(scene.get("bullets") or [])[:5]
    size = 33 if len(bullets) <= 4 else 31
    for b in bullets:
        lines = c.wrap(b, size, 1500)
        c.rect(x + 2, y - size * 0.62, x + 2 + 12, y - size * 0.62 + 12, ACCENT)
        y = draw_lines(c, x + 40, y, lines, size, MUTED, spacing=1.28)
        y += 22
    if y - size > BASE_H * (1 - SUB_ZONE):
        print(f"  warning: bullets in scene '{scene.get('id')}' run into the subtitle zone (y={y:.0f}px)")
    c.save(out)


def render_image(scene: dict, w: int, h: int, out: Path, missing: bool = False, layer: str = "all",
                 shrink: float = 1.0) -> tuple[float, float]:
    """layer: 'all' = complete frame; 'figure' = figure card only on the plate (for the stepped zoom);
    'chrome' = transparent frame with heading/caption/panel on opaque plate bands, overlaid on the zoomed figure.
    shrink < 1 draws the figure smaller about its box centre, so a later zoom of 1/shrink fills the box exactly.
    Print figures sit on a white card (they are drawn for paper) inside the dark plate.
    Returns the figure box centre as (x, y) fractions measured from the top-left corner."""
    c = Canvas(w, h, None if layer == "chrome" else PLATE)
    draw_text = layer in ("all", "chrome")
    top = 70
    if scene.get("heading"):
        lines = c.wrap(scene["heading"], 46, 1700, 600, -0.03)
        if draw_text:
            c.rect(92, top + 46 * 0.8 - 24, 104, top + 46 * 0.8 - 12, ACCENT)
            draw_lines(c, 120, top + 46 * 0.8, lines, 46, INK, 600, spacing=1.06, track=-0.03)
        top += len(lines) * 46 * 1.06 + 26
    bottom = BASE_H * (1 - SUB_ZONE) - 16
    if scene.get("caption"):
        cap_lines = c.wrap(scene["caption"], 24, 1640)
        cap_h = len(cap_lines) * 24 * 1.3
        if draw_text:
            draw_lines(c, BASE_W / 2, bottom - cap_h + 22, cap_lines, 24, MUTED, spacing=1.3, anchor="ms")
        bottom -= cap_h + 18
    left, right = 96, BASE_W - 96
    bullets = list(scene.get("bullets") or [])[:5]
    if bullets:
        right = 1270
        px = 1320
        y = top + 30
        for b in (bullets if draw_text else []):
            lines = c.wrap(b, 27, 500)
            c.rect(px, y - 27 * 0.62, px + 10, y - 27 * 0.62 + 10, ACCENT)
            y = draw_lines(c, px + 26, y, lines, 27, MUTED, spacing=1.28)
            y += 20
    if layer == "chrome":
        # opaque plate bands that mask the zoomed figure wherever text lives, then the text on top
        for box in [(0, 0, BASE_W, top), (0, bottom, BASE_W, BASE_H), (0, 0, left, BASE_H), (right, 0, BASE_W, BASE_H)]:
            c.dr.rectangle([box[0] * c.k, box[1] * c.k, box[2] * c.k, box[3] * c.k], fill=M.rgb(PLATE, 255))
        _redraw_text(c, scene, top, bottom, bullets)
    elif missing:
        c.rect(left, top, right, bottom, D.CARD)
        c.dr.rectangle([left * c.k, top * c.k, right * c.k - 1, bottom * c.k - 1], outline=M.rgb(D.FRAME), width=2)
        c.text((left + right) / 2, (top + bottom) / 2, "Figure pending", 48, MUTED, 600, anchor="ms")
        c.caps((left + right) / 2, (top + bottom) / 2 + 50, str(scene.get("image", "")), 20, SUBTLE, anchor="ms")
    else:
        img = Image.open(ROOT / scene["image"]).convert("RGB")
        pad = 22
        bw, bh = (right - left - 2 * pad) * shrink, (bottom - top - 2 * pad) * shrink
        r = min(bw / img.width, bh / img.height)
        iw, ih = img.width * r, img.height * r
        cx, cy = (left + right) / 2, (top + bottom) / 2
        cw_, ch_ = iw + 2 * pad * shrink, ih + 2 * pad * shrink
        c.rect(cx - cw_ / 2, cy - ch_ / 2, cx + cw_ / 2, cy + ch_ / 2, "#ffffff")
        c.rect(cx - cw_ / 2, cy - ch_ / 2, cx - cw_ / 2 + 6, cy - ch_ / 2 + 6, ACCENT)   # hard-corner card tick
        res = img.resize((max(1, int(iw * c.k)), max(1, int(ih * c.k))), Image.LANCZOS)
        c.im.paste(res, (int((cx - iw / 2) * c.k), int((cy - ih / 2) * c.k)))
    c.save(out, grain=layer == "all")     # zoom layers stay flat so figure and chrome bands match exactly
    return (left + right) / 2 / BASE_W, (top + bottom) / 2 / BASE_H


def _redraw_text(c: Canvas, scene: dict, top: float, bottom: float, bullets: list) -> None:
    """Heading, caption and side panel for the chrome layer (drawn after the opaque bands)."""
    t = 70
    if scene.get("heading"):
        lines = c.wrap(scene["heading"], 46, 1700, 600, -0.03)
        c.rect(92, t + 46 * 0.8 - 24, 104, t + 46 * 0.8 - 12, ACCENT)
        draw_lines(c, 120, t + 46 * 0.8, lines, 46, INK, 600, spacing=1.06, track=-0.03)
    if scene.get("caption"):
        cap_lines = c.wrap(scene["caption"], 24, 1640)
        cap_h = len(cap_lines) * 24 * 1.3
        b = BASE_H * (1 - SUB_ZONE) - 16
        draw_lines(c, BASE_W / 2, b - cap_h + 22, cap_lines, 24, MUTED, spacing=1.3, anchor="ms")
    if bullets:
        y = top + 30
        for bl in bullets:
            lines = c.wrap(bl, 27, 500)
            c.rect(1320, y - 27 * 0.62, 1330, y - 27 * 0.62 + 10, ACCENT)
            y = draw_lines(c, 1346, y, lines, 27, MUTED, spacing=1.28)
            y += 20


def render_subtitle(text_lines: list[str], w: int, h: int, out: Path) -> None:
    c = Canvas(w, h, None)
    size = 32
    width = max(c.width(ln, size) for ln in text_lines) + 56
    box_h = size * 1.25 * len(text_lines) + 26
    y1 = BASE_H - 28
    x0 = (BASE_W - width) / 2
    c.rect(x0, y1 - box_h, x0 + width, y1, (11, 9, 8, 222))
    c.rect(x0, y1 - box_h, x0 + 4, y1, ACCENT)
    draw_lines(c, BASE_W / 2, y1 - box_h + 13 + size * 0.95, text_lines, size, INK, spacing=1.25, anchor="ms")
    c.save(out)


# --------------------------------------------------------------------------- subtitle chunking
def chunk_narration(text: str, w: int, h: int, max_lines: int = 2) -> list[list[str]]:
    """Split narration into on-screen chunks of at most `max_lines` lines."""
    c = Canvas(w, h, None)
    maxw = 1500
    sentences = re.split(r"(?<=[.!?;:])\s+", " ".join(str(text).split()))
    chunks: list[list[str]] = []
    for s in sentences:
        if not s:
            continue
        lines = c.wrap(s, 32, maxw)
        while len(lines) > max_lines:
            # try to break the sentence at a comma near the middle of the allowed span
            head = " ".join(lines[:max_lines])
            cut = head.rfind(", ")
            if cut > len(head) * 0.35:
                part, rest = head[: cut + 1], head[cut + 2:] + " " + " ".join(lines[max_lines:])
            else:
                part, rest = head, " ".join(lines[max_lines:])
            chunks.append(c.wrap(part, 32, maxw))
            lines = c.wrap(rest.strip(), 32, maxw)
        chunks.append(lines)
    return chunks


# --------------------------------------------------------------------------- audio
def tts(text: str, voice: str, rate: int, out_wav: Path) -> float:
    aiff = out_wav.with_suffix(".aiff")
    run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ac", "1", "-ar", str(AUDIO_SR),
         "-c:a", "pcm_s16le", str(out_wav)])
    aiff.unlink(missing_ok=True)
    return probe_duration(out_wav)


def speakable(text: str, pronounce: dict) -> str:
    for k, v in (pronounce or {}).items():
        text = re.sub(rf"\b{re.escape(k)}\b", v, text)
    return text


def build_audio_track(placements: list[tuple[float, Path]], total: float, out: Path) -> None:
    n = int(math.ceil(total * AUDIO_SR))
    buf = bytearray(n * 2)
    for start, wav_path in placements:
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1 and wf.getsampwidth() == 2 and wf.getframerate() == AUDIO_SR
            data = wf.readframes(wf.getnframes())
        off = int(round(start * AUDIO_SR)) * 2
        data = data[: max(0, len(buf) - off)]
        buf[off: off + len(data)] = data
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(AUDIO_SR)
        wf.writeframes(bytes(buf))


# --------------------------------------------------------------------------- video segments
def x264_args(preview: bool, final: bool = False) -> list[str]:
    preset = "ultrafast" if preview else ("medium" if final else "veryfast")
    crf = "23" if preview else ("19" if final else "14")
    return ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]


def encode_segment(base_cmd_inputs: list[str], vchain: str, overlays: list[tuple[Path, float | None, float | None]],
                   nframes: int, fps: int, out: Path, preview: bool) -> None:
    """vchain: filter applied to input 0 producing the scene video. overlays: full-frame RGBA PNGs drawn on top,
    each either always (t0 is None) or between t0 and t1 seconds (subtitles)."""
    inputs = list(base_cmd_inputs)
    graph = [f"[0:v]{vchain},format=yuv420p[v0]"]
    last = "v0"
    for i, (png, t0, t1) in enumerate(overlays, start=1):
        inputs += ["-loop", "1", "-framerate", str(fps), "-i", str(png)]
        en = "" if t0 is None else f":enable='between(t,{t0:.3f},{t1:.3f})'"
        graph.append(f"[{last}][{i}:v]overlay=0:0{en}:format=auto[s{i}]")
        last = f"s{i}"
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]",
           "-frames:v", str(nframes), "-r", str(fps), *x264_args(preview), "-an", str(out)]
    run(cmd)


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", default=str(VIDEO_DIR / "script.yaml"))
    ap.add_argument("--out", default=None, help="output MP4 (default from script, or *_preview.mp4 with --preview)")
    ap.add_argument("--preview", action="store_true", help="first 3 scenes at 960x540 with a fast encode")
    ap.add_argument("--scenes", type=int, default=None, help="render only the first N kept scenes")
    ap.add_argument("--allow-tbd", action="store_true", help="keep scenes with missing images or TBD narration")
    ap.add_argument("--subtitles", action="store_true", help="burn subtitles into the picture")
    ap.add_argument("--no-xfade", action="store_true", help="hard cuts instead of the stepped tile wipe")
    ap.add_argument("--voice", default=None, help="override the script's voice")
    ap.add_argument("--rate", type=int, default=None, help="override the script's speaking rate (wpm)")
    ap.add_argument("--keep-build", action="store_true", help="keep intermediate files in video/build/")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe", "say"):
        if shutil.which(tool) is None:
            raise SystemExit(f"'{tool}' not found on PATH")

    script_path = Path(args.script).resolve()
    cfg = yaml.safe_load(script_path.read_text())
    voice = args.voice or cfg.get("voice", "Samantha")
    rate = args.rate or int(cfg.get("rate", 175))
    fps = int(cfg.get("fps", 30))
    padding = float(cfg.get("padding", 0.6))
    lead = float(cfg.get("lead_in", padding / 3))
    xf = 0.0 if args.no_xfade else float(cfg.get("crossfade", 0.3))
    pronounce = cfg.get("pronounce", {}) or {}
    meta_title = cfg.get("meta_title", "Swarm Immunity: How Nature's Collectives Inspire Defences for Agentic AI")
    meta_artist = cfg.get("meta_artist", "Dhairya Pandya")

    w, h = (960, 540) if args.preview else (BASE_W, BASE_H)
    if args.out:
        out_mp4 = Path(args.out).resolve()
    else:
        default = VIDEO_DIR / cfg.get("output", "swarm_immunity.mp4")
        out_mp4 = default.with_name(default.stem + "_preview.mp4") if args.preview else default
    build = VIDEO_DIR / "build" / ("preview" if args.preview else "full")
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)

    # ---- select scenes
    kept: list[dict] = []
    for i, sc in enumerate(cfg["scenes"]):
        sc.setdefault("id", f"scene{i:02d}")
        narr = str(sc.get("narration", "") or "")
        missing_asset = False
        if sc["type"] == "image":
            missing_asset = not (ROOT / sc["image"]).exists()
        elif sc["type"] == "clip":
            missing_asset = not (ROOT / sc["path"]).exists()
        tbd = "TBD" in narr
        if (missing_asset or tbd) and not args.allow_tbd:
            why = "missing " + (sc.get("image") or sc.get("path")) if missing_asset else "narration TBD"
            print(f"skip  {sc['id']:<16} ({why})")
            continue
        sc["_missing"] = missing_asset
        kept.append(sc)
    limit = 3 if args.preview else args.scenes
    if limit:
        kept = kept[:limit]
    if not kept:
        raise SystemExit("no scenes to render")

    # ---- narration audio, durations
    for sc in kept:
        narr = " ".join(str(sc.get("narration", "") or "").split())
        sc["_narr"] = narr
        if narr:
            wav = build / f"{sc['id']}.wav"
            spoken = sc.get("speak") or speakable(narr, pronounce)
            sc["_audio"], sc["_alen"] = wav, tts(spoken, voice, rate, wav)
        else:
            sc["_audio"], sc["_alen"] = None, 0.0
        dur = sc["_alen"] + padding if narr else float(sc.get("duration", 4.0))
        if sc["type"] == "clip" and not sc["_missing"] and not narr and "duration" not in sc:
            dur = probe_duration(ROOT / sc["path"]) - float(sc.get("start", 0))
        dur = max(dur, float(sc.get("min_duration", 0)), 2 * xf + 0.5)
        sc["_nframes"] = int(math.ceil(dur * fps))
        sc["_dur"] = sc["_nframes"] / fps

    # ---- timeline (xfade offsets) and subtitles
    starts, t = [], 0.0
    for k, sc in enumerate(kept):
        starts.append(t)
        t += sc["_dur"] - (xf if k < len(kept) - 1 else 0.0)
    total = t
    srt_entries = []
    for sc, st in zip(kept, starts):
        sc["_subs"] = []
        if not sc["_narr"]:
            continue
        chunks = chunk_narration(sc["_narr"], w, h)
        weights = [max(1, sum(len(l) for l in ch)) for ch in chunks]
        acc, s0 = 0.0, lead
        for j, (ch, wt) in enumerate(zip(chunks, weights)):
            a = s0 + sc["_alen"] * acc / sum(weights)
            acc += wt
            b = s0 + sc["_alen"] * acc / sum(weights)
            sc["_subs"].append((ch, a, b))
            srt_entries.append((st + a, st + b, "\n".join(ch)))

    srt_path = out_mp4.with_suffix(".srt")
    with open(srt_path, "w") as f:
        for n, (a, b, txt) in enumerate(srt_entries, start=1):
            f.write(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{txt}\n\n")

    # ---- render segments
    segs = []
    for k, sc in enumerate(kept):
        sid, typ = sc["id"], sc["type"]
        print(f"scene {sid:<16} {typ:<8} {sc['_dur']:6.2f}s  (narration {sc['_alen']:.2f}s)")
        frame = build / f"{sid}.png"
        kb = typ == "image" and bool(sc.get("kenburns")) and not sc["_missing"]
        rw, rh = (2 * w, 2 * h) if kb else (w, h)
        sub_pngs = []
        if args.subtitles:
            for j, (lines, a, b) in enumerate(sc["_subs"]):
                p = build / f"{sid}_sub{j:02d}.png"
                render_subtitle(lines, w, h, p)
                sub_pngs.append((p, a, b))
        seg = build / f"{k:02d}_{sid}.mp4"
        nf = sc["_nframes"]
        if typ == "title":
            render_title(sc, rw, rh, frame)
        elif typ == "bullets":
            render_bullets(sc, rw, rh, frame)
        elif typ == "image" and kb:
            zmax = float(sc.get("zoom", 1.06))
            kb_cx, kb_cy = render_image(sc, rw, rh, frame, layer="figure", shrink=1 / zmax)
            chrome = build / f"{sid}_chrome.png"
            render_image(sc, w, h, chrome, layer="chrome")
            sub_pngs.insert(0, (chrome, None, None))
        elif typ == "image":
            render_image(sc, rw, rh, frame, missing=sc["_missing"])
        elif typ == "clip":
            pass
        else:
            raise SystemExit(f"unknown scene type {typ!r} in {sid}")

        if typ == "clip" and not sc["_missing"]:
            bg = sc.get("background", "black")
            vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg},"
                  f"setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration={sc['_dur']:.3f}")
            inputs = ["-ss", str(sc.get("start", 0)), "-i", str(ROOT / sc["path"])]
            encode_segment(inputs, vf, sub_pngs, nf, fps, seg, args.preview)
        elif typ == "clip":  # placeholder for a missing clip
            render_image({"heading": sc.get("heading", "Screen recording"), "image": sc["path"]}, w, h, frame,
                         missing=True)
            encode_segment(["-loop", "1", "-framerate", str(fps), "-i", str(frame)], "null", sub_pngs, nf, fps,
                           seg, args.preview)
        elif kb:
            steps = int(sc.get("zoom_steps", 3))       # stepped punch-in, never a smooth tween
            zexpr = f"1+{zmax - 1:.4f}*floor(on*{steps}/{max(nf, 1)})/{max(steps - 1, 1)}"
            vf = (f"zoompan=z='{zexpr}':x='{kb_cx:.4f}*iw*(1-1/zoom)':y='{kb_cy:.4f}*ih*(1-1/zoom)'"
                  f":d={nf}:s={w}x{h}:fps={fps}")
            encode_segment(["-framerate", str(fps), "-i", str(frame)], vf, sub_pngs, nf, fps, seg, args.preview)
        else:
            encode_segment(["-loop", "1", "-framerate", str(fps), "-i", str(frame)], "null", sub_pngs, nf, fps,
                           seg, args.preview)
        segs.append(seg)

    # ---- audio track
    audio = build / "narration.wav"
    build_audio_track([(st + lead, sc["_audio"]) for sc, st in zip(kept, starts) if sc["_audio"]],
                      total + 0.05, audio)

    # ---- assemble
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for s in segs:
        cmd += ["-i", str(s)]
    cmd += ["-i", str(audio), "-i", str(srt_path)]
    ai, si = len(segs), len(segs) + 1
    graph = []
    if len(segs) == 1:
        graph.append("[0:v]null[vout]")
    elif xf > 0:
        last, off = "0:v", 0.0
        for k in range(1, len(segs)):
            off += kept[k - 1]["_dur"] - xf
            lab = "vout" if k == len(segs) - 1 else f"x{k}"
            graph.append(f"[{last}][{k}:v]xfade=transition=custom:expr='{TILE_WIPE}':duration={xf:.3f}"
                         f":offset={off:.3f}[{lab}]")
            last = lab
    else:
        graph.append("".join(f"[{k}:v]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[vout]")
    graph.append(f"[{ai}:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample={AUDIO_SR}[aout]")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]", "-map", f"{si}:s",
            *x264_args(args.preview, final=True), "-r", str(fps),
            "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng", "-metadata:s:a:0", "language=eng",
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-metadata", f"title={meta_title}", "-metadata", f"artist={meta_artist}",
            "-metadata", f"album_artist={meta_artist}",
            "-movflags", "+faststart", "-t", f"{total:.3f}", str(out_mp4)]
    run(cmd)

    if not args.keep_build:
        shutil.rmtree(build, ignore_errors=True)
        if build.parent.exists() and not any(build.parent.iterdir()):
            build.parent.rmdir()
    dur = probe_duration(out_mp4)
    print(f"\nwrote {out_mp4.relative_to(ROOT) if out_mp4.is_relative_to(ROOT) else out_mp4}")
    print(f"wrote {srt_path.relative_to(ROOT) if srt_path.is_relative_to(ROOT) else srt_path}")
    print(f"scenes: {len(kept)}   voice: {voice} @ {rate} wpm   total duration: {dur:.1f} s ({dur / 60:.2f} min)")
    if not args.preview and args.scenes is None and not 180 <= dur <= 300:
        print(f"WARNING: duration {dur:.1f} s is outside the 180-300 s target")


if __name__ == "__main__":
    main()
