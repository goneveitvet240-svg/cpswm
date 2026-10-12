"""Check attacks from a legal pending event, not an already-rejected duplicate."""

from __future__ import annotations

import copy
from dataclasses import replace
from uuid import uuid4

import pytest
from test_current_event import data as shared_data
from test_current_event import state_for

from cpswm.system.reproducibility import content_uuid


@pytest.fixture(scope="module")
def data():
    return shared_data.__wrapped__()


@pytest.fixture(scope="module")
def valid_paid_source(data):
    donor = state_for(data)
    step = data[1].steps[0]
    donor.observe(step)
    donor.predict()
    return copy.deepcopy(next(iter(donor.runtime.location_sources.values())))


def pending(data):
    state = state_for(data, consume=False)
    step = data[1].steps[0]
    state.observe(step)
    state.predict()
    assert state.runtime._last_observation.observed_location_id is None
    return state


def test_fresh_pending_positive_path_accepts_owned_paid_receipts(data, valid_paid_source):
    s = pending(data)
    source = valid_paid_source
    s.runtime.replace_current_location(source["updated"], source["payload"], s.environment)
    assert (
        s.runtime.step_index == 1 and s.runtime._last_observation.observed_location_id is not None
    )
    s.runtime.verify_internal_contracts()


@pytest.mark.parametrize(
    "attack",
    [
        "paid_hash",
        "paid_found",
        "paid_location",
        "wrong_step",
        "wrong_object",
        "wrong_episode",
        "wrong_event",
        "unrelated_actor",
        "source_id",
        "omit_receipt",
    ],
)
def test_complete_pending_forgeries_rejected_atomically(data, valid_paid_source, attack):
    s = pending(data)
    r = s.runtime
    payload = copy.deepcopy(valid_paid_source["payload"])
    observation = valid_paid_source["updated"]
    receipt = payload["paid_updates"][-1]["receipt"]
    if attack == "paid_hash":
        receipt["receipt_sha256"] = "0" * 64
    elif attack == "paid_found":
        receipt["found"] = False
    elif attack == "paid_location":
        receipt["request"]["location_id"] = str(uuid4())
    elif attack == "wrong_step":
        payload["step_id"] = str(uuid4())
    elif attack == "wrong_object":
        payload["object_id"] = str(uuid4())
    elif attack == "wrong_episode":
        payload["episode_id"] = str(uuid4())
    elif attack == "wrong_event":
        payload["event_id"] = str(uuid4())
    elif attack == "unrelated_actor":
        observation = replace(
            observation, actor_posterior={"owner": 0.8, "guest": 0.1, "unknown_actor": 0.1}
        )
    elif attack == "omit_receipt":
        payload["paid_updates"] = []
    observation = replace(
        observation,
        position_source_id=(
            uuid4() if attack == "source_id" else content_uuid("paid-current-location", payload)
        ),
    )
    old = r._state_sha256()
    ledger = r.rgrc_ledger.head_hash
    steps = r.step_index
    with pytest.raises(ValueError):
        r.replace_current_location(observation, payload, s.environment)
    assert r._state_sha256() == old and r.rgrc_ledger.head_hash == ledger and r.step_index == steps
    assert not r.location_sources
