"""Raw AI2-THOR acquisition plumbing; no simulator truth enters observation candidates.

This is not an embodied policy, actor scheduler, calibrated sensor model, or
permission to pass raw candidates to a method. A separately approved adapter is
required. The controller is supplied by the runtime owner, never substituted
automatically when a simulator is missing.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np


class ControllerLike(Protocol):
    def step(self, **kwargs: Any) -> Any: ...


def simulator_preflight() -> dict[str, Any]:
    installed = importlib.util.find_spec("ai2thor") is not None
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "ai2thor_installed": installed,
        "ai2thor_version": importlib.metadata.version("ai2thor") if installed else None,
        "real_simulator_run_verified": False,
        "status": "RUNTIME_PROBE_REQUIRED" if installed else "BLOCKED_MISSING_AI2THOR",
        "note": "No installation, Unity startup, scene download or simulated success in preflight.",
    }


def _json_file(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, allow_nan=False, indent=2)


class RawCaptureSession:
    """One serial controller history. Any uncertain step poisons the session.

    Truth and observation directories are logical separation, NOT OS-level
    isolation. Do not mount the evaluator directory into a method process.
    No retry of an uncertain external action is performed automatically.
    """

    def __init__(
        self,
        controller: ControllerLike,
        output: Path,
        *,
        run_id: str,
        runtime_provenance: dict[str, Any],
        allowed_actions: tuple[str, ...],
        depth_unit: str,
    ) -> None:
        if not run_id or not allowed_actions or len(set(allowed_actions)) != len(allowed_actions):
            raise ValueError("explicit run identity and unique action contract required")
        if depth_unit not in {"m", "mm"}:
            raise ValueError("runtime-specific depth unit must be explicit")
        if not runtime_provenance:
            raise ValueError("runtime version/build and scene provenance must be supplied")
        # Detach caller metadata before creating a directory or executing an action.
        provenance = json.loads(json.dumps(runtime_provenance, allow_nan=False))
        output.mkdir(parents=True, exist_ok=False)
        (output / "observations").mkdir()
        (output / "evaluator_only").mkdir()
        _json_file(
            output / "manifest.json",
            {
                "schema": "structure-two-raw-simulator-capture@0.1",
                "run_id": run_id,
                "runtime_provenance_declared": provenance,
                "depth_unit": depth_unit,
                "allowed_actions_declared": allowed_actions,
                "method_adapter_authorized": False,
                "continuous_model_selected": False,
            },
        )
        self._controller, self._output = controller, output
        self._allowed_actions = frozenset(allowed_actions)
        self._depth_unit, self._run_id = depth_unit, run_id
        self._step = 0
        self._poisoned = False

    def capture(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._poisoned:
            raise RuntimeError(
                "uncertain previous action; reconcile controller before a new session"
            )
        request = json.loads(json.dumps(request, allow_nan=False))
        if request.get("action") not in self._allowed_actions:
            raise ValueError("action outside explicitly supplied acquisition contract")
        index = self._step
        started = datetime.now(UTC).isoformat()
        self._poisoned = True
        try:
            event = self._controller.step(**request)
            arrived = datetime.now(UTC).isoformat()
            metadata = json.loads(json.dumps(event.metadata, allow_nan=False))
            if (
                metadata.get("lastAction") != request["action"]
                or type(metadata.get("lastActionSuccess")) is not bool
            ):
                raise ValueError("missing or mismatched actual execution receipt")
            rgb = np.array(event.frame, copy=True)
            if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8 or not rgb.size:
                raise ValueError("RGB must be a nonempty H/W/3 uint8 sensor frame")
            depth = getattr(event, "depth_frame", None)
            if depth is not None:
                depth = np.array(depth, copy=True)
                if (
                    depth.shape != rgb.shape[:2]
                    or depth.dtype.kind != "f"
                    or not np.isfinite(depth).all()
                    or (depth < 0).any()
                ):
                    raise ValueError("depth must match RGB, be finite and nonnegative")
            array_path = self._output / "observations" / f"{index:06d}.npz"
            with array_path.open("xb") as stream:
                if depth is None:
                    np.savez(stream, rgb=rgb)
                else:
                    np.savez(stream, rgb=rgb, depth=depth)
            candidate = {
                "run_id": self._run_id,
                "step_index": index,
                "request": request,
                "request_time": started,
                "received_at": arrived,
                "last_action_success": metadata["lastActionSuccess"],
                "sensor_file": array_path.name,
                "sensor_sha256": hashlib.sha256(array_path.read_bytes()).hexdigest(),
                "depth_unit": self._depth_unit if depth is not None else None,
                "status": "RAW_OBSERVATION_CANDIDATE_NOT_METHOD_AUTHORIZATION",
            }
            # errorMessage/actionReturn/objects/poses/segmentation IDs are not method inputs.
            _json_file(self._output / "evaluator_only" / f"{index:06d}.json", metadata)
            _json_file(self._output / "observations" / f"{index:06d}.json", candidate)
            self._step += 1
            self._poisoned = False
            return candidate
        except BaseException as error:
            _json_file(
                self._output / f"uncertain_step_{index:06d}.json",
                {
                    "run_id": self._run_id,
                    "step_index": index,
                    "error_type": type(error).__name__,
                    "action_may_have_executed": True,
                    "automatic_retry_forbidden": True,
                },
            )
            raise
