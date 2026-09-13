# Independent second review — person interaction evidence

Initial inspected SHA: `cf81e207de29971981ce6eafd845e1599a32de23`, `/private/tmp/cpswm-pc-a-person-evidence-20260914`.

## Initial findings

1. P2 — Association accepts invalid causal visual times. Its datetime comparisons neither require awareness nor normalize UTC. Both a fully naive time triplet and a DST-fold triplet with capture occurring one actual hour after arrival pass and commit association state. Require aware datetimes and compare UTC instants before mutation.
2. P2 — Calibration constructor validation is not enforced at the public fit boundary. A previously valid frozen CalibrationExample forcibly changed to annotation_source='prediction' is fitted normally. Invalidated instances should be revalidated at fit/evaluation boundaries. This does not imply the module can authenticate caller claims of independent annotation; the finding is a bypass of its explicit synthetic/prediction label rejection.
3. Source evidence gap — Initial fixed CLI source emitted no executing code SHA/file hashes; its source_sha256 referred to video bytes only. Such output cannot independently bind this result to a code version. Source evidence should explicitly state its actual scope and not claim full runtime attestation.

Independent initial tests: **3 failed, 2 passed in 0.41 s** (`test_independent.py`, `initial_stdout.txt`, `initial_junit.xml`). Synthetic fixture helpers are reused only to construct records; attacks/assertions are independently authored. Geometric ambiguity branches retain distinct IDs and alternatives; a long gap creates new unverified tracks. Same-input holdout leakage rejects even with renamed sequence; disjoint fixture holdout evaluates legally.

## Actual CLI run during repair

`probe_cli.py` ran the actual pinned detector on a 200x200 crop of one sampled frame from the supplied public video, from foreign cwd. It produced four person-category candidates, zero roles, unchanged core, zero writes/actions. However the production files were being repaired during this run: output explicitly shows `git_dirty=true` and new code-identity fields absent from initial fixed source. This is repair-time diagnostic evidence only, not a frozen-cf81 acceptance result. Final fixed-source verification is required.

The deliberately explicit example.org source label in this probe is not an authenticated source URL assertion; video bytes were pinned independently by hash. It demonstrates caller-supplied provenance labels remain a trust boundary.

## Scope

Association is geometric sequence-local identity hypothesis only. Roles are unordered/ordered bbox overlap candidates, not contact, release, causal transfer, household person identity or calibrated role posterior. No real held-out annotation calibration, semantic promotion or physical execution is established. Frozen source verification and the two independent reviews cannot upgrade those absent capabilities.

## Final fixed-source verification

Final SHA: `6f142dbf732009a82e08cd882b62f55708dfdd6d`.

- Unchanged original five probes: **5 passed, 0.47 s**, including naive/DST rejection and invalidated calibration source rejection. Initial failures remain separately retained.
- New calibration entry independent tests: **5 passed, 0.31 s**. Unlabeled fifth candidate does not become negative; duplicate/unmatched/non-bool annotation and digest mismatch reject; same-video fit/evaluation overlap rejects. These are synthetic math/entry tests, not independent real labels or empirical calibration.
- Independent role test: **1 passed, 0.29 s**. Two opposite role candidates remain explicit and uncalibrated, memory authority remains false, and a large identity gap clears temporal roles.
- Actual final CLI from foreign cwd on an odd-sized 201x199 crop: successful exact decode, one frame, four person-category candidates, no roles, unchanged core, zero memory writes/actions. Output correctly binds final code SHA and three disk-file hashes with `git_dirty=false` and explicitly scoped disk-file identity. Source URL is a caller-supplied label; our example.org probe URL is not asserted as the original media publisher.

Evidence: `final_probe_cli.py`, `final_cli_stdout.txt`, `final_cli_output/result.json`; `final_*`, `calibration_*`, `roles_*` pytest outputs and XML. The calibration loader consumes caller-supplied result provenance plus hash-pinned annotation bytes. It cannot authenticate video/source labels or independent annotator truth; its metrics apply only to explicitly annotated detector candidates and grant no role/memory authority.

Verdict: no remaining reproducible blocking finding within the inspected and independently tested front-end diagnostic paths. All three initial findings are addressed within their declared scope. Eleven independent pytest cases and the actual pinned-detector CLI positive path pass on the common final SHA. This does not establish independent real calibration, semantic promotion, physical action, or full-system acceptance.
