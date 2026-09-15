# Development status

Snapshot: 15 September 2026. This page describes development branches, not a released system.

## Implementation

| Area | Available work | Remaining work |
|---|---|---|
| Evidence and recovery | Source-linked observations, persistent runtime state, replay and execution receipts | Full real-world correction and recovery demonstrations |
| Inference and memory | Typed particles, conditional blocks, reversible updates and proposal scoring interfaces | Native supervision, complete trainers and qualified runtime configuration |
| Perception | RGB-D adapters, pretrained detectors and geometric association components | Calibrated semantic transitions, person roles, contact/release and world pose |
| Embodied actions | Camera selection and simulator execution interfaces | A validated policy using natural observations throughout the memory–action loop |
| Evaluation | Component regressions, adversarial probes and recorded-input diagnostics | Fixed-version system comparison and cross-machine acceptance |

## Latest recorded-input experiment

The latest report evaluates two pretrained detectors on 180 RGB-D frames from three HO-Cap sequences. At IoU ≥ 0.5 and detection threshold 0.5, SSDlite matched 0 of 720 annotated target appearances; Faster R-CNN v2 matched 165, leaving 555 unmatched. These are target appearances across frames, not 720 distinct objects.

Localization-score calibration also failed to improve the held-out sequence: Brier score increased from 0.28247 to 0.38176. The run produced no semantic memory updates or task actions. This is a small development diagnostic on recorded input, not evidence of complete object understanding or method superiority.

[Report and evidence](https://github.com/goneveitvet240-svg/cpswm/blob/7e00bf81ea5671228ba6be32d3d550bbc1a29cba/docs/reviews/pc_a/real_semantic_input_2026-09-15/REPORT.md) · [Implementation review](https://github.com/goneveitvet240-svg/cpswm/pull/26)

## Review series

The main development stack is #15 → #16 → #20 → #21 → #22 → #23 → #24 → #25 → #26. Each later branch builds on earlier work; the open PRs are not independent releases. B's #17 remains a separate original delivery. #20 reports receiving selected B changes after local review, which does not replace cross-machine acceptance. #2 retains comparison preparation.

| PR | Scope |
|---|---|
| [#26](https://github.com/goneveitvet240-svg/cpswm/pull/26) | Paired RGB-D input and object localization evaluation |
| [#25](https://github.com/goneveitvet240-svg/cpswm/pull/25) | Proposal decoding and posterior camera collection interfaces |
| [#24](https://github.com/goneveitvet240-svg/cpswm/pull/24) | Pose measurements, proposal loss and camera decisions |
| [#23](https://github.com/goneveitvet240-svg/cpswm/pull/23) | Persistent state and observation execution |
| [#22](https://github.com/goneveitvet240-svg/cpswm/pull/22) | Instance association and provisional role candidates |
| [#21](https://github.com/goneveitvet240-svg/cpswm/pull/21) | Pretrained natural-image frontend |
| [#20](https://github.com/goneveitvet240-svg/cpswm/pull/20) | Continuous evidence, revision and placement interfaces |
| [#16](https://github.com/goneveitvet240-svg/cpswm/pull/16) | Local pose representation |
| [#15](https://github.com/goneveitvet240-svg/cpswm/pull/15) | Earlier unified runtime candidate |
| [#17](https://github.com/goneveitvet240-svg/cpswm/pull/17) | B repair and audit archive |
| [#2](https://github.com/goneveitvet240-svg/cpswm/pull/2) | Comparison and acceptance preparation |

## Source versions

Commit IDs below identify the fetched PR heads. Reports may name an earlier tested code commit followed by evidence-only changes; those distinctions remain in the original reports. This documentation update does not rerun their experiments.

| PR | Head commit |
|---|---|
| #2 | [`329787241996631a6abb4fcd3b12d2c13a135777`](https://github.com/goneveitvet240-svg/cpswm/commit/329787241996631a6abb4fcd3b12d2c13a135777) |
| #15 | [`e6bdd018d3fd49cb304293d25651506e5342344f`](https://github.com/goneveitvet240-svg/cpswm/commit/e6bdd018d3fd49cb304293d25651506e5342344f) |
| #16 | [`25ec3478476af6399321e17c8a4981753d578ce0`](https://github.com/goneveitvet240-svg/cpswm/commit/25ec3478476af6399321e17c8a4981753d578ce0) |
| #17 | [`fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`](https://github.com/goneveitvet240-svg/cpswm/commit/fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a) |
| #20 | [`0cb04a3a63b19786649a7b2091a14e67ec1c637d`](https://github.com/goneveitvet240-svg/cpswm/commit/0cb04a3a63b19786649a7b2091a14e67ec1c637d) |
| #21 | [`7516193f4cdcf1686d8187d2b8ce0398ecc0cf96`](https://github.com/goneveitvet240-svg/cpswm/commit/7516193f4cdcf1686d8187d2b8ce0398ecc0cf96) |
| #22 | [`b196cb81170fae8e0a54f27d14769e728e79aae2`](https://github.com/goneveitvet240-svg/cpswm/commit/b196cb81170fae8e0a54f27d14769e728e79aae2) |
| #23 | [`d041adca826023f65cc3ac6af696e55862bb3f51`](https://github.com/goneveitvet240-svg/cpswm/commit/d041adca826023f65cc3ac6af696e55862bb3f51) |
| #24 | [`238e5daf8c1f6a28c25ef616c37a26035c321f83`](https://github.com/goneveitvet240-svg/cpswm/commit/238e5daf8c1f6a28c25ef616c37a26035c321f83) |
| #25 | [`bdf5f55dfaddf978e548aeedcd28e2bc465a5054`](https://github.com/goneveitvet240-svg/cpswm/commit/bdf5f55dfaddf978e548aeedcd28e2bc465a5054) |
| #26 | [`7e00bf81ea5671228ba6be32d3d550bbc1a29cba`](https://github.com/goneveitvet240-svg/cpswm/commit/7e00bf81ea5671228ba6be32d3d550bbc1a29cba) |

[Live review list](https://github.com/goneveitvet240-svg/cpswm/pulls)
