# Swarm Immunity: How Nature's Collectives Inspire Defences for Agentic AI

**Which bio-inspired swarm designs resist compromised agents, and which defences are worth their cost?** A safety benchmark of bio-inspired coordination
strategies for LLM agent swarms with compromised agents. The code package is `hiveguard`. Built for the Apart × AIAF Swarm Alignment
Hackathon (Nov 6–8, 2026).

- [DESIGN.md](DESIGN.md): pre-registration (hypotheses, metrics, analysis plan). Committed alone in the first commit, before any code.
- [RESEARCH.md](RESEARCH.md): literature notes.
- [DEVIATIONS.md](DEVIATIONS.md): every change made to the pre-registered plan during the sprint.
- [paper/paper.md](paper/paper.md): the report draft.

**Status: work in progress.** No results have been produced yet.

## Setup

```bash
uv venv -p 3.12 && uv pip install -e '.[dev]'
pytest
```

## Pipeline

```bash
# LLM providers (any subset). The mock provider works offline.
export OPENROUTER_API_KEY=...   # or NVIDIA_API_KEY=..., or run `ollama serve` with a model pulled

# 1. Pilot (DESIGN §10.1): N=6, R=3, S2 and S4, f in {0, 1/6}, 3 seeds per model; prints the go criteria
hiveguard pilot --models openrouter:<model> nvidia:<model>

# 2. Calibrate the ABM's kappa and lambda on the pilot runs, then freeze them
hiveguard calibrate --pilot results/pilot.csv --out results/abm_params.json

# 3. Stage A: ABM screen over the full grid, plus the red-team searchers
hiveguard stageA --params results/abm_params.json
hiveguard search --params results/abm_params.json --strategies S2 S4 S9 --topologies scale_free full

# 4. Stage B: LLM blocks
hiveguard stageB --block core    --models openrouter:<model>
hiveguard stageB --block tier2   --models openrouter:<model>
hiveguard stageB --block modules --strategies <best> <worst> --models openrouter:<model>
hiveguard stageB --block attacks --strategies <best> --models openrouter:<model>
hiveguard stageB --block confirm --strategies <most> <least> --redteam results/redteam.json --models openrouter:<model>

# Replay any LLM run byte for byte from the cache
hiveguard replay <run_id>
```

Every LLM call is cached in `.cache/llm.sqlite`, keyed by `sha256(provider, model, prompt, seed, temperature)`.
Every run writes `logs/<run_id>.jsonl`: config, then per agent and round the prompt, prompt hash, raw
response, parsed output and choice.

## Reproducing the results

Every number in the report can be regenerated from this repository. Three levels of reproduction are available:

| Level | Needs | Command | What it checks |
|---|---|---|---|
| 1. Re-analyse | nothing | `python -m hiveguard.run analyze` | figures, hypothesis verdicts and `results/results.json` from the committed run tables |
| 2. Replay LLM runs | nothing (no API key, no cost) | `python -m hiveguard.run replay <run_id>` | re-executes a logged LLM run against the committed response cache `.cache/llm.sqlite` and checks that the log is **byte-identical** |
| 3. Re-run | an OpenRouter key | `python scripts/stage_b_pipeline.py` | fresh LLM calls; results vary within the reported CIs because sampling is stochastic |

The ABM results (Stage A, red team) are deterministic given the seed and the frozen parameters in `results/abm_params.json`. To rebuild them, run `python -m hiveguard.run stageA --params results/abm_params.json` and `python -m hiveguard.run search ...`, with the arguments recorded in EXPERIMENT_LOG.md.

The provenance of the results is recorded in these files:
- `EXPERIMENT_LOG.md`: what was run and when, in time order;
- `DEVIATIONS.md`: every change to the pre-registered plan;
- `logs/*.jsonl`: one file per LLM run, holding the config, every prompt, raw reply, parsed output and the result;
- `results/*.csv`: one row per run.

## Code map

| File | Contents |
|---|---|
| `hiveguard/config.py` | `RunConfig`, seeding, YAML IO |
| `hiveguard/task.py` | hidden-profile best-of-n generator |
| `hiveguard/topology.py` | ring, small-world, scale-free, star, full |
| `hiveguard/world.py` | task, graph, roles and target for one run (shared by ABM and LLM) |
| `hiveguard/abm.py` | ABM twins of S0–S10 (plus exploratory S11), attacks A1–A5, modules M1–M6 |
| `hiveguard/search.py` | red-team searchers: random, hub, GA, binary PSO, MAP-Elites |
| `hiveguard/stage_a.py` | Stage A grid and red-team runner (multiprocess) |
| `hiveguard/schema.py` | pydantic output schema and tolerant JSON extraction |
| `hiveguard/llm.py` | OpenAI-compatible client (NVIDIA, OpenRouter, Ollama, mock), rate limits, sqlite cache |
| `hiveguard/agents.py` | prompt builders |
| `hiveguard/llm_strategies.py` | LLM views and update instructions for S0–S10 (plus exploratory S11) |
| `hiveguard/env.py` | LLM round loop, modules, board, JSONL logs, replay |
| `hiveguard/llm_runs.py` | pilot and Stage B blocks (resumable CSV) |
| `hiveguard/calibrate.py` | kappa/lambda fit on pilot runs |
| `hiveguard/metrics.py` | Acc, Con, T50, deadlock, consensus time, f*, bootstrap, Holm |

## Pre-existing work declaration

Pre-sprint materials (written 2026-11-01 to 2026-11-05): `RESEARCH.md` (literature notes) and
`DESIGN.md` (the pre-registration). No experiment code, data or results existed before the sprint
began on 2026-11-06. All code under `hiveguard/`, `analysis/` and `tests/` was written during the sprint.

SHA-256 of the pre-registration files at the first commit:

```
0d8805c20d4e3973e1b076ce944b5de9abf806bda7b4d0714c26bd83b08cd5c8  DESIGN.md
af96a648ac2a2bbecfa39a43cf36deb54f8f91747a50bf88d34c39644b4e8b60  RESEARCH.md
```
