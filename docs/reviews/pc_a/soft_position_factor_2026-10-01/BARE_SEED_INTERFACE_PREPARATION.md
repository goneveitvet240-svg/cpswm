# Bare-seed diagnostic — interface preparation only

**Plan/interface preparation, not implementation, new R1, or a real-data result.** Read-only inspection is bound to clean worktree `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`, HEAD `1bd6c204d349024196c23df12cca61dbcea91e6c`. No model, experiment, pytest, SDK or Unity invocation was made. No production code or sealed `LogWeightR1` evidence was changed. The only output of this task is this document.

This follows `BARE_SEED_DIAGNOSTIC_PLAN.md`: keep the fixed 96 frames, train houses 1–8, exposed validation houses 9–12, complete grids and VOID cases, two SDK references, and frozen soft/uniform outputs. It proposes no formal estimator/reference selection. The current round's R2 and delivery must finish before implementation and execution under a new review gate.

## 1. Exact public seed → original world point

The implementation field is **`world_points_m`**, not `world_points`. Its source is [soft_surface_position.py:152](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/src/cpswm/data_preflight/soft_surface_position.py:152).

| Entry | Exact field/path | Meaning/check |
| --- | --- | --- |
| Public frame identity | `public['input_sha256']` and `public['provenance']` | Digest of camera, RGB/depth array hashes, original provenance and all canonical candidate rows; not just a filename |
| Canonical neighborhood | `public['neighborhoods'][j]` | Locate by exact `neighborhood_id`; IDs must be unique |
| Original complete grid | `neighborhood['pixels_uv']` | Canonical grid order, including invalid pixels; not pixels selected from a mask |
| Original point array | `neighborhood['world_points_m']` | Same-length array as pixels; each valid entry is `camera.world_point(u,v,depth[v,u])`, invalid entry is `None` |
| Other aligned arrays | `valid`, `rendered_depth_m`, `rgb_values` | Require aligned lengths; retain full original support |
| Seed row | `public['seeds'][i]` | `seed_id`, `measurement_id`, `neighborhood_id`, `pixel_uv`, `valid`, `reason`, `coefficients`, `sources` |
| Bare point lookup | `neighborhood['world_points_m'][index_of_exact_seed_pixel]` | Exactly one matching pixel within that seed's complete neighborhood; fail for missing/duplicate mapping |

For every seed, verify the original chain using the existing canonical digest:

```text
input_sha256 == content_sha256(public.provenance)
neighborhood_id == content_sha256({input_sha256, pixels: neighborhood.pixels_uv})
seed_id == content_sha256({neighborhood_id, seed_uv: seed.pixel_uv})
seed.measurement_id == seed.seed_id
seed.valid == neighborhood.valid[matching_index]
```

The public validity rule is exactly finite rendered depth with `0 < depth < far_plane_m - near_plane_m` ([line 158](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/src/cpswm/data_preflight/soft_surface_position.py:158)). An invalid seed remains a row with `available=false`, `reason='invalid_depth'`, and bare point `None`. Do not expand a narrow box, replace depth, move to a nearby valid/masked pixel, add a near-plane offset, or use a different pinhole formula. Copying the verified original point avoids changing the established camera/depth convention.

The canonical order is sorted complete grids followed by their grid pixel order. Preserve the original `public['seeds']` order and the house/frame order; do not sort by error, masks, object ID or hashes. Empty grids/candidate frames remain in the 96-frame schedule.

The low-level public entry is [soft_position_dataset.public_readout](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/soft_position_dataset.py:26), which calls `_recheck_public(record)` and then `readout_frame`; it accepts no labels. `_recheck_public` reconstructs from the original command, delivery and detector outputs and checks the RGB-D/camera/candidate/feature arrays ([instance_affinity_dataset.py:196](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/instance_affinity_dataset.py:196)).

## 2. Exact label pairing; no estimator multiplicity in the denominator

**In this frozen implementation, soft and uniform have the same `measurement_id`, not different IDs.** `seed.measurement_id=seed_id` at [soft_surface_position.py:211](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/src/cpswm/data_preflight/soft_surface_position.py:211); each of the two observations also sets `measurement_id=seed_id` at [line 224](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/src/cpswm/data_preflight/soft_surface_position.py:224). `label_readout` copies that exact ID at [soft_position_dataset.py:131](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/soft_position_dataset.py:131).

