# Structure Two action-information upper-bound diagnostic

Date: 2026-08-29  
Protocol: `structure-two-action-information-upper-bound@0.1`  
Artifact: `artifacts/project_two_v04_development/structure_two_action_information_upper_bound_v0_1.json`  
Evidence status: exploratory validation-only oracle diagnostic; not a method result

## Decision

The diagnostic does **not** support adding another actor-only mechanism or a gate that chooses
among the five existing transition/consolidation policies.

The measurable headroom is concentrated in the final action ranking:

- the correct owner-habit target was already in the deterministic trace's top two candidates on
  `1121/1152` steps;
- the correct current search location was already in the top two on `1080/1152` steps;
- a truth-owned oracle allowed only to reorder those top-two candidates reduced action regret by
  `-0.168403/step`, with paired episode bootstrap interval
  `[-0.192708, -0.144097]`;
- the oracle intervened on only `166/1152` steps.

This means the current representation often retains the correct candidate but lacks a validated,
visible-only signal for ordering the leading alternatives. It does not show that a learned
reranker can recover the oracle benefit.

## Frozen source and scope

- Reused the six strongest-neighbor families and eight prior validation seeds: 48 episodes and
  1152 steps.
- Reused the previously selected parameters without retuning:
  `brainctl_matched=0.75` and Structure-Two profile `responsive`.
- Used the same frozen action evaluator and the same transformed visible stream for every
  non-oracle policy.
- Did not open or consume the sealed holdout seeds.
- Retained the complete Structure-Two runtime and all seven operator receipts in the underlying
  policy states. Oracle arms are evaluator-owned diagnostics only.

## Overall action-only results

| Arm | Action regret / step | Put-back error | Search error | Interpretation |
|---|---:|---:|---:|---|
| `brainctl_reference` | 0.263021 | 0.052083 | 0.210938 | prior strongest matched neighbor reference |
| `deterministic_conflict_transition` | 0.257812 | 0.068576 | 0.189236 | best fixed Structure-Two operator policy |
| `top2_readout_oracle` | 0.089410 | 0.026910 | 0.062500 | truth may only reorder current top two |
| `true_actor_oracle` | 0.270833 | 0.075521 | 0.195312 | actor posterior alone is replaced by one-hot truth |
| `owner_habit_target_oracle` | 0.189236 | 0.000000 | 0.189236 | only put-back target is supplied |
| `search_location_target_oracle` | 0.068576 | 0.068576 | 0.000000 | only current search target is supplied |
| `existing_operator_selector_oracle` | 0.257812 | 0.068576 | 0.189236 | truth selects among five existing policies |
| `full_action_oracle` | 0.000000 | 0.000000 | 0.000000 | sanity upper bound |

The deterministic transition arm differed from `brainctl_reference` by `-0.005208/step`, with
interval `[-0.013889, +0.001736]`. This is a validation-only action comparison and does not reverse
the prior sealed strongest-neighbor failure.

## Source-isolation comparisons

All differences are oracle minus deterministic; negative values favor the oracle.

| Information intervention | Mean difference | 95% paired episode interval | Result |
|---|---:|---:|---|
| top-two action reorder | -0.168403 | [-0.192708, -0.144097] | large ranking headroom |
| true actor only | +0.013021 | [+0.003472, +0.024306] | no actor-only headroom |
| true owner-habit target | -0.068576 | [-0.085938, -0.052083] | put-back target headroom |
| true current search target | -0.189236 | [-0.216146, -0.164062] | search target dominates headroom |
| best per-step existing operator vs best fixed operator | 0.000000 | [0.000000, 0.000000] | no policy complementarity |

The true-actor intervention read actor truth on 1144 steps but changed only 19 action decisions.
Its harmful result must not be interpreted as proof that actor information is irrelevant: replacing
only actor creates an off-manifold combination with unchanged identity, cause, and regime beliefs.
It does show that actor truth alone is not a sufficient fix for the current coupled runtime.

The operator selector chose deterministic conflict transition on all 1152 steps. Therefore there
is no retrospective one-step action headroom from learning when to switch among the five already
implemented sequential, quarantine, transition, reactivation, and joint policies on this replay.

## Family breakdown

| Family | Deterministic | Top-two oracle | True-actor oracle | Search-target oracle | Owner-target oracle |
|---|---:|---:|---:|---:|---:|
| `high_multi_actor_contamination` | 0.1979 | 0.0833 | 0.1979 | 0.0573 | 0.1406 |
| `delayed_identity_correction` | 0.3802 | 0.1458 | 0.4062 | 0.1250 | 0.2552 |
| `open_world_hidden_event` | 0.4479 | 0.1719 | 0.4792 | 0.1354 | 0.3125 |
| `clean_recurrent_habit` | 0.1042 | 0.0052 | 0.1042 | 0.0104 | 0.0938 |
| `low_consequence_location` | 0.2083 | 0.0573 | 0.2188 | 0.0417 | 0.1667 |
| `misspecified_consequence` | 0.2083 | 0.0729 | 0.2188 | 0.0417 | 0.1667 |

The ranking headroom appears in all six families and is largest in delayed identity correction and
open-world hidden events. The actor-only intervention does not repair either family.

## What this rules out and what remains unresolved

This diagnostic rejects, for the current validation replay, the immediate claims that:

1. perfect actor attribution alone would repair Structure Two;
2. a learned gate over the existing memory/transition policies has latent one-step action value;
3. another consolidation or reactivation weighting scheme is the evidenced next mechanism.

It leaves one narrower hypothesis:

> A visible-only decision rule may be able to choose between the leading two action candidates
> better than the current deterministic readout.

The oracle result is only an upper bound. The cheapest next falsifier would train a small top-two
pairwise reranker on disjoint development seeds, using only visible belief features, and require a
held-out action-only improvement over both deterministic transition and an independently retuned
strong neighbor before any new sealed test is opened.

## Truth and external-validity limitations

The evaluator exposes `true_actor`, `true_mechanism`, `true_location`, and
`true_owner_habit_location`. It does not expose true identity match, change cause, regime change,
or regime identifier. Those missing oracle axes were not fabricated and remain unresolved.

All 48 episodes are D0 synthetic replay. No claim about real embodied perception, query cost,
robot execution, or paper-level novelty follows from this result.

## Verification

- New tests: `tests/test_structure_two_action_information_upper_bound.py`.
- Relevant regression suite: 14 tests passed across the new diagnostic, strongest-neighbor gate,
  and transition/reactivation gate.
- Artifact hash verification passed.
- Full deterministic recomputation passed with content SHA-256
  `13cafbd8305a8b1c28369b96d6331f461204e9ef8e799dd606d72b8acbe61d37`.
