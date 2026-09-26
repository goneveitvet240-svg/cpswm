"""First review: raw hand joins, causal features and three-arm numerical consumption."""

import json
import math
from uuid import UUID, uuid5

import pytest
import torch
from test_runtime_candidates import context, generate, pixel

from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
from cpswm.data_preflight.proposal_samples import export_context
from cpswm.data_preflight.proposal_trainer import distribution
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork
from cpswm.perception_mapping.natural_hands import HAND_MODEL_SHA256, HandCandidate, HandFrame


def with_hands(p, *, x=25.0, empty=False):
    visual = p.visual_frame()
    hands = HandFrame(
        visual.observation_id,
        visual.capture_time,
        visual.input_sha256,
        visual.receipt_sha256,
        (HAND_MODEL_SHA256, "test-fixture", 4, 0.5, 0.5),
        visual.width,
        visual.height,
        ()
        if empty
        else (
            HandCandidate(
                uuid5(visual.observation_id, "fixture-hand"), ((x, 35.0),) * 21, "Right", 0.8
            ),
        ),
    )
    return ProposalPixelObservation.from_frame(visual, hands)


def two_people(p):
    data = p.model_dump()
    data["candidates"] = (
        *p.candidates,
        {
            "candidate_id": uuid5(p.observation_id, "other-person"),
            "category": "person",
            "detector_score": 0.9,
            "box_xyxy": (30, 10, 80, 90),
        },
    )
    return ProposalPixelObservation.model_validate(data)


def features(ctx):
    return export_context(ctx)["visible_prefix"]["pixel_observations"]


def test_raw_geometry_identity_conditions_share_existing_actor_keys():
    observations = tuple(with_hands(two_people(pixel(i)), x=35) for i in (0, 1))
    ctx = context(observations)
    rows = features(ctx)
    assert len(rows) == 2 and all(len(r["hands"]["candidates"]) == 1 for r in rows)
    for row in rows:
        pair = row["person_identity_pairs"][0]
        assert set(pair["actor_keys"]) <= set(ctx.actor_support)
        assert pair["hypotheses"] == ["same_person_multiple_detections", "distinct_people"]
        measurement = row["hand_object_measurements"][0]
        assert set(measurement["compatible_person_keys"]) == set(pair["actor_keys"])
        assert measurement["person_assignment_status"] == "AMBIGUOUS"
        assert measurement["minimum_landmark_to_box_px"] == 15
        assert measurement["instance_key"] in ctx.instance_support
        for role in row["conditional_roles"]:
            assert role["identity_pair_id"] == pair["pair_id"]
            assert role["actor_key"] in ctx.actor_support
            assert role["recipient_key"] in ctx.actor_support
            assert role["required_identity_hypothesis"] == "distinct_people"
    assert ctx.visible.opportunities == ctx.visible.detections == ()


def test_not_run_empty_and_out_of_image_are_not_contact_absence():
    missing, empty, outside = [
        features(context([p]))[0]
        for p in (
            pixel(0),
            with_hands(pixel(0), empty=True),
            with_hands(pixel(0), x=-5),
        )
    ]
    assert "hands" not in missing and "hand_object_measurements" not in missing
    assert empty["hands"]["candidates"] == empty["hand_object_measurements"] == []
    assert "NO_PERSON_CONTACT" in empty["hands"]["semantic_status"]
    row = outside["hand_object_measurements"][0]
    assert row["person_assignment_status"] == "UNKNOWN"
    assert row["minimum_landmark_to_box_px"] == 55


@pytest.mark.parametrize(
    "field,value",
    [
        ("observation_id", UUID(int=888)),
        ("input_sha256", "f" * 64),
        ("capture_receipt_sha256", "f" * 64),
        ("width", 99),
        ("semantic_status", "CONTACT_CONFIRMED"),
        ("visual_source_sha256", "f" * 64),
    ],
)
def test_invalid_hand_join_or_privilege_is_rejected(field, value):
    original = with_hands(pixel(0))
    payload = original.model_dump()
    payload["hand_observation"][field] = value
    with pytest.raises(ValueError):
        ProposalPixelObservation.model_validate(payload)
    assert ProposalPixelObservation.model_validate(original.model_dump()) == original


