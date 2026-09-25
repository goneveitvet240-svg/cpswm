"""Automatic candidate production plus model inference and regenerated recovery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from cpswm.data_preflight.proposal_inference_session import (
    InferenceReceipt,
    ProposalInferenceSession,
    encoded,
)
from cpswm.data_preflight.proposal_samples import ProposalContext
from cpswm.data_preflight.runtime_candidates import GeneratedSupport, generate_runtime_candidates
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class GeneratedInference:
    support: GeneratedSupport
    receipt: InferenceReceipt


class RuntimeCandidateSession:
    """No caller-supplied target list; restore regenerates every complete support.

    This is a proposal-only session. It never promotes sampled candidates to
    posterior parents or grants a pending conditional reference native authority.
    """

    def __init__(self, checkpoint: Path, *, manifest_sha256: str, seed: int) -> None:
        self._lock = RLock()
        self._engine = ProposalInferenceSession(
            checkpoint, manifest_sha256=manifest_sha256, seed=seed
        )
        self._requests: dict[str, dict[str, Any]] = {}

    def process(
        self,
        *,
        request_id: str,
        context: ProposalContext,
        bootstrap_ledger_lineage_ref: str,
        max_candidates: int = 4096,
    ) -> GeneratedInference:
        with self._lock:
            generated = generate_runtime_candidates(
                context,
                bootstrap_ledger_lineage_ref=bootstrap_ledger_lineage_ref,
                max_candidates=max_candidates,
            )
            metadata = {
                "bootstrap_ledger_lineage_ref": bootstrap_ledger_lineage_ref,
                "max_candidates": max_candidates,
                "generation_report": generated.report,
            }
            if request_id in self._requests and self._requests[request_id] != metadata:
                raise ValueError("generated request identity reused with changed dependencies")
            receipt = self._engine.infer(
                request_id=request_id, context=generated.context, support=generated.targets
            )
            self._requests[request_id] = metadata
            return GeneratedInference(generated, receipt)

    def snapshot(self) -> bytes:
        with self._lock:
            return encoded(
                {
                    "format": "runtime-candidate-session@1",
                    "engine": json.loads(self._engine.snapshot()),
                    "requests": self._requests,
                    "native_publication_authorized": False,
                    "ledger_authorized": False,
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
    ) -> RuntimeCandidateSession:
        if hashlib.sha256(snapshot).hexdigest() != snapshot_sha256:
            raise ValueError("runtime candidate snapshot identity mismatch")
        payload = json.loads(snapshot)
        if payload.get("format") != "runtime-candidate-session@1":
            raise ValueError("unknown runtime candidate session format")
        raw_engine = encoded(payload["engine"])
        records = payload["engine"]["records"]
        if set(payload["requests"]) != {r["receipt"]["request_id"] for r in records}:
            raise ValueError("candidate generation journal coverage mismatch")
        requests = {}
        # Check support production BEFORE expensive network replay. A fully valid
        # alternate support plus correctly rescored receipts is still not this
        # deterministic generator's output and cannot bypass this boundary.
        for record in records:
            request_id = record["receipt"]["request_id"]
            metadata = payload["requests"][request_id]
            generated = generate_runtime_candidates(
                ProposalContext.model_validate(record["inputs"]["context"]),
                bootstrap_ledger_lineage_ref=metadata["bootstrap_ledger_lineage_ref"],
                max_candidates=metadata["max_candidates"],
            )
            expected = sorted(
                generated.targets, key=lambda t: content_sha256(t.model_dump(mode="json"))
            )
            if (
                record["inputs"]["context"] != generated.context.model_dump(mode="json")
                or record["inputs"]["support"] != [t.model_dump(mode="json") for t in expected]
                or metadata["generation_report"] != generated.report
            ):
                raise ValueError("stored support differs from regenerated causal candidates")
            requests[request_id] = {
                "bootstrap_ledger_lineage_ref": metadata["bootstrap_ledger_lineage_ref"],
                "max_candidates": metadata["max_candidates"],
                "generation_report": generated.report,
            }
        result = cls.__new__(cls)
        result._lock = RLock()
        result._engine = ProposalInferenceSession.restore(
            checkpoint,
            manifest_sha256=manifest_sha256,
            snapshot=raw_engine,
            snapshot_sha256=hashlib.sha256(raw_engine).hexdigest(),
        )
        result._requests = requests
        if result.snapshot() != encoded(payload):
            raise ValueError("candidate session metadata or authority differs")
        return result
