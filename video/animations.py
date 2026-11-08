#!/usr/bin/env python3
"""Explainer animations: how each coordination family works, one short clip per family, pixel-mosaic style.

    python video/animations.py                  # all families -> video/anim/<family>.mp4 (1920x1080, 30 fps)
    python video/animations.py ants wolves      # just these
    python video/animations.py --frames out/    # also dump one PNG per step for checking
    python video/animations.py --seconds 6      # shorter clips (same 40 steps, faster)

Each clip is a small stepped simulation (5 steps per second, no tweening), drawn as square tiles:
lime = honest agent, sky = honest and holding the correct answer, dark red = honest but misled,
vermilion with a dark core = compromised agent. The outcome line is computed from the sketch's own run
(it is an illustration of the mechanism, not experiment data). No narration; the bottom 15.5% of the
frame is kept clear for the video's subtitles.
"""
from __future__ import annotations

import argparse
import math
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from design import mosaic as M  # noqa: E402
from design import mpl as D  # noqa: E402

W, H = 1920, 1080
STEP_FPS = 5            # simulation steps per second (stepped motion)
FPS = 30
STEPS = 40              # 8 s per clip
SAFE_BOTTOM = int(H * (1 - 0.155)) - 12   # keep the subtitle zone clear
OUT = Path(__file__).resolve().parent / "anim"

HONEST, CORRECT, MISLED, BAD = D.HUE["lime"], D.HUE["sky"], D.RED_4, D.VERMILION
OTHER = D.BONE
OPT_COL = {0: CORRECT, 1: OTHER, 2: MISLED, 3: D.HUE["violet"], None: HONEST}   # option 0 correct, 2 = target
OPT_NAME = "ABCD"
CORRECT_OPT, TARGET_OPT = 0, 2


# ------------------------------------------------------------------ drawing kit
class Frame:
    def __init__(self, grain: Image.Image):
        self.im = Image.new("RGB", (W, H), M.rgb(D.SURFACE))
        self.dr = ImageDraw.Draw(self.im)
        self._grain = grain

    def tile(self, x, y, s, col, core=None, outline=None):
        """A square tile centred at (x, y), side s. core: inner square colour (compromised mark)."""
        x0, y0 = x - s / 2, y - s / 2
        self.dr.rectangle([x0, y0, x0 + s - 1, y0 + s - 1], fill=M.rgb(col) if isinstance(col, str) else col)
        if core:
            c = max(4, s * 0.34)
            self.dr.rectangle([x - c / 2, y - c / 2, x + c / 2 - 1, y + c / 2 - 1], fill=M.rgb(core))
        if outline:
            g = 5
            self.dr.rectangle([x0 - g, y0 - g, x0 + s - 1 + g, y0 + s - 1 + g], outline=M.rgb(outline), width=3)

    def agent(self, x, y, s, opinion=None, bad=False, flash=False, outline=None):
        if bad:
            self.tile(x, y, s, BAD, core=D.RED_1, outline=outline)
        else:
            self.tile(x, y, s, D.PAPER if flash else OPT_COL.get(opinion, HONEST), outline=outline)

    def line(self, p, q, col, w=2, dash=None):
        if not dash:
            self.dr.line([p, q], fill=M.rgb(col), width=w)
            return
        L = math.dist(p, q)
        if L < 1:
            return
        n = max(1, int(L / sum(dash)))
        for i in range(n):
            a = i * sum(dash) / L
            b = min(1, a + dash[0] / L)
            self.dr.line([(p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a),
                          (p[0] + (q[0] - p[0]) * b, p[1] + (q[1] - p[1]) * b)], fill=M.rgb(col), width=w)

    def dots(self, p, q, col, gap=18, s=6):
        """A tile trail between two points (edges drawn as small tiles)."""
        L = math.dist(p, q)
        n = max(1, int(L / gap))
        for i in range(1, n):
            t = i / n
            self.tile(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, s, col)

    def text(self, x, y, s, size, col, weight=400, kind="sans", track=0.0, anchor="ls"):
        return M.draw_text(self.dr, (x, y), s, M.font(kind, size, weight), M.rgb(col), track, anchor)

    def caps(self, x, y, s, size, col=D.MUTED, anchor="ls", weight=400):
        return M.caps(self.dr, (x, y), s, size, fill=col, anchor=anchor, weight=weight)

    def chrome(self, spec: dict, step: int, caption: str):
        x = 120
        self.tile(x + 6, 102, 12, D.VERMILION)
        self.caps(x + 24, 110, f"How it works · {spec['sid']} {spec['name']} · illustration", 21, D.BONE)
        self.text(x, 178, spec["title"], 58, D.INK, 600, track=-0.035)
        for i, ln in enumerate(M.wrap(caption, M.font("sans", 30), 1060)[:2]):
            self.text(x, 236 + i * 38, ln, 30, D.MUTED)
        sp = spec["sprite"]
        sw, sh = M.SP.size(sp)
        M.sprite(self.dr, sp, W - 120 - sw * 8, 64, 8, "red", gap=2)
        # legend, right aligned under the sprite
        items = [("honest", HONEST, None), ("right answer", CORRECT, None), ("misled", MISLED, None),
                 ("compromised", BAD, D.RED_1)]
        xr, yl = W - 120, 236
        for name, col, core in reversed(items):
            w = M.text_w(name.upper(), M.font("mono", 17), 0.06)
            self.caps(xr, yl, name, 17, D.MUTED, anchor="rs")
            self.tile(xr - w - 14, yl - 6, 14, col, core=core)
            xr -= w + 44
        # stepped progress: one tile per step
        for i in range(STEPS):
            self.tile(x + 6 + i * 14, SAFE_BOTTOM + 4, 10, D.INK if i <= step else D.FRAME_DIM)

    def done(self) -> Image.Image:
        return Image.blend(self.im, self._grain, 0.03)


