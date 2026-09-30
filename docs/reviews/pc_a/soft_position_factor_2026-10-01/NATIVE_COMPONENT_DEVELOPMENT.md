# Controlled native position consumer: development record

2026-10-01, A-side component development. This is an implementation record, not
either adversarial review round, B-machine acceptance, or a natural identity /
camera closed-loop result. The component author cannot count these checks as an
independent R1 or R2.

## Source and execution scope

Working directory:
`/private/tmp/cpswm-pc-a-soft-position-factor-20261001`

Interpreter:
`/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`
(`Python 3.13.5`, queried while writing this record).

Only these two new source/test files were implemented by this component author:

- `tools/controlled_position_producer.py`
- `tests/test_native_position_production.py`

At documentation time, `git rev-parse HEAD` returned
`0c89fb5b71098d3690d568e9f4ae7a33d5e722e5`. The following file hashes were read
after source writing stopped:

```text
218feed24f64773d2bff05612463e286ac9fcc752aed01d8190f8c06320c9121  tools/controlled_position_producer.py
ef00a9ca94845a4a9e29e44b0ea64bdaef79f50871d4861b58f7f1a228062a59  tests/test_native_position_production.py
```

The tests ran during implementation, before a frozen whole-change review. A full
commit SHA was not captured at the instant of each test launch; the later HEAD
above is not a retroactive claim that all its files were tested by these commands.
Root is conducting the combined regression separately.

## Actual development commands and results

The command common to the first three pytest launches was:

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q tests/test_native_position_production.py --maxfail=2
```

| Tool session | Exit | Result and implementation state |
|---|---:|---|
| `31863` | 1 | Stopped after 2 failures. Packet binding attempted to JSON-hash raw bytes directly. Corrected to bind envelopes, payload SHA256s, receipt, sampling metadata and depth unit. |
| `49683` | 1 | Stopped after 2 failures. The configured input detection ID differed from the current native CIAV after-record ID, so no position factor had activated. Added the explicit CIAV-only before-record mapping and retained the actual published after-record for withdrawal. |
| `37970` | 0 | 7 tests passed. At this intermediate version, the replay test ingested 12 semantic steps in each of the factor and no-factor cases, withdrew the actual measured native after-record, replayed all retained consumed sources and recovered via SQLite. It preceded the final extra loaded-implementation/constant tests. |

The final development sequence was:

```sh
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/ruff format tools/controlled_position_producer.py tests/test_native_position_production.py
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/ruff check tools/controlled_position_producer.py tests/test_native_position_production.py
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q tests/test_native_position_production.py --maxfail=2 --durations=3
```

Tool session `79988` completed with exit 0. Its observed output was:

```text
1 file reformatted, 1 file left unchanged
All checks passed!
...........                                                              [100%]
============================= slowest 3 durations ==============================
12.36s call     tests/test_native_position_production.py::test_retraction_full_replay_matches_no_factor_and_survives_sqlite
2.84s setup    tests/test_native_position_production.py::test_publishes_preupdate_density_full_state_and_single_information_increment
1.91s call     tests/test_native_position_production.py::test_publishes_preupdate_density_full_state_and_single_information_increment
```

Thus the final observed result is **11 tests passed**, with ruff format/check
successful. The shell tool captured the exit code of the final command in the
sequence; the preceding successful ruff messages are shown above. No separate
per-command ruff exit-code file was created. Earlier formatting passes initially
reported line-length errors and then reformatted the files; they are not the final
lint result.

These original terminal outputs were **not redirected to log files**. They remain
visible in the development tool conversation. The excerpt above is a transcription
of observed output, not an invented preserved raw log. No total elapsed time was
reported for the final suite; only the three durations above were displayed.

Additional read-only Python probes ran the existing controlled semantic builder
to inspect source IDs and commit dates. They revealed that the native current
transition is a CIAV closure whose `before` is the configured input detection and
whose `after` is a newly generated detection. A three-step semantic-only probe
also confirmed the first measured source remains retractable with two other
steps present. These probes did not train on the 96-frame archive or run Unity.

## Final retained test range

The final replay test deliberately uses **3 steps**, not 12: one fixed measured
source and two neutral sources. After withdrawing the actual measured native
revision, it fully rebuilds the retained consumed history, compares weights and
all conditional numeric blocks against the matched no-factor run, preserves the
post-feedback semantic ledger and restores a fresh producer from SQLite. The
packet remains visible in the raw journal, but it is not reassigned to another
semantic source. The earlier 12-step result is useful development evidence for
its intermediate implementation; it is not a 12-step rerun of the final revision.

The 11 final cases cover:

1. Admitted public RGB-D originals → fresh public surface readout → predictive
   Gaussian likelihood computed from the pre-update prior → actual native
   particle publication, with full 6D statistics and q/integration cancellation.
2. Same-source native idempotence and later unrelated-source continuation without
   repeating the original measurement or resetting unresolved mass.
3. Four complete public/context attacks: depth, camera pose, re-bound packet and
   changed ledger context. Coherent public packets / real neural scores are
   constructed; rejection leaves the native workspace unchanged and the legal
   path subsequently publishes.
4. Fresh SQLite producer restore of the actual joint decision view and mutable
   consumed-key state, followed by idempotent continuation.
5. Complete three-step withdrawal/replay/no-factor comparison and SQLite restore.
6. Three loaded-state attacks: position H redirected into rotation columns,
   changed position helper, and changed producer readout. An attacker creates a
   new self-consistent bound producer, actual neural scores, statistics and
   receipts. Staging under the original configured dependency rejects the
   forgery, preserves state/ledger, and permits the original legal path after
   restoration.
7. A complete ordinary-source candidate with the same `before` record cannot
   activate the CIAV mapping; its forged source cannot stage as the native source.

Items 1–2 share one test; item 3 has four parametrized cases, item 6 has three.
Together with the remaining three individual tests, this yields 11 cases.

## Declared assumptions and binding rule

The consumer starts two explicit particles (known fixture identity / unknown
identity) plus the native aggregate unresolved bucket with equal unit mass. Full
6D prior precision is I6 and mean is zero. The controlled local reference is the
world origin. Unknown particle and aggregate bucket both use the explicit world
3D density N(0, 100 I3), so they are compared in the same metre-density units as
the known predictive Gaussian. That unknown density is an assumed fixture, not a
learned or formally selected natural clutter model. Subsequent steps retain the
actual parent weights and the aggregate unresolved probability.

Configuration fixes one semantic input record, one raw three-channel packet, one
declared public box and pixel seed. Selection does not consult private labels.
The record matches the current native `after` directly, or matches current native
`before` **only if** `after.metadata.source_id` is exactly
`structure-two-adaptive-ciav-feedback-closure`. It never searches arbitrary
historical records. The diagnostic records configured input, native before and
native after IDs. Withdrawal targets the actual published native after-record
revision. Replay starts from the original producer checkpoint and never moves
the old packet onto a retained unrelated source.

The producer binds configuration/models, actual packet metadata/payloads, helper
source bytes, loaded helper code and fixed geometry/protocol constants. The
NeuralNativeProducer wrapper additionally binds the candidate class methods and
executes the actual pinned checkpoint. The fixed controlled affinity and residual
models are synthetic test fixtures; the neural checkpoint fixture performs its
existing small controlled training. None of these tests reads or selects the
real validation masks, trains on the real 96-frame archive, runs Unity, installs a
live default, or proves natural world identity, calibrated position accuracy or
improved action utility.

Source writing stopped before this document was added. The next gate is root's
combined regression and two separately assigned adversarial review rounds.
