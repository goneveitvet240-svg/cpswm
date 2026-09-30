# Archive → Native proposal checkpoint preparation

Read-only design preparation against local frozen source `37981c3c44475b0bcbeff3379dcf90be288c49c9`, 2026-10-01. This is neither a new experiment nor R1/R2 review. No checkpoint was loaded into Torch, no model inference/training or Unity was run, and no old artifact or source file was modified. The only new file is this note. The existing `ARCHIVE_NATIVE_BRIDGE_DESIGN.md` and final section of `NEXT_RAW_UPDATE_DESIGN.md` remain applicable.

## Finding

The three previously executed proposal checkpoints can be reused as the fixed development proposal component. There is no identified need to regenerate a pytest checkpoint. Their six original files and six shared copies were read and compared byte-for-byte; all sizes and SHA256 values match the external `FILES.json`. Static compatibility is strong: the current training runner, training fixture, proposal scheduler fixture, proposal sample schema, network, trainer/loader, and inference-session files have the same bytes as the original actual-run source map. Loading/scoring the new archive-derived context remains a next-round execution obligation, not a result of this preparation.

These checkpoints are genuine saved, previously executed neural weights, but their training data are explicitly synthetic component fixtures. They are not naturally trained joint models. The known exact-enumeration integration uses q/q cancellation, so checkpoint execution is not evidence that learned q improves target weights.

## Exact artifacts and external pins

Original checkpoint common parent:

`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/neural-native-loop-20260929/round1-attempt01/actual-replay`

Append `<arm>/checkpoint` from the table. Each directory contains `manifest.json` and `weights.pt`.

| arm | External manifest SHA256 | Weights SHA256 | Manifest / weights bytes |
| --- | --- | --- | --- |
| `typed_factor_graph_transformer` | `4f17225e73bf40b0aca9c996c1803dfc03918bfa5972a66a785be871417114f4` | `3caef23484aa29ea74d63c4e191ccb0888eca476a674e533e6590dfe09a4be3e` | 1,357 / 697,454 |
| `slot_conditioned_perceiver` | `f9ef284b0d89883b47fcc010d952e49cb4a4fb0be63a5eb1200a5cd011f40b85` | `5cb915f91b043a0e2921de8728e9be93051f3e96924cbde0b7a3fe01756d2d01` | 1,349 / 839,815 |
| `autoregressive_typed_graph_policy` | `68ff631b677c207842244432931dd880a48565a0fb21956979566b3f97f3c9b2` | `082d2bdec8542c35c45fedb1f9d22df04d106ce4852cde506d98b18c5e1b9071` | 1,363 / 899,542 |

Total: 2,440,880 bytes. The identical shared common parent is:

`/private/tmp/cpswm-pc-a-soft-position-factor-20261001/docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/development-checkpoints`

Its `FILES.json` is external to the checkpoint directories and is Git-tracked under the stated frozen source. It pins the six files and explicitly labels their limited training scope. Its current SHA256 is `5bf00cc0c4f7f1e98c0cf78eca7b23afc882601382a2d90a29d6bab0346e86f2`. Use these recorded manifest pins as caller configuration; do not accept a hash merely computed from whichever current manifest is found. The historical `run_history_action_loop.open_joint()` computes the current manifest hash itself, so that convenience function should not establish the new bridge's external trust anchor.

Independent old artifact locations under the original output parent `.../output/neural-native-loop-20260929`:

| Relative file | Current read-only SHA256 | Evidence |
| --- | --- | --- |
| `round1-attempt01/actual-replay/result.json` | `e2eb757fb0454ee1c206a27d1754d01419552253ac61045008dfc61a001e2ac4` | Per-arm manifest pins, training reports, original Python/Torch and source map |
| `round1-attempt01/commands.json` | `0b2eb37969936f833409a203491d350040b5f19f186645fb8614db839c24eecc` | Actual three-arm training/replay command and exit 0 |
| `round1-attempt01/source.json` | `11aa65c39f64fe669ce71db041889d370f3235425e24e811ce6a49876e839eba` | Original frozen source `08e5cc1f5cdb049d7bbd68b66e4da829a59e4efd` |
| `round2-attempt02/commands.json` | `b49e48aeaf353709303fe7838cc9e0c94306151243eb993375e9609496bc7622` | Actual north/south camera commands select the Transformer directory, both exit 0 |

The north/south `round2-attempt02/live-{north,south}/result.json` both record manifest pin `4f17225e73bf40b0aca9c996c1803dfc03918bfa5972a66a785be871417114f4`. Their command source was `3d917ee4f5a203bd3bddbdfb1fa6a8e71713c372`. Thus this is an existing actually used camera-loop checkpoint, rather than an inferred path or a newly manufactured fixture weight.

## Original training provenance

The recorded command was the old worktree interpreter with `-u tools/run_neural_native_replay.py --output <original parent>`, under source `08e5cc1f5cdb049d7bbd68b66e4da829a59e4efd`. It returned 0 in 280.9541538753547 seconds, including replay/recovery of all three arms. The command was only read, not rerun.

`tools/run_neural_native_replay.py:run` gets one sample/support from `tests/test_typed_proposal_training.py:data`. That function calls `tests/test_structure_two_proposal_scheduler.py:sample_payload.__wrapped__()`: a controlled D0 scenario plus explicitly constructed event chains, identities, revisions, locations, and proposal candidates. The sample is marked `partition=development`, `annotation_kind=component_fixture`, `annotation_ref=unit-test:explicitly-not-native-trace`. Full runtime support retains the constructed six operation types; the compatible training targets are restricted to branch/preserve_unresolved. No archive masks or validation labels train q.

