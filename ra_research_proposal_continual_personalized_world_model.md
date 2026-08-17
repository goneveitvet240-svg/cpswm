# Continual Personalized Semantic World Models for Long-Term Household Robots

**Research Proposal for a Prospective Remote Research Assistantship**  
**Applicant:** Pang Wei, Qingdao University  
**Programme:** B.Eng. in Intelligent Manufacturing Engineering (expected June 2027)  
**Email:** m15964096907@outlook.com  
**Date:** August 2026

## Abstract

Household robots are increasingly able to map rooms, recognize open-vocabulary objects, retrieve past observations, and execute language-conditioned tasks. Yet these abilities are commonly evaluated as separate components or over short deployments. A robot that lives with a household for months must solve a harder problem: it must preserve the identity of specific objects across occlusion and movement, distinguish direct observation from inference, learn person-conditioned routines, infer unobserved transfers, revise beliefs after contradictory evidence, and use this evolving memory to decide when to retrieve, explore, ask, or act.

This proposal investigates a **Continual Personalized Semantic World Model (CPSWM)**: an event-sourced, instance-level and probabilistic memory for long-term household robots. The proposed system combines (i) temporally qualified entity and relation assertions, (ii) episodic event memory and evidence provenance, (iii) a reconstructible multi-hypothesis belief projection, (iv) personalized habit and transition models, (v) hidden-event inference, and (vi) a closed memory–query–action–writeback loop. It explicitly represents valid time, observation time and recording time; separates evidence reliability from posterior probability; and uses a shared observation-likelihood model for negative-evidence updating and active perception.

The research will be evaluated through a tiered simulator and benchmark covering object retrieval, historical memory, habit prediction, hidden-event inference, calibration, adaptation, explanation faithfulness, and downstream action utility. Oracle, controlled-noise, and real-perception tracks will isolate reasoning quality from perception error. The intended outcome is not only a memory module, but a testable systems framework for persistent, personalized, and continually revised household intelligence.

**Keywords:** embodied AI; long-term robot memory; semantic world models; continual learning; household robotics; active perception; probabilistic reasoning

## 1. Motivation and Problem Statement

Most semantic maps answer questions about the present scene: *What objects are here? Where was an object last observed?* A long-term household robot must answer materially different questions:

- Which specific cup did the owner use yesterday?
- Who most likely moved it, and when?
- Is its current location directly observed or inferred from a carry event?
- Is an unusual location a temporary deviation, an identity error, or a new habit?
- Which memory should be retrieved, which place should be inspected, and when is the evidence sufficient to stop searching?

These questions couple perception, identity, time, human behaviour, uncertainty, memory maintenance and physical action. They cannot be solved reliably by a single latest-state scene graph or an unstructured log of captions. A household is partially observable: objects are occluded, people move objects outside the robot's field of view, visually similar instances are confused, and verification is selective. It is also non-stationary: family routines, object ownership, furniture layouts and frequently used locations change over time.

The central problem is therefore:

> How can a household robot maintain and use a persistent, person-conditioned, instance-level belief about a changing home while preserving temporal validity, evidence provenance and uncertainty under partial observability?

The proposal treats long-term memory as an active world-model maintenance problem rather than a passive archive. Memory is used to predict and act; observations and action outcomes, in turn, revise memory.

## 2. Positioning and Research Gap

Recent work provides strong foundations but leaves important integration gaps. ConceptGraphs constructs open-vocabulary 3D scene graphs for perception and planning [1]. Scene Graph Memory models object-location prediction as link prediction on partially observable dynamic graphs and introduces a Dynamic House Simulator [2]. DynaMem maintains an online dynamic spatio-semantic map for open-world mobile manipulation [3], while *Where Did I Leave My Glasses?* models object-instance stationarity and active map maintenance in semi-static environments [4].

Long-horizon memory systems address a complementary axis. ReMEmbR builds a retrieval-augmented spatio-temporal memory for long-horizon robot navigation and question answering [5]. Mind Palace studies long-term active embodied question answering using episodic scene-graph world instances and value-of-information reasoning [6]. STAR further unifies temporal memory queries with spatial actions for open-world object retrieval [7].

Personalization research has shown that household planners can adapt to user preferences [8], and that interactive continual learning can support long-term personalization of semantic knowledge on a physical service robot [9]. However, preference-aligned planning and continually learned semantic categories do not by themselves provide a persistent probabilistic model of individual object histories, people–object interactions, hidden transfers and evidence-qualified belief revision.

