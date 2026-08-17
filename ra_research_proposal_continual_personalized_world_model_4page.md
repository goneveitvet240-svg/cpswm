# Continual Personalized Semantic World Models for Long-Term Household Robots

**Research Proposal for a Prospective Remote Research Assistantship**  
**Pang Wei · Qingdao University · Intelligent Manufacturing Engineering**  
**m15964096907@outlook.com · August 2026**

## Abstract

This proposal investigates a **Continual Personalized Semantic World Model (CPSWM)** for household robots operating over days, weeks and months. The model is intended to preserve the identity and history of specific objects, learn person-conditioned routines, infer unobserved transfers, represent uncertainty, answer time-dependent language queries and improve through the robot's own actions. The proposed architecture combines event-sourced canonical memory, evidence provenance, a reconstructible multi-hypothesis belief projection, personalized transition models and a closed memory-query-action-writeback loop. Evaluation will use symbolic, controlled-noise and real-perception tracks so that reasoning quality can be separated from perception error.

## 1. Problem and Research Gap

Existing semantic maps and embodied memories provide important pieces of this problem. ConceptGraphs supports open-vocabulary 3D scene graphs [1]; Scene Graph Memory predicts object locations in partially observable dynamic graphs [2]; DynaMem updates a dynamic spatio-semantic memory for mobile manipulation [3]; ReMEmbR retrieves long-horizon spatio-temporal experience [4]; and Mind Palace combines episodic memory retrieval with active exploration [5]. Other work studies active maintenance of semi-static object maps [6] and personalized household planning or semantic learning [7,8].

These lines do not make dynamic mapping, long-term memory or personalization individually unexplored. The remaining systems question is how to maintain a single, auditable household model that jointly supports instance identity, person-object relations, hidden events, temporal validity, probabilistic revision, continual habit change and action-dependent verification. In a home, “not detected” is not the same as “absent”; a reported event may have happened before it was recorded; and an inferred location must not be stored as a direct observation.

## 2. Research Questions

The project retains seven linked questions: **RQ1** long-term representation beyond a current-state map; **RQ2** instance identity across days and occlusion; **RQ3** person-conditioned habits; **RQ4** hidden object transfers; **RQ5** grounded language access; **RQ6** action-to-memory writeback; and **RQ7** the stability-plasticity trade-off during continual adaptation. The central hypothesis is that temporally qualified, evidence-sourced and multi-hypothesis memory will improve both historical reasoning and matched-budget robot action compared with latest-state maps, unstructured retrieval memories and hard-assignment baselines.

## 3. Proposed Framework

The complete system contains 32 stable responsibility modules organized into six layers. These are architectural boundaries, not a requirement to deploy 32 independent services.

| Layer | Modules | Role |
|---|---:|---|
| A. Contracts and runtime | M01-M04 | Ontology, identity, time, coordinates, persistence and orchestration |
| B. Observation and mapping | M05-M12 | Sensors, SLAM, geometry, observability, semantics, instance association and interaction events |
| C. World model and reasoning | M13-M19 | Assertions, events, provenance, belief projection, habits, hidden events and memory lifecycle |
| D. Query and explanation | M20-M22 | Structured retrieval, language grounding, explanations and user correction |
| E. Planning and action | M23-M27 | Active sensing, navigation, manipulation and writeback |
| F. Simulation and evaluation | M28-M32 | Privacy, simulator, routines, benchmark, evaluation and deployment |

### 3.1 Canonical records and derived belief

M13 stores append-only temporal relation assertions, M14 stores episodic events, and M15 records evidence provenance. M16 is a **derived projection**, not an independent source of truth: it reconstructs current or historical posteriors over identity, location, state, ownership and relations from canonical records and learned models. Checkpoints and watermarks allow bounded replay after corrections or deletions. Evidence reliability is kept separate from posterior probability so that a detector score is not misused as a world-state belief.

### 3.2 Time, negative evidence and hidden events

Each record distinguishes **valid time** (when it held in the world), **observed time** (when evidence was obtained) and **recorded time** (when it entered storage). A shared observation-likelihood model combines geometric visibility with perception response. It is used both to update beliefs after a failed detection and to estimate information gain for active sensing.

M17 learns conditional routines over person, object instance, time, activity and context. M18 fills observational gaps with ranked hidden-event hypotheses rather than hard facts. For example, after observing a person pick up a cup and enter the kitchen, probability can move from the desk toward the kitchen while retaining a non-zero “still carried” hypothesis. M19 manages consolidation, contradiction, change points, uncertainty growth and selective forgetting.

### 3.3 Language and action loop

Natural language is compiled into typed, budgeted queries. Results include top-k candidates, evidence, competing hypotheses, retrieval coverage and projection lag. The language model may propose constraints or explanations but cannot write unsupported facts. Search, navigation and manipulation outcomes return through the same evidence path, allowing one task to improve later tasks.

## 4. Research Methodology

The complete architecture will be studied through five connected work packages. Staged implementation changes component fidelity without deleting final capabilities.

