# Deviations from the pre-registration

The pre-registration is [DESIGN.md](DESIGN.md), committed alone in the first commit of this repository
(SHA-256 `0d8805c2…08cd5c8`). Every change made during the sprint is logged here with its reason.
Changes are listed in the order they were made.

| # | Date | Section | Change | Reason |
|---|---|---|---|---|
| D1 | 2026-11-08 | §5.1 | Facts are dealt to all N positions with a seed that does not depend on `f`. Positions that become attackers lose their facts. Honest agents hold the same facts at every `f`. | In the original plan, facts were split over honest agents only, so each honest agent held more facts as `f` grew (about 4 at `f=0`, about 5.3 at `f=3/12`). That mixed up attacker fraction with information per agent. |
| D2 | 2026-11-08 | §5.1 | Redundancy `m` is `max(2, round(4N/24))` instead of a fixed 2. | With m=2, agents at N=200 would hold 0.24 facts each, so most ABM agents would be uninformed. This keeps about 4 facts per agent at every N. m=2 is unchanged at N=12. |
| D3 | 2026-11-08 | §8, §10.2 | Number of attackers k = nearest integer to `f·N`, halves rounded up. The effective `k/N` is logged and used in fits. | The ABM grid includes `f` values that are not multiples of 1/N. |
| D4 | 2026-11-08 | §8 | Random placement is nested: the attackers at `f=1/12` are a subset of those at `f=3/12` (same seed). | Makes the `f` comparison paired. |
| D5 | 2026-11-08 | §5.3, §6.1 | Rounds are indexed 0..R−1. Round 0 is an independent answer from private facts only; social updates happen in rounds 1..R−1. Onset `o` means the attacker behaves honestly in rounds `< o`. | The design left round 0 implicit. This keeps calls per run at N·R = 72 for the LLM, as budgeted. |
| D6 | 2026-11-08 | §13 | All ABM twins, modules and attacks live in `hiveguard/abm.py`. All LLM views and prompts live in `hiveguard/llm_strategies.py` and `hiveguard/agents.py`. There is no `strategies/` folder with one file per strategy. | Sprint time. The interfaces match §13 in spirit (`init/step` per strategy; modules as sender weights and gates). |
| D7 | 2026-11-08 | §5.5 | Sybil aliases (A4) multiply an attacker's weight only on board strategies (S4, S5, S9, S10) and in quorum counts on the board. With direct messages, A4 behaves like A2. | Aliases exist only on a shared medium. Direct messages carry the sender's real id. |