This proposal therefore does **not** claim that dynamic mapping, long-term embodied memory, personalization, or active search is individually unexplored. Its research gap is the disciplined integration and evaluation of the following properties in one long-term household world model:

1. persistent instance identity across days, locations and occlusions;
2. person-conditioned ownership, use, activity and location dynamics;
3. explicit separation of observations, reports, inferences and robot-executed changes;
4. hidden-event hypotheses instead of premature hard state assignments;
5. event-sourced canonical memory with a reconstructible probabilistic belief view;
6. shared uncertainty semantics across negative-evidence updating and active sensing;
7. memory retrieval budgets, evidence-grounded explanations and action writeback;
8. evaluation under routine shifts, selective verification and perception noise.

## 3. Research Questions and Hypotheses

The complete project is organized around seven research questions.

**RQ1 — Representation.** How should long-term memory extend a semantic map beyond a current-state snapshot?  
**Hypothesis H1:** temporally qualified assertions plus event memory will improve historical queries and contradiction handling over latest-state maps and unstructured retrieval memories.

**RQ2 — Instance identity.** How can specific objects be maintained across days, rooms, occlusion and visual ambiguity?  
**H2:** multi-hypothesis association that combines appearance, geometry, trajectory and relation history will reduce irreversible identity switches compared with greedy hard assignment.

**RQ3 — Personalization.** How can the robot learn habits conditioned on person, object instance, time, activity and context?  
**H3:** hierarchical person-conditioned transition models will improve object-location and routine prediction over household-agnostic and class-level frequency baselines.

**RQ4 — Hidden events.** How can unobserved movements, placements and handovers be inferred from incomplete event chains?  
**H4:** evidence-scored causal candidates will improve top-k location recall and search efficiency without requiring the system to write inferred events as observed facts.

**RQ5 — Language access.** How can a language model query long-term memory without becoming the source of world truth?  
**H5:** compiling language into typed, budgeted world-model queries will increase answer traceability and reduce unsupported responses relative to direct long-context prompting.

**RQ6 — Action coupling.** How can task execution continually improve the world model?  
**H6:** writing navigation observations, manipulation outcomes and failed detections back as evidence will improve subsequent retrieval and reduce repeated search cost.

**RQ7 — Continual adaptation.** How can the system adapt to routine changes without overwriting stable knowledge?  
**H7:** change-point-aware consolidation and selective weakening will achieve a better stability–plasticity trade-off than fixed decay or full-history retraining.

## 4. Proposed System Framework

The complete architecture contains six layers and 32 stable responsibility modules. The modules may initially run in one repository and process; the boundaries define semantics and testability rather than requiring microservices.

| Layer | Modules | Function |
|---|---:|---|
| A. Contracts and runtime foundation | M01–M04 | Ontology, identity, time, coordinates, persistence and orchestration |
| B. Embodied observation and mapping | M05–M12 | Sensor adaptation, SLAM, 3D structure, observability, semantics, instance association and interaction events |
| C. Long-term world model and reasoning | M13–M19 | Canonical assertions, episodic events, provenance, belief projection, habits, hidden events and memory lifecycle |
| D. Query, language and explanation | M20–M22 | Structured retrieval, language grounding, evidence-grounded explanation and user correction |
| E. Planning, search and action | M23–M27 | Task planning, active perception, navigation, manipulation and closed-loop writeback |
| F. Simulation, benchmark and governance | M28–M32 | Privacy, long-term simulation, synthetic routines, benchmark protocols, evaluation and deployment |

### 4.1 Canonical memory and derived belief

The architectural core separates what was recorded from what is currently believed.

- **M13 Temporal Entity–Relation Assertion Graph** stores append-only claims such as `Cup_17 belongs_to Person_A` or `Cup_17 located_at Desk` together with temporal validity, source and evidence reliability.
- **M14 Episodic Event Memory** stores event histories such as observation, pickup, carry, placement, handover and room transition.
- **M15 Evidence Provenance and Audit** connects each assertion or event to its originating observation, user report, model inference or robot action.
- **M16 Multi-Hypothesis Belief Projection** derives current or historical posteriors over identity, location, state, owner and relations from M13–M15 plus learned models.

