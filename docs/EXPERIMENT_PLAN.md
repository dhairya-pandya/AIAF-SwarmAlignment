# Experiment plan for the submission sprint (2026-11-09)

The study design and hypotheses are in [DESIGN.md](DESIGN.md). Changes to that design are logged in [DEVIATIONS.md](DEVIATIONS.md). [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) records what was run, with the numbers.

## Submission constraints (Apart sprint page, checked 2026-11-09)

- **Deadline:** Sun 8 Nov 2026, 23:59 AoE, which is **Mon 9 Nov 17:29 IST**. Target submission is **16:00 IST**.
- **Report:** PDF in the official template. 4–8 pages, excluding references and appendices.
  - Title, a 150–250-word abstract, and authors with affiliations.
  - Required appendix: **Limitations and Dual-Use / Ethical Considerations**.
- **Optional:** public GitHub repo, 3–5 min video, slides.
- **Judging:** each scored 1–5 on Impact & Innovation, Execution Quality, and Presentation & Clarity.
- **Rules:**
  - Pre-sprint work must be marked as preexisting in both the README and the report.
  - Made-up results or references can lead to disqualification.
  - Unfinished work is allowed if its limitations are stated honestly.

## Fit to scope

- **Track 2 (primary), The Science of Agent Networks.** The track asks "how compromise spreads through network shapes; whether behaviour changes smoothly or jumps suddenly". This is our core contribution:
  - contamination across 5 topologies and 11 coordination strategies;
  - tipping points f* (where contamination crosses 50%);
  - whether tipping is sharp (a jump) or gradual (smooth).
- **Track 4 (secondary), Multi-Agent Oversight and Control.** It asks "test whether control protocols hold against several coordinating agents". Our defence modules M1–M6 are control protocols, tested against coordinated attackers (A1–A5, red-team-optimised placement).
- **Track 1 (touch).** "Whether small models can stand in for frontier agents / what makes results transfer". The ABM-vs-LLM check (H6) and the red-team transfer check (H7) speak to it.

## Phases, gates and budget

The model is `openai/gpt-oss-120b` via OpenRouter at reasoning effort low (DEVIATIONS D18). Its oracle accuracy was 1.00 on 12 seeds.

Cost per call is estimated from the oracle screen: about 3k prompt tokens plus about 600 completion tokens, which comes to roughly $0.0002–0.0005. Spend is checked against the key's usage after every phase.

| Phase | IST | What | Runs / calls | Budget | Gate to continue |
|---|---|---|---|---|---|
| P0 Pilot | 02:00–02:30 | S2, S4 at f ∈ {0, 1/6}, plus S0a oracle; N=6, R=3, 3 seeds | 15 / ~270 | $0.20 | valid ≥ 0.98, refusals < 0.02, oracle ≥ 0.9; S2 acc at f=0 in 0.6–0.9, else adjust margin once (pre-registered) |
| P1 Calibrate + ABM | 02:30–03:15 | Fit κ, λ to the pilot and **freeze** them (commit before P2). Rerun the full Stage A (~300k runs) and the red-team search (k=1 and k=2, S2/S3/S4/S9, 2 topologies) | ABM only | $0 | calibration loss logged; f* curves non-degenerate |
| P2 Core | 03:15–05:00 | Tier-1 S0b, S1, S2, S3, S4, S7, S9 (+S0a) at f ∈ {0, 1/12, 3/12}; S2/S3 on ring + full; N=12, R=6, 3 seeds | 84 / ~5.8k | $3.00 | valid ≥ 0.95; spend ≤ 1.5× plan |
| P3 Defences | 05:00–06:30 | M1–M4 on the best and worst Tier-1 strategy at f ∈ {0, 3/12}; M5 = gpt-oss-120b + a second-family reasoning model | 54 / ~3.8k | $2.00 | — |
| P4 Attacks + confirm | 06:30–08:00 | A1–A5 on the best strategy at f=1/12. Best red-team genome per searcher on the most and least robust strategy | 15 + 30 / ~3.2k | $1.50 | — |
| P5 Tier-2 (optional) | if ahead | S5, S6, S8 at f ∈ {0, 1/12, 3/12} | 27 / ~1.9k | $1.00 | skipped first if late |
| Reserve | — | Reruns, the second-model screen, failures | — | $2.30 | — |
| **Total** | | | ~15k calls | **≤ $10** | |

**Cut order if time or money runs short:** P5, then the M5 arm of P3, then 3 seeds → 2 in P3/P4. P2 is never cut, because it decides H1, H2, H4, H8 and H9.

**After the runs:**

| Phase | IST | What |
|---|---|---|
| P6 Analysis | 08:00–09:30 | `hiveguard analyze` over everything: figures 1–7, H0–H10 verdicts with Holm correction, `results.json` |
| P7 Site | 09:30–10:00 | `hiveguard site`, deploy to Vercel |
| P8 Report | 10:00–14:30 | Fill `paper/paper.md` from `results.json` only; port to the official template; abstract of 150–250 words; Limitations and Dual-Use appendix; preexisting-work statement |
| P9 Submit | 14:30–16:00 | Final checks: tests pass, a replay is byte-identical, every number traces to a file, no fabricated references. Make the repo public; submit the PDF on the sprint page |
| Video (optional) | after submit | 3–5 min: problem, key figure, defences, replay clip |

## Logging (what makes the results checkable)

- **LLM calls:** every call is in the sqlite cache, keyed by provider, model, messages, seed, temperature, max_tokens and extras. Every run writes a JSONL log with its config, every turn (prompt, raw reply, parsed output, errors) and its result. `hiveguard replay <run_id>` re-derives the run from the cache, byte for byte.
- **Block results:** each block appends rows to `results/<block>.csv` and resumes after an interruption.
- **Notebook:** each phase adds an entry to EXPERIMENT_LOG.md (what ran, cost, gate outcome, surprises).
- **Plan changes:** any change to DESIGN is added to DEVIATIONS.md before the data it affects is analysed.
