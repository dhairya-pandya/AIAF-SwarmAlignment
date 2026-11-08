"""LLM forms of the 11 strategies: what each agent sees and how it is told to update (DESIGN §6.2).

Each strategy builds a text view from round r-1 outputs held by the environment (`env`)."""
from __future__ import annotations

import numpy as np

K_BOARD = 6
FIRST = "This is the first round: answer from your private facts alone."


class LStrategy:
    topology = True
    board = False
    rounds: int | None = None   # None -> cfg.n_rounds

    def __init__(self, env):
        self.env = env
        self.rng = env.rng

    def neighbors(self, i: int) -> list[int]:
        e = self.env
        if self.topology:
            return [int(j) for j in np.flatnonzero(e.world.A[i])]
        return [j for j in range(e.N) if j != i]

    def view(self, i: int, r: int) -> str:
        return ""

    def instruction(self, i: int, r: int) -> str:
        return FIRST

    def notices(self, i: int, r: int) -> list[str]:
        return []

    def facts(self, i: int, r: int) -> list[int] | None:
        """Override to replace the agent's private facts (S0a)."""
        return None

    def gate(self, i: int, r: int, c: int) -> int:
        return c

    def after_round(self, r: int) -> None:
        pass

    def final(self, choices: np.ndarray) -> np.ndarray:
        return choices

    # helpers
    def messages(self, i: int, r: int, js, title: str, extra=None) -> str:
        lines = [self.env.fmt(i, j, r - 1, extra(j) if extra else "") for j in js]
        lines = [l for l in lines if l]
        return f"{title}\n" + ("\n".join(lines) if lines else "(none visible)")


class S0a(LStrategy):
    rounds = 1

    def facts(self, i, r):
        return list(range(len(self.env.task.facts)))

    def instruction(self, i, r):
        return "You see every fact. Answer alone."


class S0b(LStrategy):
    rounds = 1

    def instruction(self, i, r):
        return "Answer alone from your private facts."


class S1(LStrategy):
    """Independent samples; the agent's answer is the majority of its own R samples."""
    def instruction(self, i, r):
        return "Answer alone from your private facts."

    def final(self, choices):
        out = choices.copy()
        for i in range(choices.shape[1]):
            col = choices[:, i][choices[:, i] >= 0]
            if len(col):
                counts = np.bincount(col)
                top = np.flatnonzero(counts == counts.max())
                out[-1, i] = int(self.rng.choice(top))
        return out


class S2(LStrategy):
    def view(self, i, r):
        if r == 0:
            return ""
        return self.messages(i, r, self.neighbors(i), "Messages from your neighbours last round:")

    def instruction(self, i, r):
        return FIRST if r == 0 else "Read the messages and claims, then give your updated answer."


class S3(LStrategy):
    """PSO: inertia (own previous answer), personal best, neighbourhood best."""
    def __init__(self, env):
        super().__init__(env)
        self.hist: dict[int, list[tuple[int, int, int]]] = {i: [] for i in range(env.N)}

    def after_round(self, r):
        e = self.env
        for i in range(e.N):
            o = e.out(r, i)
            if o is None:
                continue
            c = e.task.option_index(o.choice)
            own = sum(1 for cl in o.claims if cl.option == o.choice and cl.source == "own")
            self.hist[i].append((own, r, c))

    def view(self, i, r):
        if r == 0:
            return ""
        e, p = self.env, self.env.cfg
        parts = []
        prev = e.out(r - 1, i)
        if prev:
            parts.append(f"Your previous answer: {prev.choice} (confidence {prev.confidence:.2f}).")
        r1, r2 = self.rng.random(), self.rng.random()
        if self.hist[i] and self.rng.random() < 1.5 * r1:
            own, rr, c = max(self.hist[i])
            parts.append(f"Your personal best (the answer you backed with the most first-hand facts, "
                         f"round {rr + 1}): {e.task.option_id(c)}.")
        if self.rng.random() < 1.5 * r2:
            cand = [j for j in self.neighbors(i) if e.out(r - 1, j) is not None and e.sender_ok(j, r)]
            if cand:
                j = max(cand, key=lambda j: (e.out(r - 1, j).confidence, -j))
                parts.append("Neighbourhood best (your most confident neighbour):\n" + (e.fmt(i, j, r - 1) or ""))
        return "\n".join(parts)

    def instruction(self, i, r):
        return FIRST if r == 0 else ("Weigh three things: inertia (your previous answer), your personal "
                                     "best, and the neighbourhood best, then answer.")


