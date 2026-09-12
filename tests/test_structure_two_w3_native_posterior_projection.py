"""Real native posterior producer/consumer; no positive test enrolls an authority."""

import sys
from dataclasses import replace
from math import exp
from uuid import uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_particles import candidates
from test_structure_two_w3_round5_boundaries import direct_outcome, state
from test_structure_two_w3_round6_prepared_boundary import reseal, snapshot

from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import native_content_sha256
from cpswm.system.structure_two_semantic_identity import semantic_memory_state


def projected(core, step=0):
    source = core.current_posterior_projection_source()
    args = candidates(core, step=step)
    return reseal(
        args,
        evidence_semantics="posterior_projection_not_likelihood",
        source_posterior_snapshot_id=source.source_id,
        posterior_projection_log_factor=source.log_factor(args["receipts"][0]),
    )


def test_default_observation_publishes_real_pchmp_source_and_weight_consumes_it():
    probe = old._legacy_history(1)
    core = probe.system.core
    source = core.current_posterior_projection_source()
    assert source.history_after == core._event_histories[source.history_after.latest.revision_id]
    assert source.transition.evidence and source.posterior.evidence_subgraph
    assert source.producer_context[0].applied_weight > 0
    args = projected(core)
    before = snapshot(probe)
    batch = core.stage_prepared_particle_candidates(**args)
    p = exp(args["receipts"][0].posterior_projection_log_factor)
    assert batch.particle_weights[0].posterior_probability == pytest.approx(
        4 * p / (4 * p + 4 / 3 + 1)
    )
    assert batch.particle_weights[0].posterior_probability > 0
    distribution, unresolved = core.prepared_particle_location_marginal()
    assert sum(distribution.values()) > 0 and unresolved > 0
    assert snapshot(probe)[1:] == before[1:]
    after = snapshot(probe)
    assert core.stage_prepared_particle_candidates(**args) == batch
    assert snapshot(probe) == after


@pytest.mark.parametrize(
    "attack",
    [
        "random",
        "current_uuid",
        "foreign_run",
        "foreign_object",
        "factor",
        "raw_mislabeled",
        "revoked",
        "stale",
    ],
)
def test_invalid_projection_is_atomic_and_legal_retry_works(attack):
    probe = old._legacy_history(1)
    core = probe.system.core
    args = projected(core)
    if attack in {"foreign_run", "foreign_object"}:
        other = old.BackboneWiringProbe.build(seed=8 if attack == "foreign_object" else 7)
        other.system.core.process_transition(other.transition_for(other.observed_days()[0]))
        args = reseal(
            args,
            source_posterior_snapshot_id=other.system.core.current_posterior_projection_source().source_id,
        )
    elif attack in {"random", "current_uuid"}:
        args = reseal(
            args,
            source_posterior_snapshot_id=uuid4()
            if attack == "random"
            else core.current_snapshot.snapshot_id,
        )
    elif attack == "factor":
        args = reseal(
            args,
            posterior_projection_log_factor=args["receipts"][0].posterior_projection_log_factor
            + 0.1,
        )
    elif attack == "raw_mislabeled":
        args = reseal(
            args,
            evidence_semantics="raw_observation_likelihood",
            posterior_projection_log_factor=0.0,
        )
    elif attack in {"revoked", "stale"}:
        if attack == "revoked":
            core.apply_event_revision_outcome(
                direct_outcome(core, next(iter(core._committed_events)))
            )
        core.process_transition(probe.transition_for(probe.observed_days()[1]))
    before = snapshot(probe)
    with pytest.raises(ValueError):
        core.stage_prepared_particle_candidates(**args)
    assert snapshot(probe) == before
    assert core.stage_prepared_particle_candidates(**projected(core)).particle_weights


