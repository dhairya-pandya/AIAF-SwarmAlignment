# Study 2: confirmatory follow-up (pre-registration)

Written and committed on 2026-11-09, before any Study 2 run. Study 1 (DESIGN.md) is complete. Its LLM results suggested three effects that were large but uncertain or untested, because 6 seeds and a 10-hypothesis Holm family left too little power. Study 2 tests only these three effects, on **fresh seeds**, with a 3-hypothesis Holm family. Study 1 data are not reused in the confirmatory tests.

## Design

Everything is unchanged from Study 1 except the seeds:
- `openai/gpt-oss-120b` with low reasoning effort, temperature 0.7, `max_tokens` 4000;
- N = 12, R = 6, attack A2, random placement;
- the same task generator, prompts and analysis code.

**Seeds:** 6–17 (12 new seeds). Study 1 used seeds 0–5.

| Arm | Strategy | Topology | f | Module | Runs |
|---|---|---|---|---|---|
| a | S7 grey-wolf hierarchy | full | 3/12 | none | 12 |
| b | S7 grey-wolf hierarchy | full | 3/12 | M3 quorum | 12 |
| c | S2 leaderless debate | full | 3/12 | none | 12 |
| d | S2 leaderless debate | ring | 3/12 | none | 12 |
| e | S2 leaderless debate | ring | 3/12 | M3 quorum | 12 |

That is 60 runs. At about $0.021 per run (measured in Study 1), the cost is about $1.30. A budget guard stops the study before the OpenRouter spend exceeds $9.85 of $10.

## Hypotheses

The unit is the seed. Arms are paired by seed, because each seed fixes the task, the graph and the attacker set. The outcome is contamination (Con) of honest agents at the final round.

| ID | Hypothesis | Contrast | Supported if |
|---|---|---|---|
| C1 | A quorum on first-hand evidence reduces leader capture | Con(b) − Con(a) | one-sided paired bootstrap p < α after Holm (3 tests), and the mean difference < 0 |
| C2 | Leaderless debate on a fully connected graph is less contaminated than a confidence-elected hierarchy | Con(c) − Con(a) | as above |
| C3 | A quorum on first-hand evidence reduces contamination of leaderless debate on a sparse (ring) graph | Con(e) − Con(d) | as above |

- **Test:** paired percentile bootstrap over seeds (10,000 resamples, fixed RNG seed 0). The one-sided p is the share of resamples with mean difference ≥ 0.
- **Correction:** Holm across C1–C3 at family-wise α = 0.05.
- **Effect sizes:** reported with 95% CIs whatever the verdict.
- **Verdicts:**
  - *supported*: the Holm-adjusted p < 0.05 and the effect is in the predicted direction;
  - *not supported*: the effect is in the opposite direction, or the CI excludes the predicted sign;
  - *inconclusive*: anything else.

## Power and expected results (written before data)

From Study 1:
- **C1:** mean effect −0.28, paired SD 0.44. With 12 seeds, SE ≈ 0.13 and power ≈ 0.65 at one-sided α = 0.05/3.
- **C2:** effect 0.61, SD 0.38. Power ≈ 1.
- **C3:** no prior estimate. Study 1's S2 on the ring had Con 0.39 at f = 3/12.

## Secondary (descriptive, no test)

- Pooled Study 1 + Study 2 estimates for C1–C3, with 18 seeds per arm.
- Accuracy in each arm.

## What changes in the report

A new subsection, "Confirmatory follow-up (Study 2)", reports C1–C3 exactly as specified here, whatever the outcome. Study 1 verdicts are not changed.