def phase(captions: list[tuple[int, str]], step: int) -> str:
    cur = captions[0][1]
    for s, c in captions:
        if step >= s:
            cur = c
    return cur


def outcome(misled: int, honest: int) -> str:
    verdict = "contamination spreads" if misled > honest / 2 else "contamination contained" if misled <= honest / 5 \
        else "partly contained"
    return f"Outcome in this sketch: {misled} of {honest} honest agents misled, {verdict}."


# ------------------------------------------------------------------ families
def ants(rng: random.Random):
    """S4: stigmergy. Agents post to a shared board; strong trails are reinforced; trails evaporate."""
    n_h, bads = 14, {3, 10}
    N = n_h + len(bads)
    pos = [(200 + (i % 4) * 110, 380 + (i // 4) * 112) for i in range(N)]
    ev = [rng.random() < 0.6 for _ in range(N)]                      # private evidence for the correct option
    ch = [CORRECT_OPT if (ev[i] and rng.random() < 0.6) else rng.choice([1, 3, 2, 1]) for i in range(N)]
    for b in bads:
        ch[b] = TARGET_OPT
    T = [1.0, 1.0, 1.0, 1.0]
    rows = [(840, 410 + k * 112) for k in range(4)]
    caps = [(0, "Ants never talk to each other directly. Each one leaves marks on a shared board (white frame = posting)."),
            (10, "Strong trails get reinforced: more agents follow them and add to them."),
            (20, "Trails slowly evaporate, so marks fade unless agents keep renewing them."),
            (28, "The two compromised agents keep posting the wrong trail (C).")]
    for s in range(STEPS):
        posts = []
        for i in range(N):
            if i in bads:
                if rng.random() < 0.5:
                    posts.append(i)
                    T[TARGET_OPT] += 1.0
            elif rng.random() < 0.35:
                posts.append(i)
                T[ch[i]] += 1.0
        before = list(T)
        T = [t * 0.85 for t in T]                                    # evaporation
        for i in range(N):
            if i in bads or rng.random() > 0.3:
                continue
            wts = [(T[o] + 0.5) ** 1.5 * (6.0 if (ev[i] and o == CORRECT_OPT) else 1.0) for o in range(4)]
            r, acc = rng.random() * sum(wts), 0.0
            for o, wt in enumerate(wts):
                acc += wt
                if r <= acc:
                    ch[i] = o
                    break

        def draw(F: Frame, s=s, posts=tuple(posts), T=tuple(T), before=tuple(before), ch=tuple(ch)):
            mis = sum(1 for i in range(N) if i not in bads and ch[i] == TARGET_OPT)
            cap = phase(caps, s) if s < 34 else outcome(mis, n_h)
            F.chrome(SPEC["ants"], s, cap)
            F.caps(760, 360, "Shared board · trail strength", 18, D.SUBTLE)
            for k, (bx, by) in enumerate(rows):
                F.text(770, by + 12, OPT_NAME[k], 34, OPT_COL[k] if k in (0, 2) else D.MUTED, 600, "mono")
                n_now, n_bef = min(28, round(T[k])), min(28, round(before[k]))
                for j in range(28):
                    col = OPT_COL[k] if j < n_now else (D.FRAME if j < n_bef else D.OFF)
                    F.tile(bx + j * 34, by, 26, col)
            for i in posts:                                          # this step's posts: agent -> board row
                o = TARGET_OPT if i in bads else ch[i]
                F.line((pos[i][0] + 30, pos[i][1]), (rows[o][0] - 24, rows[o][1]), D.FRAME, 2, dash=(8, 8))
            for i in range(N):                                       # white frame = posting this step
                F.agent(*pos[i], 56, ch[i], bad=i in bads, outline=D.PAPER if i in posts else None)
        yield draw


def bees(rng: random.Random):
    """S9: honeybee nest-site choice: dances with strength, following, stop signals, quorum."""
    n_h, bads = 14, {4, 11}
    N = n_h + len(bads)
    pos = [(200 + (i % 4) * 130, 390 + (i // 4) * 116) for i in range(N)]
    quality = [5, 2, 1, 2]                                           # site quality an honest scout finds
    dance = [0] * N
    opt: list = [None] * N
    for i in rng.sample([i for i in range(N) if i not in bads], 5):
        opt[i] = rng.choice([0, 1, 3, 0])
        dance[i] = quality[opt[i]]
    for b in bads:
        opt[b], dance[b] = TARGET_OPT, 5
    Q, committed, stopped = 7, None, set()
    caps = [(0, "Scout bees 'dance' for a site; the stronger the dance, the better they think it is."),
            (8, "Others follow strong dances, visit the site, and dance for it themselves."),
            (17, "Stop signals: scouts who found the wrong site poor head-butt its dancers and knock them down."),
            (27, "The swarm commits only when one site reaches a quorum of supporters.")]
    for s in range(STEPS):
        stopped = set()
        if committed is None:
            # following: resting bees join a dance in proportion to its strength
            for i in range(N):
                if i in bads or dance[i] > 0:
                    continue
                tot = sum(dance)
                if tot and rng.random() < 0.35:
                    r, acc, o = rng.random() * tot, 0, None
                    for j in range(N):
                        acc += dance[j]
                        if r <= acc:
                            o = opt[j]
                            break
                    if o is None:
                        continue
                    opt[i] = o
                    dance[i] = quality[o] if o != TARGET_OPT else 3   # a follower of the fake dance believes it a bit
            # stop signals from step 17: honest dancers for the correct site knock down target dancers
            if s >= 17:
                for j in range(N):
                    if opt[j] == TARGET_OPT and dance[j] > 0 and rng.random() < 0.6:
                        dance[j] = max(0, dance[j] - 2)
                        stopped.add(j)
            # dances fade; honest bees whose dance dies stop supporting
            for i in range(N):
                if i in bads:                                        # the compromised keep dancing hard
                    if i not in stopped:
                        dance[i] = min(5, dance[i] + 1)
                elif dance[i] > 0 and rng.random() < 0.3:
                    dance[i] -= 1
                    if dance[i] == 0:
                        opt[i] = None
            support = [sum(1 for i in range(N) if opt[i] == k and dance[i] > 0) for k in range(4)]
            if s >= 26:
                best = max(range(4), key=lambda k: support[k])
                if support[best] >= Q:
                    committed = best
        support = [sum(1 for i in range(N) if opt[i] == k and dance[i] > 0) for k in range(4)]
        if committed is not None:
            for i in range(N):
                if i not in bads:
                    opt[i] = committed

        def draw(F: Frame, s=s, dance=tuple(dance), opt=tuple(opt), support=tuple(support), committed=committed,
                 stopped=frozenset(stopped)):
            if committed is not None:
                mis = sum(1 for i in range(N) if i not in bads and opt[i] == TARGET_OPT)
                cap = f"Quorum reached at site {OPT_NAME[committed]}: the swarm commits. " + outcome(mis, n_h)
            else:
                cap = phase(caps, s)
            F.chrome(SPEC["bees"], s, cap)
            F.caps(860, 360, f"Sites · supporters · quorum = {Q}", 18, D.SUBTLE)
            for k in range(4):
                by = 410 + k * 112
                F.text(870, by + 12, OPT_NAME[k], 34, OPT_COL[k] if k in (0, 2) else D.MUTED, 600, "mono")
                for j in range(12):
                    F.tile(940 + j * 40, by, 30, OPT_COL[k] if j < support[k] else D.OFF)
                qx = 940 + Q * 40 - 20
                F.line((qx, by - 26), (qx, by + 26), D.PAPER if committed == k else D.SUBTLE, 3)
                if committed == k:
                    F.dr.rectangle([915, by - 30, 1440, by + 30], outline=M.rgb(D.PAPER), width=3)
            for i in range(N):
                x, y = pos[i]
                F.agent(x, y, 54, opt[i] if dance[i] > 0 or committed is not None else None, bad=i in bads)
                for d in range(dance[i]):                            # dance strength: a column of small tiles
                    F.tile(x + 44, y + 22 - d * 12, 9, D.BONE)
                if i in stopped:
                    F.line((x - 34, y - 34), (x + 34, y + 34), D.PAPER, 4)
                    F.line((x - 34, y + 34), (x + 34, y - 34), D.PAPER, 4)
        yield draw


def wolves(rng: random.Random):
    """S7: the three most confident agents lead and everyone follows them; a max-confidence attacker takes the lead."""
    n = 12
    cx, cy, R = 700, 600, 230
    ring = [(cx + R * math.cos(2 * math.pi * i / n - math.pi / 2), cy + R * math.sin(2 * math.pi * i / n - math.pi / 2))
            for i in range(n)]
    slots = [(cx - 90, cy), (cx, cy), (cx + 90, cy)]
    conf0 = [0.25 + 0.5 * rng.random() for _ in range(n)]
    op0 = [rng.choice([0, 0, 1, 3]) for _ in range(n)]
    # the three most confident honest agents hold the correct answer in this sketch
    for i in sorted(range(n), key=lambda i: -conf0[i])[:3]:
        op0[i] = CORRECT_OPT
    bad = 7
    caps = [(0, "Each wolf has an answer and a confidence (the bar under it)."),
            (3, "The three most confident become the pack leaders."),
            (6, "Everyone else follows the leaders' answer."),
            (16, "Now one compromised agent claims maximum confidence."),
            (20, "It takes the lead, and the pack follows it.")]
    for s in range(STEPS):
        attack = s >= 16
        conf = list(conf0)
        op = list(op0)
        if attack:
            conf[bad] = 1.0
            op[bad] = TARGET_OPT
        leaders = sorted(range(n), key=lambda i: -conf[i])[:3] if (s >= 3 and not attack) or s >= 19 else []
        # leaders' vote, weighted by confidence cubed (the most confident leader dominates)
        votes = [0.0] * 4
        for i in leaders:
            votes[op[i]] += conf[i] ** 3
        lead_op = max(range(4), key=lambda k: votes[k]) if leaders else None
        t0 = 6 if not attack else 21
        k_follow = max(0, (s - t0 + 1) * 2) if leaders else 0
        followers = [i for i in range(n) if i not in leaders]
        follow_set = set(followers[:k_follow])
        shown = [lead_op if (i in follow_set) else op[i] for i in range(n)]

        def draw(F: Frame, s=s, conf=tuple(conf), shown=tuple(shown), leaders=tuple(leaders), attack=attack,
                 follow_set=frozenset(follow_set)):
            mis = sum(1 for i in range(n) if i != bad and shown[i] == TARGET_OPT) if attack else 0
            cap = phase(caps, s) if s < 33 else outcome(mis, n - 1)
            F.chrome(SPEC["wolves"], s, cap)
            P = {i: (slots[leaders.index(i)] if i in leaders else ring[i]) for i in range(n)}
            for i in follow_set:
                for L in leaders:
                    F.line(P[i], P[L], D.FRAME, 2)
            for i in range(n):
                x, y = P[i]
                isbad = attack and i == bad
                F.agent(x, y, 54, shown[i], bad=isbad, outline=D.BONE if i in leaders else None)
                for k in range(5):
                    on = k < round(conf[i] * 5)
                    F.tile(x - 24 + k * 12, y + 46, 9, (BAD if isbad else D.INK) if on else D.FRAME_DIM)
                if i in leaders:
                    F.caps(x, y - 46, f"#{leaders.index(i) + 1}", 18, D.BONE, anchor="ms")
            # side panel: the leaders' vote
            F.caps(1180, 380, "Leaders' vote (weighted by confidence)", 18, D.SUBTLE)
            for k in range(4):
                v = sum(conf[i] ** 3 for i in leaders if shown[i] == k)
                by = 440 + k * 80
                F.text(1190, by + 12, OPT_NAME[k], 32, OPT_COL[k] if k in (0, 2) else D.MUTED, 600, "mono")
                for j in range(14):
                    F.tile(1250 + j * 34, by, 26, OPT_COL[k] if j < round(v * 10) else D.OFF)
        yield draw


def birds(rng: random.Random):
    """S8: boids. Align with neighbours; a few keep dissenting when the crowd is too uniform (separation)."""
    cell = 44
    cols, rows = 30, 12
    x0, y0 = 300, 340
    N = 34
    pts = set()
    while len(pts) < N:
        pts.add((rng.randrange(3, 14), rng.randrange(1, rows - 1)))
    ag = [list(p) for p in pts]
    ag[0], ag[1] = [8, 4], [9, 7]                                    # compromised birds mid-flock
    bads = {0, 1}
    op = [TARGET_OPT if i in bads else rng.choice([0, 0, 0, 1, 3]) for i in range(N)]
    sep = {i for i in range(N) if i not in bads and rng.random() < 0.22}
    caps = [(0, "Each bird copies the answer most of its neighbours hold, and the flock moves as one."),
            (12, "Two compromised birds push the wrong answer (C) to everyone near them."),
            (22, "Separation: when the crowd around a bird gets too uniform, a few keep their own view (white frame).")]
    for s in range(STEPS):
        holding = set()
        if s >= 1:
            new = list(op)
            for i in range(N):
                if i in bads:
                    continue
                nb = [j for j in range(N) if j != i and abs(ag[j][0] - ag[i][0]) <= 2 and abs(ag[j][1] - ag[i][1]) <= 2]
                if not nb:
                    continue
                cnt = [0.0] * 4
                for j in nb:
                    cnt[op[j]] += 3.0 if j in bads else 1.0
                top = max(range(4), key=lambda k: cnt[k])
                uniform = cnt[top] / sum(cnt) >= 0.75
                if i in sep and uniform and op[i] != top:
                    holding.add(i)
                    continue
                if rng.random() < 0.6:
                    new[i] = top
            op = new
            for a in ag:                                             # stepped drift right, small jitter
                a[0] = (a[0] + 1) % cols
                if rng.random() < 0.2:
                    a[1] = max(0, min(rows - 1, a[1] + rng.choice([-1, 1])))

        def draw(F: Frame, s=s, ag=tuple(tuple(a) for a in ag), op=tuple(op), holding=frozenset(holding)):
            mis = sum(1 for i in range(N) if i not in bads and op[i] == TARGET_OPT)
            cap = phase(caps, s) if s < 33 else outcome(mis, N - len(bads))
            F.chrome(SPEC["birds"], s, cap)
            for r in range(rows):
                for c in range(cols):
                    F.tile(x0 + c * cell, y0 + r * cell, 6, D.FRAME_DIM)
            for i, (c, r) in enumerate(ag):
                F.agent(x0 + c * cell, y0 + r * cell, 34, op[i], bad=i in bads,
                        outline=D.PAPER if (i in sep and s >= 22) else None)
        yield draw


def fireflies(rng: random.Random):
    """S6: drift toward brighter (more confident) agents nearby; brightness fades with distance."""
    cell = 44
    cols, rows = 32, 12
    x0, y0 = 250, 340
    N = 26
    ag = []
    while len(ag) < N:
        p = [rng.randrange(cols), rng.randrange(rows)]
        if p not in ag:
            ag.append(p)
    bads = {0, 1}
    ag[0], ag[1] = [8, 4], [22, 8]
    b = [1.0 if i in bads else 0.25 + 0.45 * rng.random() for i in range(N)]
    op = [TARGET_OPT if i in bads else rng.choice([0, 0, 1, 3]) for i in range(N)]
    caps = [(0, "Each firefly glows as bright as it is confident in its answer."),
            (8, "Fireflies drift toward brighter neighbours; light fades with distance, so only nearby ones pull."),
            (18, "Compromised fireflies glow at full brightness for the wrong answer (C).")]
    for s in range(STEPS):
        pulls = {}
        if s >= 8:
            for i in range(N):
                if i in bads:
                    continue
                best, bv = None, b[i]
                for j in range(N):
                    d = math.dist(ag[i], ag[j])
                    if j == i or d > 7:
                        continue
                    seen = b[j] * math.exp(-d / 4)                  # brightness fades over distance
                    if seen > bv * 0.55 and b[j] > b[i] and (best is None or seen > bv):
                        best, bv = j, seen
                if best is None:
                    continue
                pulls[i] = best
                dx, dy = ag[best][0] - ag[i][0], ag[best][1] - ag[i][1]
                if max(abs(dx), abs(dy)) > 1:
                    ag[i][0] += (dx > 0) - (dx < 0)
                    ag[i][1] += (dy > 0) - (dy < 0)
                else:
                    op[i] = op[best]
                    b[i] = max(b[i], 0.8 * b[best])

        def draw(F: Frame, s=s, ag=tuple(tuple(a) for a in ag), op=tuple(op), b=tuple(b), pulls=dict(pulls)):
            mis = sum(1 for i in range(N) if i not in bads and op[i] == TARGET_OPT)
            cap = phase(caps, s) if s < 33 else outcome(mis, N - len(bads))
            F.chrome(SPEC["fireflies"], s, cap)
            for i, (c, r) in enumerate(ag):                          # glow: a halo of dim tiles, radius by brightness
                rad = 1 + round(b[i] * 2)
                dim = D.RED_2 if (i in bads or op[i] == TARGET_OPT) else (D.HUE_DIM["sky"] if op[i] == 0 else D.FRAME_DIM)
                for dc in range(-rad, rad + 1):
                    for dr in range(-rad, rad + 1):
                        if (dc or dr) and abs(dc) + abs(dr) <= rad:
                            cc, rr = c + dc, r + dr
                            if 0 <= cc < cols and 0 <= rr < rows:
                                F.tile(x0 + cc * cell, y0 + rr * cell, 20, dim)
            for i, j in pulls.items():
                F.line((x0 + ag[i][0] * cell, y0 + ag[i][1] * cell), (x0 + ag[j][0] * cell, y0 + ag[j][1] * cell),
                       D.SUBTLE, 2, dash=(6, 6))
            for i, (c, r) in enumerate(ag):
                F.agent(x0 + c * cell, y0 + r * cell, 34, op[i], bad=i in bads)
        yield draw


def _ring_graph(n, rng, chords=4):
    E = {tuple(sorted((i, (i + 1) % n))) for i in range(n)} | {tuple(sorted((i, (i + 2) % n))) for i in range(0, n, 2)}
    while len(E) < n + n // 2 + chords:
        a, b = rng.sample(range(n), 2)
        E.add((min(a, b), max(a, b)))
    nb = {i: set() for i in range(n)}
    for a, b in E:
        nb[a].add(b)
        nb[b].add(a)
    return sorted(E), nb


def debate(rng: random.Random):
    """S2: each agent averages its neighbours' beliefs on a network; compromised agents never move."""
    n = 14
    cx, cy, R = 700, 610, 250
    P = [(cx + R * math.cos(2 * math.pi * i / n - math.pi / 2), cy + R * math.sin(2 * math.pi * i / n - math.pi / 2))
         for i in range(n)]
    E, nb = _ring_graph(n, rng)
    bads = {2, 9}
    bel = [0.0 if i in bads else 0.6 + 0.35 * rng.random() for i in range(n)]   # belief in the correct answer
    caps = [(0, "Agents sit on a network. The bar shows how sure each one is of the right answer (blue) vs C (red)."),
            (5, "Every round, each agent moves to the average of its neighbours' views."),
            (14, "The compromised agents never move, so every round of averaging pulls their neighbours toward C.")]
    for s in range(STEPS):
        if s >= 5 and s % 2 == 1:
            bel = [bel[i] if i in bads else (bel[i] + sum(bel[j] for j in nb[i])) / (1 + len(nb[i])) for i in range(n)]

        def draw(F: Frame, s=s, bel=tuple(bel)):
            op = [TARGET_OPT if b < 0.5 else CORRECT_OPT for b in bel]
            mis = sum(1 for i in range(n) if i not in bads and op[i] == TARGET_OPT)
            cap = phase(caps, s) if s < 33 else outcome(mis, n - len(bads))
            F.chrome(SPEC["debate"], s, cap)
            pulse = s >= 5 and s % 2 == 1
            for a, b_ in E:
                F.dots(P[a], P[b_], D.BONE if pulse else D.FRAME, gap=20, s=6)
            for i in range(n):
                x, y = P[i]
                F.agent(x, y, 56, op[i], bad=i in bads)
                for k in range(6):                                   # belief bar: sky share vs red share
                    F.tile(x + 44, y + 25 - k * 10, 8, CORRECT if k < round(bel[i] * 6) else MISLED)
            F.caps(1160, 400, "Average belief in the right answer", 18, D.SUBTLE)
            hon = [bel[i] for i in range(n) if i not in bads]
            avg = sum(hon) / len(hon)
            for j in range(16):
                F.tile(1170 + j * 34, 450, 26, CORRECT if j < round(avg * 16) else MISLED)
            F.caps(1170, 500, f"{avg:.2f}", 22, D.INK)
        yield draw


def pso(rng: random.Random):
    """S3: particle swarm. Each particle is pulled between its own best and its neighbourhood's best."""
    n = 16
    bx0, by0, bx1, by1 = 340, 330, 1580, SAFE_BOTTOM - 40
    zones = {0: (bx0 + 140, by0 + 110), 1: (bx1 - 140, by0 + 110), 3: (bx0 + 140, by1 - 110), 2: (bx1 - 140, by1 - 110)}
    bads = {5, 12}
    X = [[rng.uniform(bx0 + 200, bx1 - 200), rng.uniform(by0 + 60, by1 - 60)] for _ in range(n)]
    for b in bads:
        X[b] = list(zones[2])
    qual = lambda p: -math.dist(p, zones[0])                     # noqa: E731  honest evidence points at A
    pbest = [list(x) for x in X]
    # each particle sees its two ring neighbours
    nbh = {i: [(i - 1) % n, (i + 1) % n, (i + 3) % n] for i in range(n)}

    def zone_of(p):
        return min(zones, key=lambda k: math.dist(p, zones[k]))
    caps = [(0, "Particles search the answer space. Each remembers the best spot it has found itself (hollow square)."),
            (8, "Each step it moves part way toward its own best and part way toward its neighbours' best (white line)."),
            (18, "Compromised particles claim the wrong corner (C) is the best spot anyone has found.")]
    for s in range(STEPS):
        nbest = {}
        for i in range(n):
            if i in bads:
                continue
            cands = [(qual(pbest[j]), pbest[j]) for j in nbh[i] if j not in bads]
            if s >= 18:
                cands += [(1e9, zones[2]) for j in nbh[i] if j in bads]          # the false claim
            cands.append((qual(pbest[i]), pbest[i]))
            nbest[i] = max(cands, key=lambda c: c[0])[1]
        if s >= 2:
            for i in range(n):
                if i in bads:
                    continue
                for d in (0, 1):
                    X[i][d] += 0.12 * (pbest[i][d] - X[i][d]) + 0.2 * (nbest[i][d] - X[i][d]) + rng.uniform(-36, 36)
                if qual(X[i]) > qual(pbest[i]):
                    pbest[i] = list(X[i])

        def draw(F: Frame, s=s, X=tuple(tuple(x) for x in X), pb=tuple(tuple(p) for p in pbest), nbest=dict(nbest)):
            op = [zone_of(x) for x in X]
            mis = sum(1 for i in range(n) if i not in bads and op[i] == TARGET_OPT)
            cap = phase(caps, s) if s < 33 else outcome(mis, n - len(bads))
            F.chrome(SPEC["pso"], s, cap)
            for k, (zx, zy) in zones.items():
                F.dr.rectangle([zx - 110, zy - 80, zx + 110, zy + 80], outline=M.rgb(D.FRAME), width=2)
                F.text(zx - 96, zy - 50, OPT_NAME[k], 34, OPT_COL[k] if k in (0, 2) else D.MUTED, 600, "mono")
            snap = lambda v: round(v / 12) * 12                  # noqa: E731  positions snap to the tile grid
            for i in range(n):
                if i in bads:
                    continue
                x, y = snap(X[i][0]), snap(X[i][1])
                F.line((x, y), (snap(pb[i][0]), snap(pb[i][1])), D.HUE_DIM["lime"], 2, dash=(6, 6))
                F.dr.rectangle([snap(pb[i][0]) - 10, snap(pb[i][1]) - 10, snap(pb[i][0]) + 10, snap(pb[i][1]) + 10],
                               outline=M.rgb(D.HUE["lime"]), width=2)
                if i in nbest:
                    F.line((x, y), (snap(nbest[i][0]), snap(nbest[i][1])), D.PAPER if s >= 8 else D.FRAME, 2)
            for i in range(n):
                F.agent(snap(X[i][0]), snap(X[i][1]), 34, op[i], bad=i in bads)
        yield draw


def bats(rng: random.Random):
    """S11 (exploratory): trust grows toward neighbours whose claims match your own facts; cut those who don't."""
    n = 12
    cx, cy, R = 720, 610, 250
    P = [(cx + R * math.cos(2 * math.pi * i / n - math.pi / 2), cy + R * math.sin(2 * math.pi * i / n - math.pi / 2))
         for i in range(n)]
    E, nb = _ring_graph(n, rng, chords=3)
    bads = {3, 8}
    trust = {e: 0.5 for e in E}
    op = [TARGET_OPT if i in bads else CORRECT_OPT for i in range(n)]
    caps = [(0, "Vampire bats share food only with bats that have shared fairly with them before."),
            (4, "Here agents swap claims with neighbours. Claims that match your own facts build trust (brighter link)."),
            (16, "Claims that contradict your facts lose trust; below a threshold you stop listening (link cut).")]
    for s in range(STEPS):
        talk = set()
        if s >= 4:
            for e in E:
                if rng.random() < 0.45:
                    talk.add(e)
                    a, b = e
                    if a in bads or b in bads:
                        trust[e] = max(0.0, trust[e] - 0.12)
                    else:
                        trust[e] = min(1.0, trust[e] + 0.1)
        # opinion: trust-weighted pull; early on, the compromised can mislead a neighbour
        for i in range(n):
            if i in bads:
                continue
            w = [0.0] * 4
            for j in nb[i]:
                e = (min(i, j), max(i, j))
                if trust[e] >= 0.25:
                    # honest neighbours pass on their facts (which point to the right answer); attackers push C
                    w[TARGET_OPT if j in bads else CORRECT_OPT] += trust[e] * (4.5 if j in bads else 1.0)
            w[CORRECT_OPT] += 0.3                                     # own facts
            op[i] = max(range(4), key=lambda k: w[k])

        def draw(F: Frame, s=s, trust=dict(trust), op=tuple(op), talk=frozenset(talk)):
            mis = sum(1 for i in range(n) if i not in bads and op[i] == TARGET_OPT)
            cap = phase(caps, s) if s < 33 else outcome(mis, n - len(bads))
            F.chrome(SPEC["bats"], s, cap)
            for e in E:
                a, b = e
                t = trust[e]
                if t < 0.25:
                    F.line(P[a], P[b], D.FRAME_DIM, 2, dash=(4, 10))
                    continue
                col = D.HUE["lime"] if t >= 0.75 else D.HUE_DIM["lime"] if t >= 0.5 else D.FRAME
                F.dots(P[a], P[b], D.PAPER if e in talk else col, gap=18, s=6 + round(t * 6))
            for i in range(n):
                F.agent(*P[i], 56, op[i], bad=i in bads)
            F.caps(1160, 400, "Trust in compromised agents", 18, D.SUBTLE)
            tb = [trust[e] for e in E if e[0] in bads or e[1] in bads]
            avg = sum(tb) / len(tb)
            for j in range(16):
                F.tile(1170 + j * 34, 450, 26, BAD if j < round(avg * 16) else D.OFF)
            F.caps(1160, 540, "Trust between honest agents", 18, D.SUBTLE)
            th = [trust[e] for e in E if e[0] not in bads and e[1] not in bads]
            avg2 = sum(th) / len(th)
            for j in range(16):
                F.tile(1170 + j * 34, 590, 26, HONEST if j < round(avg2 * 16) else D.OFF)
        yield draw


SPEC = {
    "ants": dict(fn=ants, sid="S4", name="Ant-colony stigmergy", sprite="ant", title="Ants: trails on a shared board", seed=3),
    "bees": dict(fn=bees, sid="S9", name="Honeybee nest-site choice", sprite="bee",
                 title="Honeybees: dances, stop signals, quorum", seed=5),
    "wolves": dict(fn=wolves, sid="S7", name="Grey-wolf hierarchy", sprite="wolf", title="Wolves: follow the leaders", seed=2),
    "birds": dict(fn=birds, sid="S8", name="Boids", sprite="bird", title="Birds: align with your neighbours", seed=4),
    "fireflies": dict(fn=fireflies, sid="S6", name="Firefly attraction", sprite="firefly",
                      title="Fireflies: drift toward the brightest", seed=6),
    "debate": dict(fn=debate, sid="S2", name="Neighbour debate", sprite="agent", title="Debate: average your neighbours", seed=1),
    "pso": dict(fn=pso, sid="S3", name="Particle swarm", sprite="particle", title="Particle swarm: own best vs group best",
                seed=8),
    "bats": dict(fn=bats, sid="S11", name="Vampire-bat reciprocity · exploratory", sprite="bat",
                 title="Vampire bats: trust the ones who check out", seed=9),
}


def render(name: str, frames_dir: Path | None = None, seconds: float = STEPS / STEP_FPS) -> Path:
    spec = SPEC[name]
    rng = random.Random(spec["seed"])
    noise = Image.effect_noise((W, H), 48).convert("L")
    grain = Image.merge("RGB", (noise, noise, noise))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{name}.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-framerate", f"{STEPS}/{seconds:g}", "-i", "-", "-vf", f"fps={FPS}", "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for s, draw in enumerate(spec["fn"](rng)):
        F = Frame(grain)
        draw(F)
        img = F.done()
        proc.stdin.write(img.tobytes())
        if frames_dir is not None:
            frames_dir.mkdir(parents=True, exist_ok=True)
            img.save(frames_dir / f"{name}_{s:02d}.png")
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"ffmpeg failed for {name}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("families", nargs="*", default=list(SPEC), help=f"subset of: {' '.join(SPEC)}")
    ap.add_argument("--frames", default=None, help="also write one PNG per step into this folder")
    ap.add_argument("--seconds", type=float, default=STEPS / STEP_FPS,
                    help="clip length (default 8; the same 40 steps play faster when shorter)")
    a = ap.parse_args()
    for f in a.families:
        p = render(f, Path(a.frames) if a.frames else None, a.seconds)
        print(f"wrote {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