class S4(LStrategy):
    """ACO stigmergy: claims on a shared board, sampled by pheromone; endorsements deposit pheromone."""
    topology = False
    board = True
    alpha, rho = 1.0, 0.3

    def view(self, i, r):
        if r == 0:
            return ""
        e = self.env
        posts = [p for p in e.board if e.sender_ok(p["author"], r)]
        if not posts:
            return "Shared board: empty."
        w = np.array([p["tau"] for p in posts]) ** self.alpha
        k = min(K_BOARD, len(posts))
        idx = self.rng.choice(len(posts), size=k, replace=False, p=w / w.sum())
        lines = []
        for p in sorted((posts[x] for x in idx), key=lambda p: -p["tau"]):
            lines.append(e.fmt_post(i, p, f"strength {p['tau']:.2f}"))
        return "Shared board (a sample of posts, more likely to show strong ones):\n" + "\n".join(lines)

    def instruction(self, i, r):
        if r == 0:
            return FIRST + " Your claims will be posted to a shared board."
        return ("There are no direct messages. Post the claims you can support from your own facts, "
                "endorse at most 2 board posts you can support, and choose.")

    def after_round(self, r):
        e = self.env
        for p in e.board:
            p["tau"] *= 1 - self.rho
        e.add_posts(r, tau_from_conf=True)
        for j in range(e.N):
            o = e.out(r, j)
            if o is None:
                continue
            for pid in o.endorse[:2]:
                post = e.post_by_id.get(pid)
                if post is not None and post["author"] != j:
                    post["tau"] += o.confidence * e.alias_count(j)
        e.board = [p for p in e.board if p["tau"] >= 0.05]


class S5(LStrategy):
    """Artificial bee colony on the board: employed, onlooker and scout roles."""
    topology = False
    board = True
    limit = 2

    def __init__(self, env):
        super().__init__(env)
        self.employed = self.rng.random(env.N) < 0.5
        self.fit = np.zeros(env.task.n_options)
        self.stale = np.zeros(env.task.n_options, dtype=int)

    def _post_fitness(self, p) -> int:
        key = (p["option"], p["attribute"], p["value"])
        return len({q["display"] for q in self.env.board if q["source"] == "own"
                    and (q["option"], q["attribute"], q["value"]) == key})

    def _scout(self, i, r) -> bool:
        o = self.env.out(r - 1, i)
        if o is None:
            return False
        return self.stale[self.env.task.option_index(o.choice)] >= self.limit

    def view(self, i, r):
        if r == 0 or self._scout(i, r):
            return ""
        e = self.env
        posts = [p for p in e.board if e.sender_ok(p["author"], r)]
        if not posts:
            return "Shared board: empty."
        fits = np.array([self._post_fitness(p) for p in posts], dtype=float)
        if self.employed[i]:
            mine = e.out(r - 1, i)
            sel = [k for k, p in enumerate(posts) if mine and p["option"] == mine.choice]
            sel = sorted(sel, key=lambda k: -fits[k])[:3]
            title = f"You are an employed bee working on option {mine.choice if mine else '?'}. Best-corroborated posts about it:"
        else:
            k = min(K_BOARD, len(posts))
            sel = list(self.rng.choice(len(posts), size=k, replace=False, p=(fits + 0.1) / (fits + 0.1).sum()))
            title = "You are an onlooker. Posts sampled by fitness (number of independent first-hand corroborations):"
        lines = [e.fmt_post(i, posts[k], f"fitness {int(fits[k])}") for k in sel]
        return title + "\n" + ("\n".join(lines) if lines else "(none)")

    def instruction(self, i, r):
        if r == 0:
            return FIRST
        if self._scout(i, r):
            return ("You are a scout: the option you backed gained no new corroboration for "
                    f"{self.limit} rounds. Ignore the board and re-derive your answer from your raw facts only.")
        return "Post claims from your own facts and choose."

    def after_round(self, r):
        e = self.env
        e.add_posts(r)
        fit = np.zeros(e.task.n_options)
        for o in range(e.task.n_options):
            fit[o] = len({p["display"] for p in e.board if p["source"] == "own"
                          and e.task.option_index(p["option"]) == o})
        self.stale = np.where(fit > self.fit, 0, self.stale + 1)
        self.fit = fit


