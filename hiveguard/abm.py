"""Agent-based-model twins of the 11 pre-registered strategies (plus exploratory S11 and S12), plus attacks and defence modules (DESIGN §6–8).

Conventions
- Rounds r = 0..R-1. Round 0 is an independent answer from private evidence. In round r >= 1
  every agent sees the reports of round r-1 (synchronous update).
- B: (N, n) beliefs on the simplex. choice: (N,) ints.
- Honest informed agents have evidence E_i = softmax(partial_score_i / temp). Attackers (before
  onset) and uninformed agents have uniform E.
- Modules act through per-sender weights (M1, M2), per-receiver gates (M3), extra agents (M4),
  heterogeneous deference (M5) and topology rewiring (M6, handled in world.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .config import RunConfig, seed_int
from .metrics import run_metrics
from .world import World, build_world


@dataclass
class ABMParams:
    kappa: float = 0.5           # deference: weight on social information (calibrated)
    lam: float = 2.0             # confidence sensitivity (calibrated)
    temp: float = 10.0           # evidence softmax temperature (score units)
    c_att: dict = field(default_factory=lambda: {"A1": 0.95, "A2": 0.9, "A3": 0.9, "A4": 0.9, "A5": 1.0})
    # S3 PSO
    omega: float = 0.6
    c1: float = 1.5
    c2: float = 1.5
    # S4 ACO
    aco_alpha: float = 1.0
    aco_beta: float = 2.0
    aco_rho: float = 0.3
    tau0: float = 1.0
    # S7 GWO
    gwo_noise: float = 0.05
    # S9 honeybee
    bee_delta: float = 0.25
    bee_sigma: float = 0.2
    bee_q: int = 3
    # S5 ABC
    abc_limit: int = 2
    # S6 firefly
    ff_beta0: float = 1.0
    ff_gamma: float = 0.5
    ff_alpha: float = 0.05
    # S8 boids
    boids_psep: float = 0.3
    boids_thresh: float = 0.8
    # S10 response threshold
    s10_theta: tuple = (0.2, 0.8)
    # S11 reciprocity / reputation (exploratory, DEVIATIONS D22)
    s11_eta: float = 0.5
    s11_floor: float = 0.05
    # modules
    m1_rho: float = 0.3
    m1_hide: float = 0.1
    m2_stops: int = 2
    m2_rounds: int = 2
    m3_q: int = 2
    m4_conf: float = 0.4
    m5_spread: tuple = (0.5, 1.0, 1.5)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- helpers

def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    z = x - x.max(axis=axis, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=axis, keepdims=True)


def proj_simplex(Y: np.ndarray) -> np.ndarray:
    """Euclidean projection of each row onto the probability simplex."""
    n = Y.shape[1]
    U = -np.sort(-Y, axis=1)
    css = np.cumsum(U, axis=1) - 1.0
    idx = np.arange(1, n + 1)
    cond = U - css / idx > 0
    rho = n - 1 - np.argmax(cond[:, ::-1], axis=1)
    theta = css[np.arange(len(Y)), rho] / (rho + 1)
    return np.maximum(Y - theta[:, None], 0.0)


def argmax_rand(B: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return np.argmax(B + rng.uniform(0, 1e-9, B.shape), axis=1)


def sample_rows(P: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    P = P / P.sum(1, keepdims=True)
    u = rng.random((len(P), 1))
    return np.minimum((np.cumsum(P, 1) < u).sum(1), P.shape[1] - 1)


def onehot(idx: np.ndarray, n: int) -> np.ndarray:
    out = np.zeros((len(idx), n))
    out[np.arange(len(idx)), idx] = 1.0
    return out


@dataclass
class Reports:
    """What each agent displays at the end of a round."""
    B: np.ndarray
    conf: np.ndarray
    choice: np.ndarray
    fh: np.ndarray      # carries a first-hand (source: own) claim for its choice
    mult: np.ndarray    # identities on the board (sybil aliases)


def social_mean(V: np.ndarray, rep: Reports, lam: float):
    """Confidence-weighted mean of visible reports. Returns (M, has_any)."""
    W = V * (rep.mult * np.maximum(rep.conf, 1e-6) ** lam)[None, :]
    s = W.sum(1, keepdims=True)
    M = (W @ rep.B) / np.where(s > 0, s, 1.0)
    return M, s[:, 0] > 0


# ---------------------------------------------------------------- strategies

class Strategy:
    topology = True     # visibility follows the graph; False = broadcast / shared board
    board = False       # stigmergic medium (enables sybil aliases)

    def base_visibility(self, sim: "ABMSim") -> np.ndarray:
        if self.topology:
            return sim.world.A.astype(float)
        return 1.0 - np.eye(sim.N)

    def init(self, sim: "ABMSim"):
        B = sim.E.copy()
        return B, argmax_rand(B, sim.rng)

    def step(self, sim: "ABMSim", r: int, rep: Reports, V: np.ndarray):
        raise NotImplementedError

    def post(self, sim: "ABMSim", r: int) -> None:
        pass


class S0a(Strategy):
    """Oracle: every honest agent sees all facts."""
    def init(self, sim):
        full = sim.world.task.partial_scores(range(len(sim.world.task.facts)))
        B = np.tile(softmax(full / sim.p.temp), (sim.N, 1))
        B[~sim.world.honest] = sim.E[~sim.world.honest]
        return B, argmax_rand(B, sim.rng)

    def step(self, sim, r, rep, V):
        return sim.B.copy(), sim.choice.copy()


class S0b(Strategy):
    """Solo: own facts only."""
    def step(self, sim, r, rep, V):
        return sim.B.copy(), sim.choice.copy()


class S1(Strategy):
    """Independent agents, R samples each (compute-matched), majority over own samples."""
    def init(self, sim):
        R = sim.R
        draws = np.stack([sample_rows(sim.E, sim.rng) for _ in range(R)], 1)
        counts = np.stack([(draws == o).sum(1) for o in range(sim.n)], 1).astype(float)
        B = counts / R
        return B, argmax_rand(B, sim.rng)

    def step(self, sim, r, rep, V):
        return sim.B.copy(), sim.choice.copy()


class S2(Strategy):
    """Free debate as DeGroot averaging with confidence^lambda weights."""
    def step(self, sim, r, rep, V):
        M, has = social_mean(V, rep, sim.p.lam)
        k = sim.kappa[:, None]
        B = np.where(has[:, None], (1 - k) * sim.B + k * M, sim.B)
        return B, argmax_rand(B, sim.rng)


class S3(Strategy):
    """PSO: inertia + personal best + neighbourhood best (lbest on sparse graphs, gbest on full)."""
    def init(self, sim):
        B, c = super().init(sim)
        self.hist = [B.copy()]
        return B, c

    def step(self, sim, r, rep, V):
        p, N = sim.p, sim.N
        H = np.stack(self.hist)                           # (T, N, n)
        fit = (H * sim.E[None]).sum(2)                    # first-hand support of each past belief
        t_best = H.shape[0] - 1 - np.argmax(fit[::-1], axis=0)   # latest among ties
        pbest = H[t_best, np.arange(N)]
        cand = (V > 0) | np.eye(N, dtype=bool)
        score = np.where(cand, rep.conf[None, :], -1.0) + sim.rng.uniform(0, 1e-9, (N, N))
        nbest = rep.B[np.argmax(score, axis=1)]
        r1, r2 = sim.rng.random((N, 1)), sim.rng.random((N, 1))
        B = proj_simplex(p.omega * sim.B + p.c1 * r1 * (pbest - sim.B) + p.c2 * r2 * (nbest - sim.B))
        return B, argmax_rand(B, sim.rng)

    def post(self, sim, r):
        self.hist.append(sim.B.copy())


class S4(Strategy):
    """ACO stigmergy: option pheromone, choice ~ tau^alpha * e^beta, evaporation rho."""
    topology = False
    board = True

    def init(self, sim):
        self.tau = np.full(sim.n, sim.p.tau0)
        P = self._probs(sim)
        return P, sample_rows(P, sim.rng)

    def _probs(self, sim):
        P = self.tau[None, :] ** sim.p.aco_alpha * np.maximum(sim.E, 1e-12) ** sim.p.aco_beta
        return P / P.sum(1, keepdims=True)

    def step(self, sim, r, rep, V):
        dep = np.bincount(rep.choice, weights=sim.w_send * rep.mult * rep.conf, minlength=sim.n)
        self.tau = (1 - sim.p.aco_rho) * self.tau + dep
        P = self._probs(sim)
        return P, sample_rows(P, sim.rng)


class S7(Strategy):
    """Grey wolf hierarchy: alpha/beta/delta = top-3 reported confidence, broadcast to all."""
    topology = False

    def select_leaders(self, sim: "ABMSim", rep: Reports) -> np.ndarray:
        conf = np.where(sim.w_send > 0, rep.conf, -1.0) + sim.rng.uniform(0, 1e-9, sim.N)
        return np.argsort(-conf)[:3]

    def step(self, sim, r, rep, V):
        p, N = sim.p, sim.N
        a = 2.0 * (1 - r / max(sim.R - 1, 1))
        leaders = self.select_leaders(sim, rep)
        L = rep.B[leaders].mean(0)
        noise = sim.rng.normal(0, p.gwo_noise, sim.B.shape)
        B = proj_simplex((1 - a / 2) * L[None, :] + (a / 2) * (sim.B + noise))
        for l in leaders:
            others = [j for j in leaders if j != l]
            k = sim.kappa[l]
            B[l] = (1 - k) * sim.E[l] + k * rep.B[others].mean(0)
        self.leaders = leaders
        self.leader_hist = getattr(self, "leader_hist", []) + [leaders.copy()]
        return B, argmax_rand(B, sim.rng)


class S12(S7):
    """Elephant matriarch: leadership by corroborated knowledge (exploratory; McComb et al. 2001, DEVIATIONS D24).

    Same leader-follower update as S7 (3 leaders broadcast to all, followers move toward the leaders' consensus,
    leaders revise from their own evidence and each other), but the 3 leaders are the agents with the highest
    corroboration score instead of the highest reported confidence.
    ABM proxy for the LLM score (own claims confirmed by another agent's own claim): agent j's score is the
    number of facts j holds that at least one other agent also holds. Honest agents report their own facts
    truthfully, so in the ABM a held fact is never contradicted and the "fewer contradicted claims" tie-break
    is constant; ties are broken by seeded noise. Attackers and uninformed agents hold no facts, so they score 0
    and are elected only when fewer than 3 visible agents have a positive score. Senders hidden by a module
    (w_send = 0) cannot lead, as in S7. The score is static because ABM reports always restate the same facts."""

    def init(self, sim):
        n_f = len(sim.world.task.facts)
        H = np.zeros((sim.N, n_f))
        for i, h in enumerate(sim.world.holdings):
            H[i, h] = 1.0
        holders = H.sum(0)
        self.score = (H * (holders[None, :] >= 2)).sum(1)       # facts j shares with at least one other agent
        return super().init(sim)

    def select_leaders(self, sim, rep):
        sc = np.where(sim.w_send > 0, self.score, -1.0) + sim.rng.uniform(0, 1e-3, sim.N)
        return np.argsort(-sc)[:3]


class S9(Strategy):
    """Honeybee nest-site selection: dances with decay, cross-inhibiting stop signals, quorum commit."""
    topology = False
    board = True

    def init(self, sim):
        self.D = np.zeros(sim.n)
        self.committed = np.zeros(sim.N, dtype=bool)
        self.quorum = np.zeros(sim.n)
        return super().init(sim)

    def step(self, sim, r, rep, V):
        p = sim.p
        dance = sim.w_send * rep.mult * rep.conf
        self.D = (1 - p.bee_delta) * self.D + np.bincount(rep.choice, weights=dance, minlength=sim.n)
        # cross-inhibition: honest agents stop rival options they hold contradicting facts about
        ch = rep.choice
        e_ch = sim.E[np.arange(sim.N), ch]
        rival = sim.F & (sim.E < e_ch[:, None])
        rival[np.arange(sim.N), ch] = False
        stops = (rival & sim.world.honest[:, None]).sum(0)
        self.D = np.maximum(self.D - p.bee_sigma * stops, 0.0)
        self.quorum = np.bincount(ch, weights=(sim.w_send > 0) * rep.mult, minlength=sim.n)
        k = sim.kappa[:, None]
        Dn = self.D / self.D.sum() if self.D.sum() > 0 else np.full(sim.n, 1.0 / sim.n)
        P = k * Dn[None, :] + (1 - k) * sim.E
        choice = sample_rows(P, sim.rng)
        B = P
        B[self.committed] = sim.B[self.committed]
        choice[self.committed] = sim.choice[self.committed]
        return B, choice

    def post(self, sim, r):
        self.committed |= (self.quorum[sim.choice] >= sim.p.bee_q) & ~sim.world.attacker


class S5(Strategy):
    """Artificial bee colony: employed / onlooker roles, scouts abandon claims that stop gaining support."""
    topology = False
    board = True

    def init(self, sim):
        self.employed = sim.rng.random(sim.N) < 0.5
        self.last_fit = np.zeros(sim.n)
        self.stale = np.zeros(sim.n, dtype=int)
        return super().init(sim)

    def step(self, sim, r, rep, V):
        p, k = sim.p, sim.kappa[:, None]
        fit = np.bincount(rep.choice, weights=sim.w_send * rep.mult * rep.fh, minlength=sim.n)
        self.stale = np.where(fit > self.last_fit, 0, self.stale + 1)
        self.last_fit = fit
        B = sim.B.copy()
        onl = ~self.employed
        pick = sample_rows(np.tile(fit + 1e-3, (sim.N, 1)), sim.rng)
        B[onl] = (1 - k[onl]) * B[onl] + k[onl] * onehot(pick[onl], sim.n)
        scouts = self.stale[sim.choice] >= p.abc_limit
        B[scouts] = sim.E[scouts]
        self.stale[np.unique(sim.choice[scouts])] = 0
        return B, argmax_rand(B, sim.rng)


class S6(Strategy):
    """Firefly: move toward brighter agents within graph distance 2, attractiveness beta0*exp(-gamma d^2)."""
    def base_visibility(self, sim):
        D = sim.world.dist
        return ((D <= 2) & (D > 0)).astype(float)

    def step(self, sim, r, rep, V):
        p = sim.p
        D = sim.world.dist.astype(float)
        bright = rep.conf
        brighter = bright[None, :] > bright[:, None]
        beta = p.ff_beta0 * np.exp(-p.ff_gamma * D ** 2) * V * brighter * bright[None, :]
        B = (sim.B + beta @ rep.B) / (1 + beta.sum(1, keepdims=True))
        B = proj_simplex(B + p.ff_alpha * sim.rng.normal(size=B.shape))
        return B, argmax_rand(B, sim.rng)


class S8(Strategy):
    """Boids opinion dynamics: alignment toward neighbours plus a separation push against unanimity."""
    def step(self, sim, r, rep, V):
        p = sim.p
        M, has = social_mean(V, rep, p.lam)
        k = sim.kappa[:, None]
        B = np.where(has[:, None], (1 - k) * sim.B + k * M, sim.B)
        vis = V > 0
        counts = (vis[:, :, None] * onehot(rep.choice, sim.n)[None]).sum(1)
        share = counts.max(1) / np.maximum(vis.sum(1), 1)
        sep = (share > p.boids_thresh) & (sim.rng.random(sim.N) < p.boids_psep)
        B[sep] = 0.5 * B[sep] + 0.5 * sim.E[sep]
        return B, argmax_rand(B, sim.rng)


class S10(Strategy):
    """Response-threshold division of labour: verifiers flag claims contradicted by their facts."""
    topology = False
    board = True

    def init(self, sim):
        lo, hi = sim.p.s10_theta
        self.theta = sim.rng.uniform(lo, hi, sim.N)
        self.s = 1.0
        return super().init(sim)

    def step(self, sim, r, rep, V):
        p = sim.p
        can = sim.world.honest
        verify = can & (sim.rng.random(sim.N) < self.s ** 2 / (self.s ** 2 + self.theta ** 2))
        ch = rep.choice
        Fc = sim.F[:, ch]                                      # (verifier j, post k)
        contra = Fc & (sim.E[:, ch] < sim.E.max(1, keepdims=True))
        flagged = (contra & verify[:, None]).any(0)
        checked = (Fc & verify[:, None]).any(0)
        live = sim.w_send > 0
        self.s = 1.0 - float(checked[live].mean()) if live.any() else 1.0
        M, has = social_mean(V * ~flagged[None, :], rep, p.lam)
        k = sim.kappa[:, None]
        prop = (~verify & has)[:, None]
        B = np.where(prop, (1 - k) * sim.B + k * M, sim.B)
        return B, argmax_rand(B, sim.rng)


class S11(Strategy):
    """Reciprocity / reputation (exploratory; vampire-bat reciprocal food sharing, Wilkinson 1984).

    Each agent keeps a trust score per graph neighbour (start 1.0) and checks each visible neighbour's report
    against its own first-hand facts before the S2 DeGroot update:
    - match: the neighbour holds a fact about its chosen option that the receiver also holds (its first-hand
      claims about that option include one the receiver can confirm) -> trust x (1 + eta);
    - contradiction: otherwise, if the receiver holds facts about the neighbour's chosen option and its own
      evidence ranks that option below its evidence argmax -> trust x (1 - eta), floored at s11_floor;
    - neutral: the receiver holds no facts about that option.
    Attackers hold no facts, so they never match and are contradicted at a rate set by fact overlap.
    The S2 sender weight confidence^lambda is multiplied by trust, so eta = 0 reproduces S2."""

    def init(self, sim):
        self.T = np.ones((sim.N, sim.N))
        n_f = len(sim.world.task.facts)
        H = np.zeros((sim.N, n_f))
        for i, h in enumerate(sim.world.holdings):
            H[i, h] = 1.0
        opt = np.array([f.option for f in sim.world.task.facts])
        # shared[o, i, j]: i and j hold a common fact about option o
        self.shared = np.stack([(H[:, opt == o] @ H[:, opt == o].T) > 0 for o in range(sim.n)])
        return super().init(sim)

    def update_trust(self, sim, rep: Reports, V: np.ndarray) -> None:
        p, ch = sim.p, rep.choice
        vis = V > 0
        match = vis & self.shared[ch, :, np.arange(sim.N)].T          # (receiver i, sender j)
        contra = vis & ~match & sim.F[:, ch] & (sim.E[:, ch] < sim.E.max(1, keepdims=True))
        self.T = np.where(contra, np.maximum(self.T * (1 - p.s11_eta), p.s11_floor),
                          np.where(match, self.T * (1 + p.s11_eta), self.T))

    def step(self, sim, r, rep, V):
        self.update_trust(sim, rep, V)
        M, has = social_mean(V * self.T, rep, sim.p.lam)
        k = sim.kappa[:, None]
        B = np.where(has[:, None], (1 - k) * sim.B + k * M, sim.B)
        return B, argmax_rand(B, sim.rng)


STRATEGY_CLASSES = {"S0a": S0a, "S0b": S0b, "S1": S1, "S2": S2, "S3": S3, "S4": S4, "S5": S5,
                    "S6": S6, "S7": S7, "S8": S8, "S9": S9, "S10": S10, "S11": S11,
                    "S12": S12}
SOCIAL = {"S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12"}


# ---------------------------------------------------------------- simulation

class ABMSim:
    def __init__(self, cfg: RunConfig, params: ABMParams | None = None, world: World | None = None):
        self.cfg = cfg
        self.p = params or ABMParams()
        self.world = world or build_world(cfg)
        w = self.world
        self.N, self.n, self.R = w.N, cfg.n_options, cfg.n_rounds
        self.rng = np.random.default_rng(seed_int(cfg.seed, "abm", cfg.strategy))
        self.E = np.full((self.N, self.n), 1.0 / self.n)
        self.F = np.zeros((self.N, self.n), dtype=bool)
        for i in range(self.N):
            if w.holdings[i]:
                self.E[i] = softmax(w.task.partial_scores(w.holdings[i]) / self.p.temp)
                for fid in w.holdings[i]:
                    self.F[i, w.task.facts[fid].option] = True
        self.kappa = np.full(self.N, self.p.kappa)
        if "M5" in cfg.modules:
            groups = np.random.default_rng(seed_int(cfg.seed, "m5")).integers(0, len(self.p.m5_spread), self.N)
            self.kappa = np.clip(self.p.kappa * np.array(self.p.m5_spread)[groups], 0, 1)
        self.strategy = STRATEGY_CLASSES[cfg.strategy]()
        self.onset = cfg.effective_onset
        self.c_att = self.p.c_att[cfg.attack]
        self.w_send = np.ones(self.N)

    # -- attackers

    def active(self, r: int) -> np.ndarray:
        """Attackers that attack in round r."""
        return self.world.attacker & (r >= self.onset)

    def _force_attackers(self, r: int) -> None:
        act = self.active(r)
        self.B[act] = onehot(np.full(act.sum(), self.world.target), self.n)
        self.choice[act] = self.world.target

    def reports(self, r: int) -> Reports:
        w = self.world
        conf = self.B.max(1)
        fh = w.honest & self.F[np.arange(self.N), self.choice] & (np.argmax(self.E, 1) == self.choice)
        mult = np.ones(self.N)
        act = self.active(r)
        conf = np.where(act, self.c_att, conf)
        fh = np.where(act, self.cfg.attack != "A1", fh)
        if self.cfg.attack == "A4" and self.strategy.board:
            mult = np.where(act, 3.0, mult)
        return Reports(self.B.copy(), conf, self.choice.copy(), fh, mult)

    # -- modules

    def _sender_weights(self, r: int, rep: Reports, base: np.ndarray) -> np.ndarray:
        w = np.ones(self.N)
        mods = self.cfg.modules
        if "M1" in mods:
            self._streak = np.where(rep.choice == self._prev_choice, self._streak + 1, 0)
            self._prev_choice = rep.choice.copy()
            wt = (1 - self.p.m1_rho) ** self._streak
            w *= np.where(wt < self.p.m1_hide, 0.0, wt)
        if "M2" in mods:
            act = self.active(r - 1)
            stoppable = self.world.honest | (act & (self.cfg.attack != "A1"))
            Fc = self.F[:, rep.choice]
            Ec = self.E[:, rep.choice]
            stop = self.world.honest[:, None] & Fc & (Ec < self.E.max(1, keepdims=True))
            counts = (base * stop).sum(0)
            newly = stoppable & (counts >= self.p.m2_stops)
            self._hidden_until = np.where(newly, r + self.p.m2_rounds, self._hidden_until)
            w *= np.where(r < self._hidden_until, 0.0, 1.0)
        return w

    def _uninformed(self, rep: Reports, V: np.ndarray, B: np.ndarray, choice: np.ndarray) -> None:
        U = self.world.uninformed
        if not U.any():
            return
        counts = (V[U] * rep.mult[None, :]) @ onehot(rep.choice, self.n)
        o = argmax_rand(counts, self.rng)
        a = (self.p.m4_conf - 1 / self.n) / (1 - 1 / self.n)
        B[U] = a * onehot(o, self.n) + (1 - a) / self.n
        choice[U] = o

    def _quorum_gate(self, rep: Reports, V: np.ndarray, B: np.ndarray, choice: np.ndarray, acting) -> None:
        q = int(self.cfg.module_params.get("M3_q", self.p.m3_q))
        changed = acting & (choice != self.choice)
        if not changed.any():
            return
        mult_q = rep.mult if self.strategy.board else np.ones(self.N)
        support_w = (V > 0) * (rep.fh * mult_q)[None, :] * (rep.choice[None, :] == choice[:, None])
        blocked = changed & (support_w.sum(1) < q)
        B[blocked] = self.B[blocked]
        choice[blocked] = self.choice[blocked]

    # -- main loop

    def run(self) -> dict:
        self._streak = np.zeros(self.N, dtype=int)
        self._prev_choice = np.full(self.N, -1)
        self._hidden_until = np.zeros(self.N, dtype=int)
        self.B, self.choice = self.strategy.init(self)
        self.B = self.B.copy()
        self._force_attackers(0)
        if self.world.uninformed.any():
            U = self.world.uninformed
            self.choice[U] = self.rng.integers(0, self.n, U.sum())
        hist = [self.choice.copy()]
        base = self.strategy.base_visibility(self)
        np.fill_diagonal(base, 0.0)
        rep = self.reports(0)
        for r in range(1, self.R):
            self.w_send = self._sender_weights(r, rep, base)
            V = base * self.w_send[None, :]
            B, choice = self.strategy.step(self, r, rep, V)
            B, choice = B.copy(), choice.copy()
            acting = ~self.active(r)
            self._uninformed(rep, V, B, choice)
            if "M3" in self.cfg.modules:
                self._quorum_gate(rep, V, B, choice, acting & ~self.world.uninformed)
            self.B[acting] = B[acting]
            self.choice[acting] = choice[acting]
            self._force_attackers(r)
            self.strategy.post(self, r)
            hist.append(self.choice.copy())
            rep = self.reports(r)
        m = run_metrics(np.array(hist), self.world.honest, self.world.task.correct,
                        self.world.target, self.n)
        m["choices"] = np.array(hist)
        return m


def run_abm(cfg: RunConfig, params: ABMParams | None = None) -> dict:
    return ABMSim(cfg, params).run()
