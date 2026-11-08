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
2. A pre-registered comparison of these strategies under attack. The hypotheses, metrics and analysis plan were written before the sprint and committed before any experiment ran; every later change is logged (Track 2).
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

Figure 1 summarises the pipeline. A hidden-profile task makes communication necessary (§3.1). A swarm of LLM agents, a fraction of which are compromised, solves it under one of 11 coordination strategies (§3.2–3.3), optionally with a defence module (§3.4). Attacks are placed at random, on hubs, or by red-team search on a cheap agent-based twin (§3.5). Outcomes are scored with the metrics defined in §3.6.

### 3.1 Task: a hidden profile that forces pooling

**Design.** Each instance is a fictional best-of-4 choice. Option $o$ has six integer attributes $v_{o,a}\in\{0,\dots,10\}$, and public weights $w_a\in\{1,\dots,5\}$ define its quality $Q_o=\sum_a w_a v_{o,a}$. The correct option is $o^\star=\arg\max_o Q_o$. The 24 facts $(o,a,v_{o,a})$ are each dealt to $m$ agents, so every agent holds about four. An instance is accepted only if two conditions hold. First, the quality gap $Q_{o^\star}-\max_{o\neq o^\star}Q_o$ lies in $[4,16]$. Second, fewer than 40% of agents would pick $o^\star$ from their own facts. To decide that, an agent scores option $o$ by $\sum_{\text{known}} w_a(v_{o,a}-5)$, treating unknown values as the neutral 5.

**Why.** The task is a hidden profile [C13] on a best-of-$n$ problem [C6]. Pooling facts is required to answer correctly, so misinformation that enters the pool has a measurable cost. Each fact is shown with its points, e.g. `A.durability = 8 (+6 pts)` (DEVIATIONS D17). This keeps the difficulty in aggregation rather than arithmetic. A full-information oracle (S0a) scores 1.00 with the agent model used here (§3.2).

**Controls.** Facts are dealt to positions before roles are assigned. Honest agents therefore hold identical facts at every attacker fraction, and attacker sets are nested across $f$ (D1, D4). An agent that becomes compromised loses its facts. All attackers push a single wrong *target* option $t$, drawn from the seed.

### 3.2 Agents, rounds and topologies

A run has $N$ agents and $R$ synchronous rounds. In round 0 each agent answers from its private facts. In rounds $1,\dots,R-1$ it also sees what its strategy shows it (§3.3). Every reply must be a JSON object with these fields:
- a choice and a confidence in $[0,1]$;
- at most 8 structured claims $(o,a,v,\text{source})$, where the source is `own` or the id of the agent the claim came from;
- at most 3 endorsements and at most 3 stop signals, which refer to claim ids;
- a message of at most 60 words.

A reply that fails validation gets one repair prompt. If the repair also fails, the agent abstains for that round.

LLM agents are `gpt-oss-120b` at low reasoning effort and temperature 0.7, accessed through OpenRouter. It was chosen by an oracle screen of five models before any main run (D18). Honest agents are told the task and their facts. Attackers are additionally told the target and their attack type. Every call is cached by a hash of (model, messages, seed, temperature, max_tokens). Every turn is logged, and any run can be replayed byte-for-byte from the cache.

**Topologies.** We use ring, Watts–Strogatz small-world, Barabási–Albert scale-free, star and fully connected graphs. The headline LLM block uses $N=12$ and $R=6$. The agent-based twins also run $N=50$ and $N=200$.

### 3.3 Coordination strategies and their agent-based twins

Table 1 lists the strategies. They range from no communication (S0b, S1) through neighbour debate (S2) and particle-swarm updates (S3) to strategies built on a shared medium: ant-colony stigmergy (S4), bee colony (S5), honeybee dance with quorum (S9) and response-threshold verification (S10). Others use distance-weighted attraction (firefly, S6), a leader hierarchy (grey wolf, S7) or flocking with separation (boids, S8).

Following critiques that many animal metaphors repackage a few components [B1, B2], each strategy is tagged with the eight mechanism components of Figure 2: direct messages, shared medium, memory, hierarchy, distance decay, roles, negative feedback, quorum. This lets us ask whether outcomes group by component or by metaphor (H10).

Each strategy has an agent-based (ABM) twin. In the twin, each agent holds a belief $b_i$ on the 4-option simplex. Its private evidence is $e_i=\mathrm{softmax}(\beta\,s_i)$, where $s_i$ is its partial score vector. Social updates follow the strategy's rule; S2, for example, uses DeGroot averaging $b_i\leftarrow(1-\kappa)b_i+\kappa\,\overline{b}_{\mathcal N(i)}$ with sender weights proportional to confidence$^\lambda$.

Two parameters are calibrated on pilot LLM runs and then frozen before any main run (§3.7):
- the deference $\kappa$;
- the confidence sensitivity $\lambda$.

The twins make large sweeps and red-team search affordable: about $10^5$ runs per minute on a laptop, compared with minutes per LLM run.

