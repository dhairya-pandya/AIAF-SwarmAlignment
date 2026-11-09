import pandas as pd
import pytest

from hiveguard.config import MODULES, STRATEGIES, RunConfig
from hiveguard.env import LLMEnv, replay, run_llm
from hiveguard.llm import CacheMiss, LLMClient
from hiveguard.llm_runs import block_configs, run_block
from hiveguard.schema import parse_output


def test_parse_output_tolerant():
    raw = 'Sure!\n```json\n{"choice": "b", "confidence": 0.7, "claims": [{"option": "B", "attribute": "safety", "value": 8, "source": "own"}], "message": "x"}\n```'
    o = parse_output(raw, {"A", "B", "C", "D"})
    assert o.choice == "B" and o.claims[0].value == 8
    with pytest.raises(ValueError):
        parse_output('{"choice": "Z", "confidence": 0.5}', {"A", "B"})
    with pytest.raises(ValueError):
        parse_output("no json here", {"A"})


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_runs_with_mock(tmp_path, strategy):
    cl = LLMClient(tmp_path / "c.sqlite")
    m = run_llm(RunConfig(strategy=strategy, backend="llm", f=0.25), cl, tmp_path / "logs")
    assert m["valid_rate"] == 1.0
    assert m["calls"] == (12 if strategy in ("S0a", "S0b") else 72)


@pytest.mark.parametrize("module", MODULES)
def test_modules_run(tmp_path, module):
    cl = LLMClient(tmp_path / "c.sqlite")
    for s in ["S2", "S4", "S9"]:
        run_llm(RunConfig(strategy=s, backend="llm", f=0.25, modules=[module], models=["mock:a", "mock:b"]),
                cl, tmp_path / "logs")


def test_replay_is_byte_identical(tmp_path):
    cfg = RunConfig(strategy="S4", backend="llm", f=0.25, attack="A4", modules=["M2"])
    run_llm(cfg, LLMClient(tmp_path / "c.sqlite"), tmp_path / "logs")
    assert replay(cfg.run_id, tmp_path / "logs", tmp_path / "c.sqlite")


def test_replay_only_raises_on_miss(tmp_path):
    with pytest.raises(CacheMiss):
        run_llm(RunConfig(strategy="S2", backend="llm"), LLMClient(tmp_path / "c.sqlite", replay_only=True), None)


def test_attacker_sees_target_honest_does_not(tmp_path):
    env = LLMEnv(RunConfig(strategy="S2", backend="llm", f=0.25), LLMClient(tmp_path / "c.sqlite"), None)
    a = int(env.world.attackers[0])
    h = int(next(i for i in range(env.N) if env.world.honest[i]))
    assert "hidden target" in env._messages(a, 0)[0]["content"]
    assert "hidden target" not in env._messages(h, 0)[0]["content"]


def test_sybil_aliases_on_board(tmp_path):
    env = LLMEnv(RunConfig(strategy="S9", backend="llm", f=0.25, attack="A4"), LLMClient(tmp_path / "c.sqlite"), None)
    env.run()
    a = int(env.world.attackers[0])
    assert len({d["display"] for d in env.strategy.dances if d["author"] == a}) == 3


def test_pilot_block_resumes(tmp_path):
    cfgs = block_configs("pilot", ["mock:mock"], 1)
    out = str(tmp_path / "p.csv")
    run_block(cfgs, out, str(tmp_path / "c.sqlite"), str(tmp_path / "logs"), 4)
    df = run_block(cfgs, out, str(tmp_path / "c.sqlite"), str(tmp_path / "logs"), 4)
    assert len(df) == len(cfgs) == 5   # S2, S4 x f in {0, 1/6}, plus the S0a oracle check
    assert isinstance(df, pd.DataFrame)


def test_core_block_size():
    cfgs = block_configs("core", ["mock:mock"], 3)
    # S2, S3 on ring+full; S0b, S1, S4, S7, S9 on full only; plus S0a oracle
    assert len(cfgs) == (2 * 2 + 5) * 3 * 3 + 3


def test_s11_trust_from_claims(tmp_path):
    from hiveguard.schema import Claim
    env = LLMEnv(RunConfig(strategy="S11", backend="llm", f=0.25), LLMClient(tmp_path / "c.sqlite"), None)
    st, t = env.strategy, env.task
    i = int(next(k for k in range(env.N) if env.world.honest[k]))
    f = t.facts[env.world.holdings[i][0]]
    opt, att = t.option_id(f.option), t.attributes[f.attribute]
    other = [x for x in range(len(t.facts)) if x not in env.world.holdings[i]][0]
    g = t.facts[other]
    assert st.check(i, [Claim(option=opt, attribute=att, value=f.value)]) == (1, 0)
    assert st.check(i, [Claim(option=opt, attribute=att, value=(f.value + 1) % 11)]) == (0, 1)
    assert st.check(i, [Claim(option=t.option_id(g.option), attribute=t.attributes[g.attribute], value=g.value)]) == (0, 0)
    env.run()
    assert all(st.floor <= v for row in st.trust.values() for v in row.values())
    assert "trust" in env._messages(i, 1)[1]["content"]


def test_s12_corroboration_leaders(tmp_path):
    from hiveguard.schema import Claim, Output
    env = LLMEnv(RunConfig(strategy="S12", backend="llm", f=0.25, attack="A5"), LLMClient(tmp_path / "c.sqlite"), None)
    st, t = env.strategy, env.task
    a0, a1 = t.attributes[0], t.attributes[1]

    class T:
        def __init__(self, claims, conf=0.5):
            self.out = Output(choice="A", confidence=conf, claims=claims)
    turns = [T([]) for _ in range(env.N)]
    turns[0] = T([Claim(option="A", attribute=a0, value=7), Claim(option="B", attribute=a1, value=3)])
    turns[1] = T([Claim(option="A", attribute=a0, value=7)])
    turns[2] = T([Claim(option="B", attribute=a1, value=3), Claim(option="A", attribute=a0, value=2)])
    turns[3] = T([Claim(option="A", attribute=a0, value=7, source="ag-11")], conf=1.0)   # relayed, not first-hand
    env.turns.append(turns)
    env.claim_ids.append([[f"{env.disp[j]}-r0-{k}" for k in range(len(tt.out.claims))] for j, tt in enumerate(turns)])
    sc = st.corroboration(0)
    assert sc[0] == (2, 1) and sc[1] == (1, 1) and sc[2] == (1, 1) and sc[3] == (0, 0)
    L = st.leaders(1)
    assert L[0] == 0 and set(L[1:]) == {1, 2} and st.leaders(1) == L
    msg = env._messages(5, 1)[1]["content"]
    assert "independently confirmed" in msg
    for i in (0, 5):
        ins = st.instruction(i, 1)
        assert "independently confirmed" in ins and "confiden" not in ins.lower()


def test_s12_mock_run_excludes_attackers(tmp_path):
    env = LLMEnv(RunConfig(strategy="S12", backend="llm", f=0.25, attack="A5"), LLMClient(tmp_path / "c.sqlite"),
                 tmp_path / "logs")
    m = env.run()
    assert m["calls"] == 72 and m["valid_rate"] == 1.0
    assert all(len(L) == 3 for L in env.strategy._leaders.values())
