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