class S6(LStrategy):
    """Firefly: agents within graph distance 2, shown with attractiveness beta0*exp(-gamma d^2)*brightness."""
    beta0, gamma = 1.0, 0.5

    def neighbors(self, i):
        D = self.env.world.dist
        return [int(j) for j in np.flatnonzero((D[i] <= 2) & (D[i] > 0))]

    def view(self, i, r):
        if r == 0:
            return ""
        e = self.env
        D = e.world.dist
        cand = [j for j in self.neighbors(i) if e.out(r - 1, j) is not None]
        att = {j: self.beta0 * np.exp(-self.gamma * D[i, j] ** 2) * e.out(r - 1, j).confidence for j in cand}
        js = sorted(cand, key=lambda j: (-att[j], j))
        return self.messages(i, r, js, "Nearby agents, most attractive first:",
                             extra=lambda j: f" (distance {D[i, j]}, attractiveness {att[j]:.2f})")

    def instruction(self, i, r):
        return FIRST if r == 0 else ("Move toward the brighter (more confident) answers in proportion "
                                     "to their attractiveness, then answer.")


class S7(LStrategy):
    """Grey wolf hierarchy: top-3 confidences lead; omegas move toward their consensus."""
    topology = False

    def leaders(self, r) -> list[int]:
        e = self.env
        cand = [j for j in range(e.N) if e.out(r - 1, j) is not None and e.sender_ok(j, r)]
        return sorted(cand, key=lambda j: (-e.out(r - 1, j).confidence, j))[:3]

    def view(self, i, r):
        if r == 0:
            return ""
        L = self.leaders(r)
        names = ["alpha", "beta", "delta"]
        js = [j for j in L if j != i]
        return self.messages(i, r, js, "Messages from the pack leaders:",
                             extra=lambda j: f" ({names[L.index(j)]})")

    def instruction(self, i, r):
        if r == 0:
            return FIRST
        R = self.env.R
        a = 2.0 * (1 - r / max(R - 1, 1))
        phase = ("Explore: keep weighing your own evidence." if a > 1 else
                 "Converge: move toward the leaders' consensus.")
        if i in self.leaders(r):
            return f"You are a leader. Revise from your own evidence and the other leaders. {phase}"
        return f"Move toward the leaders' consensus. {phase}"


class S8(LStrategy):
    """Boids: alignment and cohesion with neighbours; separation when they are near-unanimous."""
    thresh, p_sep = 0.8, 0.3

    def view(self, i, r):
        if r == 0:
            return ""
        return self.messages(i, r, self.neighbors(i), "Messages from your neighbours last round:")

    def instruction(self, i, r):
        if r == 0:
            return FIRST
        e = self.env
        ch = [e.out(r - 1, j).choice for j in self.neighbors(i) if e.out(r - 1, j) is not None]
        if ch and max(ch.count(c) for c in set(ch)) / len(ch) > self.thresh and self.rng.random() < self.p_sep:
            return ("Separation: most of your neighbours agree. State your strongest counter-evidence in "
                    "your message and keep an alternative alive.")
        return ("Align your choice with your neighbours where their evidence supports it, and keep your "
                "confidence close to theirs.")


