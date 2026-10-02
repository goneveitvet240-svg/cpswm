"""Explicit scheduled/empirical surface episodes on the existing durable owner.

This boundary never borrows the CIAV name for a forced scan. A separate frozen
policy specification is part of the canonical candidate profile and every
command is checked against that specification and the actual owner history.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from cpswm.system.structure_two_continuous_input import (
        ContinuousEvidenceInput,
        ObservationCommand,
        ObservationExecutor,
    )
    from cpswm.system.structure_two_joint_consumption import JointDecisionView

from cpswm.system.reproducibility import canonical_json, content_sha256

PREFIX = "owned-surface-policy@1:"


def policy_configuration(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) not in (
        {"mode", "schedule", "budget"},
        {
            "mode",
            "schedule",
            "budget",
            "queries",
            "model",
            "model_pin",
            "alternatives",
            "action_cost",
        },
    ):
        raise ValueError("explicit frozen surface schedule and budget required")
    if value["mode"] not in ("fixed_scan", "empirical_joint"):
        raise ValueError("unsupported surface policy")
    if type(value["budget"]) is not int or value["budget"] < 1:
        raise ValueError("positive integer action budget required")
    rows = value["schedule"]
    if type(rows) is not list or len(rows) != value["budget"]:
        raise ValueError("schedule must account for every budgeted action")
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"action", "degrees"}
            or row["action"] not in {"Pass", "RotateRight", "RotateLeft"}
            or type(row["degrees"]) is not float
            or not 0 <= row["degrees"] <= 90
            or (row["action"] == "Pass") != (row["degrees"] == 0)
        ):
            raise ValueError("invalid bounded camera action")
    if value["mode"] == "fixed_scan" and set(value) != {"mode", "schedule", "budget"}:
        raise ValueError("fixed policy has unexpected fields")
    if value["mode"] == "empirical_joint":
        if "model" not in value:
            raise ValueError("empirical policy requires a frozen model")
        if any(
            type(q) is not dict
            or set(q) != {"category", "ordinal"}
            or type(q["category"]) is not str
            or not q["category"]
            or type(q["ordinal"]) is not int
            or q["ordinal"] < 0
            for q in value["queries"]
        ):
            raise ValueError("invalid public query")
        from cpswm.perception_mapping.surface_action_model import validate

        validate(value["model"], value["model_pin"])
        if value["action_cost"] != 0.0001:
            raise ValueError("this development policy retains the existing declared action cost")
        if not value["queries"] or not value["alternatives"]:
            raise ValueError("empirical policy requires public queries and allowed actions")
        policy_configuration(
            dict(
                mode="fixed_scan", schedule=value["alternatives"], budget=len(value["alternatives"])
            )
        )
    return value


def owner_policy(stream: ContinuousEvidenceInput) -> dict[str, Any]:
    profile = stream._system.core._particle_workspace.raw_candidate_profile
    if type(profile) is not dict or profile.get("profile") != "owned-mask-surface-support-raw@1":
        raise ValueError("surface policy requires its registered owner profile")
    return policy_configuration(profile["arguments"]["configuration"]["pipeline"])


def policy_reason(
    stream: ContinuousEvidenceInput,
    *,
    view: JointDecisionView,
    source_ids: tuple[UUID, ...],
    index: int,
) -> dict[str, Any]:
    policy = owner_policy(stream)
    if not 0 <= index < policy["budget"]:
        raise ValueError("surface action budget exhausted")
    selected = policy["schedule"][index]
    forecast_detail = None
    if policy["mode"] == "empirical_joint" and index > 0:
        from cpswm.perception_mapping.surface_action_model import forecast

        state = effective_surface_state(stream)
        if not state["action_ids"]:
            return dict(stopped=True, reason="no_effective_reference")
        reports = [
            report_from_surface_state(
                state,
                category=q["category"],
                ordinal=q["ordinal"],
                reference_action=state["action_ids"][0],
            )
            for q in policy["queries"]
        ]
        current = [
            forecast(
                policy["model"],
                category=r["category"],
                ordinal=r["ordinal"],
                status=r["status"],
                action="Stop",
                degrees=0.0,
            )
            for r in reports
        ]
        if any(v is None for v in current):
            return dict(stopped=True, reason="unsupported_current_joint_success")
        baseline = sum(v["probability"] for v in current if v is not None) / len(current)
        options = []
        for option in policy["alternatives"]:
            values = [
                forecast(
                    policy["model"],
                    category=r["category"],
                    ordinal=r["ordinal"],
                    status=r["status"],
                    **option,
                )
                for r in reports
            ]
            if all(v is not None for v in values):
                expected = sum(v["probability"] for v in values if v is not None) / len(values)
                options.append(
                    dict(
                        **option,
                        expected=expected,
                        net_gain=expected - baseline - policy["action_cost"],
                    )
                )
        if not options or max(v["net_gain"] for v in options) <= 0:
            return dict(
                stopped=True,
                reason="no_positive_predicted_joint_gain",
                current=baseline,
                options=options,
            )
        winner = max(options, key=lambda r: (r["net_gain"], -r["degrees"], r["action"]))
        selected = {k: winner[k] for k in ("action", "degrees")}
        forecast_detail = dict(current=baseline, options=options, model_pin=policy["model_pin"])
    return dict(
        schema=PREFIX,
        policy_sha256=content_sha256(policy),
        index=index,
        source_belief_sha256=view.content_sha256,
        source_observation_ids=[str(k) for k in source_ids],
        **selected,
        forecast=forecast_detail,
    )


def validate_surface_command(
    stream: ContinuousEvidenceInput, command: ObservationCommand, view: JointDecisionView
) -> dict[str, Any]:
    import json

    if not command.reason.startswith(PREFIX):
        raise ValueError("not a surface policy command")
    body = json.loads(command.reason.removeprefix(PREFIX))
    if type(body.get("index")) is not int:
        raise ValueError("surface schedule index is not an integer")
    earlier = [
        c
        for c, status in stream.observation_history()
        if c.reason.startswith(PREFIX)
        and c.action_id != command.action_id
        and c.decision_time <= command.decision_time
        and status != "CANCELLED_STALE_JOINT"
    ]
    if len(earlier) != body["index"]:
        raise ValueError("surface command schedule or budget differs")
    expected = policy_reason(stream, view=view, source_ids=command.source_ids, index=len(earlier))
    if (
        body != expected
        or command.action != expected["action"]
        or command.degrees != expected["degrees"]
    ):
        raise ValueError("surface command differs from frozen owner policy")
    return dict(body)


def collect_scheduled_surface(
    stream: ContinuousEvidenceInput, *, executor: ObservationExecutor, decision_time: datetime
) -> Any:
    """One owner issue/delivery/update; READY retry never duplicates acquisition."""
    with stream._lock, stream._system.core._execution_lock:
        stream._require_resolved_dispatches()
        ready = [c for c, status in stream.observation_history() if status == "READY"]
        if ready:
            if len(ready) != 1 or not ready[0].reason.startswith(PREFIX):
                raise ValueError("another pending command requires resolution")
            command = ready[0]
        else:
            view = stream._native_joint_decision_view()
            index = sum(
                c.reason.startswith(PREFIX) and s != "CANCELLED_STALE_JOINT"
                for c, s in stream.observation_history()
            )
            if index >= owner_policy(stream)["budget"]:
                return None
            ids = tuple(
                r.envelope().identity.observation_id
                for r in stream.visible_prefix(cutoff=decision_time)
            )
            reason = policy_reason(stream, view=view, source_ids=ids, index=index)
            if reason.get("stopped"):
                return None
            command = stream.prepare_observation(
                action=reason["action"],
                degrees=reason["degrees"],
                reason=PREFIX + canonical_json(reason),
                source_ids=ids,
                decision_time=decision_time,
            )
        delivery = stream.execute_observation(command, executor=executor)
        update = (
            stream.consume_owned_position_observation(command.action_id)
            if delivery.success
            else None
        )
        return command, delivery, update


def effective_surface_state(stream: ContinuousEvidenceInput) -> dict[str, Any]:
    """Rebuild support from canonical effective owner contexts, not diagnostic caches."""
    from cpswm.system.native_joint_replay import consumed_schedule
    from cpswm.system.native_raw_verification import reconstruct

    with stream._lock, stream._system.core._execution_lock:
        owner_policy(stream)
        view = stream._native_joint_decision_view()
        workspace = stream._system.core._particle_workspace
        contexts = [u.context for u in consumed_schedule(workspace) if u.context is not None]
        observations = [c for c in contexts if c.observation_update is not None]
        if not observations:
            return dict(view_sha256=view.content_sha256, records=[], history={}, action_ids=[])
        last = observations[-1]
        if any(
            c.observation_update is not None
            and c.observation_update.action_id in stream._position_withdrawals
            for c in observations
        ):
            raise ValueError("withdrawn observation remains in effective surface state")
        candidate = reconstruct(workspace.raw_candidate_profile)
        from cpswm.system.mask_surface_support import MaskSurfaceSupportProducer

        assert isinstance(candidate, MaskSurfaceSupportProducer)
        candidate.recompute_updates(
            last, tuple(c for c in contexts if c is not last and len(c.records) < len(last.records))
        )
        assert candidate.last_diagnostic is not None
        sequence = candidate.last_diagnostic["sequence"]
        if sequence is None:
            return dict(view_sha256=view.content_sha256, records=[], history={}, action_ids=[])
        return dict(
            view_sha256=view.content_sha256,
            records=sequence["records"],
            history=sequence["history"],
            action_ids=[str(c.action_id) for c in sequence["captures"]],
        )


def surface_report(
    stream: ContinuousEvidenceInput, *, category: str, ordinal: int, reference_action: str
) -> dict[str, Any]:
    return report_from_surface_state(
        effective_surface_state(stream),
        category=category,
        ordinal=ordinal,
        reference_action=reference_action,
    )


def report_from_surface_state(
    state: dict[str, Any], *, category: str, ordinal: int, reference_action: str
) -> dict[str, Any]:
    """Public first-frame ordinal query; labels and target AABBs are not arguments.

    An ordinal refers to initial image x order, never a later re-identification.
    This concrete public task does not resolve arbitrary language descriptions.
    """
    if type(category) is not str or not category or type(ordinal) is not int or ordinal < 0:
        raise ValueError("public category and nonnegative ordinal required")
    report = dict(
        status="unknown",
        category=category,
        ordinal=ordinal,
        reference_action=reference_action,
        source_view_sha256=state["view_sha256"],
        anchor_id=None,
        selected_pixel_uv=None,
        world_point_m=None,
        action_id=None,
        observation_ids=[],
        reason="reference_not_effective",
        valid_at=None,
        scene_id=None,
        temporal_scope="last_effective_capture_only",
    )
    if not state["action_ids"] or state["action_ids"][0] != reference_action:
        return report
    first, last = state["records"][0], state["records"][-1]
    candidates = sorted(
        (
            c
            for c in first["detector"]["candidates"]
            if c["category"] == category and c["detector_score"] >= 0.5
        ),
        key=lambda c: (c["box_xyxy"][0] + c["box_xyxy"][2], c["candidate_id"]),
    )
    if len(candidates) <= ordinal:
        report["reason"] = "initial_query_unresolved"
        return report

    def x(c: dict[str, Any]) -> float:
        return float(c["box_xyxy"][0] + c["box_xyxy"][2])

    if sum(x(c) == x(candidates[ordinal]) for c in candidates) != 1:
        report["reason"] = "ambiguous_initial_order"
        return report
    anchor = candidates[ordinal]["candidate_id"]
    track = next(t for t in last["tracks"] if t["anchor_id"] == anchor)
    report["reason"] = track["status"]
    if track["world_point_m"] is None:
        return report
    report.update(
        status="reported",
        anchor_id=anchor,
        selected_pixel_uv=track["selected_pixel_uv"],
        world_point_m=track["world_point_m"],
        action_id=state["action_ids"][-1],
        observation_ids=last["detector"]["observation_ids"],
        feature_ids=track["selected_feature_ids"],
        valid_at=last["detector"]["camera"]["capture_time"],
        scene_id=last["detector"]["camera"]["scene_sha256"],
    )
    return report
