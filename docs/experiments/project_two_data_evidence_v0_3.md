# Project Two data evidence batch v0.3

Status: materialized development evidence batch, 2026-08-24. This batch expands
data volume and factor coverage; it is not labeled as external or confirmatory
evidence.

## Materialized volume

- 80 episodes: 20 validation and 60 test.
- 2,560 temporal replay steps across 80 disjoint households, scenes, objects.
- 20 split-safe object families with repeated seeds per family.
- 1,718 delayed execution-feedback records and 842 missing-observation steps.
- Actor truth coverage: owner 1,840; guest 640; unknown actor 80.
- Mechanism truth coverage: direct relocation 2,186; handoff relocation 294;
  unknown mechanism 80.
- Dominant feedback outcomes: success 1,116; object slipped 602.

## Evidence separation

The runner materializes four files under
`artifacts/project_two_data/d0_multiseed_v0_3/`:

- `manifest.json`: split and content-hash bindings.
- `visible_replay.jsonl`: the only replay payload available to methods.
- `evaluator_truth.jsonl`: evaluator-only actor, mechanism, and location truth.
- `evidence_report.json`: volume, factor coverage, missingness, and gate results.

The full Structure Two route remains present: hidden-event inference,
multi-actor reasoning, open-world unknown mass, reversible attribution, and
embodied execution feedback. D1 simulator/annotated replay and D2 real-perception
replay retain the same typed import boundary; neither is claimed as loaded by
this D0 development batch.

## Reproduction

```bash
.venv/bin/python apps/evaluation_runner/run_project_two_data_evidence.py \
  --output-dir artifacts/project_two_data/d0_multiseed_v0_3
```