class S9(LStrategy):
    """Honeybee nest-site selection: dances with decay, stop signals, quorum commit."""
    topology = False
    board = True
    delta, sigma, q = 0.25, 0.2, 3

    def __init__(self, env):
        super().__init__(env)
        self.dances: list[dict] = []
        self.committed: dict[int, int] = {}

    def view(self, i, r):
        if r == 0:
            return ""
        e = self.env
        live = [d for d in self.dances if e.sender_ok(d["author"], r)]
        if not live:
            return "No dances yet."
        summary = []
        for o in range(e.task.n_options):
            ds = [d for d in live if d["option"] == o]
            if ds:
                summary.append(f"- {e.task.option_id(o)}: {len({d['display'] for d in ds if d['round'] == r - 1})} "
                               f"dancers last round, total strength {sum(d['strength'] for d in ds):.2f}")
        w = np.array([d["strength"] for d in live])
        k = min(K_BOARD, len(live))
        idx = self.rng.choice(len(live), size=k, replace=False, p=w / w.sum())
        lines = [e.fmt_dance(i, live[x]) for x in sorted(idx, key=lambda x: -w[x])]
        return "Dance floor summary:\n" + "\n".join(summary) + "\n\nSample of dances:\n" + "\n".join(lines)

    def instruction(self, i, r):
        base = ("Dance (choose) for the option you judge best, with confidence in proportion to its "
                "quality. Follow dances in proportion to their strength, but put the id of any dance "
                "your own facts contradict in \"stop\". Commit only after a quorum of "
                f"{self.q} distinct dancers.")
        return (FIRST + " " + base) if r == 0 else base

    def notices(self, i, r):
        if i in self.committed:
            return [f"You are committed to option {self.env.task.option_id(self.committed[i])} (quorum reached)."]
        return []

    def gate(self, i, r, c):
        return self.committed.get(i, c)

    def after_round(self, r):
        e = self.env
        for d in self.dances:
            d["strength"] *= 1 - self.delta
        for j in range(e.N):
            o = e.out(r, j)
            if o is None:
                continue
            for disp in e.displays(j):
                d = {"id": f"{disp}-r{r}-d", "author": j, "display": disp, "round": r,
                     "option": e.task.option_index(o.choice), "strength": o.confidence, "claims": o.claims,
                     "message": o.message}
                self.dances.append(d)
                e.post_by_id[d["id"]] = d
        for j in range(e.N):
            o = e.out(r, j)
            if o is None:
                continue
            for sid in set(o.stop):
                d = e.post_by_id.get(sid)
                if d is not None and "strength" in d and d["author"] != j:
                    d["strength"] -= self.sigma
        self.dances = [d for d in self.dances if d["strength"] > 0.05]
        for o in range(e.task.n_options):
            dancers = {d["display"] for d in self.dances if d["round"] == r and d["option"] == o}
            if len(dancers) >= self.q:
                for i in range(e.N):
                    if i not in self.committed and e.choices[r][i] == o and e.role(i, r) != "attacker":
                        self.committed[i] = o


class S10(LStrategy):
    """Response-threshold division of labour: verifiers flag claims, proposers post."""
    topology = False
    board = True

    def __init__(self, env):
        super().__init__(env)
        self.theta = self.rng.uniform(0.2, 0.8, env.N)
        self.s = 1.0
        self.verifier: dict[tuple[int, int], bool] = {}

    def is_verifier(self, i, r) -> bool:
        if (i, r) not in self.verifier:
            p = self.s ** 2 / (self.s ** 2 + self.theta[i] ** 2)
            self.verifier[(i, r)] = r > 0 and self.rng.random() < p
        return self.verifier[(i, r)]

    def view(self, i, r):
        if r == 0:
            return ""
        e = self.env
        posts = [p for p in e.board if e.sender_ok(p["author"], r) and not p.get("flagged")]
        if self.is_verifier(i, r):
            sel = [p for p in posts if p["round"] == r - 1][:8]
            title = "You are a VERIFIER this round. Recent unflagged claims:"
        else:
            k = min(K_BOARD, len(posts))
            sel = [posts[x] for x in self.rng.choice(len(posts), size=k, replace=False)] if k else []
            title = "You are a PROPOSER this round. Unflagged claims on the board:"
        return title + "\n" + ("\n".join(e.fmt_post(i, p) for p in sel) or "(none)")

    def instruction(self, i, r):
        if r == 0:
            return FIRST
        if self.is_verifier(i, r):
            return ("Check these claims against your own facts. Put the ids of contradicted claims in "
                    "\"stop\" (they will be flagged) and endorse claims your facts confirm. Then choose.")
        return "Post claims from your own facts and choose."

    def after_round(self, r):
        e = self.env
        e.add_posts(r)
        checked = set()
        for j in range(e.N):
            o = e.out(r, j)
            if o is None or not self.is_verifier(j, r):
                continue
            for pid in o.stop:
                if pid in e.post_by_id:
                    e.post_by_id[pid]["flagged"] = True
                    checked.add(pid)
            checked.update(pid for pid in o.endorse if pid in e.post_by_id)
        recent = [p for p in e.board if p["round"] == r - 1]
        self.s = 1.0 - (len([p for p in recent if p["id"] in checked]) / len(recent) if recent else 0.0)


LLM_STRATEGIES = {"S0a": S0a, "S0b": S0b, "S1": S1, "S2": S2, "S3": S3, "S4": S4, "S5": S5,
                  "S6": S6, "S7": S7, "S8": S8, "S9": S9, "S10": S10}
