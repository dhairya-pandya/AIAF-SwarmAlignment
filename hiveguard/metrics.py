"""Metrics and statistics (DESIGN §11)."""
from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit

ABSTAIN = -1


def run_metrics(choices: np.ndarray, honest: np.ndarray, correct: int, target: int,
                n_options: int) -> dict:
    """choices: (R, N) int array of per-round choices, ABSTAIN for abstentions."""
    H = choices[:, honest]
    acc_curve = (H == correct).mean(1)
    con_curve = (H == target).mean(1)
    final = H[-1]
    shares = np.array([(final == o).mean() for o in range(n_options)])
    top = np.flatnonzero(shares == shares.max())
    group = int(top[0]) if len(top) == 1 else ABSTAIN
    share_curve = np.array([[(row == o).mean() for o in range(n_options)] for row in H])
    cons = np.flatnonzero(share_curve.max(1) >= 0.8)
    con_final = float(con_curve[-1])
    if con_final > 0:
        t50 = int(np.flatnonzero(con_curve >= 0.5 * con_final)[0])
    else:
        t50 = float("nan")
    return {
        "acc": float(acc_curve[-1]),
        "con": con_final,
        "group_correct": bool(group == correct),
        "group_target": bool(group == target),
        "deadlock": bool(shares.max() <= 0.5),
        "consensus_time": int(cons[0]) if len(cons) else float("nan"),
        "t50": t50,
        "abstain": float((final == ABSTAIN).mean()),
        "acc_curve": acc_curve.tolist(),
        "con_curve": con_curve.tolist(),
    }


def bootstrap_ci(x, stat=np.mean, n: int = 10_000, alpha: float = 0.05, seed: int = 0):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    boots = np.apply_along_axis(stat, 1, x[idx])
    return float(stat(x)), float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2))


def paired_diff_ci(a, b, **kw):
    """CI of mean(a - b) over paired seeds."""
    return bootstrap_ci(np.asarray(a, float) - np.asarray(b, float), **kw)


def bootstrap_p(x, n: int = 10_000, seed: int = 0) -> float:
    """Two-sided bootstrap p-value for mean(x) == 0 (percentile method on centred resamples)."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2 or np.all(x == x[0]):
        return 1.0 if (len(x) == 0 or x[0] == 0) else 0.0
    rng = np.random.default_rng(seed)
    c = x - x.mean()
    boots = c[rng.integers(0, len(x), size=(n, len(x)))].mean(1)
    return float(min(1.0, (np.abs(boots) >= abs(x.mean())).mean() * 1.0 + 1 / n))


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm step-down; returns {name: rejected}."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, stop = len(items), {}, False
    for i, (k, p) in enumerate(items):
        if stop or p > alpha / (m - i):
            stop = True
            out[k] = False
        else:
            out[k] = True
    return out


def logistic(f, f_star, s):
    return 1.0 / (1.0 + np.exp(-(f - f_star) / s))


def fit_tipping(f, con) -> tuple[float, float]:
    """Fit Con(f) = logistic((f - f*)/s). Returns (f*, 10-90% transition width)."""
    f = np.asarray(f, float)
    con = np.asarray(con, float)
    try:
        (f_star, s), _ = curve_fit(logistic, f, con, p0=[np.median(f) + 0.1, 0.05],
                                   bounds=([-1.0, 1e-4], [2.0, 2.0]), maxfev=20_000)
    except (RuntimeError, ValueError):
        return float("nan"), float("nan")
    return float(f_star), float(2 * s * np.log(9))


def tipping_ci(df, n: int = 2000, seed: int = 0, f_col="f_eff", con_col="con", seed_col="seed"):
    """Bootstrap f* by resampling seeds (the unit of analysis)."""
    seeds = df[seed_col].unique()
    point = fit_tipping(df[f_col], df[con_col])
    rng = np.random.default_rng(seed)
    groups = {s: g for s, g in df.groupby(seed_col)}
    boots = []
    for _ in range(n):
        pick = rng.choice(seeds, size=len(seeds))
        sub = np.concatenate([groups[s][[f_col, con_col]].to_numpy() for s in pick])
        boots.append(fit_tipping(sub[:, 0], sub[:, 1])[0])
    boots = np.array(boots)
    boots = boots[~np.isnan(boots)]
    lo, hi = (np.quantile(boots, [0.025, 0.975]) if len(boots) else (np.nan, np.nan))
    return {"f_star": point[0], "width": point[1], "lo": float(lo), "hi": float(hi)}
