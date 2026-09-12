"""Semantic revision state alongside (never instead of) process/run bindings.

Local ledger identifiers are alpha-renamed, preserving equality and references.
Raw ledger integrity is checked first, then its canonical records are rehashed.
External object/location/source/authorization identifiers remain bound verbatim.
The envelope covers memory/revision statistics, membership, pending regime evidence
and action readout; it is not a serialization of arbitrary Python execution state.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from cpswm.system.continual.hybrid_statistics import HybridStatisticLedger
from cpswm.system.reproducibility import content_sha256

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def semantic_memory_state(core: Any) -> dict[str, Any]:
    """Return inspectable semantic content; all runtime binding checks stay active."""
    aliases: dict[str, str] = {}

    def bind(value: Any, label: str) -> None:
        if value is not None:
            aliases.setdefault(str(value), label)

    # The operation order, not a random UUID sort, defines replacement identities.
    for index, operation in enumerate(core.revision_transactions):
        bind(operation.corrected_revision_id, f"correction:{index}")
    for index, event in enumerate(core._observed_events.values()):
        bind(event.evidence.metadata.record_id, f"evidence:{index}")
    for index, event in enumerate(core._revision_parent_events.values()):
        bind(event.evidence.metadata.record_id, f"parent_evidence:{index}")
    for index, history in enumerate(core._revision_binding_history.values()):
        for version, binding in enumerate(history):
            bind(binding.snapshot_id, f"published:{index}:{version}")
    bind(core.current_snapshot.snapshot_id, "current_snapshot")

    history_hashes: dict[str, str] = {}
    revisions_to_normalize = {}
    for history in core._event_histories.values():
        # Re-run the raw revision content hashes and content-derived UUID checks
        # before translating any synthesized feedback evidence identities.
        type(history).model_validate(history.model_dump())
    for index, operation in enumerate(core.revision_transactions):
        history = core._event_histories.get(operation.corrected_revision_id)
        if history is None or history.latest.revision_id != operation.corrected_revision_id:
            continue  # synchronous statistical corrections retain the original CHEH history
        parents = [
            r.revision_no
            for r in history.revisions
            if r.revision_id == operation.superseded_revision_id
        ]
        if len(parents) != 1:
            raise ValueError("feedback history is missing its formal parent")
        for revision in history.revisions:
            if revision.revision_no <= parents[0]:
                continue
            label = f"feedback_revision:{index}:{revision.revision_no}"
            bind(revision.revision_id, label)
            for slot, cluster in enumerate(revision.revision_evidence_cluster_ids):
                bind(cluster, f"{label}:cluster:{slot}")
            # Location revisions cite actual external feedback; actor/mechanism/
            # role revisions consume model-created evidence records. Their
            # source/claim fingerprints and the formal feedback IDs stay intact.
            if revision.update_kind.value != "revise_location":
                for slot, record in enumerate(revision.revision_evidence_record_ids):
                    if record not in operation.evidence_source_record_ids:
                        bind(record, f"{label}:evidence:{slot}")
            revisions_to_normalize[revision.revision_id] = revision

    exported = core._hybrid_loop.ledger.export_state()
    HybridStatisticLedger.restore_from_export(exported)
    for entry in exported.entries:
        row = entry.record
        bind(row.get("record_id"), f"ledger:{entry.sequence}")
        bind(row.get("evidence_cluster_id"), f"cluster:{entry.sequence}")
        certificate = row.get("risk_certificate", {})
        bind(certificate.get("belief_snapshot_id"), f"risk_snapshot:{entry.sequence}")
        bind(certificate.get("counterfactual_id"), f"counterfactual:{entry.sequence}")

    def canonical(value: Any) -> Any:
        if isinstance(value, UUID):
            return aliases.get(str(value), str(value))
        if isinstance(value, str):
            if value in history_hashes:
                return history_hashes[value]
            return _UUID.sub(lambda match: aliases.get(match[0], match[0]), value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, np.ndarray):
            return value.tolist()
        if is_dataclass(value) and not isinstance(value, type):
            return {item.name: canonical(getattr(value, item.name)) for item in fields(value)}
        if hasattr(value, "model_dump"):
            return canonical(value.model_dump(mode="json"))
        if isinstance(value, Mapping):
            return {str(canonical(key)): canonical(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [canonical(item) for item in value]
        if isinstance(value, (set, frozenset)):
            return sorted((canonical(item) for item in value), key=repr)
        return value

    for revision in revisions_to_normalize.values():
        history_hashes[revision.revision_content_sha256] = content_sha256(
            canonical(revision.content_payload())
        )

    # Raw content_hash and chain hashes are derived from raw UUIDs.  Recompute
    # their semantic counterparts after verifying the original full hash chain.
    records = []
    previous = "0" * 64
    ledger_hashes = {previous: previous}
    for entry in exported.entries:
        row = canonical(entry.record)
        if "content_hash" in row:
            row["content_hash"] = content_sha256(
                {key: value for key, value in row.items() if key != "content_hash"}
            )
        record_hash = content_sha256(row)
        chain_hash = content_sha256((entry.sequence, previous, record_hash))
        records.append(
            {
                "sequence": entry.sequence,
                "record": row,
                "previous_hash": previous,
                "record_hash": record_hash,
                "entry_hash": chain_hash,
            }
        )
        previous = chain_hash
        ledger_hashes[entry.entry_hash] = chain_hash
    # Validate raw authorization and complete historical links before replacing
    # any hash derived from local identities. Revoked grants remain valid history;
    # their live eligibility is computed separately by the original guard.
    operations = {}
    consumed = set()
    for operation in core.revision_transactions:
        if operation.superseded_revision_id in consumed:
            raise ValueError("duplicate revision transaction parent")
        consumed.add(operation.superseded_revision_id)
        if operation.superseded_revision_id not in core._revision_parent_events:
            raise ValueError("missing revision parent input")
        if operation.corrected_revision_id is not None:
            if operation.corrected_revision_id in operations:
                raise ValueError("duplicate corrected revision identity")
            operations[operation.corrected_revision_id] = operation

    semantic_records: dict[UUID, dict[str, Any]] = {}
    visiting = set()

    def qualification(rid: UUID) -> dict[str, Any]:
        if rid in visiting:
            raise ValueError("cyclic qualification lineage")
        if rid in semantic_records:
            return semantic_records[rid]
        record = core._write_eligibility.get(rid)
        if record is None or record.revision_id != rid:
            raise ValueError("missing or mismatched qualification reference")
        visiting.add(rid)
        normalized: dict[str, Any] = canonical(record)
        if record.parent_revision_id is not None:
            parent = core._write_eligibility.get(record.parent_revision_id)
            if parent is None or record.parent_eligibility_sha256 != content_sha256(parent):
                raise ValueError("invalid raw parent qualification digest")
            operation = operations.get(rid)
            if (
                operation is None
                or operation.superseded_revision_id != record.parent_revision_id
                or operation.evidence_source_record_ids
                != record.correction_evidence_source_record_ids
                or record.correction_outcome_sha256 != content_sha256(operation)
                or record.origin_path != "formal_correction_transaction"
                or sum(
                    g.authority == "formal_correction_transaction" for g in record.authorizations
                )
                != 1
            ):
                raise ValueError("invalid raw correction lineage")
            normalized["parent_eligibility_sha256"] = content_sha256(
                qualification(record.parent_revision_id)
            )
            normalized["correction_outcome_sha256"] = content_sha256(canonical(operation))
        elif record.origin_path == "formal_correction_transaction":
            raise ValueError("missing formal correction parent")
        for index, grant in enumerate(record.authorizations):
            if grant.authority == "formal_correction_transaction":
                operation = operations.get(rid)
                if (
                    operation is None
                    or grant.granting_revision_id != record.parent_revision_id
                    or grant.basis_sha256 != content_sha256(operation)
                ):
                    raise ValueError("invalid raw correction authorization")
                digest = content_sha256(canonical(operation))
            elif grant.authority in (
                "ccrr_habit_change_promotion",
                "unblocked_transition_commit",
                "ccrr_rebuild_replay_promotion",
            ):
                basis = json.loads(grant.basis_json)
                grantor = core._write_eligibility.get(grant.granting_revision_id)
                if grant.basis_sha256 != content_sha256(basis):
                    raise ValueError("invalid raw authorization basis")
                if grant.authority == "ccrr_habit_change_promotion":
                    if (
                        basis.get("conclusion") != "habit_change"
                        or grantor is None
                        or grantor.origin_write_blocked
                    ):
                        raise ValueError("invalid raw CCRR authorization")
                elif record.origin_write_blocked:
                    raise ValueError("blocked origin cannot use replay or ordinary authority")
                elif grant.authority == "unblocked_transition_commit" and (
                    grant.granting_revision_id != rid
                    or not (
                        basis.get("allow_long_term_write")
                        or basis.get("rgrc_gate_enabled") is False
                    )
                ):
                    raise ValueError("invalid raw ordinary authorization")
                semantic_basis = canonical(basis)
                if grant.authority == "ccrr_rebuild_replay_promotion":
                    log_ids = basis.get("observation_log_revision_ids")
                    if (
                        log_ids is None
                        or grant.granting_revision_id is not None
                        or content_sha256(tuple(log_ids)) != basis.get("observation_log_sha256")
                    ):
                        raise ValueError("invalid raw replay authorization log")
                    semantic_basis["observation_log_sha256"] = content_sha256(
                        tuple(canonical(log_ids))
                    )
                normalized["authorizations"][index]["basis_json"] = json.dumps(
                    semantic_basis, sort_keys=True
                )
                digest = content_sha256(semantic_basis)
            else:
                raise ValueError("unknown write authority")
            normalized["authorizations"][index]["basis_sha256"] = digest
        visiting.remove(rid)
        semantic_records[rid] = normalized
        return normalized

    for rid in core._write_eligibility:
        qualification(rid)
    observations = canonical(core._observed_events)
    qualifications = {}
    for rid in core._write_eligibility:
        row = dict(core.observation_write_eligibility(rid))
        # These hashes bind the exact raw parent/outcome; preserve their semantic
        # meaning by hashing the corresponding normalized full bodies.
        record = core._write_eligibility[rid]
        normalized = semantic_records[rid]
        if record.parent_revision_id is not None:
            row["parent_eligibility_sha256"] = normalized["parent_eligibility_sha256"]
            row["correction_outcome_sha256"] = normalized["correction_outcome_sha256"]
        for index, grant in enumerate(row["authorizations"]):
            grant["basis_sha256"] = normalized["authorizations"][index]["basis_sha256"]
            grant["basis"] = json.loads(normalized["authorizations"][index]["basis_json"])
        qualifications[str(canonical(rid))] = canonical(row)
    router = core._automatic_regimes
    workspace = core._particle_workspace

    def prepared(value: Any) -> Any:
        """Translate verified ledger-prefix references, retaining full bodies."""
        value = canonical(value)
        if isinstance(value, dict):
            return {key: prepared(item) for key, item in value.items()}
        if isinstance(value, list):
            return [prepared(item) for item in value]
        if isinstance(value, str):
            if value.startswith("hybrid-ledger:"):
                raw = value.removeprefix("hybrid-ledger:")
                if raw not in ledger_hashes:
                    raise ValueError("prepared particle has a foreign ledger prefix")
                return "hybrid-ledger:" + ledger_hashes[raw]
            return ledger_hashes.get(value, value)
        return value

    particle_payload = prepared(workspace.state_payload())
    for pid, particle in workspace.records.items():
        if (
            particle.source_frame_sha256 != content_sha256(particle.source_frame)
            or particle.ledger_head_sha256 not in ledger_hashes
            or particle.state.statistic_state_ref != particle.statistics.reference
            or particle.state.ledger_lineage_ref != "hybrid-ledger:" + particle.ledger_head_sha256
            or (
                particle.state.parent_particle_id is not None
                and particle.state.parent_particle_id not in workspace.records
            )
        ):
            raise ValueError("invalid raw prepared particle lineage or source")
        particle_payload["records"][str(canonical(pid))]["source_frame_sha256"] = content_sha256(
            prepared(particle.source_frame)
        )
    if set(workspace.input_journal) != set(workspace.input_bodies):
        raise ValueError("missing raw prepared input journal body")
    for cluster, digest in workspace.input_journal.items():
        body = workspace.input_bodies[cluster]
        if digest != content_sha256(body):
            raise ValueError("invalid raw prepared input digest")
        particle_payload["input_journal"][str(canonical(cluster))] = content_sha256(prepared(body))
    return {
        "schema": "structure-two-semantic-memory@1",
        "configuration": canonical(
            (
                core.owner_key,
                core.object_instance_id,
                core.locations,
                core.authorization_scope_id,
                core.loop_config,
                core._action_readout,
            )
        ),
        "observed": observations,
        "committed": canonical(core._committed_events),
        "quarantined": canonical(core._quarantined_events),
        "fast_action": canonical(core._fast_action_events),
        "qualifications": qualifications,
        "operations": canonical(core.revision_transactions),
        "revision_parent_events": canonical(core._revision_parent_events),
        "prepared_particle_workspace": particle_payload,
        "event_histories": canonical(core._event_histories),
        "bindings": canonical(core._revision_binding_history),
        "derived_archive": canonical(core._derived_event_archive),
        "derived_lifecycle": canonical(core._derived_event_lifecycle),
        "dirichlet": core._habit.canonical_state_hash(),
        "rls": canonical({name: core.rls_regime_snapshot(name) for name in core._regimes._heads}),
        "active_regime": core.active_regime,
        "observation_count": core.observation_count,
        "regime_pending": canonical(router._pending),
        "cause_snapshot": canonical(core.current_cause_snapshot),
        "ledger": {"config": canonical(exported.config), "records": records, "head": previous},
        "action": canonical(core.action_location_distribution(core.current_snapshot)),
    }


def semantic_memory_identity(core: Any) -> dict[str, str]:
    source_root = Path(__file__).resolve().parents[1]
    source_hash = content_sha256(
        {
            str(path.relative_to(source_root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source_root.rglob("*.py"))
        }
    )
    semantic = semantic_memory_state(core)
    return {
        "semantic_state_sha256": content_sha256(semantic),
        "source_sha256": source_hash,
        "source_bound_semantic_sha256": content_sha256((source_hash, semantic)),
        "execution_state_sha256": core._execution_observable_state_sha256(),
    }
