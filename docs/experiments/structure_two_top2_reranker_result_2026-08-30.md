# Structure Two visible-only top-two reranker result

Date: 2026-08-30  
Protocol: `structure-two-reversible-multiaxis-top2-reranker@0.1`  
Artifact: `artifacts/project_two_v04_development/structure_two_top2_reranker_v0_1.json`  
Evidence status: development-only D0 synthetic validation; sealed holdout unopened

## Decision

The development gate passed. A two-head antisymmetric reranker, trained on disjoint development
seeds and restricted to the deterministic policy's existing top two candidates, reduced action
regret against both the deterministic Structure-Two readout and the previously frozen BrainCTL
matched reference.

This is positive evidence for the narrow claim that the current visible Structure-Two state
contains learnable action-ranking information. It is not evidence of real-world embodied
superiority, official BrainCTL reproduction, or paper-level novelty.

## Frozen phases

- Training: 8 new seeds across the 6 prior strongest-neighbor families.
- Calibration: 4 disjoint new seeds; used only to select search and put-back abstention thresholds.
- Validation: the 8 prior strongest-neighbor validation seeds across the same 6 families.
- Validation cluster unit: one seed averaged across all 6 families.
- Sealed strongest-neighbor holdout: not opened.
- Model supervision: immediate `H=1` action-regret difference, read only on training seeds.
- Inference: visible evidence cards and action-selected verification outcomes only; no evaluator
  truth field appears in the feature schema.

The fitted dataset contained 4384 swap-augmented pairwise examples: 2164 search examples and 2220
put-back examples. Calibration selected a search abstention threshold of 0.20 and a put-back
threshold of 0.35.

## Primary result

| Method | Action regret / step | Put-back error | Search error | Search path cost |
|---|---:|---:|---:|---:|
| deterministic conflict transition | 0.257812 | 0.068576 | 0.189236 | 1.263889 |
| reversible top-two reranker | **0.171007** | 0.067708 | **0.103299** | **1.177951** |
| frozen BrainCTL matched reference | 0.263021 | **0.052083** | 0.210938 | 1.284722 |

- Reranker minus deterministic: `-0.086806/step`, paired seed-cluster bootstrap 95% interval
  `[-0.106771, -0.062500]`.
- Reranker minus frozen BrainCTL: `-0.092014/step`, paired seed-cluster bootstrap 95% interval
  `[-0.118056, -0.061632]`.
- Relative to the earlier top-two oracle headroom of `0.168403/step`, this visible-only model
  recovered about 51.5% of the available validation headroom.

The result is not a search/put-back trade. Put-back error fell slightly, while most of the gain
came from reducing search error. The reranker emitted 122 swaps, 2147 keeps, and 19 abstentions.

## Family result

All values are reranker minus deterministic action regret per step; negative favors the reranker.

| Family | Difference |
|---|---:|
| high multi-actor contamination | -0.046875 |
| delayed identity correction | -0.098958 |
| open-world hidden event | -0.135417 |
| clean recurrent habit | -0.072917 |
| low-consequence location | -0.083333 |
| misspecified consequence | -0.083333 |

Every required-gain family improved and every prior guardrail-family margin held. The largest gain
occurred in open-world hidden events; no family reversed direction on mean validation regret.

## What the two heads learned

The search head placed its largest absolute weights on current observation, recency, reversible
mass change, habit-cause support, and the current action mass. The put-back head placed its largest
weights on action/base mass, habit-cause support, owner-identity support, recent frequency, and a
negative non-owner-identity contribution.

This division matches the intended separation: search is driven mostly by fresh location evidence,
while put-back is more conservative and uses owner-habit evidence. Nonzero weights are descriptive,
not a causal feature ablation; a grouped feature ablation remains necessary before claiming that
the multi-axis terms, rather than simple recency/history, are the source of the gain.

## Audit gates

All implemented audit gates passed:

- all seven existing operator receipts remained present;
- the reranker could only keep or swap the original top two candidates;
- swapping A and B exactly negated every feature contribution and the final score;
- deterministic Structure Two and BrainCTL consumed the same transformed visible stream;
- the feature firewall excluded evaluator/oracle/latent fields;
- no validation or sealed truth entered model fitting;
- the sealed holdout remained unopened;
- deterministic full recomputation reproduced artifact SHA-256
  `b99901fbc5282ceedfd49f30019d5917ab49100025b9f0c55d6854cd4170b129`.

Focused regression: 18 tests passed across the reranker, action-information diagnostic,
strongest-neighbor gate, and transition/reactivation gate. Ruff passed on all new Python files.
Targeted mypy found no new error in the reranker module after its local fixes, but the imported
pre-existing Structure-Two modules still expose 39 strict-mode errors, so repository-wide mypy is
not clean evidence for this run.

## Remaining falsifiers

1. Grouped feature ablation: compare rank-only, location-history, and full multi-axis evidence
   under independently calibrated thresholds.
2. Distribution shift: generate families not sharing the same frozen scenario parameters as
   training and calibration.
3. Sealed strongest-neighbor gate: open only after the ablation and shift checks are frozen.
4. Longer-horizon counterfactual: requires a simulator where the selected action changes future
   observations; the current replay supports an exact immediate label but not an honest `H>1`
   causal label.
5. External embodied evidence: repeat with real or externally generated perception and execution
   traces before making a real-world superiority claim.
