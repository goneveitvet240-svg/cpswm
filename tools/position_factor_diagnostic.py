"""Controlled position arithmetic only: no labels, native receipts or owner authority.

The caller rederives and pins canonical public readout order. This helper checks
the fixed schedule and consumes its first available seed without inspecting
private membership, truth positions, validation error, or native world identity.
"""

from __future__ import annotations

import json
import math
from uuid import UUID

import numpy as np

from cpswm.data_preflight.soft_surface_position import DOMAIN
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.reproducibility import canonical_json, content_sha256, content_uuid
from cpswm.system.structure_two_conditional_updates import rebuild_conditional_state
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

COMBINATIONS = tuple(e + "/" + r for e in position.ESTIMATORS for r in position.REFERENCES)
BRANCHES = ("known", "unknown", "aggregate")
PUBLIC_KEYS = {
    "measurement_id",
    "estimator",
    "estimator_pin",
    "domain_id",
    "frame_id",
    "action_id",
    "valid_at",
    "world_point_m",
}
CONFIG = {
    "selection": "first_available_in_fixed_house_sdk_frame_and_public_seed_order",
    "frames": 96,
    "known_prior_mean": [0.0] * 6,
    "known_prior_covariance": np.eye(6).tolist(),
    "reference_origin_m": [0.0, 0.0, 0.0],
    "initial_branch_weights": {name: 1.0 for name in BRANCHES},
    "unknown_and_aggregate_world_mean_m": [0.0, 0.0, 0.0],
    "unknown_and_aggregate_world_covariance_m2": (100 * np.eye(3)).tolist(),
    "information_weight": 1.0,
    "location_and_rls_measurement_contributions": "zero",
    "density_dimension": 3,
    "density_units": "m^-3",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _uuid(value):
    try:
        return type(value) is str and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _public_records(records):
    _require(type(records) is list and len(records) == 96, "exactly 96 public frames required")
    seen_actions, seen_seeds, pins, selected = set(), set(), {}, {}
    for ordinal, record in enumerate(records):
        position._keys(
            record,
            {"house_index", "sdk_index", "action_id", "observations"},
            "public diagnostic record",
        )
        house, offset = ordinal // 8 + 1, ordinal % 8 + 4
        _require(
            type(record["house_index"]) is int
            and record["house_index"] == house
            and type(record["sdk_index"]) is int
            and record["sdk_index"] == offset,
            "fixed public house/frame schedule differs",
        )
        action = record["action_id"]
        _require(_uuid(action) and action not in seen_actions, "invalid or repeated public action")
        seen_actions.add(action)
        observations = record["observations"]
        _require(
            type(observations) is list and len(observations) % 2 == 0,
            "paired public estimators required",
        )
        frame_context = None
        for index in range(0, len(observations), 2):
            pair = observations[index : index + 2]
            for estimator, observation in zip(position.ESTIMATORS, pair, strict=True):
                position._keys(
                    observation, PUBLIC_KEYS | {"seed_id", "available", "reason"}, "public readout"
                )
                for key in ("measurement_id", "seed_id", "estimator_pin"):
                    position._digest(observation[key])
                _require(
                    type(observation["estimator"]) is str
                    and observation["estimator"] == estimator
                    and observation["seed_id"] == observation["measurement_id"]
                    and type(observation["action_id"]) is str
                    and observation["action_id"] == action
                    and type(observation["domain_id"]) is str
                    and observation["domain_id"] == DOMAIN,
                    "public estimator, seed, action or domain differs",
                )
                position._text(observation["frame_id"], "world frame")
                stamp = position._time(observation["valid_at"])
                context = (observation["frame_id"], stamp)
                _require(
                    frame_context is None or frame_context == context, "public frame epoch differs"
                )
                frame_context = context
                _require(
                    pins.setdefault(estimator, observation["estimator_pin"])
                    == observation["estimator_pin"],
                    "estimator pin changes across public frames",
                )
                _require(
                    type(observation["available"]) is bool, "public availability must be boolean"
                )
                if observation["available"]:
                    _require(observation["reason"] is None, "available readout has failure reason")
                    position._vector(observation["world_point_m"], 3, "public world point")
                    if estimator not in selected:
                        selected[estimator] = dict(
                            frame_ordinal=ordinal,
                            observation_ordinal=index + position.ESTIMATORS.index(estimator),
                            seed_ordinal=index // 2,
                            house_index=house,
                            sdk_index=offset,
                            observation={key: observation[key] for key in PUBLIC_KEYS},
                        )
                else:
                    _require(
                        type(observation["reason"]) is str
                        and observation["reason"] == "invalid_depth"
                        and observation["world_point_m"] is None,
                        "unavailable public readout must retain its reason and no point",
                    )
            _require(
                pair[0]["seed_id"] == pair[1]["seed_id"]
                and pair[0]["available"] == pair[1]["available"],
                "estimators do not share a public seed and validity",
            )
            identity = pair[0]["seed_id"]
            _require(identity not in seen_seeds, "repeated public measurement identity")
            seen_seeds.add(identity)
    return selected, pins


def _prior():
    return ConditionalAnalyticState(
        locations=(UUID(int=1), UUID(int=2)),
        alpha=(1.0, 1.0),
        a=((1.0,),),
        b=(0.0,),
        information=tuple(tuple(v for v in row) for row in np.eye(6).tolist()),
        information_vector=(0.0,) * 6,
    )


def _state(state):
    return dict(
        information=[list(row) for row in state.information],
        information_vector=list(state.information_vector),
        mean=np.linalg.solve(state.information, state.information_vector).tolist(),
        alpha=list(state.alpha),
        a=[list(row) for row in state.a],
        b=list(state.b),
        evidence_cluster_ids=[str(v) for v in state.evidence_cluster_ids],
        sha256=content_sha256(state),
    )


def _weights(logs):
    values = np.asarray([logs[name] for name in BRANCHES], dtype=np.float64)
    _require(bool(np.isfinite(values).all()), "nonfinite controlled branch density")
    unnormalized = np.exp(values - values.max())
    return dict(zip(BRANCHES, (unnormalized / unnormalized.sum()).tolist(), strict=True))


def diagnose(models, records, *, model_pins):
    """Return a deterministic JSON diagnostic; input records cannot carry labels.

    ``models`` and ``model_pins`` use estimator/reference keys, or None/None for
    a recorded fitting failure. Public order is supplied by the pinned driver,
    not authenticated here. Unknown and aggregate are identical world-space
    Gaussian fixtures, not a learned clutter or open-world model.
    """
    position._keys(models, set(COMBINATIONS), "diagnostic models")
    position._keys(model_pins, set(COMBINATIONS), "diagnostic model pins")
    selected, observed_pins = _public_records(records)
    restored = {}
    for name in COMBINATIONS:
        model, pin = models[name], model_pins[name]
        if model is None:
            _require(pin is None, "failed fit must have no model pin")
            restored[name] = None
            continue
        restored[name] = position.restore(model, pin)
        estimator, reference = name.split("/")
        _require(
            model["estimator"] == estimator
            and model["reference_kind"] == reference
            and model["domain_id"] == DOMAIN
            and (
                estimator not in observed_pins or model["estimator_pin"] == observed_pins[estimator]
            ),
            "model differs from public estimator/reference/domain",
        )
    prior = _prior()
    baseline = dict(
        log_factors={name: 0.0 for name in BRANCHES},
        normalized_weights=_weights({name: 0.0 for name in BRANCHES}),
        known_state=_state(prior),
    )
    rows = {}
    for name, model in restored.items():
        estimator, reference_kind = name.split("/")
        choice = selected.get(estimator)
        if model is None or choice is None:
            rows[name] = dict(
                status="fit_failed" if model is None else "no_available_public_observation",
                selected=choice,
                model_sha256=model_pins[name],
                no_factor=baseline,
                factor_applied=False,
                posterior=None,
            )
            continue
        observation = choice["observation"]
        reference = dict(
            reference_id=content_sha256(
                ["controlled-origin-reference", name, observation["action_id"]]
            ),
            reference_kind=reference_kind,
            domain_id=DOMAIN,
            frame_id=observation["frame_id"],
            valid_at=observation["valid_at"],
            xyz_m=[0.0] * 3,
        )
        cluster = content_uuid(
            "controlled-position-diagnostic-cluster", observation["measurement_id"]
        )
        sources = (
            content_uuid("controlled-position-diagnostic-source", observation["measurement_id"]),
        )
        measurement, predictive = position.condition(
            model,
            model_pins[name],
            observation,
            reference,
            prior,
            evidence_cluster_id=cluster,
            source_record_ids=sources,
        )
        with np.errstate(over="raise", invalid="raise"):
            try:
                point = np.asarray(observation["world_point_m"], dtype=np.float64)
                broad_logpdf = float(
                    -0.5
                    * (
                        3 * math.log(2 * math.pi)
                        + 3 * math.log(100.0)
                        + (point / 10) @ (point / 10)
                    )
                )
            except FloatingPointError as error:
                raise ValueError("controlled unknown density overflow") from error
        logs = dict(
            known=predictive["observation_log_likelihood"],
            unknown=broad_logpdf,
            aggregate=broad_logpdf,
        )
        normalized = _weights(logs)
        posterior = rebuild_conditional_state(prior, (measurement,))
        replay = rebuild_conditional_state(prior, (measurement,))
        retracted = rebuild_conditional_state(prior, ())
        _require(replay == posterior and retracted == prior, "controlled replay differs")
        before_duplicate = content_sha256(posterior)
        try:
            rebuild_conditional_state(posterior, (measurement,))
        except ValueError as error:
            duplicate_error = str(error)
            _require("repeated evidence cluster" in duplicate_error, "unexpected duplicate failure")
        else:
            raise ValueError("controlled duplicate evidence was accepted")
        _require(content_sha256(posterior) == before_duplicate, "duplicate attempt changed state")
        rows[name] = dict(
            status="controlled_numeric_diagnostic",
            selected=choice,
            model_sha256=model_pins[name],
            reference=reference,
            predictive=predictive,
            no_factor=baseline,
            log_factors=logs,
            normalized_weights=normalized,
            known_before=_state(prior),
            known_after=_state(posterior),
            delta_information=(
                np.asarray(posterior.information) - np.asarray(prior.information)
            ).tolist(),
            delta_information_vector=(
                np.asarray(posterior.information_vector) - np.asarray(prior.information_vector)
            ).tolist(),
            replay_matches=True,
            retracted=_state(retracted),
            duplicate_rejected=True,
            duplicate_error=duplicate_error,
            duplicate_state_unchanged=True,
            factor_applied=True,
        )
    result = dict(
        schema="controlled-position-factor-diagnostic@1",
        scope="CONTROLLED_NUMERIC_DIAGNOSTIC_WITHOUT_NATURAL_INSTANCE_ASSOCIATION",
        config=CONFIG,
        public_records_sha256=content_sha256(records),
        model_pins=model_pins,
        frames=96,
        combinations=rows,
        private_labels_accepted=False,
        native_receipts_produced=False,
        owner_pipeline_executed=False,
        natural_world_identity_authority=False,
        runtime_authority=False,
        calibrated=False,
        independent_acceptance=False,
    )
    return json.loads(canonical_json(result))
