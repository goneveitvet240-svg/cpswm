# Independent review round 1 — continuous input component

Audited source: `d6245385eb86e2bbbca973234ab39336b5ccfd4a` in `/private/tmp/cpswm-pc-a-continuous-loop-20260913`. Production source read only. Independent probe: `PYTHONPATH=src .venv/bin/python /private/tmp/cpswm-continuous-review1/probe.py`; raw output retained in `probe.out`. Probe reuses fixture construction only, independently exercises untested temporal cases and injected trace failure.

## Findings requiring repair

1. **P2: duplicate feedback loses arrival watermark** — `structure_two_continuous_input.py:358-361`. Initial feedback at t, identical redelivery at t+2h succeeds, then admission at t+1h also succeeds. The idempotent return avoids `_last_arrival` update, unlike raw duplicate admission. This violates declared causal delivery ordering and permits a new command/observation to be backdated relative to already received feedback. Update the arrival watermark for a valid duplicate without applying revision twice; retain conflict rejection.
2. **P2: execution feedback is received outside causal clock** — `execute_placement`, successful-feedback return. Command at t returns feedback whose recorded_time and valid_time.end are t+1s, yet another command at t is accepted. There is no execution receipt time argument and no watermark update or recorded/end coherence checks in that path. The subsequent action can therefore be causally prior to feedback the stream already received. Bind dispatch/reply to an explicit time contract or at least monotonically incorporate validated feedback evidence time; invalid feedback must retain outcome-uncertain rather than authorize re-dispatch.

## Additional independent results

- Trace sink injected OSError leaves original core snapshot unchanged and zero traces; retry after restoring sink succeeds with exactly one retained trace.
- A zero-valued synthetic image with precomputed fixture semantics commits and produces nine hypotheses. This intentionally demonstrates the **trusted producer boundary**, not semantic grounding authentication. Nonempty producer/calibration names plus raw dependency IDs cannot establish that those semantics came from pixels or a calibrated model. An arbitrary complete producer can still fabricate the semantic positive path. This is not a newly claimed authentication capability of the module, but it forbids treating this bridge as end-to-end real perception acceptance.

## Scope and disposition

Request repair of both temporal findings before component acceptance. This is a legacy traced lane bridge; it has no real semantic perception producer, full-axis/P5 proposer assembly, calibrated multi-person/pose chain or autonomous continuous task scheduler. The tests use synthetic fixtures and the execution object is a fixture world. Real archive hash/admission checks cannot replace real semantic and physical-action evidence. No overall unified runtime, final scientific benefit, or user-requested final whole-system acceptance is established by this review. Making the legacy diagnostic lane explicit is appropriate and does not implement P5_FIRST.

## Final-source re-verification

Rechecked exact final code `be6e06348106c5a46ad766c136824c5eab70192a` (HEAD verified before and after execution). No production files edited. Original failure probe and output remain untouched; `final_probe.py` and `final_probe.out` rerun the original cases using the updated fixture adapter. Additional independent assertion script `final_assertions.py` and its `final_assertions.out` cover:

- Valid duplicate feedback advances arrival watermark while returning the same revision and leaving core snapshot unchanged. Admission between first and duplicate receipt times is now rejected.
- Received placement completion advances the watermark: a new backdated decision is rejected; an already-issued same-time second command is rejected **before execution**, with executor call count remaining one. A later legal command still executes successfully.
- Injected trace write failure preserves the original snapshot and zero retained traces; restoring the sink allows one successful retry and one retained trace.

All three assertion groups passed. Both original P2 findings are fixed within this tested scope. The re-run still accepts trusted precomputed semantics attached to zero-valued synthetic pixels, as expected for this explicitly declared `legacy_component_diagnostic` lane; that result continues to establish no actual perception correctness. This final-source sign-off is **only the reviewed diagnostic bridge scope**, not full-axis/P5, real calibrated semantic generation, real physical execution, complete user-requested continuous runtime, or scientific acceptance.
