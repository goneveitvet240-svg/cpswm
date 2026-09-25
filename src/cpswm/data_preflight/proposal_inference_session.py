"""Checkpoint-backed, replayable proposal inference, without publication authority.

The caller supplies label-free current context and complete runtime support. This
module neither builds that support nor calibrates native transition/measurement
factors. Restoring re-executes recorded inference, but does not authenticate its
history: the expected snapshot/checkpoint digests must come from caller custody.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any

import torch

from cpswm.data_preflight.proposal_decoder import DecodedProposal
from cpswm.data_preflight.proposal_samples import ProposalContext, ProposalTarget
from cpswm.data_preflight.proposal_trainer import distribution, load_checkpoint
from cpswm.data_preflight.typed_proposal_networks import parameter_fingerprint
from cpswm.system.reproducibility import content_sha256


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_digest() -> str:
    """Record installed source bytes; not a signature or independent audit."""
    root = Path(__file__).resolve().parents[1]
    return content_sha256(
        {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.py"))
        }
    )


@dataclass(frozen=True)
class InferenceReceipt:
    request_id: str
    binding_sha256: str
    input_sha256: str
    decoded: DecodedProposal
    ledger_authorized: bool = False
    native_publication_authorized: bool = False


class ProposalInferenceSession:
    """One CPU inference stream with transactional RNG and idempotent requests.

    Complete targets retain replay effects and replacement revision IDs. No
    automatic conversion to the narrower native receipt is performed here.
    Instances serialize calls; returned receipts/snapshots cannot mutate history.
    """

    def __init__(self, checkpoint: Path, *, manifest_sha256: str, seed: int) -> None:
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("explicit nonnegative 63-bit sampling seed required")
        self._lock = RLock()
        self._model, manifest = load_checkpoint(checkpoint, manifest_sha256=manifest_sha256)
        self._fingerprint = parameter_fingerprint(self._model)
        self._binding = {
            "checkpoint_manifest_sha256": manifest_sha256,
            "parameters_sha256": self._fingerprint,
            "source_sha256": source_digest(),
            "torch_version": torch.__version__,
            "arm": manifest["arm"],
            "sampling_device": "cpu",
            "sampling_threads": torch.get_num_threads(),
        }
        self._binding_sha256 = content_sha256(self._binding)
        self._seed = seed
        self._generator = torch.Generator(device="cpu").manual_seed(seed)
        self._records: dict[str, str] = {}

    @property
    def binding_sha256(self) -> str:
        return self._binding_sha256

    def _check_model(self) -> None:
        if (
            parameter_fingerprint(self._model) != self._fingerprint
            or any(m.training for m in self._model.modules())
            or torch.get_num_threads() != self._binding["sampling_threads"]
        ):
            raise ValueError("inference model or execution binding changed")

    @staticmethod
    def _inputs(
        context: ProposalContext, support: tuple[ProposalTarget, ...]
    ) -> tuple[ProposalContext, tuple[ProposalTarget, ...], dict[str, Any]]:
        if type(context) is not ProposalContext:
            raise ValueError("inference requires label-free context without supervision")
        clean = ProposalContext.model_validate(context.model_dump())
        targets = tuple(
            sorted(
                (ProposalTarget.model_validate(t.model_dump()) for t in support),
                key=lambda t: content_sha256(t.model_dump(mode="json")),
            )
        )
        clean.validate_candidates(targets)
        data = {
            "context": clean.model_dump(mode="json"),
            "support": [t.model_dump(mode="json") for t in targets],
        }
        return clean, targets, data

    def score_support(
        self, *, context: ProposalContext, support: tuple[ProposalTarget, ...]
    ) -> tuple[DecodedProposal, ...]:
        """Score all supplied support without advancing sampling history."""
        with self._lock, torch.no_grad():
            self._check_model()
            clean, targets, _ = self._inputs(context, support)
            d = distribution(self._model, clean, targets)
            result = tuple(d.decode(key) for key in d.target_sha256s)
            self._check_model()
            return result

    def infer(
        self, *, request_id: str, context: ProposalContext, support: tuple[ProposalTarget, ...]
    ) -> InferenceReceipt:
        with self._lock, torch.no_grad():
            self._check_model()
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("nonempty request identity required")
            clean, targets, inputs = self._inputs(context, support)
            input_sha = content_sha256(inputs)
            if request_id in self._records:
                record = json.loads(self._records[request_id])
                if content_sha256(record["inputs"]) != input_sha:
                    raise ValueError("request identity reused with changed context or support")
                receipt = record["receipt"]
                receipt["decoded"] = DecodedProposal(**receipt["decoded"])
                return InferenceReceipt(**receipt)
            rng_before = self._generator.get_state().clone()
            try:
                decoded = distribution(self._model, clean, targets).sample(
                    generator=self._generator
                )
                self._check_model()
                result = InferenceReceipt(request_id, self.binding_sha256, input_sha, decoded)
                record_json = encoded({"inputs": inputs, "receipt": asdict(result)}).decode()
            except BaseException:
                self._generator.set_state(rng_before)
                raise
            self._records[request_id] = record_json
            return result

    def snapshot(self) -> bytes:
        with self._lock:
            self._check_model()
            return encoded(
                {
                    "format": "typed-proposal-inference-session@1",
                    "binding": self._binding,
                    "seed": self._seed,
                    "records": [json.loads(r) for r in self._records.values()],
                    "rng_sha256": hashlib.sha256(
                        self._generator.get_state().numpy().tobytes()
                    ).hexdigest(),
                    "ledger_authorized": False,
                    "native_publication_authorized": False,
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
    ) -> ProposalInferenceSession:
        if hashlib.sha256(snapshot).hexdigest() != snapshot_sha256:
            raise ValueError("inference snapshot identity mismatch")
        payload = json.loads(snapshot)
        if payload.get("format") != "typed-proposal-inference-session@1":
            raise ValueError("unknown inference snapshot format")
        result = cls(checkpoint, manifest_sha256=manifest_sha256, seed=payload["seed"])
        if payload["binding"] != result._binding:
            raise ValueError("inference snapshot dependency binding mismatch")
        for record in payload["records"]:
            inputs = record["inputs"]
            result.infer(
                request_id=record["receipt"]["request_id"],
                context=ProposalContext.model_validate(inputs["context"]),
                support=tuple(ProposalTarget.model_validate(t) for t in inputs["support"]),
            )
        # Recomputes every trace/target and the next RNG position. This also
        # rejects extra/duplicate records, modified receipts and authority flags.
        if result.snapshot() != encoded(payload):
            raise ValueError("inference history or RNG differs from recomputed replay")
        return result