### 3.4 Defence modules

The six modules are bio-inspired forms of negative feedback and structural control. Each can be added to any strategy.

| ID | Module (inspiration) | Rule |
|---|---|---|
| M1 | Evaporation (pheromone decay [A2]) | A sender whose choice is unchanged for $s$ rounds is down-weighted by $(1-\rho)^s$, with $\rho=0.3$ |
| M2 | Stop signals (honeybees [C3]) | A sender whose claim receives stop signals from $\ge2$ distinct agents is hidden for 2 rounds |
| M3 | Quorum on first-hand evidence (quorum sensing [C4, C5]) | An agent may switch to option $o$ only if $\ge q=2$ distinct agents have shown it first-hand (`own`) claims supporting $o$; otherwise its previous choice stands |
| M4 | Uninformed dilution (schooling fish [C2]) | Adds agents that hold no facts |
| M5 | Diversity (mixed populations) | Honest agents are split across two model families (LLM) or a spread of $\kappa$ (ABM) |
| M6 | Sparse topology | The communication graph is rewired to a ring |

### 3.5 Attacks and red team

Compromised agents hold no facts. All of them push the target $t$, using one of five attack types:
- **A1, confident assertion:** argues for $t$ without specific claims;
- **A2, fabricated evidence:** invents claims favouring $t$ and labels them first-hand;
- **A3, sleeper:** behaves honestly until an onset round, then switches to A2;
- **A4, sybil:** posts on shared media under 3 aliases;
- **A5, confidence capture:** always reports confidence 1, which targets confidence-weighted and leader-based strategies.

Attackers are placed at random, on the highest-betweenness nodes, or by red-team search. Five searchers compete at equal budget: random, greedy hub, a genetic algorithm, binary PSO and MAP-Elites. Each gets 500 twin evaluations over the genome (attacker node set, onset round, attack type). Fitness is mean contamination over 5 seeds. The best genome each searcher finds is then replayed on LLM agents to test whether it transfers.

### 3.6 Definitions and metrics

Let $\mathcal H$ be the honest agents and $\mathcal A$ the compromised ones. Write $k=|\mathcal A|$, $f=k/N$, and $c_i^{(r)}$ for agent $i$'s choice in round $r$.

- **Accuracy:** $\mathrm{Acc}=\frac1{|\mathcal H|}\sum_{i\in\mathcal H}\mathbb 1[c_i^{(R-1)}=o^\star]$.
- **Contamination:** $\mathrm{Con}=\frac1{|\mathcal H|}\sum_{i\in\mathcal H}\mathbb 1[c_i^{(R-1)}=t]$. At $f=0$, Con is the rate at which honest agents settle on $t$ unaided, which is the floor that attacks raise.
- **Spread speed $T_{50}$:** the first round at which Con reaches half its final value.
- **Deadlock:** no option holds a majority of honest agents at the end.
- **Consensus time:** the first round after which all honest agents agree.
- **Tipping point $f^\star$:** we fit $\mathrm{Con}(f)=\big(1+e^{-(f-f^\star)/s}\big)^{-1}$ by least squares. Its 10→90% transition width is $2s\ln 9$, and a transition is *sharp* if the width is $\le0.15$ inside the tested range.
- **Usefulness cost** of module $m$: $U_m=\mathrm{Acc}_m-\mathrm{Acc}_{\text{none}}$ at $f=0$.
- **Module value:** $V_m=\Delta\mathrm{Con}_m/(\max(0,-U_m)+0.01)$, the contamination removed per unit of accuracy lost.

Seeds are the unit of analysis. The same seed fixes the task, the graph and the attacker set in every arm of a comparison, so contrasts are paired. We report 95% bootstrap CIs over seeds and Holm-correct the confirmatory hypotheses H1–H10, separately for ABM and LLM evidence. The exact operational choices were fixed in code before calibrated or LLM data existed (D12).

### 3.7 Experimental protocol

Three stages, pre-registered in DESIGN.md and amended only through the logged deviations:
1. **Pilot and calibration.** Small LLM runs check output validity, refusals and oracle accuracy. $\kappa$ and $\lambda$ are then fitted by grid search, minimising squared error in Acc, Con and the per-round contamination curve, and frozen in a committed file.
2. **Stage A, the ABM screen.** Every strategy × module × topology × $f\in\{0,1/N,.05,.1,.15,.2,.3,.4\}$ × $N\in\{12,50,200\}$, with 30 seeds each, plus the red-team search.
3. **Stage B, LLM runs.** These blocks run on the slice that Stage A singles out:
   - the core: Tier-1 strategies × $f\in\{0,1/12,3/12\}$ × 3 seeds;
   - defence modules on the most and least robust strategy;
   - all attack types;
   - replay of the red team's best genomes.

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
- **One agent model.** The main LLM results use a single open-weight reasoning model (`gpt-oss-120b`). Other model families were screened out because they could not solve the full-information task (D18), so our results describe swarms of competent agents, not of frontier agents in general.
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
