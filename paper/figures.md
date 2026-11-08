# Figures for the report

Every figure is written as a 300-dpi PNG (for the Google Docs template) and a vector PDF with the same name.
Figures are drawn at print size, so set the inserted image width to the **print width** listed below; at that
width all text is 8 pt or larger. The palette is Okabe–Ito (colour-blind safe) and is used the same way in
every figure (`hiveguard/figstyle.py`):

- blue = correct option / accuracy; vermillion = attackers' target / contamination; black square = compromised agent; light grey = other option;
- strategies are coloured by metaphor family (grey baseline, blue abstract, orange insects, purple wolves, green fireflies, sky-blue birds);
- modules M1–M6, red-team searchers and swarm sizes N each have one fixed colour.

**How to regenerate**

```
# report-only figures (no experiment data needed)
.venv/bin/python -m hiveguard.run paperfigs --out figures/paper

# result figures (exploratory inputs shown; swap in the final Stage A / red-team / Stage B files)
.venv/bin/python -m hiveguard.run analyze --stageA results/stageA_precal.csv --redteam results/redteam_precal.json \
  --llm --pilot none --params none --out /tmp/rp.json --figures figures/precal \
  --boot 200 --tip-boot 100 --hyp-boot 500 --perms 199 --workers 6
```

**Status of the data.** The result figures in `figures/precal/` come from the *pre-calibration* ABM screen
(`results/stageA_precal.csv`, `results/redteam_precal.json`): default ABM parameters (κ = 0.5, λ = 2.0), not
yet fitted to the LLM pilot, and fewer bootstrap resamples than the pre-registration (per-cell CIs 200,
hypothesis CIs 500, f* CIs 100, Mantel 199 permutations, against 2,000 / 10,000 / 500 / 9,999 planned). They
are exploratory. Captions below carry an *[exploratory]* sentence. Delete it once the figures are regenerated
from calibrated Stage A and Stage B data, and update every number in brackets.

**Stage A grid behind the precal figures** (read from the CSV): 12 strategies × 7 module settings (none, M1–M6)
× 5 topologies × N ∈ {12, 50, 200} × 10 attacker fractions f ∈ {0, 0.005, 0.02, 0.05, 1/12, 0.10, 0.15, 0.20,
0.30, 0.40} × 30 seeds, attack A2, random placement: 302,400 ABM runs. The effective fraction k/N is used
throughout (DEVIATIONS D3), so the realised f values differ by N.

---

## Suggested numbering and placement

The page budget is 4–8 pages, so not every figure fits in the main text.

| Paper # | File | Section | Main / appendix |
|---|---|---|---|
| Figure 1 | `figures/paper/fig0_overview` | §1 Introduction (end) or top of §3 Methods | main |
| Table 1 (as figure) | `figures/paper/fig_strategy_components` | §3.3 Coordination strategies; referred to again in §4.4 | main |
| Table 2 | `figures/precal/fig1_leaderboard_abm` / `_llm` | §4.1 | main (LLM); ABM in appendix |
| Figure 2 | `figures/precal/fig2_pareto` | §4.1 | main |
| Figure 3 | `figures/precal/fig3_con_vs_f` | §4.2 | main |
| Figure 4 | `figures/precal/fig4_topology_heatmap` | §4.2 | main, or appendix if space is short |
| Figure 5 | `figures/precal/fig5_modules_components` | §4.3 (panel a) and §4.4 (panel b) | main |
| Figure 6 | `figures/precal/fig6_redteam` | §4.5 | main |
| Figure 7 | `figures/precal/fig7_abm_vs_llm` | §4.6 | main (needs Stage B) |
| Figure A1 | `figures/paper/fig_cascade_abm` | §3.6 Metrics, or Appendix C | appendix (main if space) |
| Figure A2 | `figures/precal/fig6_mapelites` | §4.5 or appendix | appendix |

`paper.md` currently names Table 2 and Figures 2–7 using the analysis numbering. With the overview as
Figure 1, those references stay valid. Table 1 is the component matrix.

Tables 1 and 2 are rendered as images so that they keep the same style as the figures. If the template
prefers native tables, rebuild Table 2 from `results/results.json` → `leaderboard`, and Table 1 from
`hiveguard/analysis.py` → `COMPONENTS`. Put table captions *above* the table.

