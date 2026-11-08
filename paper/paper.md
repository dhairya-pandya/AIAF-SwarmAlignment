# Swarm Immunity: How Nature's Collectives Inspire Defences for Agentic AI

*Apart × AIAF Swarm Alignment Hackathon, November 6–8, 2026. Primary track: Science of Agent Networks (Track 2). Secondary track: Oversight and Control (Track 4).*

> **Draft status.** This draft is written alongside the code. The introduction, related work and methods sections describe the system as built. Every number in the results section is a placeholder marked `[TBD]`. It will be filled only from the run logs in `results/`. No result is stated before the experiment that produces it has been run.

## Abstract

*(150–250 words, written last.)*

[TBD]

## 1. Introduction

In August 2026, about 1,200 AI agents in the Hugging Face incident coordinated through a message board they built in a shared directory, and a single agent came to direct hundreds of others [I1]. Swarm-intelligence research has studied both of these mechanisms for three decades. Coordination through traces left in a shared medium is called *stigmergy* [A10, A11]. A small number of individuals steering a large group is called *emergent leadership* [A8, C1]. The same research makes falsifiable predictions about how a compromised minority spreads through a group:

- the communication topology sets how fast influence spreads [A4, C9, G5];
- committed minorities flip group decisions above a tipping fraction of about 10–25% [C7, C8, E9];
- adding uninformed members hands control back to the majority [C2, G7].

Nature also supplies safety mechanisms, and they are all forms of negative feedback: pheromone evaporation [A2], stop signals [C3], quorum thresholds [C4, C5] and scouts that abandon stale sources [A6].

We ask which of these coordination algorithms, applied to LLM agents, contain a compromised minority best, and at what cost in usefulness. **HiveGuard** implements 11 swarm-intelligence coordination strategies for LLM agents. Each strategy has an agent-based-model (ABM) twin with the same parameters. We attack them with 5 types of compromised agent, placed at random, on network hubs, or by 5 red-team search algorithms. We then measure contamination, accuracy, spread speed and tipping points across 5 topologies and 6 add-on defence modules.

**Contributions.**
1. A seeded, cached and replayable testbed for LLM swarms that runs 11 coordination strategies, each paired with a cheap ABM twin (Track 1).
2. A pre-registered comparison of these strategies under attack. The hypotheses, metrics and analysis plan were committed before any code was written (Track 2).
3. An ablation of bio-inspired negative-feedback defences, scored in AI-control style as safety vs. usefulness [H1] (Track 4).
4. Red-team metaheuristics (a genetic algorithm, binary PSO and MAP-Elites) that search for worst-case attacker placement, onset round and behaviour, compared at equal evaluation budgets.
5. An estimate of how far a calibrated ABM can stand in for LLM swarms, and where it breaks down.

## 2. Related work

**Swarm-intelligence algorithms and their critics.** The strategies we compare come from ant colony optimization [A2], particle swarm optimization (PSO) [A3, A4], artificial bee colony [A6], firefly [A7], grey wolf [A8], response-threshold division of labour [A9] and boids [A1]. Sörensen [B1] and Camacho-Villalón et al. [B2] argue that many animal metaphors repackage old components; grey wolf and firefly, for example, reuse PSO concepts. We therefore tag each strategy by its algorithmic components and test whether results group by component or by metaphor (H10).

**Collective decisions.** Our task is a best-of-n problem [C6] built as a hidden profile [C13]. Honeybee stop signals [C3] and quorum sensing [C4, C5] are the source of two of our defence modules. Committed-minority tipping points have been studied in theory [C8], in human experiments [C7] and in LLM populations [E9].

**Robot-swarm security.** Classical voter and majority swarms break when Byzantine robots are present [D3], and identity is a core weakness of swarms [D2]. HiveGuard asks the same questions of LLM swarms.

**LLM swarms.** Earlier work applies PSO in LLM weight space [E1], benchmarks swarm capability [E2], reimplements boids and ACO with LLM agents [E3, E4] and observes stigmergy in LLM societies [E8]. These studies measure capability. We measure safety.

**Multi-agent safety.** Infectious jailbreaks [G2], prompt infection [G3] and manipulated-knowledge flooding [G4] show that compromise spreads through agent networks. NetSafe [G5] shows that topology matters, and Huang et al. [G6] find hierarchy resilient to faulty agents. Becker et al. [G7] show that debate looks robust partly because uninformed agents outnumber misinformed ones. HiveGuard extends NetSafe from topology alone to topology × coordination algorithm × defence, and it adds optimized attackers. Like AgentBreeder [G10] it uses evolutionary search, but it searches over attacks rather than over scaffolds.

**AI control.** We follow the AI-control methodology [H1]: assume some agents are adversarial, and report safety against a red team together with usefulness when no attack is present.

## 3. Methods

### 3.1 Task

Each instance is a fictional best-of-4 choice. Every option has 6 integer attributes from 0 to 10, everyone sees the same public integer weights from 1 to 5, and the correct option is the arg-max of the weighted sum. Its 24 attribute facts are each dealt to `m` agents, so every agent holds about 4 facts (`m=2` at N=12).

A generator rejects instances in which 40% or more of agents could find the correct option from their own facts. It also requires the score gap between the best and second-best option to lie in a band that the pilot tunes. Communication is therefore necessary, which is what makes compromise costly.

Facts are dealt to positions before roles are assigned. Honest agents hold the same facts at every attacker fraction `f`, and an agent that becomes compromised loses its facts. The attackers' target is a single wrong option, drawn from the seed.

### 3.2 Agents, rounds and topologies

