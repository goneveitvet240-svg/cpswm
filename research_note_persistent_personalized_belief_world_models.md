# Continual Personalized Semantic World Models for Long-Term Household Robots

**Pang Wei — Qingdao University**  
**One-page project overview for potential remote research collaboration**  
**Email:** m15964096907@outlook.com

## Project Vision

This project aims to build a household robot that can continuously observe, understand, and assist within the same home over weeks or months. Instead of treating every task as a new episode, the robot maintains a persistent model of specific people, objects, places, activities, relations, and events—and continually revises that model as the household changes.

For example, when asked, **“Please bring me the cup I used yesterday,”** the robot should distinguish the intended cup from visually similar cups, reconstruct who used and moved it, estimate its current location under partial observation, actively search when evidence is insufficient, retrieve the correct instance, and record the state changes caused by its own actions. The same world model should support historical questions, current-state estimation, habit prediction, navigation, manipulation, and long-term assistance.

## Core Capabilities

1. **Instance-level memory:** distinguish and track concrete objects across rooms, sessions, occlusion, and appearance changes.
2. **Personalized relational memory:** learn person-specific owner–object–activity–location–time patterns while separating routines, anomalies, guests, and habit changes.
3. **Temporal and hidden-event reasoning:** represent observed, reported, inferred, and robot-executed events while preserving alternative explanations for unobserved transfers.
4. **Probabilistic state maintenance:** combine positive and negative evidence, event history, and personalized priors into competing hypotheses about identity, location, ownership, and state.
5. **Language-to-action access:** answer evidence-grounded questions and use uncertainty to drive active search, navigation, manipulation, replanning, and action-result write-back.
6. **Continual adaptation:** consolidate useful patterns, detect household changes, withdraw unsupported beliefs, and prevent old errors from contaminating future memory.

## Technical Framework

The architecture contains six layers and 32 replaceable modules: **(1)** contracts, identity, time, storage, and runtime; **(2)** embodied perception, SLAM, 3D mapping, visibility, instance association, people, and interaction events; **(3)** relation and event memory, provenance, belief projection, personalized routines, hidden-event inference, and memory lifecycle; **(4)** structured query, language grounding, explanation, and correction; **(5)** task planning, active search, navigation, manipulation, replanning, and write-back; and **(6)** long-horizon simulation, synthetic routines, governance, benchmarking, and deployment evaluation.

The canonical memory is an append-only log of `RelationAssertion`, `EventRecord`, and provenance records. Each record distinguishes **valid time** (when something held in the world), **observed time** (when it was learned), and **recorded time** (when it entered the system). Evidence reliability is kept separate from posterior probability. A rebuildable **derived belief projection** maintains the current multi-hypothesis state, while a shared observation-likelihood model supports both negative-evidence updates and information-gain-based search.

## Initial End-to-End Study

The first vertical study follows a concrete household object-transfer scenario:

```text
synthetic human routine → person moves a specific cup → partial robot observations
→ append-only relation/event memory → hidden-transfer hypotheses
→ current location posterior → natural-language query → active search
→ negative evidence and replanning → retrieval/manipulation → action write-back
```

A symbolic simulator will generate reproducible routines, object movements, missed observations, occlusion, delayed reports, similar objects, guests, and habit changes. Baselines will include latest-observation memory, category-level memory, and episodic scene-graph retrieval under matched observation budgets. Evaluation will cover correct-instance success, Recall@k, search and action cost, incorrect-object rate, event/location accuracy, calibration, adaptation delay, explanation validity, and task success.

## Current Status and Collaboration Interest

The system architecture and interfaces are defined. An executable Python contract layer covers temporal assertions, events, belief snapshots, observation likelihoods, provenance, query budgets, corrections, checkpoints, and ground-truth isolation, with 33 passing tests. The next stage is the simulator, append-only relation/event storage, belief projection, and the end-to-end experiment above.

[*Enter the Mind Palace*](https://proceedings.mlr.press/v305/ginting25a.html) provides an important connection through multi-episodic scene-graph memory, active retrieval, and Long-term Active EQA. This project studies how episodic experience can participate in a continuously maintained, person-specific world model supporting instance identity, hidden events, manipulation, write-back, and adaptation.

I am seeking a **remote research collaboration** on concrete questions within this system and can take primary responsibility for implementation, experiments, documentation, and asynchronous coordination. I would particularly value discussion on connecting episodic world instances with persistent belief maintenance, selecting fair baselines, and evaluating whether memory improvements produce embodied task utility.