M16 is a **derived projection**, not an independent source of truth. It is checkpointed and reconstructible from canonical records. This avoids conflicting authorities between graph relations and probabilistic state, while still supporting fast queries. Evidence reliability and posterior probability are represented separately: a detector score or source trust estimate must not be mistaken for the posterior probability of a world state.

### 4.2 Temporal and provenance semantics

Every assertion and event uses three time concepts:

- **valid time:** when the state or event held in the world;
- **observed time:** when a sensor or person obtained the evidence;
- **recorded time:** when the system persisted the record.

This distinction prevents a delayed report about yesterday from being written as an event that happened today. Supersession is append-only: corrections preserve the earlier record and its provenance. Directly observed, human-reported, model-inferred and robot-executed information remain distinguishable throughout the pipeline.

### 4.3 Observation likelihood and negative evidence

A failed detection is not equivalent to absence. The system will model

\[
p(z | s, a) = Σᵥ p(z | v, s, a; θ_perception) · p(v | s, a; G_geometry)
\]

where state \(s\), observation action \(a\), visibility state \(v\), perception parameters \(\theta_{perception}\), and geometric model \(\mathcal{G}_{geometry}\) jointly determine the expected observation. The same versioned `ObservationLikelihoodModel` will be consumed by M16 for Bayesian-style negative-evidence updates and by M24 for information-gain estimation. This prevents belief updating and active search from using incompatible assumptions about visibility and detector recall.

### 4.4 Personalized habits and hidden transitions

M17 will learn conditional routines of the form

\[
P(lₜ₊₁, aₜ₊₁ | person, object, lₜ, aₜ, time, context)
\]

with partial pooling across household, person, object class and object instance. Candidate implementations to be compared include hierarchical count/Bayesian models, temporal point processes, probabilistic graphical models and neural sequence models. The proposal deliberately treats this as an empirical model-selection question rather than assuming one family in advance.

M18 will generate ranked `HiddenEventHypothesis` objects when observations leave causal gaps. For example, observing a cup on a desk, then observing a person holding it and entering a kitchen, should redistribute location probability among the desk, the kitchen and continued carriage. The inferred transition remains a hypothesis with causal parents and evidence references; it is not promoted to an observed event.

M19 will manage consolidation, contradiction, uncertainty growth, change points and forgetting. Habit-model training and change detection will use separate epoch traces so that retraining output is not immediately reinterpreted as evidence of another environmental change.

### 4.5 Language, retrieval and embodied writeback

M21 will translate temporal, personal, functional and referential language into typed `WorldModelQuery` objects. Queries include a retrieval budget; results report retrieval coverage and projection lag. M20 then retrieves top-k candidates, temporal evidence and competing hypotheses. M22 converts this evidence into an explanation and accepts explicitly authorized user corrections.

M23–M27 close the loop. The planner may retrieve memory, inspect a location, ask a clarifying question, navigate, manipulate, or verify. Every executed action produces an `ActionRecord` and subsequent observations are written back through the same evidence path. The language model may propose constraints and interpretations, but it cannot directly write ungrounded propositions as facts.

### 4.6 Long-term simulator and benchmark

Longitudinal household data are difficult and privacy-sensitive to collect. M29 therefore contains two levels:

- **M29-L0 Symbolic Simulator:** advances people, objects, rooms, containers and events without rendering pixels, then generates observations with controllable occlusion, missed detection, identity confusion and delayed reporting;
- **M29-L1 Embodied Simulator:** integrates a platform such as Habitat, iGibson or Isaac Sim for rendered sensing, navigation, manipulation and sim-to-real studies.

M30 generates multi-person household routines, object-use sequences, interruptions, guests, workday/weekend variation and controlled habit changes. Ground truth is isolated in a separate namespace and can enter the robot stack only through an explicit oracle adapter. Random forced-verification episodes and their selection probabilities provide less biased calibration samples under missing-not-at-random observation.

M31 defines a Long-term Household Memory Benchmark; M32 manages reproducible evaluation, leakage checks, ablations and deployment telemetry.

## 5. Research Methodology and Work Packages

The work packages preserve the full architecture while allowing scientific questions to be tested before every physical subsystem reaches final fidelity. Oracle, controlled-noise and real-perception implementations share contracts and are reported as separate evaluation tracks.

### WP1 — Temporal contracts, symbolic households and canonical storage

