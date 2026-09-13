"""Bounded live camera executor, with pixel-only output into continuous input.

The transport owns one Unity controller, never a second memory/model history.
A lost response is uncertain; neither this adapter nor the runtime retries it.
Environment process recovery requires separate reconciliation and is not hidden
by spawning a fresh house under an old command.
"""

from __future__ import annotations

import base64
import hashlib
import json
import selectors
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from cpswm.contracts.base import BaseRecordMetadata, SourceType
from cpswm.perception_mapping.adapters.contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery


class UnityObservationExecutor:
    def __init__(
        self,
        *,
        python: Path,
        worker: Path,
        binary: Path,
        house: Path,
        log_dir: Path,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
    ) -> None:
        self.scope = (household_id, session_id, trace_id)
        self.provenance = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (("worker", worker), ("unity", binary), ("house", house))
        }
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log = (log_dir / "transport.stderr").open("w")
        self._process = subprocess.Popen(
            [
                str(python),
                str(worker),
                "--binary",
                str(binary),
                "--house",
                str(house),
                "--log-dir",
                str(log_dir),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._log,
            text=True,
            bufsize=1,
        )
        self._seen: set[UUID] = set()
        try:
            if self._receive().get("ready") is not True:
                raise RuntimeError("Unity worker did not initialize")
        except BaseException:
            self.close()
            raise

    def _receive(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(self._process.stdout, selectors.EVENT_READ)
            while selector.select(timeout=45):
                line = self._process.stdout.readline()
                if not line:
                    raise RuntimeError("Unity worker exited; outcome uncertain")
                if line.startswith("CPSWM_RESPONSE "):
                    result: dict[str, Any] = json.loads(line.removeprefix("CPSWM_RESPONSE "))
                    return result
            raise TimeoutError("Unity receipt timed out; outcome uncertain")

    def execute(self, command: ObservationCommand) -> ObservationDelivery:
        if command.action_id in self._seen:
            raise ValueError("transport action already dispatched")
        self._seen.add(command.action_id)
        assert self._process.stdin is not None
        self._process.stdin.write(
            json.dumps(
                {
                    "action_id": str(command.action_id),
                    "action": command.action,
                    "degrees": command.degrees,
                }
            )
            + "\n"
        )
        self._process.stdin.flush()
        response = self._receive()
        if response["action_id"] != str(command.action_id):
            raise ValueError("Unity response command mismatch")
        payload = base64.b64decode(response.pop("rgb_npy"), validate=True)
        capture = datetime.fromisoformat(response["capture_time"])
        arrival = datetime.now(UTC)
        identity = uuid4()
        household, session, trace = self.scope
        metadata = BaseRecordMetadata(
            record_id=identity,
            schema_name="live-unity-rgb",
            schema_version="0.1.0",
            household_id=household,
            session_id=session,
            trace_id=trace,
            recorded_time=arrival,
            source_type=SourceType.SIMULATION,
            source_id=str(command.action_id),
            model_version="unity-camera-transport-v1",
        )
        envelope = ObservationEnvelope(
            metadata=metadata,
            identity=ObservationIdentity(
                observation_id=identity, household_id=household, session_id=session, trace_id=trace
            ),
            sensor=SensorRef(sensor_id="live-unity-camera", modality=SensorModality.RGB),
            capture_time=capture,
            arrival_time=arrival,
            clock_domain="host-utc",
            frame_id="unity-main-camera",
            payload=PayloadRef(
                payload_id=identity,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
            ),
        )
        raw = RawModalityObservation(
            envelope.model_dump_json(), payload, content_sha256((response, self.provenance)), None
        )
        return ObservationDelivery(
            command.action_id, (raw,), response["success"], response["error"], arrival
        )

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                assert self._process.stdin is not None
                self._process.stdin.write('{"stop": true}\n')
                self._process.stdin.flush()
                self._process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=5)
        self._log.close()
