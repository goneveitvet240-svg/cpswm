"""Deterministic proposal support from causal measurements and revision history.

The development grammar enumerates completed chains on the observed timestamp
grid, including hidden events and repeated handoffs. Grid points are hypothesis
times, NOT annotated event boundaries. No scores, priors or truth labels prune
the grammar. Resource overflow rejects the entire request, never a partial beam.
This finite proposal grammar is not complete continuous/open-world inference and
does not authorize native statistics, ledger writes or particle publication.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from typing import Any
from uuid import UUID

from cpswm.data_preflight.proposal_perception import (
    ProposalPixelObservation,
    pixel_hypothesis_bindings,
)
from cpswm.data_preflight.proposal_samples import (
    EventNode,
    FullHypothesis,
    LocationBinding,
    ProposalContext,
    ProposalTarget,
    VisibleRecords,
    export_context,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    OrderedActorRole,
    ParticleChangeCause,
    TypedParticleState,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

GRAMMAR = "observed-time-complete-event-grammar-development@1"


def causal_context(context: ProposalContext) -> ProposalContext:
    """Strip pending records before generation, hashing and inference persistence."""
    if type(context) is not ProposalContext:
        raise ValueError("candidate generation requires context without supervision")
    clean = ProposalContext.model_validate(context.model_dump())
    prefix = clean.visible.prefix()
    ids = {UUID(r["record_id"]) for r in json.loads(prefix.provenance_json)["included_records"]}
    visible = clean.visible
    return ProposalContext.model_validate(
        {
            **clean.model_dump(),
            "visible": {
                "opportunities": [r for r in visible.opportunities if r.metadata.record_id in ids],
                "detections": [r for r in visible.detections if r.metadata.record_id in ids],
                "actor_evidence": [
                    r for r in visible.actor_evidence if r.metadata.record_id in ids
                ],
                "arrivals": [r for r in visible.arrivals if r.record_id in ids],
                "cutoff": visible.cutoff,
                "pixel_observations": [
                    r for r in visible.pixel_observations if r.observation_id in ids
                ],
            },
        }
    )


def bootstrap_pixel_context(
    observations: tuple[ProposalPixelObservation, ...],
    *,
    cutoff: datetime,
    source_snapshot_id: UUID,
) -> ProposalContext:
    """Produce local identity *hypothesis* support from all arrived detections.

    Rebuild association in capture order when late frames arrive; all alternative
    track links are retained. A track key is never a household/person identity.
    There is no mapping from a pixel box to a world location or calibrated pose.
    """
    visible = VisibleRecords(
        opportunities=(), detections=(), arrivals=(), cutoff=cutoff, pixel_observations=observations
    )
    visible.prefix()  # validate even pending records, scope and duplicate IDs
    bindings = pixel_hypothesis_bindings(observations, cutoff)
    instances, actors = {"unknown_instance"}, {"unknown_actor"}
    for binding in bindings:
        (actors if binding.kind == "actor" else instances).add(binding.key)
    return causal_context(
        ProposalContext(
            source_snapshot_id=source_snapshot_id,
            visible=visible,
            parents=(),
            revisions=(),
            instance_support=tuple(sorted(instances)),
            actor_support=tuple(sorted(actors)),
            pixel_identity_bindings=bindings,
            location_support=(LocationBinding(location_key="unknown_location", origin="unknown"),),
        )
    )


@dataclass(frozen=True)
class GeneratedSupport:
    context_json: str
    targets_json: tuple[str, ...]
    report_json: str

    @property
    def context(self) -> ProposalContext:
        return ProposalContext.model_validate_json(self.context_json)

    @property
    def targets(self) -> tuple[ProposalTarget, ...]:
        return tuple(ProposalTarget.model_validate_json(t) for t in self.targets_json)

    @property
    def report(self) -> dict[str, Any]:
        return dict(json.loads(self.report_json))


def event_grid(
    times: tuple[datetime, ...], actors: tuple[str, ...], locations: tuple[str, ...]
) -> Iterator[tuple[dict[str, Any], ...]]:
    """All grammar-complete chains on this finite grid, no top-k or hop limit."""
    if not times:
        return

    def node(
        time: datetime, kind: str, actor: str, location: str, receiver: str | None = None
    ) -> dict[str, Any]:
        return {
            "time": time,
            "kind": kind,
            "actor_key": actor,
            "receiver_key": receiver,
            "location_key": location,
        }

    # Singleton alternatives use the latest observed time. Earlier singletons
    # are not a separate hypothesis about the current state.
    for kind, actor, loc in product(("unresolved", "no_move"), actors, locations):
        yield (node(times[-1], kind, actor, loc),)

    def suffix(
        start: int, chain: tuple[dict[str, Any], ...], holder: str, carried: bool
    ) -> Iterator[tuple[dict[str, Any], ...]]:
        for i in range(start, len(times)):
            for loc in locations:
                if carried:
                    yield (*chain, node(times[i], "place", holder, loc))
                # A nonterminal event needs at least one later terminal slot.
                if i + 1 < len(times):
                    yield from suffix(
                        i + 1, (*chain, node(times[i], "carry", holder, loc)), holder, True
                    )
                    if carried:
                        for receiver in actors:
                            if receiver != holder:
                                yield from suffix(
                                    i + 1,
                                    (*chain, node(times[i], "handoff", holder, loc, receiver)),
                                    receiver,
                                    carried,
                                )

    for i in range(len(times) - 2):
        for actor, loc in product(actors, locations):
            yield from suffix(i + 1, (node(times[i], "pick_up", actor, loc),), actor, False)


def ordered_roles(events: tuple[EventNode, ...]) -> tuple[OrderedActorRole, ...]:
    roles: list[OrderedActorRole] = []
    counts: Counter[str] = Counter()
    names = {"pick_up": "pickup_actor", "carry": "carrier", "place": "placer"}
    for event in events:
        pairs = (
            [(names[event.kind], event.actor_key)]
            if event.kind in names
            else [("handoff_giver", event.actor_key), ("handoff_receiver", event.receiver_key)]
            if event.kind == "handoff"
            else []
        )
        for role, actor in pairs:
            counts[role] += 1
            roles.append(
                OrderedActorRole(
                    role=role if counts[role] == 1 else f"{role}:{counts[role]}",
                    actor_key=actor or "",
                )
            )
    return tuple(roles)


def generate_runtime_candidates(
    context: ProposalContext,
    *,
    bootstrap_ledger_lineage_ref: str,
    max_candidates: int = 4096,
) -> GeneratedSupport:
    """Enumerate diagnostic candidates, retaining native operation prerequisites.

    Bootstrap has no invented parent. Analytic references of changed hypotheses
    are explicitly pending; retract/reactivate preserve the original reference.
    The runtime must later compute/bind all three analytic blocks before publish.
    """
    if type(max_candidates) is not int or max_candidates <= 0:
        raise ValueError("positive whole-request resource limit required")
    if not bootstrap_ledger_lineage_ref.strip():
        raise ValueError("explicit current bootstrap ledger reference required")
    context = causal_context(context)
    prefix = context.visible.prefix()
    provenance = json.loads(prefix.provenance_json)["included_records"]
    evidence = tuple(sorted((UUID(r["record_id"]) for r in provenance), key=str))
    if not evidence:
        raise ValueError("no arrived evidence; no invented candidate")
    times = tuple(sorted({context._evidence_time(r) for r in evidence}))
    arrivals = {r.record_id: r.received_at for r in context.visible.arrivals}
    arrivals.update((p.observation_id, p.arrival_time) for p in context.visible.pixel_observations)
    delayed = any(arrivals[r] > context._evidence_time(r) for r in evidence)
    revisions = {r.revision_id: r for r in context.revisions}
    parents = tuple(sorted(context.parents, key=lambda p: str(p.state.particle_id)))
    active = tuple(p for p in parents if revisions[p.state.revision_id].status == "active")
    retracted = tuple(p for p in parents if revisions[p.state.revision_id].status == "retracted")
    if parents and not active:
        raise ValueError("no active parent for required open-world fallback; do not invent one")
    root = content_sha256(
        {
            "context": export_context(context),
            "provenance": provenance,
            "grammar": GRAMMAR,
            "ledger": bootstrap_ledger_lineage_ref,
        }
    )
    targets: list[ProposalTarget] = []
    identities: set[str] = set()

    def add(
        operation: str,
        hypothesis: FullHypothesis,
        parent: FullHypothesis | None,
        suffix: tuple[UUID, ...] = (),
    ) -> None:
        body = {
            "operation": operation,
            "hypothesis": hypothesis.model_dump(mode="json"),
            "parent": None if parent is None else str(parent.state.particle_id),
            "suffix": [str(r) for r in suffix],
        }
        key = content_sha256(body)
        if key in identities:
            return
        if len(targets) >= max_candidates:
            raise ValueError("complete support exceeds candidate resource limit; no truncation")
        identities.add(key)
        state = hypothesis.state.model_copy(
            update={
                "particle_id": content_uuid(root, key + ":particle"),
                "revision_id": content_uuid(root, key + ":revision"),
                "parent_particle_id": None if parent is None else parent.state.particle_id,
                "parent_revision_id": None if parent is None else parent.state.revision_id,
            }
        )
        targets.append(
            ProposalTarget.model_validate(
                {
                    "operation": operation,
                    "candidate": {"state": state, "events": hypothesis.events},
                    "evidence_ids": evidence,
                    "replaced_revision_ids": suffix,
                    "replay_required": bool(suffix),
                }
            )
        )

    # Removal and reactivation cannot silently rewrite the source world-line.
    for existing in active:
        add("retract", existing, existing)
    for existing in retracted:
        add("reactivate", existing, existing)
    for skeleton in event_grid(
        times,
        tuple(sorted(context.actor_support)),
        tuple(sorted(p.location_key for p in context.location_support)),
    ):
        for instance in sorted(context.instance_support):
            hkey = content_sha256({"skeleton": skeleton, "instance": instance})
            events = tuple(
                EventNode(
                    event_id=content_uuid(root, f"{hkey}:event:{i}"), instance_key=instance, **body
                )
                for i, body in enumerate(skeleton)
            )
            for parent in active or (None,):
                ledger = (
                    bootstrap_ledger_lineage_ref
                    if parent is None
                    else parent.state.ledger_lineage_ref
                )
                run = 0 if parent is None else parent.state.run_length + 1
                variants: list[tuple[str, str, str | None, int]] = [
                    ("unresolved", "unresolved", None, run)
                ]
                if parent is not None:
                    for cause_enum in ParticleChangeCause:
                        if cause_enum.value != "unresolved":
                            variants.append((cause_enum.value, "unresolved", None, run))
                        if parent.state.regime_id is not None:
                            variants.append((cause_enum.value, "stay", parent.state.regime_id, run))
                    variants.append(("habit", "create", "proposed-regime:" + root, 0))
                    variants.extend(
                        ("habit", "reactivate", regime, 0)
                        for regime in sorted(
                            {p.state.regime_id for p in retracted if p.state.regime_id is not None}
                        )
                    )
                for cause, regime, regime_id, length in variants:
                    state_key = content_sha256(
                        (root, hkey, cause, regime, regime_id, length, ledger)
                    )
                    hypothesis = FullHypothesis(
                        state=TypedParticleState(
                            particle_id=content_uuid(root, "draft:" + state_key),
                            parent_particle_id=None,
                            source_snapshot_id=context.source_snapshot_id,
                            event_hypothesis_id=content_uuid(root, hkey),
                            revision_id=content_uuid(root, "draft-revision:" + state_key),
                            ordered_actor_roles=ordered_roles(events),
                            instance_association_key=instance,
                            change_cause=cause,
                            regime_decision=regime,
                            regime_id=regime_id,
                            run_length=length,
                            statistic_state_ref="pending-conditional:" + state_key,
                            ledger_lineage_ref=ledger,
                        ),
                        events=events,
                    )
                    if cause == regime == "unresolved":
                        add("preserve_unresolved", hypothesis, parent)
                    if parent is not None:
                        add("branch", hypothesis, parent)
                        add("revise", hypothesis, parent)
                        if delayed:
                            suffix: tuple[UUID, ...] = (parent.state.revision_id,)
                            while True:
                                add("rejuvenate", hypothesis, parent, suffix)
                                ancestor = revisions[suffix[0]].parent_revision_id
                                if ancestor is None or revisions[ancestor].status != "active":
                                    break
                                suffix = (ancestor, *suffix)
    context.validate_candidates(tuple(targets))
    counts = Counter(t.operation.value for t in targets)
    report = {
        "grammar": GRAMMAR,
        "context_sha256": content_sha256(export_context(context)),
        "source_records": provenance,
        "candidate_count": len(targets),
        "operation_counts": dict(counts),
        "event_time_grid": [t.isoformat() for t in times],
        "delayed_evidence": delayed,
        "truncated": False,
        "complete_within_declared_discrete_grammar": True,
        "continuous_or_open_world_support_complete": False,
        "bootstrap": not parents,
        "current_active_parents": len(active),
        "retracted_parents": len(retracted),
        "native_publication_authorized": False,
        "ledger_authorized": False,
        "analytic_updates_computed": False,
        "posterior_accuracy_calibrated": False,
    }
    return GeneratedSupport(
        context.model_dump_json(),
        tuple(t.model_dump_json() for t in targets),
        json.dumps(report, sort_keys=True),
    )
