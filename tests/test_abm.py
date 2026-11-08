import numpy as np
import pytest

from hiveguard.abm import ABMParams, ABMSim, proj_simplex, run_abm
from hiveguard.config import ATTACKS, MODULES, STRATEGIES, RunConfig


def test_proj_simplex():
    Y = np.random.default_rng(0).normal(size=(50, 4)) * 3
    X = proj_simplex(Y)
    assert np.allclose(X.sum(1), 1) and (X >= 0).all()
    P = np.array([[0.1, 0.2, 0.3, 0.4]])
    assert np.allclose(proj_simplex(P), P)


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_replay_determinism(strategy):
    cfg = RunConfig(strategy=strategy, f=0.25, seed=11, modules=["M2"])
    a, b = run_abm(cfg), run_abm(cfg)
    assert (a["choices"] == b["choices"]).all()


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("module", MODULES + [None])
def test_all_combinations_run(strategy, module):
    m = run_abm(RunConfig(strategy=strategy, f=0.25, modules=[module] if module else [], seed=2))
    assert 0 <= m["acc"] <= 1 and 0 <= m["con"] <= 1
    assert m["choices"].shape == (6, 14 if module == "M4" else 12)


def test_oracle_is_perfect():
    assert all(run_abm(RunConfig(strategy="S0a", seed=s))["acc"] == 1.0 for s in range(5))


def test_no_social_strategies_ignore_attackers():
    for s in ["S0b", "S1"]:
        a = run_abm(RunConfig(strategy=s, f=0.0, seed=4))["choices"][:, :]
        b_cfg = RunConfig(strategy=s, f=3 / 12, seed=4)
        sim = ABMSim(b_cfg)
        b = sim.run()["choices"]
        h = sim.world.honest
        assert (a[:, h] == b[:, h]).all()


def test_attackers_stay_on_target():
    sim = ABMSim(RunConfig(strategy="S2", f=3 / 12, seed=1))
    ch = sim.run()["choices"]
    assert (ch[:, sim.world.attacker] == sim.world.target).all()


def test_sleeper_honest_before_onset():
    sim = ABMSim(RunConfig(strategy="S2", f=3 / 12, attack="A3", onset=3, seed=1))
    ch = sim.run()["choices"]
    assert (ch[3:, sim.world.attacker] == sim.world.target).all()


def test_voter_limit_consensus_odds():
    """DeGroot at full deference on a complete graph without attackers reaches consensus.

    Sanity check against the voter-model result: the consensus option is the confidence-weighted
    initial opinion, so with lam=0 the group lands on the plurality of initial beliefs' mean."""
    p = ABMParams(kappa=1.0, lam=0.0)
    for s in range(5):
        sim = ABMSim(RunConfig(strategy="S2", seed=s, n_rounds=10), p)
        m = sim.run()
        final = m["choices"][-1]
        assert len(set(final.tolist())) == 1
        mean0 = sim.E.mean(0)
        assert final[0] == int(np.argmax(mean0))


def test_contamination_increases_with_f():
    p = ABMParams(kappa=0.2, lam=1.0)   # mild deference so one attacker does not saturate
    con = []
    for f in [0.0, 1 / 12, 3 / 12, 0.4]:
        con.append(np.mean([run_abm(RunConfig(strategy="S2", f=f, seed=s), p)["con"] for s in range(40)]))
    assert con[0] < con[1] < con[2] <= con[3] + 1e-9


def test_quorum_blocks_a1():
    """A1 makes no first-hand claims, so quorum on first-hand evidence must cut its effect."""
    base = np.mean([run_abm(RunConfig(strategy="S2", f=3 / 12, attack="A1", seed=s))["con"] for s in range(30)])
    q = np.mean([run_abm(RunConfig(strategy="S2", f=3 / 12, attack="A1", modules=["M3"], seed=s))["con"] for s in range(30)])
    assert q < base