1. Complete typed schemas for entities, assertions, events, evidence, belief snapshots, queries and actions.
2. Implement M29-L0 and M30 to produce reproducible, multi-week household trajectories.
3. Implement append-only M13/M14 storage and M15 provenance queries.
4. Enforce ground-truth namespace isolation and oracle-channel audit tests.

**Primary tests:** temporal interval semantics, correction/supersession, deterministic replay, no-ground-truth-leakage, and data-volume scaling.

### WP2 — Multi-hypothesis belief reconstruction and negative evidence

1. Implement M16 as an incremental projection with checkpoints and bounded replay.
2. Define factorization assumptions for coupled identity, location, held-by, inside and ownership states.
3. Calibrate observation likelihoods under controlled visibility and detector-noise regimes.
4. Compare hard latest-state, independent-edge Bayesian and structured multi-hypothesis baselines.

**Primary tests:** top-k state recall, log loss, Brier score, calibration under forced verification, contradiction recovery, projection latency and rebuild cost.

### WP3 — Personalized routines, hidden events and continual memory

1. Fit household-, person-, class- and instance-conditioned transition models.
2. Generate causal candidates for unobserved pickup, carriage, placement and handover.
3. Detect routine changes and distinguish persistent shifts from temporary anomalies.
4. Compare replay, sufficient-statistic, windowed and decay-based continual updates where applicable.

**Primary tests:** next-location accuracy, hidden-event top-k recall, adaptation delay, false change alarms, backward retention and per-person performance.

### WP4 — Grounded queries and the memory–action loop

1. Compile natural-language requests into typed temporal and relational constraints.
2. Implement budgeted hybrid retrieval over graph, event, belief, vector and spatial indices.
3. Use observation likelihoods to select memory retrieval, viewpoint inspection, clarification or stopping actions.
4. Write navigation and manipulation outcomes back into canonical memory.

**Primary tests:** answer accuracy, evidence precision/recall, unsupported-claim rate, object-retrieval success, path length, number of inspections, question cost and post-task memory improvement.

### WP5 — Perception integration, benchmark release and physical validation

1. Replace oracle components progressively with open-vocabulary perception, instance re-identification and interaction-event baselines.
2. Measure world-model degradation as controlled event and association noise increase.
3. Define dataset manifests, household-disjoint splits, evaluation budgets and fixed baseline implementations.
4. Validate selected scenarios in rendered simulation and, subject to host-lab hardware and data-governance approval, on a mobile manipulator.

**Primary tests:** oracle-to-real gap, cross-household generalization, robustness to sensor failures, privacy/deletion compliance and end-to-end action utility.

## 6. Experimental Design

### 6.1 Evaluation tracks

| Track | Input quality | Purpose |
|---|---|---|
| Oracle perception | Exact entities/events through an audited adapter | Isolate memory, reasoning and continual-learning quality |
| Controlled-noise perception | Parameterized misses, false positives, identity swaps and occlusion | Produce sensitivity and failure-boundary curves |
| Real perception | RGB-D/robot outputs with measured detector quality | Test external validity and integration cost |

### 6.2 Benchmark tasks

The benchmark will include eight task families:

1. **Object Retrieval:** locate and retrieve a target instance under a fixed action budget.
2. **Historical Memory:** answer where, when and by whom an object was observed or used.
3. **Habit Prediction:** predict person-conditioned future object and activity states.
4. **Hidden-Event Inference:** rank unobserved transfers and their causal explanations.
5. **Memory Calibration:** test whether state probabilities match empirical correctness.
6. **Adaptation:** measure recovery after routine, ownership or layout changes.
7. **Explanation Faithfulness:** verify that explanations cite records actually used by the result.
8. **Continual Identity:** preserve individual object identity across gaps, occlusion and near-duplicate instances.

### 6.3 Metrics and action utility

Representation metrics will include instance IDF1/association accuracy, temporal relation F1, event detection F1, historical-query accuracy and provenance completeness. Probabilistic metrics will include negative log-likelihood, Brier score, expected calibration error and top-k recall, reported with the forced-verification protocol where appropriate. Continual-learning metrics will include adaptation delay, false change alarms, backward retention and forward transfer.