Each parent label has exactly these ten fields:

```text
measurement_id, seed_id, estimator, eligible, void_reason,
object_id, targets, pixel_uv, house_index, split
```

For each seed require one `soft_affinity` and one `uniform` observation and label, joined by **`(measurement_id, estimator)`**, not by array index alone. Require all nine other label fields to agree exactly: `measurement_id`, `seed_id`, `eligible`, `void_reason`, `object_id`, `targets`, `pixel_uv`, `house_index`, `split`. Also require both IDs equal the original seed ID, the label pixel equal `seed.pixel_uv`, and each observation's action/frame/time/domain match the parent public frame. The two public `world_point_m` values and `estimator_pin` values are legitimately different and must not be compared as identical.

Build one estimator-independent supervision row per original seed only after those checks. Do not remove `measurement_id` to make mismatched records agree. A differing ID, reference, eligibility or reason is a failure, not a reason to pick one copy. Check `private['input_sha256']`, `readout_sha256`, `action_id`, house/split and private lineage against the verified parent. Available eligible rows require both references to be finite 3-vectors; unavailable/VOID rows retain the reason and absent targets as in the parent.

The two references are **`sdk_transform_position_m`** from SDK `objects[].position` and **`sdk_aabb_center_m`** from `objects[].axisAlignedBoundingBox.center`. They are distinct reference conventions, not interchangeable centre truth. Label priority is invalid depth → ambiguous membership → unmapped pixel → ineligible instance. A unique eligible mask connection is rendered seed membership, not proof of physical depth ownership.

Parent labels contain two estimator copies; `void_counts` explicitly has unit `estimator_observation`, while `seed_void_counts` divides by two ([soft_position_dataset.py:157](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/soft_position_dataset.py:157)). New comparison counts must be recomputed from validated unique seed rows, not by summing the old label list or blindly dividing possibly malformed counts.

## 3. Preserve the original sampling unit

- Identical complete grids across detector candidates collapse to one neighborhood and one set of seeds; all candidate `method/id/box` sources remain in `sources`. Do not multiply by the number of candidate sources.
- The same `(u,v)` in different complete grids has different neighborhood/seed IDs and remains separate under the original protocol. Do not merge by pixel, object, or equal point values. Record unique `(action_id,u,v)` additionally to expose this correlation, without changing the training/sample cohort.
- Uniform often repeats the same representative for many seeds in a neighborhood. Those seed rows stay in the matched descriptive comparison; repeated world coordinates are not new independent evidence and are not grounds for deduplication or significance calculations.
- Keep the original measurement ID across bare/soft/uniform. Serialized comparison-row identity can be `(method, reference_kind, measurement_id)`, but the seed denominator is the unique `measurement_id` cohort, not three methods × two references.
- Require identical ordered eligible measurement IDs, object-frame membership and house membership for all three methods and both references. Preserve all original VOID rows outside the eligible fitting/scoring cohort. Do not select the intersection after observing errors or silently drop an estimator's failures.

Existing `paired_rows` makes one row per chosen estimator, and its member recipe is useful ([run_soft_position_development.py:207](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/run_soft_position_development.py:207)): `frame_sha256=content_sha256(public_metadata)`, `object_sha256=content_sha256((house_index, object_id))`, original `input_sha256`, plus a label digest binding private references, instances and lineage. For new bare rows, retain the old public input identity and separately bind the bare definition/output; do not pretend a new method name recreates an old estimator model pin. Save a shared cohort identity independent of estimator-specific label-row digests. In the saved public JSON, that exact frame metadata digest is already `public['provenance']['provenance']['source_sha256']`; the double `provenance` nesting is intentional (`input_binding` contains the owner provenance dict). Verify it through the parent fresh path rather than inventing a replacement digest from a smaller row. The camera and scene binding are in `public['provenance']['camera']`.

## 4. Standalone schema is necessary

