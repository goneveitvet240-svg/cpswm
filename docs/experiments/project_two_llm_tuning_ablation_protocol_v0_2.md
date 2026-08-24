# Project Two D1/D2, LLM evidence, tuning and ablation protocol v0.2

## Gate and evidence status

The revision-to-action trace and the content-hash, truth/cache firewall,
full-rerun, and development/sealed tests pass. D0 may therefore run as an
engineering pilot. D1/D2 adapters are executable typed import boundaries but no
external dataset has been selected or loaded. D3 household execution and D4
robot execution remain explicit unavailable interfaces. No external or paid
LLM/VLM was invoked.

All maturities use `ProjectTwoReplayEpisode`, the same evaluator, split firewall,
content hashes and metric definitions. D1/D2 source parsers must produce that
contract plus a separately hashed evaluator truth envelope; they cannot create a
second inference stack.

| Tier | Source selected | License | actor/mechanism/role/location | post-action observation | span / unknowns | privacy | annotation / adapter cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 simulator or manual replay | no | user decision required | adapter validates all four axes; actual coverage unavailable | supported by contract; actual coverage unavailable | unavailable | depends on selected source | unavailable until source choice |
| D2 real-perception replay | no | user decision required | adapter validates all four axes; actual coverage unavailable | supported by contract; actual coverage unavailable | unavailable | likely household/person-sensitive; review required | unavailable until source choice |
| D3 household execution | no, interface retained | user decision required | unavailable | unavailable | unavailable | high | unavailable |
| D4 robot execution | no, interface retained | user decision required | unavailable | required | unavailable | high plus physical safety | unavailable |

## Provider-neutral evidence

The common `LLMEvidenceRequest -> LLMEvidenceOutput` contract supports a local
callable provider, an HTTPS OpenAI-compatible hosted provider, and a deterministic
fixture. Provider, model, version, prompt, temperature and candidate count enter
cache keys and provenance. Provider outputs may only create actor/mechanism/role
evidence, semantic location priors, interaction evidence, or action proposals.
Truth aliases and cache poisoning are rejected. `LLM_PRIOR_ONLY` changes the
actor prior then still runs CHEH, PCHMP, ORRER, feedback revision and Project One;
direct decision has no Project Two or Project One write surface.

## Runtime tuning

The 21 parameters are bound to actual likelihood, CHEH/PCHMP evidence,
open-world priors, ORRER, joint CF-BOCPD, CCRR, RGRC, planner and LLM request
configuration. Every case emits a runtime parameter receipt with component and
runtime-trace hashes. A changed parameter that changes neither fails through the
unused-parameter detector. The group order is frozen in
`configs/project_two_tuning/runtime_groups.yaml`; group receipts precede any
joint search. Each track and each ablation receives a separate receipt, common
budget and early-stop objective, without held-out episode IDs.

## Runtime ablations

All 19 declared cuts execute in the D0 evaluator sandbox and emit module traces.
The unsafe no-provenance and no-dedup cuts exist only as evaluator message-passing
adapters. Production components expose no unsafe switch. Prior-only and direct
decision are distinct runtime classes/paths.

## D0 pilot boundary

On one validation and one sealed test episode, eight steps each, a complete
budget-eight baseline/grouped/joint search produced 23 independent receipts.
No-LLM and direct fixture had put-back error 0.375 and regret 6.0; LLM evidence
was worse at 0.500 and 7.0; oracle had 0 and 0. LLM evidence slightly improved
unknown Brier from 0.2424 to 0.2277 but did not add action value. Revision
precision is truth-matched rather than applications/requests: No-LLM was 0.8
and the fixture LLM track was 0 on this small run.
There are not enough independent samples for p-values or Holm correction, so
both are `unavailable`. Bootstrap intervals are descriptive only.

Before selecting a source, the user must decide after reviewing license,
actor/mechanism/role/location coverage, post-action observations, time span,
unknown coverage, privacy, annotation cost and adapter cost. Before any hosted
call, the user must choose model/version after privacy, token cost and local
alternative review.