These scores are insufficient on their own. The decisive system-level outcomes are object-retrieval success, time-to-target, path length, number and cost of observations, clarification count, manipulation success and improvement in later tasks after writeback. All method comparisons will use matched action and retrieval budgets. Thresholded baselines will be independently tuned rather than inherited from the proposed method.

### 6.4 Baselines and ablations

Baselines will include:

- latest observation / last-seen map;
- static open-vocabulary scene graph;
- unstructured caption or vector memory;
- frequency and recency object-location models;
- independent-edge Bayesian update;
- scene-graph dynamic prediction inspired by SGM;
- retrieval-augmented long-horizon memory inspired by ReMEmbR;
- dynamic spatial memory and active-maintenance variants inspired by DynaMem and related work;
- task-specific active search with no persistent personalized model.

Key ablations remove multi-hypothesis identity, person conditioning, hidden-event inference, negative evidence, provenance, change-point logic, retrieval budgeting, action writeback or calibrated observation likelihood. Full-stack claims will be made only when improvements survive matched-budget action metrics and real or realistically degraded perception.

## 7. Expected Contributions

If the hypotheses are supported, the project is expected to contribute:

1. an event-sourced semantic world-model representation that joins instance, temporal, relational and evidential memory without conflating records with beliefs;
2. a derived multi-hypothesis belief mechanism for partially observed household state, including principled negative evidence;
3. person-conditioned routine and hidden-event models for long-term object dynamics;
4. a grounded language and action interface with budgeted retrieval, evidence-based explanations and closed-loop writeback;
5. a reproducible symbolic-to-embodied household simulator and benchmark for memory, calibration, adaptation and action utility;
6. empirical evidence about when improved memory actually yields better robot decisions, and where perception noise or routine drift eliminates that advantage.

## 8. Feasibility, Current Progress and Applicant Preparation

The project currently has a complete architectural specification covering all 32 modules and their contracts. The first executable component, M01 schema v0.1, already defines temporal metadata, evidence references, relation assertions, event records, belief snapshots, observation-likelihood objects, budgeted queries, user-correction authority, projection checkpoints and an isolated ground-truth namespace. Its current contract suite contains **33 passing tests**. Storage, inference and query services are not presented as completed; the next implementation work is M29-L0 plus M13/M14 append-only storage.

My current independent research focuses on replay-free analytic continual visual regression using frozen DINOv2 features and recursive second-order statistics. This work has developed my experience in continual adaptation, stability–plasticity analysis, experimental controls, ablation design, PyTorch/OpenCV implementation and reproducible GPU experiments. The proposed RA project extends this foundation from supervised domain streams to a more structured embodied setting with uncertain observations, event memory and action-dependent data.

I can contribute 30–40 hours per week remotely to implementation, dataset generation, experiments, ablations, documentation and paper writing. The exact allocation among perception, probabilistic modeling, continual learning and physical deployment would be coordinated with the host lab; the architectural contracts are designed to accept alternative lab-specific models and robot platforms.

## 9. Indicative Work Plan

The timeline below is an adaptable research sequence for a twelve-month RA period, not a reduction of the final system scope.

| Period | Main work | Research outputs |
|---|---|---|
| Months 1–2 | WP1: schemas, M29-L0/M30, canonical storage, replay and leakage tests | Reproducible longitudinal generator and event store |
| Months 3–4 | WP2: belief projection, checkpoints, observation likelihood and negative evidence | Probabilistic baseline study and failure analysis |
| Months 5–6 | WP3: personalized routines, hidden events and change detection | Habit/adaptation experiments and ablations |
| Months 7–8 | WP4: typed language queries, retrieval budgets, active sensing and writeback | Closed-loop object-retrieval evaluation |
| Months 9–10 | WP5: real perception adapters and embodied simulation | Oracle-to-noise-to-real sensitivity curves |
| Months 11–12 | Benchmark consolidation, selected physical validation and manuscript preparation | Dataset/protocol release candidate and research paper |

## 10. Risks, Falsification Criteria and Mitigation

**Identity errors propagate through memory.** Maintain competing associations, prevent one detection from overwriting stable history, and report performance by identity ambiguity. If multi-hypothesis inference does not improve matched-budget retrieval over a tuned hard-assignment baseline, the claimed benefit will be rejected or narrowed.

**Interaction-event perception is a bottleneck.** Separate person identity from event detection, keep oracle/rule-based/learned tracks, and publish sensitivity curves showing the event-noise level at which habit or hidden-event models cease to help.

