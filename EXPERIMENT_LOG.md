# Experiment log

This is a lab notebook kept in time order (IST). It records what was run, what came out, and what was decided. Numbers come from files in `results/` and `logs/`.

## 2026-11-08

- **22:51** First Stage A screen launched: ABM, uncalibrated default parameters, full grid, about 265k runs after dedup. Output: `results/stageA_precal.csv`.
  - Red-team search launched alongside: S2/S3/S4/S9 × scale-free/small-world, k=3, budget 500, 10 repeats. Output: `results/redteam_precal.json`.
- **23:30** Analysis of the uncalibrated screen (`results/results_precal.json`, `figures/precal/`). Exploratory only, not for the report.
  - S2, S6, S8, S10 and S7 saturate to contamination ≈ 1 by f ≈ 0.05–0.1.
  - S4, S5 and S9 rise roughly linearly to 0.4–0.5 at f = 0.4.
  - S3 plateaus at about 0.5–0.65.
  - The red-team search saturates on S2 at k=3: every searcher reaches 1.0, so H7 cannot discriminate. P1 reruns it with smaller k.
- **23:00–23:30** NVIDIA model screen. Most catalogue models returned 404 or timed out. `nemotron-3.5-lightning-30b-a3b` answered in 2 s with thinking off.

## 2026-11-09

- **00:00–00:40** Pilot iterations on Nemotron, all discarded (DEVIATIONS D15–D17):
  1. Replies were truncated at 500 and then 1200 tokens because the model endorsed every visible claim. Fix: cap the lists (D15). Validity rose to 1.0.
  2. Oracle (S0a, all facts) accuracy with thinking off was 0.53 over 12 seeds. The model could not combine the facts.
  3. Thinking on solved the hard seeds, but often reasoned past 8000 tokens without answering. Throughput fell to about 5 calls/min and the key hit HTTP 429 lockouts.
  4. Facts were shown with their point values (D17). Thinking-off oracle accuracy stayed at 0.54.
- **01:00** OpenRouter oracle screen (S0a, N=3, 12 seeds; logs in `results/oracle_logs/`):

  | Model | Oracle acc |
  |---|---|
  | `openai/gpt-oss-120b` | **0.97** |
  | `meta-llama/llama-3.3-70b-instruct` | 0.58 |
  | `deepseek/deepseek-chat-v3.1` | 0.56 |
  | `mistralai/mistral-small-2603` | 0.50 |
  | `qwen/qwen3-30b-a3b-instruct-2507` | 0.42 |

  Chose gpt-oss-120b (D18).
- **01:20** First gpt-oss pilot: validity 0.77. Most invalid replies were empty, because reasoning used up `max_tokens`=1200 in the social rounds. Fix: reasoning effort low, `max_tokens` 4000. Oracle accuracy after the fix: **1.00 on 12/12 seeds**.
- **01:40** The pilot rerun stopped with HTTP 402: the OpenRouter account has no credit. Total spend so far is $0.19. Waiting for credit.
- **01:55** Checked the sprint page and the organisers' email: deadline 23:59 AoE (17:29 IST), report PDF of 4–8 pages, required limitations and dual-use appendix. Wrote EXPERIMENT_PLAN.md.
- **01:58 P0 pilot passed** (`results/pilot.csv`; gpt-oss-120b, reasoning effort low, max_tokens 4000). 15 runs, 240 calls, $0.037, so about $0.00015/call.
  - Validity 1.00 and refusals 0.
  - Oracle S0a accuracy 1.00 on 3/3 seeds.
  - S2 accuracy at f=0 was 0.94; S4 at f=0 was 0.33. Margin left untuned (D19).
- **02:03 P1 calibration:** grid κ∈[0.05,0.95] × λ∈{0,…,4}, 30 ABM seeds per cell. Best fit κ=0.30, λ=0.0, loss 0.135. Frozen in `results/abm_params.json` and committed before any Stage B run.
- **02:07 P2 core block launched:** 84 runs, about 6k calls, `results/stageB_core.csv`, 8 runs in parallel.
  - P1 ABM jobs launched at the same time with the frozen params: Stage A (`results/stageA.csv`), then red-team search at k=1 and k=2 over S2/S3/S4/S7/S9 × scale-free/small-world (`results/redteam_k{1,2}.json`).
  - The red-team k was reduced from 3 because k=3 saturated at contamination 1.0 in the uncalibrated screen.
- **02:25 M5 model screen** (oracle S0a, N=3, 12 seeds, reasoning effort low): minimax-m3.1-flash 1.00, nemotron-3-super-120b 1.00, glm-5.3-flash 0.97, qwen3.6-35b-a3b 0.97. Chose gpt-oss-120b + minimax + qwen for M5 (D21).
  - Throughput in the core block is about 230 calls/min, so Stage B was extended to 6 seeds (D20).
  - Remaining blocks are chained in `scripts/stage_b_pipeline.py`.