Both [position_observation_model.py:28](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/src/cpswm/perception_mapping/position_observation_model.py:28) and `soft_surface_position.py` restrict `ESTIMATORS` to `soft_affinity, uniform`. `position.fit/restore` validates that enum. [position_factor_diagnostic.py:22](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/position_factor_diagnostic.py:22) constructs four combinations from it; `_public_records` requires paired two-estimator rows and then selects only the first available seed. It is not an all-seed comparison API.

Therefore do not add `bare_seed` to old enums, call `position.fit(..., estimator='uniform')` with bare inputs, modify the old diagnostic to accept triples, or serialize a bare model as an existing native checkpoint. The minimal separate artifact has its own schema, method definition/pin, two named reference moment models, and explicit `runtime_authority=false`, `calibrated=false`, `natural_world_identity_authority=false`. It need not invoke `position.condition`, native receipts or controlled consumption at all.

The standalone descriptive fit should implement the already declared rule, matching [position.fit](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/src/cpswm/perception_mapping/position_observation_model.py:183): finite float64 residuals `bare_point - reference`, at least 4 train rows, mean bias, full covariance `centered.T @ centered / (n-1)`, rank 3 and positive definite. Numerical/rank/PD failure is saved as `fit_failed` with the actual arrays, reason and denominators. Do not fabricate covariance or catch unrelated provenance/schema errors as an ordinary fit failure. This is small separate descriptive math; changing the production enum to reuse its wrapper would change authority and scope.

`metric` and `summarize_rows` document the current descriptive formulas ([driver:250](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/run_soft_position_development.py:250), [driver:287](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/run_soft_position_development.py:287)). Follow those exact raw/corrected Euclidean RMSE, axis RMSE, median/max and object-frame summaries. If likelihood columns are kept, they use each train covariance and are descriptive. Missing models leave corrected results unavailable; they do not remove raw eligible rows or cause a new subset to be chosen. Parent soft/uniform models and corrected rows must remain frozen, not refitted under the bare schema.

Suggested minimal function boundary: a public-only extractor from a verified readout, a strict common-label join, a train-only standalone moment fit, and a driver that generates all 96 public bare rows before private fitting/evaluation. This is a proposed implementation boundary, not code delivered here.

## 5. Parent external pin and historical fresh verification

There is no existing `verify_position_parent` function. `run_soft_position_development.verify_controls` is the closest pattern, but the new verifier must validate **the position parent's own ledger and schema**, not call the controls verifier on a position directory.

Require a caller-supplied SHA-256 of the parent `case-results.json`, a matching historical position source checkout and interpreter, and the original upstream pins/paths. The new code must:

1. Verify exact ledger bytes against the caller's pin; require run/verify phases, strict integer zero exit codes, one exact 40-hex source SHA, complete equal output maps, and no silent bool/int equivalence.
2. Verify the full 302-member parent experiment inventory. Its expected shape is 96 × `{public.json, labels.json, corrected.json}`, four model JSONs, eight training residual/member files, `controlled-position-consumption.json` and `report.json`. Even `fit_failed` cases keep their model status files and training arrays.
3. Verify `soft-surface-position-development@1`, exact model/reference identities and schedule, `report.members`, strict false authority flags, and `report.source_files == source_identity(matching_historical_position_source)`. Check parent `parent_binding` against the externally supplied controls, affinity, frontend and capture pins.
4. Reconstruct a closed, explicit argv for the historical **`tools/run_soft_position_development.py --verify`**. Use that source as cwd/PYTHONPATH; preserve `.absolute()` interpreter entries rather than resolving away virtual-environment launchers. Do not blindly execute arbitrary saved argv from a ledger.
5. Pass the original controls/affinity/frontend/capture sources and ledgers, collection inventory pin, dataset archive, SDK interpreter and binary arguments. The historical main ([line 555](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/run_soft_position_development.py:555)) recursively invokes `fresh_controls`, verifies the other parents, reconstructs all public pixels/pairs/readouts, refits train residuals, and compares all saved bytes through `save_or_verify`.
6. Require child exit 0, and recheck all parent inventories/source identities/pins afterward. A child's printed success is insufficient. Run/fresh comparison must use independently reconstructed new bare artifacts, not trust a self-signed saved report/model.