- **WP1 - Contracts and longitudinal data:** complete typed schemas; implement the M29-L0 symbolic simulator, synthetic multi-person routines, append-only M13/M14 storage and ground-truth isolation.
- **WP2 - Probabilistic belief:** implement incremental M16 reconstruction, observation-likelihood calibration, negative-evidence updates and competing identity/location hypotheses.
- **WP3 - Personalization and hidden events:** compare hierarchical statistical, graphical and sequence models for person-conditioned routines; add change detection and evidence-scored causal candidates.
- **WP4 - Grounded memory-action loop:** compile language into structured queries, perform hybrid retrieval, choose retrieval/inspection/clarification actions and write outcomes back to memory.
- **WP5 - Perception and embodied validation:** progressively replace oracle inputs with open-vocabulary perception, re-identification and interaction-event baselines, then evaluate in embodied simulation and on host-lab hardware where available.

## 5. Experimental Design

Three evaluation tracks will be reported separately: **oracle perception** isolates memory and reasoning; **controlled-noise perception** varies misses, false positives, identity swaps, occlusion and event noise; **real perception** measures external validity and integration cost. Ground truth uses a separate namespace and can enter the robot stack only through an audited oracle adapter.

The proposed Long-term Household Memory Benchmark covers eight task families: object retrieval, historical memory, habit prediction, hidden-event inference, probability calibration, adaptation after routine change, explanation faithfulness and continual instance identity. Calibration under selective verification will use randomly forced checks in simulation and record their selection probabilities.

Metrics include association accuracy, event and temporal-relation F1, top-k state recall, negative log-likelihood, Brier score, calibration error, adaptation delay and backward retention. The decisive outcomes are action-level: retrieval success, time-to-target, path length, observation cost, clarification count and improvement in later tasks after writeback. Comparisons will use matched action and retrieval budgets with independently tuned baselines.

Baselines include last-seen maps, static scene graphs, unstructured caption/vector memory, frequency and recency models, independent-edge Bayesian updates, dynamic scene-graph prediction, retrieval-augmented long-horizon memory and active search without persistent personalization. Ablations remove multi-hypothesis identity, person conditioning, hidden-event inference, negative evidence, provenance, retrieval budgeting or action writeback. If better memory metrics do not improve matched-budget actions, the corresponding systems claim will be rejected or narrowed.

## 6. Expected Contributions and Current Progress

Expected outputs are: (1) an event-sourced temporal household representation; (2) a reconstructible multi-hypothesis belief mechanism; (3) person-conditioned routine and hidden-event models; (4) a grounded language and action interface; and (5) a longitudinal simulator and benchmark connecting memory quality to robot utility.

The project already has a complete 32-module architectural specification. M01 schema v0.1 implements temporal metadata, evidence references, relation assertions, event records, belief snapshots, observation-likelihood objects, budgeted queries, user-correction authority, projection checkpoints and an isolated ground-truth namespace. The current contract suite has **33 passing tests**. Storage, inference and query services are not claimed as complete; the next implementation step is M29-L0 plus M13/M14 append-only storage.

## 7. Indicative RA Work Plan

| Period | Focus | Output |
|---|---|---|
| Months 1-3 | WP1 and initial WP2 | Simulator, canonical store and belief baselines |
| Months 4-6 | WP2-WP3 | Negative evidence, habits, hidden events and adaptation study |
| Months 7-9 | WP4 and perception adapters | Closed-loop retrieval and oracle-to-noise evaluation |
| Months 10-12 | WP5 and benchmark consolidation | Embodied validation, benchmark package and manuscript |

## 8. Preparation and Collaboration Fit

My current independent research concerns replay-free analytic continual visual regression using frozen DINOv2 features and recursive second-order statistics. It has developed my experience in continual adaptation, stability-plasticity analysis, PyTorch/OpenCV implementation, experimental controls and ablation design. I can contribute 30-40 hours per week remotely to implementation, experiments, dataset generation and writing. A host group may connect one primary hypothesis to its existing expertise, datasets or robot platform while the shared CPSWM contracts preserve the complete long-term research direction.

## References

[1] Q. Gu et al., “ConceptGraphs,” *ICRA*, 2024. https://concept-graphs.github.io/  [2] A. Kurenkov et al., “Modeling Dynamic Environments with Scene Graph Memory,” *ICML*, 2023. https://arxiv.org/abs/2305.17537

[3] P. Liu et al., “DynaMem,” *ICRA*, 2025. https://arxiv.org/abs/2411.04999  [4] A. Anwar et al., “ReMEmbR,” *ICRA*, 2025. https://arxiv.org/abs/2409.13682

[5] M. F. Ginting et al., “Enter the Mind Palace,” *CoRL*, 2025. https://proceedings.mlr.press/v305/ginting25a.html  [6] B. Bogenberger et al., “Where Did I Leave My Glasses?” arXiv:2509.19851, 2025.

[7] D. Han et al., “LLM-Personalize,” arXiv:2404.14285, 2024.  [8] A. Ayub et al., “Interactive Continual Learning Architecture for Long-Term Personalization of Home Service Robots,” arXiv:2403.03462, 2024.
