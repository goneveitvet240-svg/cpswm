# Structure Two v0.4 instrument repair and post-repair adversarial audit

Date: 2026-08-31

## Outcome

The train-only rolling reference still passes, but its evidential status has
been corrected from a false pre-run freeze claim to **retrospective exploratory
train evidence**. No v0.4 validation world, Gate B arm, or method comparison was
run.

Binding train readings:

- outer-CV mean search top-1 gain: `0.04522087598641957`;
- worst held-out fold gain: `0.03770624346913029`;
- put-back visible-history gain over sticky: `0.2651452409801924`;
- put-back context gain over pooled: `0.08341821961713758`;
- formal pooled-tail path-cost gain: `0.014315358162354104`;
- admitted weekday/weekend visible-owner observations per rollout:
  `89.91666666666667` / `31.569444444444446`;
- active weekday/weekend context samples per unobserved prediction:
  `9.900621563086936` / `3.3596206102803765` for the outer-CV readings.

The formal evaluator still uses complete-rollout encounter order. A new
report-only causal-prefix sensitivity on the final train configuration gives
search top-1 gain `0.045589237738769745`, only `0.00018312081248446355`
below the formal reading. This does not turn the offline convention into an
online information claim.

## Repairs

1. Train evidence is explicitly retrospective. The design, report, and draft
   no longer claim that the horizon/grid/folds were frozen before the first
   train outer-CV run.
2. Every trust-boundary verification recomputes deterministic evidence. A
   self-rehashed train artifact is not accepted by the finalizer, validation
   loader, or verification CLI.
3. The old failed horizon-probe artifact remains byte-identical. Its exact
   historical gate source was recovered and archived at the SHA-256 named by
   that artifact; the evolved development source is no longer misdescribed as
   its execution source.
4. Seed attestation now binds the exact validation DRAFT hash, train artifact,
   validation seeds, disclosed train split, prior validation split, and all
   sealed commitments. Raw holdout seeds must be disjoint from every disclosed
   public split.
5. Custodian key id, public-key hash, and user approval id must be recorded in
   the DRAFT before the custodian signs. The finalizer no longer accepts trust
   anchors or approval ids from command-line overrides. User approval is
   explicitly recorded as an identifier, not misrepresented as a digital
   signature.
6. Gate A now records the exact ordered rollout ids and scored step counts.
   Gate B requires exactly ten non-oracle arms, the same ordered rollout set,
   exact step coverage, the same Gate A hash, and the same frozen manifest.
7. Every Gate B trace requires an Ed25519 signature under a separate trace
   domain from the preregistered custodian key. Before signing, the custodian
   tool independently regenerates that arm from the frozen source bundle and
   requires a step-for-step match. All arms must share one producer run id and
   one producer source-bundle hash.
8. Attestation, frozen-manifest, validation, signed-trace, and dual-gate outputs
   refuse accidental overwrite.

## Adversarial audit round 1: provenance and forgery

Attacks and outcomes:

- change train gain to `999`, recompute the artifact's internal hash: rejected
  by deterministic recomputation;
- change the user approval id after the custodian signed the draft: rejected by
  the signed DRAFT SHA-256 binding;
- supply trust-key material through the finalizer CLI: impossible; those CLI
  options no longer exist;
- collide raw holdout seeds with train, old validation, or new validation:
  rejected;
- fabricate complete but different Gate B traces and self-rehash them: rejected
  by the external trace signature;
- hand fabricated unsigned traces to the legitimate custodian for signing: a
  later audit exposed this second-order gap; the custodian signer now
  independently reruns the frozen arm and rejects any differing sequence;
- edit a signed trace and self-rehash it: rejected by Ed25519 verification;
- sign fabricated traces with an attacker-selected key: rejected against the
  preregistered trust anchor.

## Adversarial audit round 2: statistical and semantic robustness

