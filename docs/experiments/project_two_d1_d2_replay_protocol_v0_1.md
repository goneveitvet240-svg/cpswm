# Project Two D1/D2 replay protocol v0.1

Status: executable development interface. It preserves hidden-event inference,
multi-actor reasoning, open-world unknowns, reversible attribution, Project One
feedback, and embodied action evaluation. It does not select an external data
source and does not claim real-world evidence.

## One data and inference stack

All maturities normalize into `ProjectTwoReplayEpisode`; evaluator labels remain
in a separate `ProjectTwoEvaluatorTruthEnvelope`. The method receives only the
visible episode. D0, D1, and D2 then run the same:

`ObservationDetectionResult -> CHEH -> ORRER -> PCHMP -> posterior -> action ->
ExecutionFeedbackProjector -> ProjectTwoFeedbackRevisionLoop -> EventRevisionOutcome
-> ProjectOneStatRequest -> HybridEventToTaskCoordinatorLoop -> BeliefSnapshot ->
next action -> frozen evaluator`.

The generic importer accepts JSONL directly. Parquet uses the same one-row/one-
episode payload with a `payload_json` column and requires an installed
`pandas` plus `pyarrow` or `fastparquet` runtime. The repository does not install
that optional engine automatically.

## D1 source candidates — decision remains with the user

| Candidate | Native useful fields | Missing Project Two fields | Installation cost | Licence and distribution risk |
|---|---|---|---|---|
| AI2-THOR / iTHOR | RGB, depth, instance/semantic segmentation, object IDs/types, visibility, object metadata, actions and post-step metadata; multi-agent API exists | Household-person identity, causal actor attribution, ordered handoff roles, unknown mechanism and long-horizon household sessions require instrumentation/annotation | Medium: Python package plus platform scene build download; headless/GPU setup raises cost | Code is Apache-2.0. Scene/assets and any redistributed derived batch still require a separate asset/notice audit |
| ProcTHOR + AI2-THOR | Procedurally generated interactive houses compatible with AI2-THOR; object/receptacle metadata and controllable actions | Same actor/role/unknown gaps as AI2-THOR; generated house specification is not an execution-feedback annotation | Medium: `procthor`/`prior` plus AI2-THOR runtime and assets | ProcTHOR code is Apache-2.0. AI2-THOR and asset/redistribution terms remain independently relevant |
| Habitat-Sim / Habitat-Lab | Configurable RGB, depth and semantic sensors, navigation/physics, episode/task datasets and human-in-the-loop tooling | Actor identity, handoff roles and causal mechanism are not standard fields; object-instance semantics depend on the selected scene dataset | High: Conda/source/Docker choices, optional Bullet physics, GPU/EGL constraints, separate scene downloads | Simulator/Lab code is MIT. Matterport3D, Gibson, HM3D and other scene/task data have their own terms; some listed Habitat task data are non-commercial/attribution restricted |

No row is a recommendation. Before selection, record the exact version, asset
licence, post-action observation support, temporal span, actor/mechanism/role/
location coverage, unknown coverage, privacy risk, annotation effort and adapter
effort. The current source-neutral D1 batch is a fixture, not evidence from one
of these simulators.

## D1 executable development batch

`apps/evaluation_runner/prepare_project_two_d1_replay.py` creates 30 episodes
(10 validation, 20 test), three scene categories, at least five object-family
buckets and 30 distinct seeds. It writes:

- `manifest.json`
- `visible_replay.jsonl`
- `evaluator_truth.jsonl`
- `coverage_report.json`

Supplying `--visible`, `--truth`, and `--dataset-version` sends a selected
JSONL/Parquet source through `D1SimulatorAnnotatedReplayAdapter`. Unregistered
actors normalize to `unknown_actor`; unsupported mechanisms normalize to
`unknown_mechanism`; both retain an unresolved-axis receipt.

## D2 collection directory and record protocol

One source session should be immutable after import:

```text
source-root/
  household-*/scene-*/session-*/
    rgb/<frame-id>.png
    depth/<frame-id>.npy          # optional for RGB-only devices
    raw_visible_episodes.jsonl
    annotations_reviewer_a.jsonl
    annotations_reviewer_b.jsonl
evaluator-only/
  adjudications.jsonl
```

Each raw visible episode carries household, scene and session identity; object
instance/category; before/after detection; source, attempted and observed
destination; execution feedback and observation opportunity. Each step adds
timestamped RGB/RGB-D frame references plus detector/tracker output with track
ID, confidence, visibility, occlusion and optional bounding box. An observed
destination is legal only when a visible post-action detection supports it.

`D2AnnotationSubmission` retains annotator identity, source kind, actor,
mechanism, ordered role, confidence, notes and time. At least two human reviews
can be compared; disagreement remains in `D2AnnotationAgreementReport` and must
not be majority-filled silently. `D2EvaluatorAdjudication` accepts only a human
source. An LLM/VLM annotation is `llm_candidate`: it may compile auditable
visible evidence but cannot create evaluator truth.

`apps/evaluation_runner/prepare_project_two_d2_replay.py` converts raw records
with `D2RealPerceptionConverter`, then reuses `D2RealPerceptionReplayAdapter`.
Without input arguments it writes a sensor-shaped executable fixture and labels
it `claim:not-real-collection`; no physical RGB/RGB-D capture is claimed.

## Hash, split, missingness and provenance

The exporter records file SHA-256 hashes, per-episode source hashes, visible
content hashes, evaluator content hashes, data version, source URI, provenance,
field availability, missingness and split membership. Visible and evaluator
files must be different resolved paths. Validation/test firewalls cover
household, scene, object instance and object family.

## Decisions reserved for the user

1. Data source: AI2-THOR, ProcTHOR, Habitat or another licensed source.
2. Capture device: RGB-only camera, RGB-D camera, fixed multi-camera setup, or
   robot-mounted perception; calibration and storage differ.
3. Scale: number of households, scenes, sessions, people, object families,
   repeated days and post-action observations.
4. Publication: private raw data, de-identified derived replay, controlled
   access, or public RGB/RGB-D release; faces, voices and household interiors
   materially change privacy/consent requirements.
5. Agreement/adjudication acceptance thresholds and who may adjudicate.

## Gate into LLM, tuning and ablation

Proceed only after real D2 records exist; hashes and split manifest validate;
visible/truth leakage checks pass; missingness and disagreement are reported;
actor/mechanism/role/location and unknown strata have user-approved coverage;
post-action observations are distinguished from attempted destinations; and the
development/sealed boundary is frozen. Until then, D2 supports interface and
pipeline validation only, not paper-level external-validity claims.

## Official source links checked 2026-08-24

- AI2-THOR repository and documentation: <https://github.com/allenai/ai2thor>,
  <https://ai2thor.allenai.org/ithor/documentation/environment-state/>
- ProcTHOR repository/licence and PRIOR loader: <https://github.com/allenai/procthor>,
  <https://github.com/allenai/procthor/blob/main/LICENSE>,
  <https://github.com/allenai/prior>
- Habitat-Sim/Lab and dataset notes: <https://github.com/facebookresearch/habitat-sim>,
  <https://github.com/facebookresearch/habitat-sim/blob/main/DATASETS.md>,
  <https://github.com/facebookresearch/habitat-lab>