@pytest.mark.parametrize(
    "attack", ["nonfinite", "short", "duplicate", "label", "authority", "over_capacity"]
)
def test_candidate_schema_cannot_smuggle_gold_or_impossible_geometry(attack):
    payload = with_hands(pixel(0)).model_dump()
    hand = payload["hand_observation"]
    candidate = hand["candidates"][0]
    if attack == "nonfinite":
        candidate["landmarks_xy_pixels"] = ((float("nan"), 1),) * 21
    if attack == "short":
        candidate["landmarks_xy_pixels"] = ((0, 0),) * 20
    if attack == "duplicate":
        hand["candidates"] *= 2
    if attack == "label":
        candidate["person_identity_gold"] = "A"
    if attack == "authority":
        hand["memory_write_authorized"] = True
    if attack == "over_capacity":
        hand["candidates"] = tuple(
            {**candidate, "candidate_id": UUID(int=400 + i)} for i in range(5)
        )
    with pytest.raises(ValueError):
        ProposalPixelObservation.model_validate(payload)


def test_future_hands_are_hidden_and_late_prefix_rebuild_is_order_independent():
    early = with_hands(pixel(1))
    late = with_hands(pixel(0, delayed=2), x=55)
    assert features(context([early, late], cutoff=1)) == features(context([early], cutoff=1))
    assert features(context([early, late], cutoff=2)) == features(context([late, early], cutoff=2))
    arrived = features(context([early, late], cutoff=2))
    assert len(arrived) == 2
    assert arrived[0]["hand_object_measurements"][0]["minimum_landmark_to_box_px"] == 0


def test_custody_and_model_version_are_excluded_from_neural_features():
    original = with_hands(pixel(0))
    payload = original.model_dump()
    payload["input_sha256"] = payload["hand_observation"]["input_sha256"] = "f" * 64
    payload["receipt_sha256"] = payload["hand_observation"]["capture_receipt_sha256"] = "e" * 64
    payload["hand_observation"]["model_binding"] = (
        HAND_MODEL_SHA256,
        "different-version",
        4,
        0.5,
        0.5,
    )
    changed = ProposalPixelObservation.model_validate(payload)
    a, b = context([original]), context([changed])
    assert features(a) == features(b)
    assert a.visible.prefix().provenance_json != b.visible.prefix().provenance_json
    text = json.dumps(features(a))
    assert HAND_MODEL_SHA256 not in text and "test-fixture" not in text
    assert "sha256" not in text and "model_binding" not in text


def test_roi_source_binding_and_all_regional_candidates_survive_projection():
    from test_hand_person_regions import roi_components

    from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer

    raw, detector, hands = roi_components()
    producer = NaturalVisionEvidenceProducer(detector, hands)
    producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    p = ProposalPixelObservation.from_frame(producer.frames()[0], producer.hand_frames()[0])
    assert p.visual_frame() == producer.frames()[0]
    assert p.hand_observation.hand_frame() == producer.hand_frames()[0]
    assert len(p.model_input()["hands"]["candidates"]) == 2  # overlapping regional duplicates kept
    bad = p.model_dump()
    bad["hand_observation"]["regions_evaluated"] = ()
    with pytest.raises(ValueError, match="ROI"):
        ProposalPixelObservation.model_validate(bad)


@pytest.mark.parametrize("arm", ARMS)
def test_numerical_hand_motion_changes_probability_with_identical_target_ids(arm):
    torch.set_num_threads(2)
    with torch.random.fork_rng():
        torch.manual_seed(22)
        model = TypedProposalNetwork(arm).eval()
    a, b = context([with_hands(pixel(0), x=25)]), context([with_hands(pixel(0), x=55)])
    support = generate(a).targets
    # Full same generated set: changed proposal UUIDs cannot explain the response.
    with torch.no_grad():
        left, right = distribution(model, a, support), distribution(model, b, support)
        x = [
            math.exp(left.decode(k).probability.joint_log_probability) for k in left.target_sha256s
        ]
        y = [
            math.exp(right.decode(k).probability.joint_log_probability) for k in left.target_sha256s
        ]
    assert left.target_sha256s == right.target_sha256s
    assert math.fsum(x) == pytest.approx(1, abs=1e-10)
    assert math.fsum(y) == pytest.approx(1, abs=1e-10)
    assert max(abs(u - v) for u, v in zip(x, y, strict=True)) > 0
