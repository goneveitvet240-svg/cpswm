"""Capture R6 outcomes for the legal control and five PC-B counterexamples.

This is a diagnostic recorder, not an acceptance test.  It deliberately records
an accepted adversarial call so the state consequence is visible in JSON.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_structure_two_formal_revision_lineage as old  # noqa: E402
from test_structure_two_w3_native_particles import candidates  # noqa: E402

from cpswm.system.evaluation_operations.structure_two_selected_method import (  # noqa: E402
    ParticleRevisionReceipt,
)


FOREIGN = tuple(
    UUID(value)
    for value in (
        "aaaaaaaa-0000-4000-8000-000000000001",
        "aaaaaaaa-0000-4000-8000-000000000002",
        "aaaaaaaa-0000-4000-8000-000000000003",
        "aaaaaaaa-0000-4000-8000-000000000004",
    )
)


def _replace_statistic(arguments: dict[str, Any], index: int, statistic: Any) -> None:
    receipt = arguments["receipts"][index]
    particle_id = receipt.proposal.proposed_state.particle_id
    arguments["statistics"][particle_id] = statistic
    raw = receipt.model_dump()
    raw["proposal"]["proposed_state"]["statistic_state_ref"] = statistic.reference
    receipts = list(arguments["receipts"])
    receipts[index] = ParticleRevisionReceipt.model_validate(raw)
    arguments["receipts"] = tuple(receipts)


def _workspace_summary(core: Any) -> dict[str, Any]:
    workspace = core._particle_workspace
    bodies = {}
    for cluster, body in workspace.input_bodies.items():
        receipts, statistics, *_ = body
        bodies[str(cluster)] = {
            "receipt_particle_ids": [
                str(item.proposal.proposed_state.particle_id) for item in receipts
            ],
            "statistic_particle_ids": sorted(str(item) for item in statistics),
            "statistic_cluster_ids": {
                str(item): [str(cluster_id) for cluster_id in statistic.evidence_cluster_ids]
                for item, statistic in statistics.items()
            },
        }
    try:
        probability, unresolved = core.prepared_particle_location_marginal()
        marginal: dict[str, Any] = {
            "status": "RETURNED",
            "probabilities": {str(key): value for key, value in probability.items()},
            "unresolved": unresolved,
            "total": sum(probability.values()) + unresolved,
        }
    except Exception as exc:  # diagnostic boundary
        marginal = {"status": "REJECTED", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "core_locations": [str(item) for item in core.locations],
        "habit_locations": sorted(str(item) for item in core._habit._locations),
        "embedding_locations": sorted(str(item) for item in core._embeddings),
        "record_particle_ids": sorted(str(item) for item in workspace.records),
        "record_statistic_clusters": {
            str(item): [str(cluster) for cluster in record.statistics.evidence_cluster_ids]
            for item, record in workspace.records.items()
        },
        "input_journal": {str(key): value for key, value in workspace.input_journal.items()},
        "input_bodies": bodies,
        "ledger_head_sha256": core._hybrid_loop.ledger.export_state().manifest.head_hash,
        "semantic_identity": dict(core.semantic_memory_identity()),
        "marginal": marginal,
    }


def _capture(
    case_id: str,
    setup: Callable[[Any, Any], Any],
    attack: Callable[[Any, Any, Any], Any],
) -> dict[str, Any]:
    probe = old._legacy_history(1)
    core = probe.system.core
    initial = _workspace_summary(core)
    context = setup(probe, core)
    pre_attack = _workspace_summary(core)
    try:
        result = attack(probe, core, context)
        call = {
            "status": "ACCEPTED_OR_RETURNED",
            "result_type": type(result).__name__,
        }
    except Exception as exc:  # diagnostic boundary
        call = {"status": "REJECTED", "error": f"{type(exc).__name__}: {exc}"}
    after = _workspace_summary(core)
    return {
        "id": case_id,
        "call": call,
        "initial": initial,
        "pre_attack": pre_attack,
        "after": after,
        "ledger_head_unchanged_during_public_call": (
            pre_attack["ledger_head_sha256"] == after["ledger_head_sha256"]
        ),
        "semantic_identity_changed_during_public_call": (
            pre_attack["semantic_identity"] != after["semantic_identity"]
        ),
    }


def no_setup(_probe: Any, _core: Any) -> None:
    return None


def setup_support_rebind(_probe: Any, core: Any) -> None:
    core.locations = (*core.locations[:-1], FOREIGN[0])


def setup_stale_readout(_probe: Any, core: Any) -> None:
    core.stage_prepared_particle_candidates(**candidates(core))
    core.locations = FOREIGN


def setup_parent_child_switch(probe: Any, core: Any) -> None:
    core.stage_prepared_particle_candidates(**candidates(core))
    core.process_transition(probe.transition_for(probe.observed_days()[1]))
    core.locations = FOREIGN


def setup_cluster_mismatch(_probe: Any, core: Any) -> dict[str, Any]:
    arguments = candidates(core)
    receipt = arguments["receipts"][0]
    particle_id = receipt.proposal.proposed_state.particle_id
    statistic = replace(
        arguments["statistics"][particle_id],
        evidence_cluster_ids=(FOREIGN[0],),
    )
    _replace_statistic(arguments, 0, statistic)
    return arguments


def setup_unreferenced_statistic(_probe: Any, core: Any) -> dict[str, Any]:
    arguments = candidates(core)
    template = next(iter(arguments["statistics"].values()))
    arguments["statistics"][FOREIGN[0]] = replace(
        template,
        locations=FOREIGN,
        evidence_cluster_ids=(FOREIGN[1],),
    )
    return arguments


def stage_default(_probe: Any, core: Any, _context: Any) -> Any:
    return core.stage_prepared_particle_candidates(**candidates(core))


def stage_step_one(_probe: Any, core: Any, _context: Any) -> Any:
    return core.stage_prepared_particle_candidates(**candidates(core, step=1))


def stage_context(_probe: Any, core: Any, context: dict[str, Any]) -> Any:
    return core.stage_prepared_particle_candidates(**context)


def readout(_probe: Any, core: Any, _context: Any) -> Any:
    return core.prepared_particle_location_marginal()


def main() -> None:
    cases = (
        ("LEGAL-CONTROL", no_setup, stage_default),
        ("W3-PCB-01", setup_support_rebind, stage_default),
        ("W3-PCB-02", setup_stale_readout, readout),
        ("W3-PCB-03", setup_parent_child_switch, stage_step_one),
        ("W3-PCB-04", setup_cluster_mismatch, stage_context),
        ("W3-PCB-05", setup_unreferenced_statistic, stage_context),
    )
    payload = {
        "schema_version": "pc-b-w3-r6-observations-v1",
        "tested_sha": "1bd513f51ab7e54a7290870a5f34b524254d55c6",
        "interpretation": (
            "A diagnostic exit code of zero means capture completed, not that the "
            "adversarial boundary passed. Inspect each call.status and state delta."
        ),
        "cases": [
            _capture(case_id, setup, attack) for case_id, setup, attack in cases
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