@pytest.mark.parametrize("attack", ["posterior", "parent", "rekey", "context", "world"])
def test_complete_resealing_cannot_replace_actual_producer_dependencies(attack):
    probe = old._legacy_history(1)
    core = probe.system.core
    source = core.current_posterior_projection_source()
    args = projected(core)
    if attack == "posterior":
        posterior = source.posterior.model_dump()
        values = posterior["posterior_by_hypothesis_id"]
        keys = list(values)
        values[keys[0]], values[keys[1]] = values[keys[1]], values[keys[0]]
        source = replace(source, posterior=type(source.posterior).model_validate(posterior))
    elif attack == "parent":
        other = old._legacy_history(2).system.core.current_posterior_projection_source()
        source = replace(source, history_before=other.history_before)
    elif attack == "rekey":
        source = replace(source, source_id=uuid4())
    elif attack == "context":
        source = replace(
            source,
            producer_context=(
                replace(source.producer_context[0], applied_weight=0.123),
                source.producer_context[1],
            ),
        )
    else:
        source = replace(source, locations=tuple(uuid4() for _ in source.locations))
    source = replace(source, body_sha256=native_content_sha256(source.body()))
    # Adversarial private corruption is a negative test, never positive enrollment.
    original = dict(core._particle_workspace.posterior_sources)
    core._particle_workspace.posterior_sources[source.source_id] = source
    args = reseal(args, source_posterior_snapshot_id=source.source_id)
    before = snapshot(probe)
    with pytest.raises(ValueError):
        core.stage_prepared_particle_candidates(**args)
    assert snapshot(probe) == before
    core._particle_workspace.posterior_sources = original
    assert core.stage_prepared_particle_candidates(**projected(core)).particle_weights


def test_same_posterior_cannot_be_recounted_under_a_new_candidate_cluster():
    probe = old._legacy_history(1)
    core = probe.system.core
    core.stage_prepared_particle_candidates(**projected(core))
    before = snapshot(probe)
    with pytest.raises(ValueError, match="already consumed"):
        core.stage_prepared_particle_candidates(**projected(core, step=1))
    assert snapshot(probe) == before
    core.process_transition(probe.transition_for(probe.observed_days()[1]))
    assert core.stage_prepared_particle_candidates(**projected(core, step=1)).particle_weights


@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
def test_consumption_interrupt_restores_dependency_journal_and_retries(exception):
    probe = old._legacy_history(1)
    core = probe.system.core
    args = projected(core)
    before = snapshot(probe)
    code = core._particle_workspace.advance.__func__.__code__
    prior = sys.getprofile()

    def profile(frame, event, result):
        if frame.f_code is code and event == "return":
            raise exception("consumer interrupted")

    try:
        sys.setprofile(profile)
        with pytest.raises(exception):
            core.stage_prepared_particle_candidates(**args)
    finally:
        sys.setprofile(prior)
    assert snapshot(probe) == before
    assert core.stage_prepared_particle_candidates(**args).particle_weights


def test_projection_semantics_reproduce_while_execution_and_source_ids_remain_distinct():
    semantics = []
    executions = []
    sources = []
    for _ in range(2):
        core = old._legacy_history(1).system.core
        sources.append(core.current_posterior_projection_source().source_id)
        core.stage_prepared_particle_candidates(**projected(core))
        semantics.append(content_sha256(semantic_memory_state(core)))
        executions.append(state(core))
    assert sources[0] != sources[1] and executions[0] != executions[1]
    assert semantics[0] == semantics[1]


@pytest.mark.parametrize("hash_seed", ["5", "11"])
def test_real_projection_consumes_under_independent_python_hash_seeds(hash_seed):
    import os
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = """
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_posterior_projection import projected
core = old._legacy_history(1).system.core
source = core.current_posterior_projection_source()
source.validate_content()
batch = core.stage_prepared_particle_candidates(**projected(core))
assert batch.particle_weights[0].posterior_probability > 0
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env={
            **os.environ,
            "PYTHONHASHSEED": hash_seed,
            "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root / "tests"))),
        },
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
