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
- **02:38 P1 done:** calibrated Stage A (`results/stageA.csv`) and red-team search at k=1 and k=2 (`results/redteam_k{1,2}.json`).
  - Preview analysis, ABM only: `results/results_abm_preview.json`, `figures/abm_preview/`.
  - H0 supported, H1 supported, H10 supported (Holm p = 0.045).
  - H3 inconclusive (M3 ranks first, Holm p = 0.096).
  - H2 and H4 not supported. H7 (ABM half) not supported (p = 0.14).
  - Shape: S4, S5, S9 and S10 rise gradually with f. S2, S6, S7 and S8 saturate by f ≈ 0.05–0.15.
- **02:33** P2 core 3-seed block done (84 runs). The pipeline moved on to the 6-seed extension.
- **02:45** Exploratory S11 (vampire-bat reciprocity / reputation) is being built in an isolated worktree. It is not pre-registered and will be excluded from confirmatory tests (D22, pending).
- **02:40** Spend after the 3-seed core plus 29 extension runs: $1.82. That is about $0.00026/call, since N=12 prompts are longer than the pilot's. Projected total was about $8.3 against $10 of credit, so:
  - added a budget guard: stop before any block once spend exceeds $9.30;
  - cut the optional Tier-2 block to 3 seeds.
  - The pipeline was restarted. Completed calls are cached, so no work was lost.
- **02:57 P2 core done** (6 seeds, 168 runs, `results/stageB_core.csv`; spend $2.68). Selection rule: best = **S4** (con at f=3/12 0.17), worst = **S7** (0.61).
  - Ranking by contamination at f=3/12: S4 0.17, S2 0.19, S9 0.24, S3 0.30, S7 0.61.
  - First observations from cell means, not yet tested:
    - **LLM debate (S2) on the full graph shows no contamination at f=3/12 (0.00, acc 0.67), but 0.39 on the ring.** That is the opposite of the ABM and of H1's dense-is-worse prediction.
    - The grey-wolf hierarchy (S7) is captured (0.61).
    - Stigmergy (S4) is the safest but least useful (acc at f=0 is 0.43, vs 0.69 for S2).
  - P3 modules block started on S4 and S7.
- **03:20 Exploratory mechanism analysis** (`analysis/exposure.py`, `results/exposure.csv`, not pre-registered). Unit: honest LLM turns in social rounds, core block, f>0.
  - **S2 debate.** Agents on the full graph see about 66 claims per turn, against about 12 on the ring. The share of attacker claims is similar (0.11 vs 0.10). Adoption of the target is 0.04 on full vs 0.20 on the ring, and final contamination 0.05 vs 0.27.
  - **Reading:** the full graph gives each agent near-complete honest evidence, so a reasoning agent can recompute the correct answer. Robustness here comes from evidence completeness, not from dilution.
  - **Pooled over all turns:** adoption is 0.53 when attacker claims are more than half of what is visible.
  - **Caveats:**
    - The cross-strategy correlation of visible claims with contamination is weak (Spearman −0.18, n=7 cells).
    - The parser does not count S4 board posts or S9 dance claims (different id format), so the claim stays limited to S2.
- **03:28–03:57 P3/P4 blocks.** Cell means below; formal tests come in the analysis.
  - **Modules, f=3/12** (none = core: S4 con 0.17, S7 con 0.61):
    - **S7 + M3 quorum: con 0.33**, with accuracy at f=0 at 0.67 vs 0.68 for none, so no usefulness cost.
    - S7 + M1 evaporation: con 0.93, so evaporation makes leader capture *worse*.
    - S7 + M2: con 0.72. S7 + M4: con 0.63.
    - S4 + M3: con 0.11 vs 0.17 for none.
  - **M5, three model families:** S7 con 0.50 vs 0.61 single-model; S4 con 0.24 vs 0.17. M5 cost about $2 because the other models are pricier.
  - **Attacks on S4, f=1/12:** A1 0.23, A2 0.21, A3 0.18, A4 0.20, A5 0.11. All are close to S4's f=0 floor of about 0.12–0.17, so stigmergy is insensitive to attack type.
  - Spend after attacks: $6.79. Confirm block started.
- **04:21 All Stage B blocks done.**
  - Final spend: $8.14 of $10.
  - Confirm block:
    - The k=1 red-team genomes saturate in the ABM: every searcher reached con 0.964 on S7/scale-free with a single attacker at node 9.
    - Replayed on LLMs, they gave S7 con 0.00–0.42 depending on attack type, and S4 0.15–0.18.
  - Tier-2 (S5, S6, S8; 3 seeds) done.
- **04:25** S11 merged (D22). Stage A + S11 combined into `results/stageA_with_s11.csv`; S11 is excluded from confirmatory tests by code.
  - Final analysis launched with pre-registered resampling (bootstrap 2000 per cell, 10k for hypotheses, 9999 Mantel permutations). Output: `results/results.json`, `figures/`.
- **04:35 Reproducibility check** found the option-name ordering bug (D23); fixed, with log-based recovery in `replay`.
  - Replay is byte-identical on spot checks from every block.
  - The full re-check of all logged runs is in `results/replay_check.csv`.
- **04:40–05:10 Paper.**
  - Results, Discussion and Conclusion written from `results/results.json`.
  - The main body was cut to fit 8 pages: tables of strategies, modules and the hypothesis scorecard moved to the appendices.
  - The curves figure lost its spare legend row. The final analysis was re-run to regenerate the figures; numbers are unchanged.
- **Confirmation set pre-registered** (`docs/CONFIRMATION_PREREG.md`, originally `STUDY2_PREREG.md`, committed before any run). It is a confirmatory follow-up on fresh seeds 6–17 with 3 hypotheses:
  - C1: quorum reduces leader capture;
  - C2: leaderless debate on a full graph beats the hierarchy;
  - C3: quorum protects debate on a ring.

  60 LLM runs, about $1.30; the budget guard stops at $9.85.
- **Confirmation results** (pre-registered, fresh seeds 6–17; `results/confirmation.json`, originally `results/study2.json`). All three hypotheses supported after Holm (3 tests):
  - **C1:** quorum on the S7 hierarchy, con −0.33 [−0.60, −0.03], Holm p = 0.030.
  - **C2:** leaderless S2 debate (full graph) vs the S7 hierarchy, con −0.62 [−0.81, −0.41], p < 0.001. Accuracy under attack 0.85 vs 0.12.
  - **C3:** quorum on S2 on the ring, con −0.10 [−0.21, +0.01], Holm p = 0.047. Marginal: the two-sided CI includes 0.
  - Spend after the confirmation set: $8.99.
- **S12 elephant matriarch** (exploratory, D24; `results/s12_llm.json`). Leaders are elected by corroborated first-hand knowledge.
  - LLM con at f=3/12 is 0.31, vs S7 on the same seeds: −0.39 [−0.64, −0.15]. Vs leaderless S2 full: +0.23 [+0.02, +0.48].
  - Acc at f=0 is 0.43 (6 seeds), which is lower than S7 and S2; the CIs are wide.
  - In the ABM, attackers never became S12 leaders, while they held more than half of the S7 leader seats under A5.
  - Final spend: $9.25. No further runs.
