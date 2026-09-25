"""Transactional learned proposals and analytic replay, without posterior promotion."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID

from cpswm.data_preflight.proposal_inference_session import encoded
from cpswm.data_preflight.proposal_samples import ProposalContext
from cpswm.data_preflight.runtime_candidate_session import (
    GeneratedInference,
    RuntimeCandidateSession,
)
from cpswm.system.conditioned_proposal_runtime import (
    ConditionalEvidenceGroup,
    ConditionalProposalModel,
    ConditionedProposal,
    ConditionedSupport,
    condition_generated_support,
)
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_conditional_updates import rebuild_conditional_state
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState


@dataclass(frozen=True)
class ConditionedInference:
    proposed: GeneratedInference
    conditioned: ConditionedSupport

    @property
    def selected(self) -> ConditionedProposal:
        key = self.proposed.receipt.decoded.probability.proposal_sha256
        return next(row for row in self.conditioned.candidates if row.scored_target_sha256 == key)


@dataclass(frozen=True)
class ConditioningRequest:
    request_id: str
    context_json: str
    ledger_lineage_ref: str
    max_candidates: int
    groups: tuple[ConditionalEvidenceGroup, ...]
    parent_statistics: dict[UUID, ConditionalAnalyticState]
    result: ConditionedInference


class ConditionedInferenceSession:
    """Own one model stream; failed analytic evaluation also rolls back proposal RNG.

    The conditional model is an exclusively owned dependency. No sampled target
    is promoted to a posterior parent. Restore replays every model computation,
    given externally pinned network weights, prior, model identity and snapshot.
    """

    def __init__(
        self,
        checkpoint: Path,
        *,
        manifest_sha256: str,
        seed: int,
        prior: ConditionalAnalyticState,
        model: ConditionalProposalModel,
        expected_model_binding_sha256: str,
    ):
        self._lock = RLock()
        self._checkpoint = checkpoint
        self._manifest = manifest_sha256
        self._seed = seed
        self._prior = rebuild_conditional_state(prior, ())
        if self._prior.evidence_cluster_ids or len(self._prior.information_vector) != 6:
            raise ValueError("explicit empty-history pose prior required")
        self._model = model
        self._model_binding = expected_model_binding_sha256
        self._model_state = StateCodec().dumps(deepcopy(model.checkpoint_state()))
        self._proposals = RuntimeCandidateSession(
            checkpoint, manifest_sha256=manifest_sha256, seed=seed
        )
        self._requests: dict[str, str] = {}
        self._check_model()

    def _check_model(self) -> None:
        if (
            self._model.binding_sha256 != self._model_binding
            or StateCodec().dumps(self._model.checkpoint_state()) != self._model_state
        ):
            raise ValueError("owned conditional inference model/state changed")

    def process(
        self,
        *,
        request_id: str,
        context: ProposalContext,
        bootstrap_ledger_lineage_ref: str,
        groups: tuple[ConditionalEvidenceGroup, ...],
        parent_statistics: dict[UUID, ConditionalAnalyticState],
        max_candidates: int = 4096,
    ) -> ConditionedInference:
        with self._lock:
            self._check_model()
            before = self._proposals.snapshot()
            try:
                proposed = self._proposals.process(
                    request_id=request_id,
                    context=context,
                    bootstrap_ledger_lineage_ref=bootstrap_ledger_lineage_ref,
                    max_candidates=max_candidates,
                )
                conditioned = condition_generated_support(
                    proposed.support,
                    bootstrap_ledger_lineage_ref=bootstrap_ledger_lineage_ref,
                    groups=groups,
                    prior=self._prior,
                    parent_statistics=parent_statistics,
                    model=self._model,
                    expected_model_binding_sha256=self._model_binding,
                    max_candidates=max_candidates,
                )
                result = ConditionedInference(proposed, conditioned)
                # This checks that conditioning kept the original scored identity.
                if result.selected.origin != proposed.receipt.decoded.target:
                    raise ValueError("conditional state substituted the scored proposal")
                request = ConditioningRequest(
                    request_id,
                    proposed.support.context_json,
                    bootstrap_ledger_lineage_ref,
                    max_candidates,
                    conditioned.groups,
                    deepcopy(parent_statistics),
                    result,
                )
                payload = StateCodec().dumps(request)
                previous = self._requests.get(request_id)
                if previous is not None:
                    saved = StateCodec().loads(previous)
                    if type(saved) is not ConditioningRequest or content_sha256(
                        saved
                    ) != content_sha256(request):
                        raise ValueError(
                            "conditional request identity reused with changed input/result"
                        )
                self._check_model()
            except BaseException:
                self._proposals = RuntimeCandidateSession.restore(
                    self._checkpoint,
                    manifest_sha256=self._manifest,
                    snapshot=before,
                    snapshot_sha256=hashlib.sha256(before).hexdigest(),
                )
                raise
            if previous is None:
                self._requests[request_id] = payload
            return deepcopy(result)

    def snapshot(self) -> bytes:
        with self._lock:
            self._check_model()
            return encoded(
                {
                    "format": "conditioned-inference-session@1",
                    "checkpoint_manifest_sha256": self._manifest,
                    "seed": self._seed,
                    "prior_sha256": content_sha256(self._prior),
                    "conditional_model_binding_sha256": self._model_binding,
                    "conditional_model_state": self._model_state,
                    "proposals": json.loads(self._proposals.snapshot()),
                    "requests": list(self._requests.values()),
                    "ledger_write_authority": False,
                    "native_publication_authority": False,
                }
            )

    @classmethod
    def restore(
        cls,
        checkpoint: Path,
        *,
        manifest_sha256: str,
        snapshot: bytes,
        snapshot_sha256: str,
        prior: ConditionalAnalyticState,
        model: ConditionalProposalModel,
        expected_model_binding_sha256: str,
    ) -> ConditionedInferenceSession:
        if hashlib.sha256(snapshot).hexdigest() != snapshot_sha256:
            raise ValueError("conditioned inference snapshot identity mismatch")
        payload: dict[str, Any] = json.loads(snapshot)
        if (
            payload.get("format") != "conditioned-inference-session@1"
            or payload["checkpoint_manifest_sha256"] != manifest_sha256
            or payload["prior_sha256"] != content_sha256(prior)
            or payload["conditional_model_binding_sha256"] != expected_model_binding_sha256
        ):
            raise ValueError("conditioned inference dependencies differ")
        result = cls(
            checkpoint,
            manifest_sha256=manifest_sha256,
            seed=payload["seed"],
            prior=prior,
            model=model,
            expected_model_binding_sha256=expected_model_binding_sha256,
        )
        for raw in payload["requests"]:
            request = StateCodec().loads(raw)
            if type(request) is not ConditioningRequest or request.request_id in result._requests:
                raise ValueError("invalid or repeated conditional inference request")
            actual = result.process(
                request_id=request.request_id,
                context=ProposalContext.model_validate_json(request.context_json),
                bootstrap_ledger_lineage_ref=request.ledger_lineage_ref,
                groups=request.groups,
                parent_statistics=request.parent_statistics,
                max_candidates=request.max_candidates,
            )
            if content_sha256(actual) != content_sha256(request.result):
                raise ValueError("conditional inference differs from complete model replay")
        if result.snapshot() != encoded(payload):
            raise ValueError("conditional journal, sampling history or authority changed")
        return result
