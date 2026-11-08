import numpy as np
import pytest

from hiveguard.config import RunConfig
from hiveguard.task import generate_task
from hiveguard.world import build_world


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("n", [6, 12, 50])
def test_hidden_profile_invariants(seed, n):
    t = generate_task(seed, n)
    assert t.correct == int(np.argmax(t.scores()))
    assert t.local_correct_share < 0.4
    assert 4.0 <= t.margin <= 16.0
    # pooled deviation scores pick the same option as the true scores
    assert int(np.argmax(t.partial_scores(range(len(t.facts))))) == t.correct
    counts = np.bincount([f for h in t.holdings for f in h], minlength=len(t.facts))
    assert (counts == t.m).all()
    assert all(len(set(h)) == len(h) for h in t.holdings)


def test_task_deterministic():
    a, b = generate_task(7, 12), generate_task(7, 12)
    assert a.holdings == b.holdings and (a.values == b.values).all()


def test_attackers_have_no_facts_and_honest_facts_do_not_depend_on_f():
    w0 = build_world(RunConfig(f=0.0, seed=3))
    w3 = build_world(RunConfig(f=3 / 12, seed=3))
    assert len(w3.attackers) == 3
    for i in range(12):
        if w3.attacker[i]:
            assert w3.holdings[i] == []
        else:
            assert w3.holdings[i] == w0.holdings[i]
    assert w0.target == w3.target != w0.task.correct


def test_nested_placement():
    w1 = build_world(RunConfig(f=1 / 12, seed=5))
    w3 = build_world(RunConfig(f=3 / 12, seed=5))
    assert set(w1.attackers) <= set(w3.attackers)


def test_attacker_count_rounding():
    assert RunConfig(f=0.05, n_agents=12).n_attackers == 1     # 0.6 -> 1
    assert RunConfig(f=1 / 24, n_agents=12).n_attackers == 1   # 0.5 rounds up
    assert RunConfig(f=0.04, n_agents=12).n_attackers == 0


def test_hub_placement_star():
    w = build_world(RunConfig(topology="star", f=1 / 12, placement="hub"))
    assert list(w.attackers) == [0]


def test_m4_adds_uninformed():
    w = build_world(RunConfig(modules=["M4"]))
    assert w.N == 14 and w.uninformed.sum() == 2 and w.honest.sum() == 12


def test_option_names_independent_of_hash_seed():
    import os
    import subprocess
    import sys
    code = "from hiveguard.task import generate_task; print(generate_task(3, 12).option_names)"
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={**os.environ, "PYTHONHASHSEED": str(h)}).stdout for h in (0, 1, 2)}
    assert len(outs) == 1
