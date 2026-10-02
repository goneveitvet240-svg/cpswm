"""Outcome table invariants and decisions: no detector confidence likelihoods."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from cpswm.perception_mapping.surface_action_model import fit, forecast, validate
from cpswm.system import surface_episode as episode
from cpswm.system.reproducibility import content_sha256


def rows():
    return [
        dict(
            category="bottle",
            ordinal=0,
            status="reported",
            action=a,
            degrees=d,
            joint_success=v,
            source_pair=a,
        )
        for a, d, v in [("Stop", 0.0, False), ("RotateRight", 1.0, True)]
    ]


def test_empirical_dedup_missing_and_forged_counts():
    model = fit(rows() * 2, training_manifest="a" * 64)
    assert model["unique_transition_count"] == 2
    validate(model, content_sha256(model))
    assert (
        forecast(
            model, category="bottle", ordinal=0, status="unknown", action="RotateRight", degrees=1.0
        )
        is None
    )
    forged = deepcopy(model)
    next(iter(next(iter(forged["cells"].values())).values()))["successes"] = 20
    with pytest.raises(ValueError):
        validate(forged, content_sha256(forged))
    with pytest.raises(ValueError):
        validate(model, "b" * 64)


def test_actual_policy_selects_gain_and_stops_without_support(monkeypatch):
    model = fit(rows(), training_manifest="a" * 64)
    policy = dict(
        mode="empirical_joint",
        schedule=[dict(action="RotateRight", degrees=1.0)] * 2,
        budget=2,
        queries=[dict(category="bottle", ordinal=0)],
        model=model,
        model_pin=content_sha256(model),
        action_cost=0.0001,
        alternatives=[dict(action="RotateRight", degrees=1.0)],
    )
    episode.policy_configuration(policy)
    monkeypatch.setattr(episode, "owner_policy", lambda s: policy)
    monkeypatch.setattr(episode, "effective_surface_state", lambda s: dict(action_ids=["ref"]))
    monkeypatch.setattr(
        episode,
        "report_from_surface_state",
        lambda *a, **kw: dict(category="bottle", ordinal=0, status="reported"),
    )
    view = SimpleNamespace(content_sha256="v")
    stream = SimpleNamespace(
        observation_history=lambda: [
            (SimpleNamespace(reason=episode.PREFIX, action_id="ref"), "DELIVERED")
        ]
    )
    selected = episode.policy_reason(stream, view=view, source_ids=(), index=1)
    assert selected["action"] == "RotateRight" and selected["forecast"]["current"] == 0
    next(iter(model["cells"].values())).clear()
    stopped = episode.policy_reason(stream, view=view, source_ids=(), index=1)
    assert stopped["stopped"] and stopped["reason"] == "unsupported_current_joint_success"


def test_fixed_policy_rejects_hidden_model_and_bad_schedule():
    p = dict(mode="fixed_scan", schedule=[dict(action="Pass", degrees=0.0)], budget=1)
    episode.policy_configuration(p)
    p["schedule"][0]["degrees"] = 1.0
    with pytest.raises(ValueError):
        episode.policy_configuration(p)


def test_withdrawn_first_reference_cannot_change_policy_target(monkeypatch):
    model = fit(rows(), training_manifest="a" * 64)
    policy = dict(
        mode="empirical_joint",
        budget=3,
        schedule=[dict(action="RotateRight", degrees=1.0)] * 3,
        queries=[dict(category="bottle", ordinal=0)],
        model=model,
        model_pin=content_sha256(model),
        action_cost=0.0001,
        alternatives=[dict(action="RotateRight", degrees=1.0)],
    )
    monkeypatch.setattr(episode, "owner_policy", lambda s: policy)
    monkeypatch.setattr(
        episode, "effective_surface_state", lambda s: dict(action_ids=["remaining"])
    )
    monkeypatch.setattr(
        episode,
        "report_from_surface_state",
        lambda *a, **kw: dict(
            category="bottle",
            ordinal=0,
            status="unknown" if kw["reference_action"] == "original" else "reported",
        ),
    )
    stream = SimpleNamespace(
        observation_history=lambda: [
            (SimpleNamespace(reason=episode.PREFIX, action_id="original"), "DELIVERED"),
            (SimpleNamespace(reason=episode.PREFIX, action_id="remaining"), "DELIVERED"),
        ]
    )
    reason = episode.policy_reason(
        stream, view=SimpleNamespace(content_sha256="view"), source_ids=(), index=2
    )
    assert reason.get("stopped") and reason["reason"] == "unsupported_current_joint_success"
