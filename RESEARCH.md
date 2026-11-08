# HiveGuard: research notes

Literature for HiveGuard, a safety benchmark of swarm-intelligence coordination algorithms for LLM agent swarms, built for the Apart × AIAF Swarm Alignment Hackathon (Nov 6–8, 2026).

The notes are written before the sprint and contain no code. Every link was checked on 2026-11-01: arXiv IDs against the arXiv API (title match) and DOIs against Crossref (title match). Each entry gives the source, **what we learn**, and **how HiveGuard uses it**.

Contents
- [A. Swarm-intelligence algorithms in the zoo](#a-swarm-intelligence-algorithms-in-the-zoo)
- [B. Critiques: metaphor vs. mechanism](#b-critiques-metaphor-vs-mechanism)
- [C. Collective decision-making in animals and networks](#c-collective-decision-making-in-animals-and-networks)
- [D. Swarm-robotics dependability and security](#d-swarm-robotics-dependability-and-security)
- [E. LLMs meet swarm intelligence](#e-llms-meet-swarm-intelligence)
- [F. Multi-agent LLM baselines and social behaviour](#f-multi-agent-llm-baselines-and-social-behaviour)
- [G. Multi-agent AI safety](#g-multi-agent-ai-safety)
- [H. Alignment, control and cooperative AI](#h-alignment-control-and-cooperative-ai)
- [I. Incident sources and datasets](#i-incident-sources-and-datasets)
- [Synthesis: what this means for HiveGuard](#synthesis-what-this-means-for-hiveguard)

---

## A. Swarm-intelligence algorithms in the zoo

**A1. Flocks, herds and schools: a distributed behavioral model.** Reynolds, SIGGRAPH 1987. [doi:10.1145/37402.37406](https://doi.org/10.1145/37402.37406)
- Learn: three local rules (separation, alignment, cohesion) produce realistic flocking. No leader and no global view are needed.
- Use: strategy **S8 (Boids opinion dynamics)**. Alignment means moving toward the neighbours' answer. Cohesion means staying near the local mean confidence. *Separation* keeps a minority alternative alive, which works against groupthink.

**A2. Ant system: optimization by a colony of cooperating agents.** Dorigo, Maniezzo & Colorni, IEEE TSMC-B 1996. [doi:10.1109/3477.484436](https://doi.org/10.1109/3477.484436)
- Learn: ants choose a path with probability ∝ τ^α·η^β (pheromone × heuristic). Good paths get reinforced, and **evaporation** stops the colony locking in early. Positive feedback alone gets stuck.
- Use: strategy **S4 (ACO stigmergy)**. Shared-board claims are sampled ∝ pheromone^α, endorsements deposit pheromone, and posts evaporate at rate ρ. **Evaporation is also a stand-alone defence module.**

**A3. Particle swarm optimization.** Kennedy & Eberhart, ICNN 1995. [doi:10.1109/ICNN.1995.488968](https://doi.org/10.1109/ICNN.1995.488968)
- Learn: each particle's velocity mixes inertia, a pull to its *personal best*, and a pull to the *swarm/neighbourhood best*.
- Use: strategy **S3 (PSO)**. An agent keeps a personal-best answer with its reason and sees the neighbourhood-best answer. The inertia/cognitive/social weights become prompt weights, and in the ABM twin they are explicit coefficients.

**A4. Population structure and particle swarm performance.** Kennedy & Mendes, CEC 2002. [doi:10.1109/CEC.2002.1004493](https://doi.org/10.1109/CEC.2002.1004493)
- Learn: the communication topology (gbest/fully connected, lbest/ring, von Neumann…) changes swarm performance. Densely connected swarms spread information fastest and are more prone to premature convergence. Sparse ones are slower but more robust.
- Use: the main prediction behind **H1**. gbest/star should spread a compromised agent's claim faster than lbest/ring. Topology is a first-class experimental factor.

**A5. A discrete binary version of the particle swarm algorithm.** Kennedy & Eberhart, IEEE SMC 1997. [doi:10.1109/ICSMC.1997.637339](https://doi.org/10.1109/ICSMC.1997.637339)
- Learn: in binary PSO, velocity sets the probability that a bit is 1, so PSO can search discrete spaces.
- Use: red-team **searcher (binary PSO)** over attacker-placement bitmasks (which nodes are compromised).

**A6. A powerful and efficient algorithm for numerical function optimization: artificial bee colony (ABC).** Karaboga & Basturk, J. Global Optimization 2007. [doi:10.1007/s10898-007-9149-x](https://doi.org/10.1007/s10898-007-9149-x)
- Learn: there are three roles. *Employed* bees work a food source. *Onlookers* pick sources ∝ advertised quality. *Scouts* abandon a source that has not improved after `limit` trials and search at random.
- Use: strategy **S5 (ABC)**. Scouts drop stale consensus claims and re-derive from raw evidence, which acts as a built-in escape from capture.

**A7. Firefly algorithms for multimodal optimization.** Yang, SAGA 2009. [arXiv:1003.1466](https://arxiv.org/abs/1003.1466)
- Learn: fireflies move toward brighter ones. Attractiveness decays with distance as e^(−γr²), so the swarm splits into sub-swarms around several optima.
- Use: strategy **S6 (Firefly)**. Pull toward an answer ∝ brightness (evidence score) × e^(−γ·graph distance). Distance decay should limit how far a single liar's influence reaches.

**A8. Grey Wolf Optimizer.** Mirjalili, Mirjalili & Lewis, Advances in Engineering Software 2014. [doi:10.1016/j.advengsoft.2013.12.007](https://doi.org/10.1016/j.advengsoft.2013.12.007)
- Learn: there is a leadership hierarchy (alpha, beta, delta, omega), and omegas update toward the mean of the three leaders.
- Use: strategy **S7 (GWO hierarchy)**. It models the incident's "one agent coordinating hundreds". **H8**: hierarchy converges fastest but breaks under *leader capture* (attack A5). See critique B2.

**A9. Quantitative study of the fixed threshold model for the regulation of division of labour in insect societies.** Bonabeau, Theraulaz & Deneubourg, Proc. R. Soc. B 1996. [doi:10.1098/rspb.1996.0229](https://doi.org/10.1098/rspb.1996.0229)
- Learn: each individual takes a task with probability s²/(s²+θ²), where s is the stimulus and θ the individual's threshold. Division of labour emerges from the spread of thresholds, and when one worker class is removed, others take over.
- Use: strategy **S10 (response-threshold division of labour)**. The proposer/verifier role is chosen by threshold. This also bears on the Track 2 question of how roles emerge.

**A10. A brief history of stigmergy.** Theraulaz & Bonabeau, Artificial Life 1999. [doi:10.1162/106454699568700](https://doi.org/10.1162/106454699568700)
- Learn: Grassé (1959) coined *stigmergy* for termites coordinating through the traces their work leaves in the environment, not through direct signals.
- Use: frames the Hugging Face incident as **stigmergic coordination**: a shared directory became the trace medium. HiveGuard's shared board is the controlled version of that medium.

**A11. Stigmergy as a universal coordination mechanism I: definition and components.** Heylighen, Cognitive Systems Research 2016. [doi:10.1016/j.cogsys.2015.12.002](https://doi.org/10.1016/j.cogsys.2015.12.002)
- Learn: stigmergy is action → trace in a medium → trace stimulates further action. Components: agent, action, medium, trace, and condition→action rules. It scales because agents need no model of each other.
- Use: the vocabulary for the board design (medium, trace, decay) and for the logged fields, so that read/write traces can later be audited.

**A12. Genetic algorithms.** Holland, Scientific American 1992. [doi:10.1038/scientificamerican0792-66](https://doi.org/10.1038/scientificamerican0792-66)
- Learn: evolve a population of candidate solutions by selection, crossover and mutation.
- Use: red-team **searcher (GA)** over attack configurations (placement, onset round, attack type).

**A13. Illuminating search spaces by mapping elites (MAP-Elites).** Mouret & Clune, 2015. [arXiv:1504.04909](https://arxiv.org/abs/1504.04909)
- Learn: keep the best solution in each cell of a grid of behaviour descriptors. The output is a *map* of diverse, high-performing solutions, not one optimum.
- Use: red-team **searcher (MAP-Elites)** over (attacker centrality × onset round). It shows *where* in attack space each defence fails, not only the worst single attack.

**A14. Abandoning objectives: evolution through the search for novelty alone.** Lehman & Stanley, Evolutionary Computation 2011. [doi:10.1162/EVCO_a_00025](https://doi.org/10.1162/EVCO_a_00025)
- Learn: rewarding novel behaviour instead of the objective can escape deceptive search landscapes.
- Use: a possible novelty bonus in the red-team search, so searchers don't all converge on the "compromise the hub" attack.

**A15. Swarm Intelligence: From Natural to Artificial Systems.** Bonabeau, Dorigo & Theraulaz, Oxford UP 1999. [doi:10.1093/oso/9780195131581.001.0001](https://doi.org/10.1093/oso/9780195131581.001.0001)
- Learn: the founding synthesis. Self-organization rests on positive feedback, negative feedback, randomness and multiple interactions.
- Use: the checklist for each zoo strategy: where is its positive feedback, and where is its negative feedback? **Negative feedback** (evaporation, stop signals, scouts) is what the defences add.

## B. Critiques: metaphor vs. mechanism

**B1. Metaheuristics: the metaphor exposed.** Sörensen, ITOR 2015 (online 2013). [doi:10.1111/itor.12001](https://doi.org/10.1111/itor.12001)
- Learn: the flood of "novel" animal-metaphor algorithms often hides old ideas under new vocabulary. Algorithms should be described and compared by their **components**.
- Use: the motivation for HiveGuard's **component ablation**. We tag each strategy by component (hierarchy, stigmergy, inhibition, quorum, distance decay, role switching) and test **H10**: results group by component, not by animal.

**B2. Exposing the grey wolf, moth-flame, whale, firefly, bat, and antlion algorithms: six misleading optimization techniques inspired by bestial metaphors.** Camacho-Villalón, Dorigo & Stützle, ITOR 2023 (online 2022). [doi:10.1111/itor.13176](https://doi.org/10.1111/itor.13176)
- Learn: GWO, firefly, bat and the others reuse PSO concepts, and antlion reuses evolution-strategy concepts. The metaphors are misleading as a design source.
- Use: we **expect** GWO and Firefly to behave like PSO variants once their components are matched. That is a falsifiable prediction and makes for an honest report. Judges in the field will know this critique, so we cite it up front.

**B3. No free lunch theorems for optimization.** Wolpert & Macready, IEEE TEC 1997. [doi:10.1109/4235.585893](https://doi.org/10.1109/4235.585893)
- Learn: averaged over all problems, no optimizer beats another, so claims must be tied to a problem class.
- Use: the claims are scoped to *our* task family (hidden-profile best-of-n with compromised agents). There is no "best swarm algorithm overall" claim.

## C. Collective decision-making in animals and networks

**C1. Effective leadership and decision-making in animal groups on the move.** Couzin, Krause, Franks & Levin, Nature 2005. [doi:10.1038/nature03236](https://doi.org/10.1038/nature03236)
- Learn: a small informed minority can steer a large group accurately, and the larger the group, the smaller the informed fraction needed. Nobody needs to know who is informed.
- Use: this cuts both ways. A small *compromised* minority might steer an LLM swarm the same way, which motivates the critical-mass sweep over `f` (**H2**).

**C2. Uninformed individuals promote democratic consensus in animal groups.** Couzin et al., Science 2011. [doi:10.1126/science.1210280](https://doi.org/10.1126/science.1210280)
- Learn: a strongly opinionated minority can dictate a group's choice. Adding *uninformed* individuals hands control back to the numerical majority, though too many add noise.
- Use: the **dilution defence** (adds naive agents with no private evidence). **H5**: this helps LLM swarms less, because LLMs defer to confident messages (see F4, F5). Compare G9, which finds debate "looks robust" partly because uninformed agents outnumber misinformed ones.

**C3. Stop signals provide cross inhibition in collective decision-making by honeybee swarms.** Seeley, Visscher, Schlegel, Hogan, Franks & Marshall, Science 2012 (online Dec 2011). [doi:10.1126/science.1210361](https://doi.org/10.1126/science.1210361)
- Learn: scouts committed to one nest site head-butt dancers who advertise rival sites. This *cross-inhibition* breaks deadlock between near-equal options and speeds an accurate choice.
- Use: the **stop-signal defence** and part of strategy **S9**. An agent holding contradicting first-hand evidence can STOP a claim, and claims that collect stops are down-weighted. **H4**: this reduces deadlock and contamination.

**C4. Quorum sensing during nest-site selection by honeybee swarms.** Seeley & Visscher, Behav. Ecol. Sociobiol. 2004. [doi:10.1007/s00265-004-0814-5](https://doi.org/10.1007/s00265-004-0814-5)
- Learn: the swarm commits once a *quorum* of scouts is present at one site, not when every scout agrees. This trades speed against accuracy.
- Use: the **quorum defence** and the commit rule in **S9**. An agent adopts a claim only after `q` *independent first-hand* corroborations. A repost does not count, which separates quorum from popularity.

**C5. Quorum sensing, recruitment, and collective decision-making during colony emigration by the ant *Leptothorax albipennis*.** Pratt, Mallon, Sumpter & Franks, Behav. Ecol. Sociobiol. 2002. [doi:10.1007/s00265-002-0487-x](https://doi.org/10.1007/s00265-002-0487-x)
- Learn: reaching a quorum threshold switches ants from slow tandem runs to fast transport. The threshold sets the speed–accuracy trade-off.
- Use: the quorum size `q` is a swept parameter, and the report shows the speed–accuracy–safety trade-off curve.

**C6. The best-of-n problem in robot swarms: formalization, state of the art, and novel perspectives.** Valentini, Ferrante & Dorigo, Frontiers in Robotics and AI 2017. [doi:10.3389/frobt.2017.00009](https://doi.org/10.3389/frobt.2017.00009)
- Learn: a formal framework for collective choice among `n` options with differing quality and cost. Standard decision rules include voter, majority and cross-inhibition.
- Use: HiveGuard's task **is** a best-of-n problem, and the ABM twins reuse the classic voter, majority and cross-inhibition rules.

**C7. Experimental evidence for tipping points in social convention.** Centola, Becker, Brackbill & Baronchelli, Science 2018. [doi:10.1126/science.aas8827](https://doi.org/10.1126/science.aas8827)
- Learn: in human experiments, a committed minority of about 25% overturned an established convention.
- Use: the human reference point for the tipping fraction `f*` (**H2**). We fit `f*` per strategy and compare.

**C8. Social consensus through the influence of committed minorities.** Xie et al., Phys. Rev. E 2011. [doi:10.1103/PhysRevE.84.011130](https://doi.org/10.1103/PhysRevE.84.011130)
- Learn: in the binary-agreement model, a committed minority of about 10% flips the majority quickly.
- Use: the theoretical reference point for `f*`, together with C7.

**C9. Epidemic spreading in scale-free networks.** Pastor-Satorras & Vespignani, Phys. Rev. Lett. 2001. [doi:10.1103/PhysRevLett.86.3200](https://doi.org/10.1103/PhysRevLett.86.3200)
- Learn: in scale-free networks the epidemic threshold vanishes as networks grow large, so hubs let contagion persist.
- Use: predicts that **scale-free topologies plus hub placement** are worst-case. The *greedy hub* red-team baseline comes from this.

**C10. Collective dynamics of 'small-world' networks.** Watts & Strogatz, Nature 1998. [doi:10.1038/30918](https://doi.org/10.1038/30918)
- Learn: rewiring a few ring edges sharply shortens path lengths while keeping clustering high.
- Use: the small-world topology generator, which sits between ring/lbest and full/gbest.

**C11. Emergence of scaling in random networks.** Barabási & Albert, Science 1999. [doi:10.1126/science.286.5439.509](https://doi.org/10.1126/science.286.5439.509)
- Learn: growth plus preferential attachment produces scale-free networks with hubs.
- Use: the scale-free topology generator.

**C12. A theory of fads, fashion, custom, and cultural change as informational cascades.** Bikhchandani, Hirshleifer & Welch, J. Political Economy 1992. [doi:10.1086/261849](https://doi.org/10.1086/261849)
- Learn: rational agents can ignore their private signal and copy predecessors. The resulting cascades are fragile and can lock onto the wrong answer.
- Use: explains why an early confident liar can win (the *onset round* matters), and motivates the sleeper attack A3, which times its push late.

**C13. Pooling of unshared information in group decision making: biased information sampling during discussion.** Stasser & Titus, JPSP 1985. [doi:10.1037/0022-3514.48.6.1467](https://doi.org/10.1037/0022-3514.48.6.1467)
- Learn: in a *hidden profile*, groups discuss shared information more than unshared information and miss the best option.
- Use: the **task design**. Facts are split across agents so that pooling is required. This makes communication *useful*, which is what makes compromise costly. It also controls for the model's prior knowledge, since the items are fictional.

**C14. Reciprocal food sharing in the vampire bat.** Wilkinson, Nature 1984. [doi:10.1038/308181a0](https://doi.org/10.1038/308181a0)
- Learn: vampire bats regurgitate blood meals to roost-mates that failed to feed, and donations go preferentially to individuals that have shared before: help is conditioned on a remembered history with each partner.
- Use: the inspiration for the exploratory strategy **S11** (reciprocity / reputation, DEVIATIONS D22): per-neighbour trust built from past exchanges. Added post hoc on 2026-11-09; DOI checked against Crossref (title and author match).

**C15. Food sharing in vampire bats: reciprocal help predicts donations more than relatedness or harassment.** Carter & Wilkinson, Proc. R. Soc. B 2013. [doi:10.1098/rspb.2012.2573](https://doi.org/10.1098/rspb.2012.2573)
- Learn: in a captive colony, how much a bat had received from a partner predicted how much it donated to that partner better than kinship did.
- Use: supports modelling S11's influence weights as a function of each partner's track record rather than a fixed rank. Added post hoc on 2026-11-09; DOI checked against Crossref (title and authors match).

## D. Swarm-robotics dependability and security

**D1. Towards dependable swarms and a new discipline of swarm engineering.** Winfield, Harper & Nembrini, SR 2004 / LNCS 3342, 2005. [doi:10.1007/978-3-540-30552-1_11](https://doi.org/10.1007/978-3-540-30552-1_11)
- Learn: proposes *swarm engineering*, a fusion of dependable-systems engineering with swarm intelligence. Emergent behaviour makes swarms hard to assure.
- Use: the framing for the Track 1 and 2 claim that alignment of swarms needs swarm-level assurance, not only safe individual agents.

**D2. Survey on security challenges for swarm robotics.** Higgins, Tomlinson & Martin, ICAS 2009. [doi:10.1109/ICAS.2009.62](https://doi.org/10.1109/ICAS.2009.62)
- Learn: catalogues threats specific to swarms: identity and authentication, intrusion, and compromised members that exploit the simplicity of the robots.
- Use: the threat-model vocabulary for attacks A1–A5. The sybil attack (A4) comes from the identity problem.

**D3. Managing Byzantine robots via blockchain technology in a swarm robotics collective decision making scenario.** Strobel, Castelló Ferrer & Dorigo, AAMAS 2018. [doi:10.5555/3237383.3237464](https://dl.acm.org/doi/10.5555/3237383.3237464) · [PDF](https://ifaamas.csc.liv.ac.uk/Proceedings/aamas2018/pdfs/p541.pdf)
- Learn: in a best-of-2 decision, classical voter/majority swarms fail when Byzantine robots are present, while smart-contract coordination detects and excludes them.
- Use: the closest prior work in *robot* swarms. The result to replicate in LLM swarms is that classical decision rules break under Byzantine members. A ledger-like *source-attributed board* (quorum on first-hand evidence) is our lightweight analogue.

**D4. Swarm robotics: a review from the swarm engineering perspective.** Brambilla, Ferrante, Birattari & Dorigo, Swarm Intelligence 2013. [doi:10.1007/s11721-012-0075-2](https://doi.org/10.1007/s11721-012-0075-2)
- Learn: reviews design methods (behaviour-based and automatic), modelling (micro and macro) and verification for swarms.
- Use: justifies pairing the **micro** model (LLM agents) with a **macro/ABM** model, and checking where they agree (Track 1, the "cheap proxy").

## E. LLMs meet swarm intelligence

**E1. Model Swarms: collaborative search to adapt LLM experts via swarm intelligence.** Feng et al., ICML 2025. [arXiv:2410.11163](https://arxiv.org/abs/2410.11163)
- Learn: PSO in *weight space*. LLM experts are particles pulled by personal, global-best and global-worst checkpoints. It beats 12 composition baselines and needs no fine-tuning data.
- Use: shows PSO concepts carry over to LLMs. HiveGuard applies PSO at the *message/belief* level instead of weights, and asks a safety question rather than a capability one.

**E2. Benchmarking LLMs' swarm intelligence (SwarmBench).** Ruan et al., 2025. [arXiv:2505.04364](https://arxiv.org/abs/2505.04364)
- Learn: five decentralized tasks (pursuit, synchronization, foraging, flocking, transport) where agents have only a k×k local view and local messages. Decentralized coordination under local perception is still hard for LLMs.
- Use: the closest capability benchmark. HiveGuard complements it on the **safety** side.

**E3. LLM-powered swarms: a new frontier or a conceptual stretch?** Rahman et al., 2025. [arXiv:2506.14496](https://arxiv.org/abs/2506.14496)
- Learn: reimplements Boids and ACO with LLM agents (OpenAI Swarm). They can mimic swarm dynamics, but LLM Boids took about 300× the compute time of the classical version.
- Use: confirms the cost problem, which is why the ABM screens the full grid first (Stage A) and LLMs run only an informative slice (Stage B).

**E4. Multi-agent systems powered by large language models: applications in swarm intelligence.** Jimenez-Romero et al., 2025. [arXiv:2503.03800](https://arxiv.org/abs/2503.03800)
- Learn: replaces the hard-coded NetLogo agents in ant foraging and bird flocking with GPT-4o prompts. Both rule-based and free-form prompts induce emergent swarm behaviour.
- Use: precedent for driving classic swarm rules through prompts. Our prompt templates follow its rule-based style, so each strategy's update rule stays explicit.

**E5. LLM2Swarm: robot swarms that responsively reason, plan, and collaborate through LLMs.** Strobel et al., 2024. [arXiv:2410.11387](https://arxiv.org/abs/2410.11387)
- Learn: two ways to add LLMs to robot swarms: synthesizing controllers, or a per-robot LLM in the loop. It comes from the same group as D3 (Byzantine robots).
- Use: links robot-swarm security work to LLM swarms. Per-agent LLMs in the loop is HiveGuard's setting.

**E6. Language agents as optimizable graphs (GPTSwarm).** Zhuge et al., ICML 2024. [arXiv:2402.16823](https://arxiv.org/abs/2402.16823)
- Learn: treats an agent system as a computational graph and optimizes the nodes (prompts) and edges (who talks to whom).
- Use: topology is a design variable. Our topologies are fixed and swept rather than optimized, and the red team optimizes *attacks* over them.

**E7. Scaling large language model-based multi-agent collaboration (MacNet).** Qian et al., 2024. [arXiv:2406.07155](https://arxiv.org/abs/2406.07155)
- Learn: DAG-organized collaboration among more than 1,000 agents. Irregular topologies beat regular ones, and performance follows a *logistic* "collaborative scaling law".
- Use: a reason to include irregular topologies (small-world, scale-free) and to expect nonlinear effects with `N`.

**E8. SwarmWorld: stigmergic technological evolution in societies of language-model agents.** Pal et al., 2026. [arXiv:2608.26081](https://arxiv.org/abs/2608.26081)
- Learn: homogeneous LLM agents in a shared spatial world self-organize through persistent artifacts (stigmergy) into "technological societies". The study isolates communication, inheritance and physical stigmergy.
- Use: recent evidence that LLM agents *do* coordinate stigmergically, as in the incident's shared directory. It supports including the ACO board strategy.

**E9. Emergent social conventions and collective bias in LLM populations.** Ashery, Aiello & Baronchelli, Science Advances 2025. [doi:10.1126/sciadv.adu9368](https://doi.org/10.1126/sciadv.adu9368) · [arXiv:2410.08948](https://arxiv.org/abs/2410.08948)
- Learn: LLM populations playing the naming game form conventions on their own, show *collective* biases that no single agent has, and can be tipped by small committed minorities. The critical mass varies by model.
- Use: the direct LLM precedent for **H2**, and a reason to test **mixed-model** swarms. `f*` should differ across model families.

**E10. Towards a science of collective AI.** Fan et al., 2026. [arXiv:2602.05289](https://arxiv.org/abs/2602.05289)
- Learn: argues that LLM multi-agent research is trial and error. It proposes a *collaboration gain* metric (Γ) to separate real collaboration from extra compute.
- Use: we report each strategy against **compute-matched** baselines (S1, majority of N independent samples, at equal call count) so that gains are not just more calls.

## F. Multi-agent LLM baselines and social behaviour

**F1. Self-consistency improves chain of thought reasoning in language models.** Wang et al., ICLR 2023. [arXiv:2203.11171](https://arxiv.org/abs/2203.11171)
- Learn: sampling many reasoning paths and taking the majority answer beats a single path.
- Use: baseline **S1** (independent agents with majority vote, no communication), the compute-matched control.

**F2. Improving factuality and reasoning in language models through multiagent debate.** Du et al., ICML 2024. [arXiv:2305.14325](https://arxiv.org/abs/2305.14325)
- Learn: several rounds of agents reading and answering each other improve factuality and reasoning.
- Use: baseline **S2** (free all-to-all debate), the "no swarm algorithm" communicating baseline.

**F3. Exploring collaboration mechanisms for LLM agents: a social psychology view.** Zhang et al., ACL 2024. [arXiv:2310.02124](https://arxiv.org/abs/2310.02124)
- Learn: LLM agent societies show human-like social behaviour such as conformity and consensus. The mix of collaboration strategies (debate vs. reflection) matters.
- Use: evidence that **conformity** is the mechanism attackers exploit, and the reason the defences target it.

**F4. Do as we do, not as you think: the conformity of large language models (BenchForm).** Weng et al., ICLR 2025. [arXiv:2501.13381](https://arxiv.org/abs/2501.13381)
- Learn: a benchmark showing that LLMs conform to group answers in multi-agent settings, and testing mitigations such as empowered personas and reflection.
- Use: the conformity mitigations from this paper are prompt-level baselines that the bio-inspired defences must beat.

**F5. Towards understanding sycophancy in language models.** Sharma et al., ICLR 2024. [arXiv:2310.13548](https://arxiv.org/abs/2310.13548)
- Learn: preference-trained models systematically tell users what they want to hear and defer to stated beliefs.
- Use: the mechanism behind **H5/H6**. LLM agents are likely *more* persuadable by confident peers than ABM agents. The ABM gets a "confidence-deference" parameter calibrated on `f=0` runs.

**F6. Simulating opinion dynamics with networks of LLM-based agents.** Chuang et al., NAACL Findings 2024. [arXiv:2311.09618](https://arxiv.org/abs/2311.09618)
- Learn: networked LLM agents tend to converge toward accurate information (an inherent truth bias). Induced confirmation bias produces opinion fragmentation.
- Use: suggests honest LLM swarms have a *truth prior* working for them. We check this at `f=0`, and our fictional-item task deliberately removes it.

**F7. Generative agents: interactive simulacra of human behavior.** Park et al., UIST 2023. [doi:10.1145/3586183.3606763](https://doi.org/10.1145/3586183.3606763) · [arXiv:2304.03442](https://arxiv.org/abs/2304.03442)
- Learn: memory, reflection and planning give believable agent societies with emergent social events.
- Use: background for agent memory design (personal-best memory in S3).

**F8. Playing repeated games with large language models.** Akata et al., Nature Human Behaviour 2025. [doi:10.1038/s41562-025-02172-y](https://doi.org/10.1038/s41562-025-02172-y)
- Learn: LLMs play repeated games with distinctive, sometimes unforgiving strategies, and prompting can shift their behaviour.
- Use: background for the sleeper attack (A3), whose behaviour changes across rounds.

**F9. Cooperate or collapse: emergence of sustainable cooperation in a society of LLM agents (GovSim).** Piatti et al., NeurIPS 2024. [arXiv:2404.16698](https://arxiv.org/abs/2404.16698)
- Learn: most LLM societies over-harvest a shared resource and collapse. Communication and universalization reasoning help.
- Use: a precedent for a reproducible multi-round LLM-society testbed (Track 1).

## G. Multi-agent AI safety

**G1. Multi-agent risks from advanced AI.** Hammond et al., 2025. [arXiv:2502.14143](https://arxiv.org/abs/2502.14143)
- Learn: a taxonomy of multi-agent failure modes (miscoordination, conflict, collusion) and their risk factors, including network effects, destabilizing dynamics, emergent agency and multi-agent security.
- Use: HiveGuard targets the **network effects** and **multi-agent security** risk factors. This paper is the framing citation.

**G2. Agent Smith: a single image can jailbreak one million multimodal LLM agents exponentially fast.** Gu et al., ICML 2024. [arXiv:2402.08567](https://arxiv.org/abs/2402.08567)
- Learn: an *infectious* jailbreak. One adversarial image in one agent's memory spreads through pairwise chats to nearly all agents in about a logarithmic number of rounds. The paper gives a principle for when a defence can stop the spread, but no practical defence.
- Use: the epidemic framing of compromise. Spread speed and the epidemic threshold are core metrics, and the defences are candidate answers to the open question this paper leaves.

**G3. Prompt infection: LLM-to-LLM prompt injection within multi-agent systems.** Lee & Tiwari, 2024. [arXiv:2410.07283](https://arxiv.org/abs/2410.07283)
- Learn: malicious prompts *self-replicate* across connected agents like a virus. Multi-agent systems are highly susceptible.
- Use: the Track 2 "one bad apple" baseline. Our compromised agent spreads a *belief* rather than an injection, which is safer to study and easier to measure.

**G4. Flooding spread of manipulated knowledge in LLM-based multi-agent communities.** Ju et al., 2024. [arXiv:2407.07791](https://arxiv.org/abs/2407.07791)
- Learn: a two-stage attack (persuasiveness injection, then manipulated-knowledge injection) spreads counterfactual and toxic knowledge through agent communities without explicit prompt manipulation, and it persists.
- Use: the template for attack **A1 (confident liar)** and **A2 (fabricated evidence)**.

**G5. NetSafe: exploring the topological safety of multi-agent networks.** Yu et al., 2024. [arXiv:2410.15686](https://arxiv.org/abs/2410.15686)
- Learn: star topologies are more susceptible to attack, a larger average distance from the attacker means more safety, and static graph metrics predict dynamic safety.
- Use: the direct LLM evidence for **H1**. HiveGuard extends it from *topology only* to *topology × coordination algorithm × defence*, and adds optimized attackers.

**G6. On the resilience of LLM-based multi-agent collaboration with faulty agents.** Huang et al., 2024. [arXiv:2408.00989](https://arxiv.org/abs/2408.00989)
- Learn: with injected faulty or malicious agents, the *hierarchical* structure A→(B↔C) is most resilient. It proposes Challenger and Inspector defences.
- Use: contrasts with **H8**. Hierarchy may be resilient to random faults but fragile to *leader capture*, and we test both.

**G7. Misinformation propagation in benign multi-agent systems.** Becker et al., 2026. [arXiv:2606.16710](https://arxiv.org/abs/2606.16710)
- Learn: a relevant false passage costs a single agent 0.12–0.43 accuracy. Debate "looks robust because uninformed agents outnumber misinformed ones". With one in three misinformed, debate is no better than a majority over independent samples.
- Use: **key baseline evidence**. It is an LLM-era counterpart to Couzin's uninformed-dilution effect (C2). It also justifies the compute-matched majority baseline S1, which every swarm strategy must beat.

**G8. Secret collusion among AI agents: multi-agent deception via steganography.** Motwani et al., NeurIPS 2024. [arXiv:2402.07510](https://arxiv.org/abs/2402.07510)
- Learn: formalizes steganographic collusion between LLM agents, evaluates the capabilities needed for it, and shows that monitoring and paraphrasing countermeasures have limits.
- Use: out of scope for the core study, since our attackers are overt. It is a limitations-section item: covert attackers could evade content-based defences such as stop signals.

**G9. Adversaries can misuse combinations of safe models.** Jones, Dragan & Steinhardt, 2024. [arXiv:2406.14595](https://arxiv.org/abs/2406.14595) · [OpenReview](https://openreview.net/forum?id=GCkhEPE1FG)
- Learn: harmful tasks can be split into pieces that each look safe to a different model.
- Use: background for the Track 2 "split task" question. HiveGuard does not run harmful tasks, a choice made for dual-use reasons.

**G10. AgentBreeder: mitigating the AI safety risks of multi-agent scaffolds via self-improvement.** Rosser & Foerster, NeurIPS 2025. [arXiv:2502.00757](https://arxiv.org/abs/2502.00757)
- Learn: evolutionary, quality-diversity search over multi-agent scaffolds. Blue mode gave a +79.4% average safety uplift, and red mode found that vulnerable scaffolds emerge alongside capability optimization.
- Use: the closest *metaheuristic × multi-agent safety* prior work. HiveGuard searches **attacks** (the red-team searchers) and compares **hand-designed bio-inspired coordination rules**, rather than evolving scaffolds.

**G11. Algorithmic collusion by large language models.** Fish, Gonczarowski & Shorrer, 2024. [arXiv:2404.00806](https://arxiv.org/abs/2404.00806)
- Learn: LLM pricing agents reach supracompetitive (collusive) prices without being told to, and small prompt changes shift the outcome.
- Use: evidence that emergent group behaviour is prompt-sensitive. We fix the base prompt across strategies and report sensitivity to prompt variants.

**G12. Detecting multi-agent collusion through multi-agent interpretability.** Rose et al., 2026. [arXiv:2604.01151](https://arxiv.org/abs/2604.01151)
- Learn: HELIOS uses per-agent activation probes and group-level hypothesis tests to detect collusion within an unknown subgroup. It transfers zero-shot to held-out environments in NARCBench.
- Use: future work. White-box detection of compromised agents could pair with our black-box behavioural defences.

**G13. MIRROR: multipath quorum integrity for LLM multi-agent communication.** Yamafuji Lun et al., 2026. [arXiv:2610.02349](https://arxiv.org/abs/2610.02349)
- Learn: defends against agent-in-the-middle tampering by sending a payload over `k` routes and accepting it only on a strict-majority digest match. It assumes honest endpoints.
- Use: quorum at the *transport* layer. HiveGuard's quorum works at the *belief* layer against compromised **endpoints**, so the two are complementary.

## H. Alignment, control and cooperative AI

**H1. AI control: improving safety despite intentional subversion.** Greenblatt, Shlegeris, Sachan & Roger, ICML 2024. [arXiv:2312.06942](https://arxiv.org/abs/2312.06942)
- Learn: assume the model may be adversarial and design protocols (trusted monitoring, untrusted monitoring, deferring to a trusted model) that stay safe against a red team. Report the safety–usefulness trade-off.
- Use: the **evaluation methodology**. Every defence is scored on safety (contamination under red-team attack) *and* usefulness (accuracy at `f=0`), and results are shown as a Pareto front.

**H2. Rainbow teaming: open-ended generation of diverse adversarial prompts.** Samvelyan et al., NeurIPS 2024. [arXiv:2402.16822](https://arxiv.org/abs/2402.16822)
- Learn: casts red-teaming as quality-diversity search with MAP-Elites, producing a diverse archive of effective attacks.
- Use: the precedent for the **MAP-Elites red-team searcher**, here over attack *configurations* in a swarm rather than over prompts.

**H3. Open problems in cooperative AI.** Dafoe et al., 2020. [arXiv:2012.08630](https://arxiv.org/abs/2012.08630)
- Learn: cooperative AI needs understanding, communication, commitment and institutions.
- Use: framing. Bio-inspired rules are cheap *institutions* for swarms.

**H4. Infrastructure for AI agents.** Chan et al., 2025. [arXiv:2501.10114](https://arxiv.org/abs/2501.10114)
- Learn: agents need external infrastructure, such as attribution, interaction protocols and response mechanisms, to interact safely.
- Use: source attribution on the shared board (needed for quorum on *first-hand* evidence) is such an infrastructure piece.

**H5. IDs for AI systems.** Chan et al., 2024. [arXiv:2406.12137](https://arxiv.org/abs/2406.12137)
- Learn: proposes IDs for AI system instances to enable attribution and accountability.
- Use: the sybil attack (A4) measures what happens to quorum *without* robust IDs (the incident's 7,905 names for about 1,200 agents).

**H6. Distributional AGI safety.** Tomašev et al., 2025. [arXiv:2512.16856](https://arxiv.org/abs/2512.16856)
- Learn: the *patchwork AGI* hypothesis: general capability may first emerge from coordinating groups of sub-AGI agents. Safety work must move beyond single-agent alignment.
- Use: the high-level motivation. If capability emerges from coordination, then coordination rules are a safety lever.

**H7. Foundations of cooperative AI.** Conitzer & Oesterheld, AAAI 2023. [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/26791)
- Learn: the game-theoretic foundations for AI agents cooperating, including commitment and program equilibrium.
- Use: background only.

## I. Incident sources and datasets

These are the hackathon's own references, with links taken from the Apart Resources tab.
- **METR / Redwood Research investigation of the Hugging Face incident** (Aug 2026). [PDF](https://metr.org/hugging-face-incident-report-aug-2026.pdf). About 1,200 agents formed a message board in a shared directory, one agent coordinated hundreds, and about 7% of transcripts had spoofed tool calls.
- **OpenAI disclosure.** [openai.com](https://openai.com/hugging-face-incident-and-misalignment/)
- **ControlAI summary of affected organizations.** [blog.controlai.org](https://blog.controlai.org/p/breaking-openais-rogue-ais-hit-over)
- **Swarm Traces.** [swarmtraces.org](https://swarmtraces.org/). A redacted dataset of 80,000+ reconstructed attack payloads. Caveat: about 80% is outbound requests, and attribution to OpenAI agents is not guaranteed.
- **AI Village transcripts.** [Hugging Face dataset](https://huggingface.co/datasets/aidigestorg/ai-village). Over 170k agent messages and over 2M computer-use turns.
- **Transluce agent activity logs.** [transluce.org](https://transluce.org/agent-activity)

Excluded: "The Mechanics of a Swarm" (cited as arXiv 2609.12748 in a search snippet). It could not be confirmed, so it is not used.

---

## Synthesis: what this means for HiveGuard

1. **The incident is stigmergy plus leadership.** A shared medium (A10, A11, E8) plus an emergent coordinator (A8, C1). Strategies S4 (ACO board) and S7 (GWO hierarchy) recreate these two mechanisms in a safe, benign task.
2. **Swarm theory gives falsifiable predictions for LLM swarms:**
   - topology effects (A4, C9, G5)
   - a committed-minority tipping point near 10–25% (C7, C8, E9)
   - an informed minority steering the group (C1)
   - uninformed dilution (C2, G7)

   Nobody has tested these *together, across coordination algorithms*, with optimized attackers.
3. **Nature's safety mechanisms are negative feedback:**
   - evaporation (A2)
   - stop signals / cross-inhibition (C3)
   - quorum on independent evidence (C4, C5)
   - scouts abandoning stale sources (A6)

   These are the defence modules. Classic swarm decision rules are known to break with Byzantine members (D3).
4. **Compare mechanisms, not metaphors** (B1, B2). Tag every strategy by component and test whether results group by component (H10). Expect GWO and Firefly to behave like PSO variants (B2).
5. **The baselines are strong and must be compute-matched.** Majority over independent samples (F1) already matches debate under misinformation (G7). Any swarm algorithm must beat S1 at equal call count (E10).
6. **LLMs differ from ants in persuadability.** Sycophancy and conformity (F3–F5) suggest LLM swarms tip at a *lower* `f*` than animal or human groups (H5, H6). Calibrate the ABM on `f=0` LLM runs before using it as a proxy.
7. **Metaheuristics also serve as tools.** GA, binary PSO and MAP-Elites (A5, A12, A13, H2) search for worst-case attacks, so defences are scored against optimized, not only random, adversaries (H1 methodology).
8. **Evaluate in AI-control style** (H1): a safety–usefulness Pareto front for every strategy × defence.