**Calibration is biased by selective verification.** Use simulator-side random forced verification and record selection probabilities. Real-deployment calibration will be reported as selectively observed unless an unbiased protocol is available.

**Derived belief reconstruction becomes too expensive.** Use watermarks, checkpoints, incremental replay and explicit rebuild-cost estimates. Deletion or correction invalidates affected checkpoints and triggers auditable reconstruction.

**LLM outputs contaminate world state.** Restrict LLMs to typed query compilation, candidate generation and explanation. All state writes require a source type, evidence reference and module-authorized path.

**Improved memory does not improve action.** Treat this as a falsification outcome. Require independently tuned, matched-budget action comparisons; calibration or retrieval metrics alone will not justify a systems claim.

**Privacy limits longitudinal data.** Start with synthetic routines and controlled simulation, minimize retained raw media, isolate households, support scoped deletion, and require explicit approval before real-home data collection.

## 11. Fit for Research Assistant Collaboration

This project is suitable for a research assistantship because it contains several independently testable questions while preserving a shared long-term systems objective. A host group can contribute expertise in embodied perception, probabilistic robotics, continual learning, human–robot interaction or mobile manipulation without adopting a monolithic implementation. In return, I would provide sustained engineering ownership of the common schemas, simulator, experimental infrastructure and selected research work packages, with regular reproducible milestones and failure reports.

The immediate collaboration target is to agree on one primary hypothesis and its evaluation track, connect it to the lab's existing platform or datasets, and implement it within the complete CPSWM architecture. This creates a concrete starting point for joint research while retaining the broader goal of a household robot that continually learns who uses which objects, how household routines evolve, what may have happened outside its field of view, and how memory should guide its next action.

## References

[1] Q. Gu et al., “ConceptGraphs: Open-Vocabulary 3D Scene Graphs for Perception and Planning,” *IEEE International Conference on Robotics and Automation (ICRA)*, 2024, pp. 5021–5028. https://concept-graphs.github.io/

[2] A. Kurenkov et al., “Modeling Dynamic Environments with Scene Graph Memory,” *International Conference on Machine Learning (ICML)*, 2023. https://arxiv.org/abs/2305.17537

[3] P. Liu et al., “DynaMem: Online Dynamic Spatio-Semantic Memory for Open World Mobile Manipulation,” *IEEE International Conference on Robotics and Automation (ICRA)*, 2025, pp. 13346–13355. https://arxiv.org/abs/2411.04999

[4] B. Bogenberger et al., “Where Did I Leave My Glasses? Open-Vocabulary Semantic Exploration in Real-World Semi-Static Environments,” arXiv:2509.19851, 2025. https://arxiv.org/abs/2509.19851

[5] A. Anwar, J. Welsh, J. Biswas, S. Pouya, and Y. Chang, “ReMEmbR: Building and Reasoning Over Long-Horizon Spatio-Temporal Memory for Robot Navigation,” *IEEE International Conference on Robotics and Automation (ICRA)*, 2025. https://arxiv.org/abs/2409.13682

[6] M. F. Ginting et al., “Enter the Mind Palace: Reasoning and Planning for Long-term Active Embodied Question Answering,” *Proceedings of the 9th Conference on Robot Learning (CoRL)*, PMLR 305:5072–5106, 2025. https://proceedings.mlr.press/v305/ginting25a.html

[7] T. Chen et al., “Searching in Space and Time: Unified Memory-Action Loops for Open-World Object Retrieval,” arXiv:2511.14004, 2025. https://arxiv.org/abs/2511.14004

[8] D. Han et al., “LLM-Personalize: Aligning LLM Planners with Human Preferences via Reinforced Self-Training for Housekeeping Robots,” arXiv:2404.14285, 2024. https://arxiv.org/abs/2404.14285

[9] A. Ayub, C. L. Nehaniv, and K. Dautenhahn, “Interactive Continual Learning Architecture for Long-Term Personalization of Home Service Robots,” arXiv:2403.03462, 2024. https://arxiv.org/abs/2403.03462

[10] A. Ayub, C. L. Nehaniv, and K. Dautenhahn, “A Personalized Household Assistive Robot that Learns and Creates New Breakfast Options through Human-Robot Interaction,” arXiv:2307.00114, 2023. https://arxiv.org/abs/2307.00114