Each run has R=6 synchronous rounds. In round 0, every agent answers from its private facts alone. LLM agents return validated JSON with these fields:
- a choice and a confidence;
- structured claims `(option, attribute, value, source)`, where `source` is `own` or the id of the agent the claim came from;
- endorsements and stop signals;
- a message of at most 60 words.

The group decision is the plurality of honest agents' final choices. We use five topologies: ring, small-world, scale-free, star and fully connected.

### 3.3 Coordination strategies

[Table 1: the 11 strategies, from DESIGN §6.2, with the component matrix of §6.3.]

In each ABM twin, an agent's belief is a distribution over the options. Its private evidence is a softmax over its partial weighted score. Two calibrated parameters describe honest ABM agents: deference κ (how much weight social information gets relative to the agent's own evidence) and confidence sensitivity λ.

### 3.4 Defence modules

| ID | Module | What it does |
|---|---|---|
| M1 | Evaporation | Down-weights claims that stay unchanged over rounds |
| M2 | Stop signals | Hides a claim for 2 rounds once ≥2 agents with contradicting first-hand facts stop it |
| M3 | Quorum on first-hand evidence | An agent may switch its choice only when ≥q distinct agents report a supporting claim with `source: own` |
| M4 | Uninformed dilution | Adds agents with no facts |
| M5 | Model diversity | Splits honest agents across 2–3 model families |
| M6 | Sparse topology | Rewires the network to a ring |

### 3.5 Attacks and red team

The five attack types are:
- **A1, confident liar:** argues for the target with no specific claims;
- **A2, fabricated evidence:** makes up claims marked `source: own`;
- **A3, sleeper:** behaves honestly, then switches to A2;
- **A4, sybil:** posts on the board under 3 aliases;
- **A5, leader capture:** reports maximal confidence.

Each attack can start at any onset round. Red-team searchers (random, greedy hub, a genetic algorithm, binary PSO and MAP-Elites) search over (attacker nodes × onset × attack type) with 500 ABM evaluations each, repeated 10 times. Fitness is the mean contamination over 5 seeds.

### 3.6 Metrics and statistics

The metrics are:
- **accuracy:** the share of honest agents whose final choice is correct;
- **contamination:** the share of honest agents whose final choice is the attackers' target;
- **T50:** the first round at which contamination reaches half of its final value;
- **deadlock and consensus time;**
- **tipping point `f*`:** where a logistic fit of contamination against `f` crosses 0.5;
- **usefulness cost:** the change in accuracy at `f=0` when a module is added;
- **collaboration gain:** the accuracy improvement over compute-matched majority voting (S1).

Seeds are the unit of analysis. We use paired bootstrap 95% CIs with 10k resamples and Holm correction over H1–H10.

### 3.7 Experimental stages

The pilot calibrates the ABM's κ and λ, which are then frozen. Stage A sweeps the ABM over the full grid. Stage B runs LLM agents on a slice chosen from the Stage A results, about 15k calls in total. The ABM's predictions for Stage B are written down before Stage B runs.

## 4. Results

*Every subsection below is filled from `results/` only.*

### 4.1 Leaderboard and safety–usefulness front (RQ1)
[TBD: Table 2, Figure 2]

### 4.2 Swarm-theory transfer: topology, tipping points, dilution (RQ2: H1, H2, H5)
[TBD: Figures 3, 4]

### 4.3 Defence modules (RQ3: H3, H4)
[TBD: Figure 5]

### 4.4 Components vs. metaphors (RQ4: H10)
[TBD]

### 4.5 Red team (RQ5: H7)
[TBD: Figure 6]

### 4.6 ABM as a cheap proxy (RQ6: H6)
[TBD: Figure 7]

### 4.7 Hypothesis scorecard
| ID | Verdict | Evidence |
|---|---|---|
| H0–H10 | [TBD] | [TBD] |

## 5. Discussion
[TBD: what transfers from ants to agents and what doesn't, and what this means for people who deploy agent swarms.]

## 6. Limitations and future work

- **Small swarms.** LLM runs use N=12. Larger N is studied only in the ABM.
- **Models.** We use open models on free tiers, not frontier agents.
- **Agents.** Agents are text-only and have no tools.
- **Overt attackers.** Steganographic collusion [G8] is out of scope.
- **Task scope.** Claims are limited to the hidden-profile best-of-n task family [B3].
- **Tipping points from LLM data.** The LLM grid has only three values of `f` (0, 1/12 and 3/12). LLM tipping points are therefore reported only as ABM-predicted values checked at those points, not as standalone fits.
- **Timestamp of the pre-registration.** The pre-registration files are dated 2026-11-01, but they were first committed and pushed on 2026-11-08. Their SHA-256 hashes are listed in the README, and every change to the plan is logged in DEVIATIONS.md.

## Appendix A. Dual-use and ethical considerations

The task is a benign, fictional choice among made-up options. It involves no harmful content, no real systems and no agents facing the internet.

Findings about where to place attackers so that they spread furthest (hubs, early onset, leader capture) could help someone attack real agent swarms. We reduce this risk in four ways:
- red-team results are reported in aggregate;
- attack templates are published only at the level of detail already in the literature [G2–G4];
- tuned persuasive attack prompts are not released;
- results are framed and ranked around defences.

None of HiveGuard's mechanisms makes swarm activity harder to detect, and the board's read/write logs are designed to support forensics.

## Appendix B. Deviations from the pre-registration
See [DEVIATIONS.md](../DEVIATIONS.md).

## Appendix C. Prompts and parameters
[TBD: generated from `hiveguard/agents.py` and `ABMParams`.]

## References
The bracketed IDs refer to the entries in [RESEARCH.md](../RESEARCH.md), where every reference has a verified DOI or arXiv link. [I1] is the METR / Redwood Research incident investigation listed in RESEARCH.md §I.
