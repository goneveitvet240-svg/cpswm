"""Multi-entity binding: one model state per (household, actor, object).

The controlled scenarios all carry a single household, a single owner and a
single object, so every arm could keep one flat model.  Real logs do not: one
JSONL file holds many households, many residents and many objects, and a model
that pools them learns a household-average habit that belongs to nobody.

Two properties are asserted here rather than assumed:

* **Partition.**  Every record lands in exactly one binding, and a binding's
  records all share its key.  Nothing is silently dropped.
* **Isolation.**  Replaying binding A and then binding B leaves B's Dirichlet,
  RLS, CF-BOCPD and CCRR state exactly as if A had never run.  This is checked
  by comparing against a run of B alone, not by inspecting private attributes.

``candidate_locations`` deserves its own guard.  A method needs the candidate
set up front, and the only honest sources are the training records themselves or
an explicit manifest the operator wrote.  Deriving it from the whole file --
test half included -- would leak the test set's locations into training.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cpswm.system.evaluation_operations.dataset_adapters import InMemoryAdapter
from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_protocol import ProjectOneProtocolConfig
from cpswm.system.evaluation_operations.project_one_stream_binding import (
    CandidatePolicy,
    ProjectOneBindingKey,
    ProjectOneMethodFactory,
    ProjectOneStreamBinding,
    bind_stream,
)

EPOCH = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)


def _record(
    index: int,
    *,
    household: str = "h1",
    actor: str = "alice",
    object_id: str = "cup",
    location: str = "table",
    context: str = "morning",
) -> ProjectOneDatasetRecord:
    return ProjectOneDatasetRecord(
        stream_id="multi",
        event_id=f"e{index:03d}",
        subject_id=actor,
        household_id=household,
        object_id=object_id,
        actor_id=actor,
        timestamp=EPOCH + timedelta(hours=index),
        context_key=context,
        context_value=0.0 if context == "morning" else 1.0,
        observed_location=location,
        observation_quality=0.9,
    )


def _stream(records):
    return InMemoryAdapter(records, (), source="test", source_version="0.1").load(
        stream_id="multi", split="pilot"
    )


def _mixed_records() -> list[ProjectOneDatasetRecord]:
    """Two households x two objects, interleaved, with distinct habits."""

    records: list[ProjectOneDatasetRecord] = []
    index = 0
    for cycle in range(6):
        records.append(
            _record(
                index,
                household="h1",
                actor="alice",
                object_id="cup",
                location="table" if cycle % 2 == 0 else "sink",
            )
        )
        index += 1
        records.append(
            _record(index, household="h1", actor="alice", object_id="keys", location="hook")
        )
        index += 1
        records.append(
            _record(
                index,
                household="h2",
                actor="bob",
                object_id="cup",
                location="desk" if cycle % 2 == 0 else "shelf",
            )
        )
        index += 1
    return records


# ---------------------------------------------------------------------------
# Partition
# ---------------------------------------------------------------------------


def test_every_record_lands_in_exactly_one_binding() -> None:
    stream, _truth = _stream(_mixed_records())
    bindings = bind_stream(stream)

    bound = [record.event_id for binding in bindings for record in binding.records]
    assert sorted(bound) == sorted(record.event_id for record in stream.records)
    assert len(bound) == len(set(bound))


def test_a_binding_holds_only_records_matching_its_key() -> None:
    stream, _truth = _stream(_mixed_records())
    for binding in bind_stream(stream):
        for record in binding.records:
            assert record.household_id == binding.key.household_id
            assert record.subject_id == binding.key.subject_id
            assert record.object_id == binding.key.object_id


def test_the_three_entity_triples_are_discovered() -> None:
    stream, _truth = _stream(_mixed_records())
    keys = {binding.key for binding in bind_stream(stream)}
    assert keys == {
        ProjectOneBindingKey(household_id="h1", subject_id="alice", object_id="cup"),
        ProjectOneBindingKey(household_id="h1", subject_id="alice", object_id="keys"),
        ProjectOneBindingKey(household_id="h2", subject_id="bob", object_id="cup"),
    }


def test_bindings_keep_records_in_chronological_order() -> None:
    stream, _truth = _stream(_mixed_records())
    for binding in bind_stream(stream):
        stamps = [record.timestamp for record in binding.records]
        assert stamps == sorted(stamps)


# ---------------------------------------------------------------------------
# Candidate locations
# ---------------------------------------------------------------------------


def test_candidate_locations_come_from_the_binding_own_records() -> None:
    """Under the leaky OBSERVED_ALL policy, retained for pre-policy runs."""

    stream, _truth = _stream(_mixed_records())
    by_key = {
        binding.key: binding for binding in bind_stream(stream, policy=CandidatePolicy.OBSERVED_ALL)
    }
    cup_h1 = by_key[ProjectOneBindingKey("h1", "alice", "cup")]
    assert set(cup_h1.candidate_locations) == {"table", "sink"}
    # h2's cup lives elsewhere entirely; its locations must not bleed across.
    assert "desk" not in cup_h1.candidate_locations
    assert cup_h1.location_source == "observed_all"


def test_an_explicit_manifest_overrides_the_observed_locations() -> None:
    stream, _truth = _stream(_mixed_records())
    key = ProjectOneBindingKey("h1", "alice", "cup")
    bindings = bind_stream(stream, candidate_locations={key: ("table", "sink", "balcony")})
    binding = next(item for item in bindings if item.key == key)
    assert binding.candidate_locations == ("table", "sink", "balcony")
    assert binding.location_source == "manifest"


def test_a_manifest_that_omits_an_observed_location_is_rejected() -> None:
    """A candidate set the data contradicts is an operator error, not a filter."""

    stream, _truth = _stream(_mixed_records())
    key = ProjectOneBindingKey("h1", "alice", "cup")
    with pytest.raises(ValueError, match="observed"):
        bind_stream(stream, candidate_locations={key: ("table",)})


def test_a_single_location_binding_is_reported_not_silently_dropped() -> None:
    """``keys`` never moves, so under a closed vocabulary no arm can run on it.

    Pinned against ``OBSERVED_ALL`` because that is the policy where the
    situation arises.  Under the default open set the binding gains the
    out-of-vocabulary slot and becomes evaluable -- which is the point of the
    open set, and is asserted separately below.
    """

    stream, _truth = _stream(_mixed_records())
    by_key = {
        binding.key: binding for binding in bind_stream(stream, policy=CandidatePolicy.OBSERVED_ALL)
    }
    keys_binding = by_key[ProjectOneBindingKey("h1", "alice", "keys")]
    assert keys_binding.candidate_locations == ("hook",)
    assert keys_binding.is_evaluable is False
    assert "single" in keys_binding.skip_reason.lower()


def test_the_open_set_default_rescues_that_same_binding() -> None:
    stream, _truth = _stream(_mixed_records())
    by_key = {binding.key: binding for binding in bind_stream(stream)}
    keys_binding = by_key[ProjectOneBindingKey("h1", "alice", "keys")]
    assert keys_binding.is_evaluable is True
    assert keys_binding.location_source == "open_set"


def test_a_two_location_binding_is_evaluable() -> None:
    stream, _truth = _stream(_mixed_records())
    by_key = {binding.key: binding for binding in bind_stream(stream)}
    assert by_key[ProjectOneBindingKey("h1", "alice", "cup")].is_evaluable is True


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def _factory() -> ProjectOneMethodFactory:
    return ProjectOneMethodFactory(config=ProjectOneProtocolConfig())


def _replay(binding: ProjectOneStreamBinding, factory: ProjectOneMethodFactory):
    methods = factory.build(binding)
    out = {}
    for method in methods:
        method.reset()
        out[method.name] = [method.observe(record) for record in binding.records]
    return out


def test_replaying_another_binding_first_changes_nothing() -> None:
    """The isolation property, checked end to end rather than by introspection."""

    stream, _truth = _stream(_mixed_records())
    by_key = {binding.key: binding for binding in bind_stream(stream)}
    first = by_key[ProjectOneBindingKey("h1", "alice", "cup")]
    second = by_key[ProjectOneBindingKey("h2", "bob", "cup")]

    alone = _replay(second, _factory())

    shared = _factory()
    _replay(first, shared)
    after = _replay(second, shared)

    for name, predictions in alone.items():
        assert len(after[name]) == len(predictions)
        for expected, actual in zip(predictions, after[name], strict=True):
            assert actual.change_probability == pytest.approx(expected.change_probability)
            assert dict(actual.predicted_location_probabilities) == pytest.approx(
                dict(expected.predicted_location_probabilities)
            )
            assert actual.decision is expected.decision


def test_the_factory_returns_fresh_instances_per_binding() -> None:
    stream, _truth = _stream(_mixed_records())
    bindings = [item for item in bind_stream(stream) if item.is_evaluable]
    factory = _factory()
    first = factory.build(bindings[0])
    second = factory.build(bindings[1])
    assert {id(item) for item in first}.isdisjoint({id(item) for item in second})


def test_the_chain_arm_carries_the_binding_identity() -> None:
    """Different objects must not collide inside the Dirichlet/RLS key space."""

    stream, _truth = _stream(_mixed_records())
    by_key = {binding.key: binding for binding in bind_stream(stream)}
    factory = _factory()
    first = factory.build(by_key[ProjectOneBindingKey("h1", "alice", "cup")])
    second = factory.build(by_key[ProjectOneBindingKey("h2", "bob", "cup")])

    def chain(methods):
        return next(item for item in methods if item.name == "full_as_is")

    payload_a = chain(first).config_payload()
    payload_b = chain(second).config_payload()
    assert payload_a["household_id"] == "h1"
    assert payload_a["owner_id"] == "alice"
    assert payload_b["household_id"] == "h2"
    assert payload_b["owner_id"] == "bob"
    assert payload_a["object_id"] == payload_b["object_id"] == "cup"


def test_building_a_non_evaluable_binding_is_refused() -> None:
    stream, _truth = _stream(_mixed_records())
    by_key = {
        binding.key: binding for binding in bind_stream(stream, policy=CandidatePolicy.OBSERVED_ALL)
    }
    with pytest.raises(ValueError, match="evaluable"):
        _factory().build(by_key[ProjectOneBindingKey("h1", "alice", "keys")])


def test_the_factory_builds_the_seven_pilot_arms() -> None:
    stream, _truth = _stream(_mixed_records())
    binding = next(item for item in bind_stream(stream) if item.is_evaluable)
    names = [method.name for method in _factory().build(binding)]
    assert names == [
        "full_as_is",
        "full_raw_clip",
        "no_rls",
        "rls_only",
        "categorical_bocpd",
        "context_frequency",
        "persistence",
    ]


def test_every_arm_in_one_binding_carries_a_distinct_config_hash() -> None:
    stream, _truth = _stream(_mixed_records())
    binding = next(item for item in bind_stream(stream) if item.is_evaluable)
    hashes = [method.config_hash() for method in _factory().build(binding)]
    assert len(set(hashes)) == len(hashes)


def test_binding_id_is_stable_and_distinct() -> None:
    stream, _truth = _stream(_mixed_records())
    first = bind_stream(stream)
    second = bind_stream(stream)
    ids = [binding.binding_id for binding in first]
    assert ids == [binding.binding_id for binding in second]
    assert len(set(ids)) == len(ids)