All three manifests record seed 0, two AdamW steps, two examples seen, learning rate 0.001, objective `compatible_proposal_nll_only`, `track=COMPONENT_FIXTURE_ONLY`, no formal architecture selected, no joint schedule, no natural closed-loop verification, and `production_authorized=false`. All use:

- Sample SHA256: `884bc672872eeaaf86becaa1349b888b34c426cde27982d06288b9eaa51e06df`.
- Runtime support SHA256: `96906162e150ddb73610f009ddc8efa60e25947fce2ededa32942fbf5c6e4d66`.
- Dense execution backend `dense@1`, hidden width 64, two layers, four attention heads, 16 Perceiver latent slots, `max_nodes=4096`, `max_bytes_per_leaf=4096`.

The two SHA values above were read from the original manifests and agree across all three; this preparation did not regenerate their fixture or revalidate the actual old optimization numerically.

## CPU environment and construction

Current available interpreter:

`/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`

Read-only Python/package metadata checks found Python 3.13.5, Torch 2.13.0, macOS 26.4 arm64, matching the original actual replay record. Current NumPy is 2.5.2, Pydantic 2.13.4, TorchVision 0.28.0. No Torch model/import/inference was required to read these package versions. Set Torch CPU threads to 2 before constructing the wrapper; the inference session binds the actual thread count and rejects changes later. Use `PYTHONPATH=src:tests:tools` for existing test/tool assembly. `PYTHONHASHSEED=0`, `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`, and `OPENBLAS_NUM_THREADS=1` can make the new command explicit, but `torch.set_num_threads(2)` remains necessary. No Unity/SDK process or GPU is needed for the archived raw packet bridge.

Minimal next-round construction, after its own source freeze/reviews and current data delivery:

```python
torch.set_num_threads(2)
candidate = ControlledPositionProducer(
    configuration=saved_configuration,
    affinity_model=saved_affinity_model,
    affinity_pin=externally_pinned_affinity,
    position_model=saved_position_model,
    position_pin=externally_pinned_position,
)
joint = NeuralNativeProducer(
    candidate,
    fixed_checkpoint_directory,
    manifest_sha256=recorded_external_manifest_pin,
    use_owned_visual_context=False,
)
```

Import the canonical classes from `cpswm.system.controlled_position_producer` and `cpswm.system.native_neural_production`. The tools compatibility alias reexports the canonical producer; do not subclass it or introduce a new unregistered producer type, because raw owner reconstruction uses exact canonical types. The raw profile then binds the actual configuration, position/affinity models, verifier/source identities, and neural binding. q's checkpoint is distinct from the newly learned affinity and position residual models; this note locates only q and does not claim the latter have completed real-data execution yet.

The configuration fields remain exactly `semantic_record_id`, `packet`, `candidate`, `seed_uv`, `enabled`. Derive packet binding from the unchanged original raw tuple, predeclare one complete public candidate/seed independently of private labels, and use the scope/time-preserving semantic fixture and strict full-neighborhood receipt in `ARCHIVE_NATIVE_BRIDGE_DESIGN.md`. The offline archive command is not an owner-issued observation command. `use_owned_visual_context=False` preserves that distinction; the controlled candidate itself reads the actual RGB-D from its owner-admitted context.

There are two existing engineering precedents, with no scientific winner selected here: the actual camera loop used the Transformer pin; current controlled-consumer tests use `ARMS[1]` (Perceiver). Either existing weight can serve a predeclared fixed execution carrier. Keep the three alternatives recorded, and do not choose based on archive validation results or call the engineering carrier a formal architecture decision.

## Fresh SQLite recovery and remaining obligations

Reconstruct the exact saved configuration/models and the same fixed checkpoint wrapper in the fresh process before `ContinuousEvidenceInput.resume(store, producer=..., context_builder=..., joint_producer=fresh_joint)`. Wrapper construction registers the external checkpoint directory in the process-local content-addressed registry (`sha256:<manifest pin>`). A saved evidence record alone cannot authorize a path or replace that registration. The existing controlled fixture builder must be rebuilt with the saved synthetic case, and its probe/system/step pointers restored as described in the bridge design. Do not rebuild random CIAV IDs and label a new empty run as SQLite recovery.

`load_checkpoint` verifies the caller's external manifest digest, development format, weights digest, CPU tensor schema/dtype/finiteness, then sets eval mode. `ProposalInferenceSession` binds parameters, implementation digest, Torch version, arm, CPU device, and thread count. New candidate/raw/implementation bindings differ from the old camera runtime: reuse original weight bytes, but create a new run manifest and SQLite state; do not transplant old producer state or claim identical old runtime binding.

Required next-round execution evidence remains: successful actual checkpoint load and complete-support scoring on the new context within dense limits; one real archive packet's public readout and both explicitly development position references; complete native target-weight/statistic consequences; no duplicate measurement, withdrawal/replay to paired no-factor baseline, and fresh-process SQLite recovery. Use saved original bytes and new source-bound owner admission. No claim of natural identity, formal position-reference choice, multi-capture owner update, improved q, task success, or B independent acceptance follows from this preparation.

## Preparation verification boundary

Commands performed were read-only `git rev-parse HEAD` / `git status --short`, scoped `rg` / `sed` / `cat` on the named project files, and standard-library Python (`pathlib`, `hashlib`, `json`, `platform`, `sys`, `importlib.metadata`) for byte comparisons and environment metadata. The manifest/weight check completed with exit 0 and all six originals equaled all six shared copies and external listed pins. Outputs are in the tool session, not a fabricated saved raw log. No remote-latest claim is made; this note binds the explicit local frozen SHA and archived command records.
