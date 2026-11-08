#!/usr/bin/env python3
"""Render the narrated project video from a YAML scene script.

    python video/make_video.py                      # full render -> video/swarm_immunity.mp4
    python video/make_video.py --subtitles          # burn subtitles into the picture
    python video/make_video.py --preview            # first 3 scenes, 960x540, fast encode
    python video/make_video.py --allow-tbd          # keep placeholder scenes (missing images / TBD narration)

Scene types (see video/script.yaml): title, bullets, image, clip.
Narration is spoken with macOS `say`; scene length = narration length + `padding` seconds.
A sidecar .srt is always written next to the MP4 and also muxed as a soft subtitle track.

Requires: ffmpeg/ffprobe on PATH, macOS `say`, matplotlib, PyYAML.
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

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = Path(__file__).resolve().parent

FONT = ["Avenir Next", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
plt.rcParams["font.family"] = FONT

# Colours
NAVY = "#0B1F3A"
NAVY_2 = "#13325C"
AMBER = "#F2B134"
LIGHT = "#EEF3F9"
MUTED = "#A9BCD2"
INK = "#0B1F3A"
INK_MUTED = "#4A5B70"
WHITE = "#FFFFFF"

BASE_W, BASE_H = 1920, 1080
SUB_ZONE = 0.155  # bottom fraction of the frame kept free for subtitles
AUDIO_SR = 48000


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
    """A 16:9 matplotlib figure whose font sizes are expressed at 1920x1080 and scale with resolution."""

    def __init__(self, w: int, h: int, bg: str | None):
        self.w, self.h = w, h
        self.dpi = 100 * w / BASE_W
        self.fig = plt.figure(figsize=(BASE_W / 100, BASE_H / 100), dpi=self.dpi)
        if bg is None:
            self.fig.patch.set_alpha(0.0)
        else:
            self.fig.patch.set_facecolor(bg)
        self.renderer = self.fig.canvas.get_renderer()

    def text(self, x, y, s, size, color, weight="normal", ha="left", va="baseline", **kw):
        return self.fig.text(x, y, s, fontsize=size, color=color, weight=weight, ha=ha, va=va,
                             parse_math=False, **kw)

    def width_frac(self, s: str, size: float, weight: str = "normal") -> float:
        t = self.text(0, 0, s, size, "k", weight)
        wpx = t.get_window_extent(self.renderer).width
        t.remove()
        return wpx / self.fig.bbox.width

    def wrap(self, s: str, size: float, max_frac: float, weight: str = "normal") -> list[str]:
        lines: list[str] = []
        for para in str(s).split("\n"):
            cur = ""
            for word in para.split():
                trial = f"{cur} {word}".strip()
                if cur and self.width_frac(trial, size, weight) > max_frac:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        return lines

    def line_h(self, size: float, spacing: float = 1.25) -> float:
        """Line height in figure-height fraction for a font size given in points at 1080p."""
        return size * spacing / 72 * 100 / BASE_H

    def save(self, path: Path) -> None:
        self.fig.savefig(path, dpi=self.dpi, facecolor=self.fig.get_facecolor(),
                         transparent=self.fig.patch.get_alpha() == 0.0)
        plt.close(self.fig)


def draw_lines(c: Canvas, x, y_top, lines, size, color, weight="normal", ha="left", spacing=1.25):
    """Draw lines downward from y_top; return the y below the last line."""
    lh = c.line_h(size, spacing)
    y = y_top
    for ln in lines:
        c.text(x, y, ln, size, color, weight, ha=ha, va="top")
        y -= lh
    return y


# --------------------------------------------------------------------------- frame renderers
def render_title(scene: dict, w: int, h: int, out: Path) -> None:
    c = Canvas(w, h, NAVY)
    c.fig.add_artist(Rectangle((0, 0), 1, 0.012, transform=c.fig.transFigure, color=AMBER))
    tag = scene.get("kicker")
    tsize = float(scene.get("title_size", 62))
    while tsize > 24 and max(c.width_frac(wd, tsize, "bold") for wd in str(scene.get("title", "x")).split()) > 0.84:
        tsize -= 2  # shrink until the longest unbreakable word (e.g. a URL) fits
    title_lines = c.wrap(scene.get("title", ""), tsize, 0.84, "bold")
    sub_lines = c.wrap(scene.get("subtitle", ""), 32, 0.80) if scene.get("subtitle") else []
    author_lines = c.wrap(scene.get("author", ""), 26, 0.84, "bold") if scene.get("author") else []
    extra_lines = c.wrap(scene.get("affiliation", ""), 22, 0.84) if scene.get("affiliation") else []
    total = (len(title_lines) * c.line_h(tsize, 1.15) + 0.03 + len(sub_lines) * c.line_h(32)
             + 0.07 + len(author_lines) * c.line_h(26) + len(extra_lines) * c.line_h(22))
    y = 0.5 + SUB_ZONE / 2 + total / 2
    x = 0.08
    if tag:
        c.text(x, y + 0.05, tag.upper(), 20, AMBER, "bold", va="top")
    y = draw_lines(c, x, y, title_lines, tsize, WHITE, "bold", spacing=1.15)
    c.fig.add_artist(Rectangle((x, y - 0.012), 0.09, 0.006, transform=c.fig.transFigure, color=AMBER))
    y -= 0.03
    y = draw_lines(c, x, y, sub_lines, 32, LIGHT)
    y -= 0.07
    y = draw_lines(c, x, y, author_lines, 26, WHITE, "bold")
    draw_lines(c, x, y, extra_lines, 22, MUTED)
    c.save(out)


def render_bullets(scene: dict, w: int, h: int, out: Path) -> None:
    c = Canvas(w, h, NAVY)
    c.fig.add_artist(Rectangle((0, 0), 1, 0.012, transform=c.fig.transFigure, color=AMBER))
    x = 0.07
    y = 0.90
    if scene.get("kicker"):
        c.text(x, y, scene["kicker"].upper(), 20, AMBER, "bold", va="top")
        y -= 0.05
    y = draw_lines(c, x, y, c.wrap(scene.get("heading", ""), 46, 0.86, "bold"), 46, WHITE, "bold", spacing=1.15)
    y -= 0.045
    bullets = list(scene.get("bullets") or [])[:5]
    size = 31 if len(bullets) <= 4 else 29
    gap = 0.028
    for b in bullets:
        lines = c.wrap(b, size, 0.84)
        c.fig.add_artist(Rectangle((x + 0.002, y - c.line_h(size) * 0.62), 0.009, 0.016,
                                   transform=c.fig.transFigure, color=AMBER))
        y = draw_lines(c, x + 0.03, y, lines, size, LIGHT)
        y -= gap
    if y + gap < SUB_ZONE:
        print(f"  warning: bullets in scene '{scene.get('id')}' run into the subtitle zone (y={y:.3f})")
    c.save(out)


def render_image(scene: dict, w: int, h: int, out: Path, missing: bool = False, layer: str = "all",
                 shrink: float = 1.0) -> tuple[float, float]:
    """layer: 'all' = complete frame; 'figure' = figure only on white (for Ken Burns);
    'chrome' = transparent frame with heading/caption/panel on opaque white bands, overlaid on the zoomed figure.
    shrink < 1 draws the figure smaller about its box centre, so a later zoom of 1/shrink fills the box exactly.
    Returns the figure box centre as (x, y) fractions measured from the top-left corner."""
    c = Canvas(w, h, None if layer == "chrome" else WHITE)
    draw_text = layer in ("all", "chrome")
    top = 0.955
    if scene.get("heading"):
        lines = c.wrap(scene["heading"], 38, 0.88, "bold")
        y = top - len(lines) * c.line_h(38, 1.15)
        if draw_text:
            draw_lines(c, 0.06, top, lines, 38, INK, "bold", spacing=1.15)
        top = y - 0.02
    bottom = SUB_ZONE + 0.015
    if scene.get("caption"):
        cap_lines = c.wrap(scene["caption"], 24, 0.86)
        cap_h = len(cap_lines) * c.line_h(24)
        if draw_text:
            draw_lines(c, 0.5, bottom + cap_h, cap_lines, 24, INK_MUTED, ha="center")
        bottom += cap_h + 0.02
    left, right = 0.05, 0.95
    bullets = list(scene.get("bullets") or [])[:5]
    if bullets:
        right = 0.66
        px = 0.69
        y = top - 0.01
        for b in (bullets if draw_text else []):
            lines = c.wrap(b, 25, 0.27)
            c.fig.add_artist(Rectangle((px, y - c.line_h(25) * 0.62), 0.007, 0.014,
                                       transform=c.fig.transFigure, color=AMBER))
            y = draw_lines(c, px + 0.018, y, lines, 25, INK)
            y -= 0.022
    if layer == "chrome":
        # opaque bands that mask the zoomed figure wherever text lives
        band = dict(transform=c.fig.transFigure, color=WHITE, zorder=-1)
        c.fig.add_artist(Rectangle((0, top), 1, 1 - top, **band))
        c.fig.add_artist(Rectangle((0, 0), 1, bottom, **band))
        c.fig.add_artist(Rectangle((0, 0), left, 1, **band))
        c.fig.add_artist(Rectangle((right, 0), 1 - right, 1, **band))
    if draw_text:
        c.fig.add_artist(Rectangle((0, 0), 1, 0.012, transform=c.fig.transFigure, color=AMBER))
    if layer == "chrome":
        pass
    elif missing:
        c.fig.add_artist(FancyBboxPatch((left, bottom), right - left, top - bottom,
                                        boxstyle="round,pad=0,rounding_size=0.01",
                                        transform=c.fig.transFigure, fc="#F1F4F8", ec="#C9D3DF", lw=2))
        c.text((left + right) / 2, (top + bottom) / 2 + 0.03, "Figure pending", 40, INK_MUTED, "bold",
               ha="center", va="center")
        c.text((left + right) / 2, (top + bottom) / 2 - 0.04, str(scene.get("image", "")), 24, INK_MUTED,
               ha="center", va="center")
    else:
        img = mpimg.imread(ROOT / scene["image"])
        bw, bh = (right - left) * shrink, (top - bottom) * shrink
        ax = c.fig.add_axes([(left + right - bw) / 2, (top + bottom - bh) / 2, bw, bh])
        ax.imshow(img, interpolation="antialiased")
        ax.set_aspect("equal")
        ax.axis("off")
    c.save(out)
    return (left + right) / 2, 1 - (top + bottom) / 2


def render_subtitle(text_lines: list[str], w: int, h: int, out: Path) -> None:
    c = Canvas(w, h, None)
    size = 30
    lh = c.line_h(size, 1.2)
    width = max(c.width_frac(ln, size) for ln in text_lines) + 0.03
    box_h = lh * len(text_lines) + 0.022
    y0 = 0.025
    c.fig.add_artist(FancyBboxPatch((0.5 - width / 2, y0), width, box_h,
                                    boxstyle="round,pad=0,rounding_size=0.008",
                                    transform=c.fig.transFigure, fc="black", ec="none", alpha=0.8))
    draw_lines(c, 0.5, y0 + box_h - 0.011, text_lines, size, WHITE, ha="center", spacing=1.2)
    c.save(out)


# --------------------------------------------------------------------------- subtitle chunking
def chunk_narration(text: str, w: int, h: int, max_lines: int = 2) -> list[list[str]]:
    """Split narration into on-screen chunks of at most `max_lines` lines."""
    c = Canvas(w, h, None)
    sentences = re.split(r"(?<=[.!?;:])\s+", " ".join(str(text).split()))
    chunks: list[list[str]] = []
    for s in sentences:
        if not s:
            continue
        lines = c.wrap(s, 30, 0.80)
        while len(lines) > max_lines:
            # try to break the sentence at a comma near the middle of the allowed span
            head = " ".join(lines[:max_lines])
            cut = head.rfind(", ")
            if cut > len(head) * 0.35:
                part, rest = head[: cut + 1], head[cut + 2:] + " " + " ".join(lines[max_lines:])
            else:
                part, rest = head, " ".join(lines[max_lines:])
            chunks.append(c.wrap(part, 30, 0.80))
            lines = c.wrap(rest.strip(), 30, 0.80)
        chunks.append(lines)
    plt.close(c.fig)
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
    ap.add_argument("--no-xfade", action="store_true", help="hard cuts instead of crossfades")
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
            zexpr = f"1+{zmax - 1:.4f}*on/{max(nf - 1, 1)}"
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
            graph.append(f"[{last}][{k}:v]xfade=transition=fade:duration={xf:.3f}:offset={off:.3f}[{lab}]")
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