The parent ledger will be created only after the current round's successful actual run and fresh verify; do not substitute the controlled R1 ledger, invent its future hash, or infer success from the frozen source alone. The current `SO/run_experiment.py` shows how run/verify output maps are recorded; it has not been executed for this interface task.

Historical fresh verification may read private evaluation files. The new diagnostic's declared order is about data passed to public extraction and when the new predictions are computed; it is not malicious-process or filesystem isolation. It must not claim that the entire program has never read validation labels.

## 6. Minimum retained originals and output evidence

For pure extraction/scoring after a trusted fresh parent verification, the numerical minimum is the verified public readouts, all original paired labels, frozen parent models/corrected rows, frame identities, and the external parent pin. That is not sufficient for independent fresh provenance verification on its own.

Keep accessible for a reproducible verifier:

- Parent position `case-results.json` and all 302 experiment files, matching source map/checkout and historical interpreter.
- Full original collection inventory/configuration, per-house capture provenance and eight command/delivery state files, with the original RGB/depth/camera payloads. Keep the complete capture archive, including initialization/warm-up material; do not trim it to only the 96 public views.
- Original detector/frontend outputs and source, affinity/controls outputs and source, and their caller-pinned ledgers. Preserve complete candidate grids and sources, not only successful matched objects.
- Private SDK event metadata, instance catalogs/colors/masks/segmentation and RGB-D originals, plus complete runtime partition/asset eligibility audit. `private_readout` maps public local frame `t` to SDK index `t+4` ([driver:130](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/tools/run_soft_position_development.py:130)). All invisible/ineligible/unknown instances remain in the provenance audit.
- Source archive, capture-source verification code and SDK/binary identity dependencies used by the historical verifier. No new acquisition or Unity run is implied by retaining these inputs.

Minimum new artifact evidence: fixed definition/config and source map; full parent binding and member map; one bare public row for every original seed including unavailable rows, with neighborhood/pixel lookup; shared cohort/label join records; all train residual arrays and member identities for both references; fitted standalone models or explicit failure files; all corrected public rows; split/house/object-frame metrics and full denominators; complete byte inventory; actual run/fresh argv, exits and logs. The new verifier must reject extra/missing files, re-signed wrong points/labels/models/reports and changed parent/input pins, while a lawful run and lawful fresh recovery still pass.

## 7. Denominators to save explicitly

Keep these for every frame, all 12 houses, both splits, each reference and each reported method where applicable:

- Scheduled/processed frames; frames with no candidates, no grid pixels, no depth-valid seed and no eligible seed. An empty stratum stays as an explicit zero with null metrics.
- Candidate-source count; unique complete neighborhood count; total canonical seed measurements; unique `(action_id,u,v)` pixels as an additional correlation audit; publicly valid/invalid seed counts.
- Unique eligible seed count; exclusive VOID reason counts summing to total seeds minus eligible seeds; original estimator-observation label count reported separately (2 × seeds), never used as the sample count.
- Eligible distinct frames, object-frame pairs, house-qualified objects and houses; ordered measurement cohort digest, per-object-frame membership/counts and per-house cohort digest. Keep original input/frame identities and label-lineage digests.
- Train row count for each fit, contributing frames/object-frames/objects/houses, rank/PD status, exact residual/member hashes; separate model availability/failure count. No independent-sample claim follows from seed count.
- Raw evaluable seeds and corrected evaluable seeds/model availability, with identical eligible cohorts for all successful methods. A failed correction is reported missing, not a new filtered cohort or an estimator winner.

The existing train `_members` denominator contract is at [position_observation_model.py:117](/private/tmp/cpswm-pc-a-soft-position-factor-20261001/src/cpswm/perception_mapping/position_observation_model.py:117); its unique measurement check applies separately per method fit, not to a flattened three-method list. Counts and cohort hashes should be both saved so equal totals cannot conceal exchanged houses, object IDs or seeds.

This preparation used no actual validation scores and selected no model, reference, threshold, outlier rule or scientific conclusion. The bare comparison, archive-to-native bridge and future owner raw-capture transactions remain separate planned work with their own evidence requirements.