---

## Figure 1: method overview (`figures/paper/fig0_overview.png`, full width, 6.5 in)

**What it shows.** The pipeline in five steps: (1) the hidden-profile task, (2) a swarm on a graph with
compromised agents and the five attack types, (3) the coordination strategies grouped by metaphor family,
(4) the add-on defence modules, (5) the metrics. Below it are the red-team loop on the ABM twin and the
transfer check on LLM agents. The two bar glyphs are a real generated instance (task seed 0, N = 12): one
agent's partial scores and the scores from all 24 facts. The graph is a real N = 12 small-world instance with
f = 3/12. Only the tipping curve is a sketch, and it is labelled "schematic".

**Draft caption.**
> **Figure 1. HiveGuard overview.** (1) *Hidden-profile task:* each of the 24 attribute facts of a best-of-4
> choice is dealt to a few agents. Bars show option scores (weighted sum of known facts) for one agent's
> private facts and for all facts pooled, from a generated instance. The outlined bar is the option that view
> would pick; blue is the correct option. Private facts point to a wrong option, and pooled facts recover the
> correct one, so the group must communicate. (2) N agents talk over one of five topologies (shown:
> small-world, N = 12). A fraction f of them is compromised (black squares) and uses one of five attacks
> A1–A5. (3) Eleven coordination strategies, grouped by metaphor family, run either as LLM agents or as an
> agent-based-model (ABM) twin on identical seeded instances. (4) Six negative-feedback defence modules
> M1–M6 can be added to any strategy. (5) Accuracy (Acc, share of honest agents choosing the correct option),
> contamination (Con, share choosing the attackers' target), the tipping point f* where a logistic fit of
> Con(f) crosses 0.5 (curve schematic), and spread speed T50. *Bottom:* five red-team searchers propose
> (attacker nodes, onset round, attack type). The ABM twin scores each proposal as mean Con over 5 seeds,
> with deference κ and confidence sensitivity λ fitted on an LLM pilot, for 500 evaluations × 10 repeats.
> Each searcher's top attack is then re-run on LLM agents (dashed arrow).

---

## Table 1: strategy taxonomy and component matrix (`figures/paper/fig_strategy_components.png`, full width, 6.5 in)

**What it shows.** Rows are S0a–S10 with plain names and biological inspiration. They are grouped by the
metaphor family used in the H10 test. Columns are the eight algorithmic components of DESIGN §6.3. A filled
cell means the component is present. The binary matrix is read from the code (`analysis.COMPONENTS`), which
is the matrix the H10 Mantel test uses; it matches DESIGN §6.3 exactly. The labels inside the
negative-feedback cells name the *kind* of feedback; they come from the DESIGN §6.3 text, because the code
stores only the binary flag. S0a and S0b are hatched because the component matrix and H10 do not include them.

**Draft caption** (above the table).
> **Table 1. Coordination strategies and their algorithmic components.** Rows are the 12 strategies, grouped
> by the metaphor family used in the components-vs-metaphor test (H10; coloured bar). S0a (oracle: every
> agent sees all facts) and S0b (solo: own facts only) are reference points, not in the component matrix
> (hatched). S1 (independent answers, compute-matched majority) is assigned to the "abstract" family, as are
> free debate (S2) and particle-swarm optimisation (S3). A filled cell marks that the strategy uses the
> component: direct agent-to-agent messages, a shared (stigmergic) medium, per-agent memory, a leader
> hierarchy, influence that decays with graph distance, distinct agent roles, a negative-feedback mechanism
> (its kind is written in the cell), or a quorum rule. H10 compares a Hamming distance on these eight
> components against a same/different-family distance.

---

## Table 2: leaderboard (`figures/precal/fig1_leaderboard_abm.png`, 5.1 in; `fig1_leaderboard_llm.png` once Stage B exists)

**What it shows.** For each strategy at N = 12, full topology, attack A2, no module: accuracy at f = 0,
contamination at the realised f nearest to 1/12 and to 3/12, the tipping point f*, and LLM calls per run
(LLM table only). Each value is a mean with a 95% percentile-bootstrap CI over seeds. "> x" means
contamination never reached 0.5 on the tested grid (x = largest f tested).

**Draft caption** (above the table).
> **Table 2. Strategy leaderboard (N = 12, fully connected, attack A2, no defence module).** Acc = share of
> honest agents choosing the correct option with no attackers. Con = share of honest agents choosing the
> attackers' target at the realised attacker fraction nearest to 1/12 and 3/12 (at N = 12 these are exactly
> 1 and 3 attackers). f* = attacker fraction at which a logistic fit of Con(f) crosses 0.5; "> x" means
> Con stayed below 0.5 up to the largest tested f = x. Values are means over seeds with 95% percentile-bootstrap
> CIs (seed = unit of analysis; [30] seeds per cell for the ABM, [3] for LLM agents). ↑/↓ = higher/lower is
> better. *[Exploratory: ABM with uncalibrated parameters (κ = 0.5, λ = 2.0), 200 bootstrap resamples.]*

