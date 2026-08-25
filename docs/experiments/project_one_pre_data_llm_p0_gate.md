# Project One pre-data/LLM P0 hard gate

Status date: 2026-08-25

This checkpoint restores a collectable, executable baseline before any new
dataset or LLM result is admitted. It does not upgrade formal B1 maturity.

## Evaluation-path boundary

The retained short route is named `offline_method_evaluation`:

`dataset -> ProjectOneDatasetRecord -> ProjectOneStream -> method arm`

It bypasses M05--M16. Every data-pilot report and written manifest therefore
contains:

- `evaluation_mode=offline_method_evaluation`;
- `claim_scope=method_evaluation_only`;
- `formal_b1_claim_allowed=false`;
- the exact `bypassed_modules` list M05--M16.

The equivalence contract compares only the visible method-input record emitted
at the M16-to-method seam. Equality there means both routes provide the same
field values to an arm. It does **not** mean M05--M16 executed, and the claim
guard rejects using this receipt as formal B1 evidence.

## Runtime-parameter gate

Every project-one tuning candidate now carries a runtime receipt binding each
declared tuning parameter to the exact path in the instantiated method config.
An absent or ambiguous binding raises `UnusedProjectOneParameterError`.

SHIFT validation candidates additionally bind `warmup_days`, hazard,
detection threshold and, for joint CF-BOCPD, `beam_width`,
`maximum_simultaneous_causes`, and `simultaneous_hazard_scale` to the concrete
adapter/model/run arguments. The old SHIFT grid explicitly uses
`maximum_simultaneous_causes=1`, preserving its historical single-cause
semantics while still making the new constructor parameters auditable.

## Reproducibility and maturity

`benchmarks/p0_checkpoint/content_manifest_v0_1.json` records independent
content hashes for code, configs, data-schema files and split manifests. The
generator excludes its own output, so two unchanged runs reproduce the same
hash. The progress ledger date and M32 limitation were refreshed without
claiming a maturity upgrade: formal B1 remains blocked because M05--M16 have
not run as an integrated real-data path.

Local transfer archives and pre-change backups are retained, not deleted, in
the ignored `.checkpoint_quarantine/2026-08-25-pre-p0/` directory.