- 200 deterministic random balanced four-fold assignments:
  - outer mean gain range: `[0.04240893037861323, 0.04577235855125421]`;
  - worst-fold range: `[0.028479728453153875, 0.044528385536306725]`;
  - failures below mean `0.02`: `0/200`;
  - failures below worst-fold `0.018`: `0/200`.
- leave-one-world-out selection:
  - mean gain: `0.04577235855125421`;
  - minimum held-world gain: `0.022189349112426038`;
  - held worlds below `0.02`: `0/24`.
- every non-duration world-distribution field still equals v0.2;
- the exact ten-arm set equals the non-oracle `NeighborArm` set;
- analytic world-level error remains seed invariant;
- the encounter-order causal-prefix sensitivity remains above the train
  threshold;
- Gate A and Gate B runners both fail closed while their signed prerequisites
  are absent.

The earlier targeted post-repair suite passed `65` tests. After the official
world-rollout adapter and custodian recomputation repair, the expanded relevant
suite passed `105` tests and all touched files pass `ruff check`. The train
artifact was independently recomputed after the earlier suite. After adding
the Gate-B materiality criteria and binding external verification actions into
each prediction token, an additional gate-focused suite passed `76`
tests and the touched gate files again passed `ruff check`.

## Current fail-closed status

The official v0.4 arm adapter is implemented. It projects the world rollout to
the replay firewall without reapplying legacy family perturbations, exposes the
complete known-location catalogue explicitly, and uses one preregistered
unit-cost configuration only for Gate-B distinguishability. The complete
producer/custodian-recomputation bundle covers `236` files and is frozen at
`5c0240d16ad24d8cad2dd4d96263615f1e9890ba510fd131491057e45a48064d`.

Gate B now rejects merely cosmetic arm differences. In addition to exact trace
collisions, every declared arm pair must disagree on at least `0.01` of scored
predictions, and at least `0.20` of validation episodes must contain more than
one arm trajectory. These are preregistered author-chosen materiality thresholds
reused from the corrected-instrument validity audit; they establish neither
adapter fidelity nor method efficacy.

Each Gate-B step token now also binds whether the model selected and executed a
physical verification, in addition to the put-back and first-search locations.
Internal promote/escrow bookkeeping is not counted as an external action.

The DRAFT remains **not ready to sign** for one external reason: the repository
does not contain the original 24 raw v0.2 holdout world seeds, their evaluator
custody salt, or an independently held user-approved Ed25519 key. All eight
other sealed-seed files in the repository reproduce zero of the v0.2 world
commitments. This search is recorded in
`artifacts/project_two_v04_development/structure_two_custody_material_preflight_2026-08-31.json`.

Until the original custodian supplies those materials, the final manifest
cannot be created. Therefore the
following files correctly do not exist: the final v0.4 manifest, the seed
attestation, the validation Gate A artifact, and the dual-gate authorization.
Method comparison remains forbidden.

The Gate B trace signature proves custody, integrity, and exact agreement with
execution of the frozen adapter. It does not prove that matched external arms
reproduce official external code, nor does Gate B establish method efficacy.

## Hashes

- train design file: `ae538b466102a5b8282c24ab251989bf5f51e16451b1ffc9960736c09233e9f7`;
- train artifact file: `8db810c5e02e0d4d6098dba957dcfc7568477e7ede2a0d3867ab8bbfad8ad752`;
- train artifact content: `b231e30fcd6a61e8138fddf834fc94b06bcb205f88562522e5bf361250298470`;
- current unsigned DRAFT file: `8093c7631678d471be65e1b5ae3917a69a0a3901e90b8c55fd437ecc84b9cdad`;
- frozen arm producer/custodian source bundle: `5c0240d16ad24d8cad2dd4d96263615f1e9890ba510fd131491057e45a48064d`;
- preserved failed v0.3 artifact file: `d62a18086e6ab49a93d9f43c65ab116376960c10aed41d8bf492463686cbd130`;
- archived exact v0.3 gate source: `8b8b9010ce219b32750446271778a78c0378ca7b930bc389d29418a59d6529f7`.