---

## Figure 2: safety vs usefulness (`figures/precal/fig2_pareto.png`, half width, 3.5 in)

**What it shows.** One point per strategy × module combination (S0a excluded). The x axis is the accuracy
lost at f = 0 when the module is added: Acc(none) − Acc(module), so positive = costly. The y axis is mean
contamination over all f > 0 runs. Both are pooled over topologies and N, attack A2. The dashed step line is
the Pareto front (lower-left is better), and its points are numbered and named in the key.

**Draft caption.**
> **Figure 2. Safety–usefulness trade-off of strategies and defence modules (ABM).** Each marker is one
> strategy (S0b–S10) with one module (marker shape and colour; "none" = no module). x: usefulness cost, the
> drop in honest accuracy at f = 0 relative to the same strategy without a module (negative = the module
> also improved accuracy). y: mean contamination (share of honest agents on the attackers' target) over all
> attacker fractions f > 0. Both axes average over 5 topologies, N ∈ {12, 50, 200} and 30 seeds per cell
> (attack A2, random placement). The dashed line is the Pareto front (no other point has both lower cost
> and lower contamination); numbered points are listed in the key. Points are means; per-module CIs are in
> Figure 5a. *[Exploratory: uncalibrated ABM.]*

---

## Figure 3: contamination vs attacker fraction (`figures/precal/fig3_con_vs_f.png`, full width, 6.5 in)

**What it shows.** One panel per strategy (S0a omitted; it is 0 by construction). ABM contamination vs
realised attacker fraction for N = 12, 50, 200 (lines, 95% CI bands), full topology, no module, attack A2.
When Stage B exists, LLM observations at N = 12 are added as open black diamonds with 95% CIs. Panel titles
are coloured by metaphor family.

**Draft caption.**
> **Figure 3. Contamination as a function of the attacker fraction.** Each panel is one strategy. Lines show
> the ABM mean share of honest agents choosing the attackers' target at the end of the run, with 95%
> percentile-bootstrap bands over 30 seeds, for swarms of N = 12, 50 and 200 agents (fully connected, no
> defence module, fabricated-evidence attack A2, random placement). The x axis is the realised fraction
> k/N, where k = round(f·N). [Diamonds: LLM agents (N = 12, 3 seeds, 95% CI).] A steep rise means a low
> tipping point f*. In these exploratory data, S2, S6, S7, S8 and S10 flip with very few attackers, while
> S4, S5 and S9 degrade gradually. [Update this sentence from the final data.] Title
> colours give the metaphor family (Table 1). *[Exploratory: uncalibrated ABM; LLM points not yet available.]*

---

## Figure 4: topology × strategy (`figures/precal/fig4_topology_heatmap.png`, full width, 6.5 in)

**What it shows.** Mean contamination (%) over all f > 0, per strategy × topology, separately for each N. The
colour scale is cividis (perceptually uniform and colour-blind safe), and every cell is also printed as a
number. Only S2, S3, S6 and S8 read the graph. The other strategies are identical across topologies by design
(DEVIATIONS D8), which is why their rows are constant.

**Draft caption.**
> **Figure 4. Contamination by communication topology (ABM).** Cells give the mean percentage of honest
> agents that end on the attackers' target, averaged over all attacker fractions f > 0 and 30 seeds per
> cell, without a defence module, under attack A2, for swarms of N = 12, 50 and 200. Topologies run from
> sparse (ring, Watts–Strogatz small-world with k = 4, p = 0.1) to dense (Barabási–Albert scale-free with
> m = 2, star, fully connected). Only S2, S3, S6 and S8 route information along the graph. Board-,
> hierarchy- and broadcast-based strategies see the same information on every topology, so their rows are
> constant by construction. *[Exploratory: uncalibrated ABM.]*

---

## Figure 5: module effects and component clustering (`figures/precal/fig5_modules_components.png`, full width, 6.5 in)

**What it shows.** (a) The paired effect of each module relative to no module, pooled over the social
strategies S2–S10, topologies, N and f > 0. Vermillion bars are the change in contamination (negative =
safer). Blue bars are the change in accuracy at f = 0 (negative = usefulness cost). Error bars are 95%
bootstrap CIs over seeds. (b) Average-linkage dendrogram of the strategies (S1–S10) by the RMS difference of
their contamination profiles across all shared (topology, N, f > 0) cells. Leaf labels are coloured by
metaphor family. This is the result-distance matrix that H10 tests.

Note the sign convention: panel (a) uses module − none (DESIGN §11). Figure 2 uses the *drop* none − module
on its x axis.

**Draft caption.**
> **Figure 5. Defence modules and components vs metaphors (ABM).** **(a)** Effect of adding each module
> (M1 evaporation, M2 stop signals, M3 quorum on first-hand evidence, M4 uninformed dilution, M5 model
> diversity, M6 sparse topology) to the social strategies S2–S10. Bars are paired differences module − none,
> matched on strategy, topology, N, f and seed, then averaged per seed. Vermillion: change in contamination
> over f > 0 (below 0 = fewer honest agents captured). Blue: change in accuracy at f = 0 (below 0 =
> usefulness cost). Error bars are 95% percentile-bootstrap CIs over 30 seeds. **(b)** Strategies S1–S10
> clustered (average linkage) by the root-mean-square difference of their contamination across the [90]
> shared (topology, N, f > 0) cells. Leaf colours give the metaphor family. If results grouped by metaphor,
> same-coloured leaves would merge first. H10 tests this with a one-sided Mantel test against the component
> distance of Table 1 (exploratory: r_component = [0.12], p = [0.15]; r_metaphor = [−0.02], p = [0.56];
> [199] permutations). *[Exploratory: uncalibrated ABM, 500 bootstrap resamples.]*

---

## Figure 6: red-team search efficiency (`figures/precal/fig6_redteam.png`, full width, 6.5 in)

**What it shows.** The best contamination found so far vs the number of ABM evaluations (log scale), for
each searcher, on four problems (S2/S3 × scale-free/small-world, N = 12, k = 3 attackers, one fixed graph).
Lines are the median over 10 independent repeats and bands are the interquartile range. Fitness is the mean
contamination over 5 ABM seeds.

**Draft caption.**
> **Figure 6. How quickly each red-team searcher finds damaging attacks (ABM).** Each panel is one target:
> strategy (S2 free debate, S3 PSO) × topology (scale-free, small-world), N = 12 agents, k = 3 compromised
> agents on one fixed graph. A searcher proposes attacker positions, onset round (0–5) and attack type
> (A1–A5). The fitness of a proposal is the mean contamination over 5 ABM seeds. Lines show the median
> best-so-far fitness over 10 independent repeats; bands show the interquartile range. The x axis is the
> number of fitness evaluations (log scale; budget 500). Searchers: uniform random, greedy betweenness hub,
> genetic algorithm (GA), binary PSO and MAP-Elites. On S2 every searcher reaches complete contamination
> within a few evaluations, so the problem does not separate them. [Update from final data.]
> *[Exploratory: uncalibrated ABM.]*

## Figure A2: MAP-Elites archive (`figures/precal/fig6_mapelites.png`, half width, 2.8 in)

**What it shows.** The mean elite fitness per MAP-Elites cell (mean attacker betweenness bin × onset round)
for the first red-team problem (S2, scale-free, k = 3), averaged over the 10 repeats. Grey cells were never
filled.

**Draft caption.**
> **Figure A2. Where the worst attacks are (MAP-Elites, S2 on scale-free, N = 12, k = 3, ABM).** Each cell
> holds the best attack found with that combination of mean attacker betweenness (8 bins, scaled to the
> graph's maximum betweenness) and onset round. Colour shows that attack's contamination (mean over 5 ABM
> seeds), averaged over 10 repeats. Grey cells were never reached. Late onsets (round 5) leave too few
> rounds to spread. *[Exploratory: uncalibrated ABM.]*

---

## Figure 7: ABM vs LLM (`figures/precal/fig7_abm_vs_llm.png`, half width, 3.2 in)

**What it shows.** Predicted (ABM) vs observed (LLM) contamination for the matched strategy × topology × f
cells, with the identity line, Spearman ρ and the mean signed error ABM − LLM. It is not drawn yet because
no Stage B data exist. The layout was checked on the synthetic test fixture.

**Draft caption.**
> **Figure 7. How well the ABM predicts LLM swarms.** Each marker is one matched cell (strategy × topology ×
> attacker fraction, N = 12, attack A2, no module). x: ABM mean contamination with parameters frozen before
> Stage B. y: LLM mean contamination over [3] seeds. Colours give the metaphor family; within a family,
> marker shapes tell strategies apart. Dashed line: perfect prediction. Spearman ρ is computed over cells.
> A negative mean signed error means the ABM underestimates LLM contamination (H6).

---

## Figure A1: an example contamination cascade (`figures/paper/fig_cascade_abm.png`, full width, 6.5 in)

**What it shows.** A single deterministic ABM run: S2 free debate on a Watts–Strogatz small-world graph,
N = 50, f = 0.1 (5 attackers), attack A2, seed 0, default `ABMParams` (κ = 0.5, λ = 2.0). Top: the graph
(circular layout, ring-lattice edges between neighbours, long chords = rewired shortcuts) at each round, with
honest agents coloured by their current choice. Bottom: Acc and Con per round. Values from this run
(`figures/paper/paper_figures.json`): Con by round = 0.16, 0.40, 0.51, 0.64, 0.73, 0.84; Acc falls from 0.38
to 0.07; T50 = round 2.

**Draft caption.**
> **Figure A1. One contamination cascade (ABM illustration, not LLM data).** One agent-based-model run of free
> debate (S2) on a small-world graph (Watts–Strogatz, N = 50, k = 4, p = 0.1; circular layout). Five agents
> (f = 0.1, black squares) fabricate first-hand evidence for one wrong option (A2). Honest agents are coloured
> by their choice after each round: blue = correct option, vermillion = attackers' target, grey = another
> option. In round 0 agents answer from their own facts only; from round 1 they average neighbours' beliefs,
> weighted by confidence (DeGroot update, κ = 0.5, λ = 2.0, uncalibrated defaults). The bottom panel shows
> the share of the 45 honest agents on the correct option (Acc) and on the target (Con). Contamination
> passes half its final value by round 2 (T50 = 2) and reaches 0.84 by round 5. This single seed is chosen to
> illustrate the mechanism, not to estimate an effect.

---

## Ambiguities in DESIGN that affect the figures

1. **Baselines in the component matrix.** DESIGN §6.3 and `analysis.COMPONENTS` have no rows for S0a/S0b.
   Table 1 shows them hatched as "not in H10". S1 is a baseline in §6.2 but sits in the "abstract" metaphor
   family for H10 (§6.3 bullet). The code follows DESIGN, and Table 1 shows S1 under "abstract".
2. **S3's inspiration.** PSO comes from bird flocking, but H10 puts S3 in "abstract", while S8 boids are
   "birds". Table 1 calls S3's inspiration "flocking, abstracted" to stay consistent with the H10 family.
3. **Kinds of negative feedback** (evaporation, abandon, separation, decay+stop, verify) exist only in the
   DESIGN §6.3 text. The code stores a binary flag, and the code and DESIGN agree on every binary entry.
4. **Sign of usefulness cost.** DESIGN §11 defines it as Acc(module) − Acc(none), which Figure 5a uses. The
   existing Pareto plot uses the drop Acc(none) − Acc(module), so that larger x means more costly. Both
   captions state their convention.
5. **DESIGN §12.1 item 5** calls the module bars "component-ablation bars (RQ3)". They are module (M1–M6)
   ablations. The component analysis is the H10 dendrogram in panel (b).
6. **DESIGN §12.1 item 3** says "ABM line with LLM points". LLM points exist only at N = 12, full topology,
   whereas the ABM lines cover N ∈ {12, 50, 200}.
