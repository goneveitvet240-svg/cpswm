"""Explicit camera configuration is bounded and leaves old workers unchanged."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cpswm.system.reproducibility import content_sha256
from cpswm.system.unity_observation import UnityObservationExecutor


@pytest.mark.parametrize("size", [None, 320, 640])
def test_capture_config_passed_only_when_explicit(tmp_path, monkeypatch, size):
    import cpswm.system.unity_observation as module

    calls = []
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda args, **kwargs: calls.append(args) or SimpleNamespace(poll=lambda: 0),
    )
    monkeypatch.setattr(UnityObservationExecutor, "_receive", lambda self: {"ready": True})
    files = {}
    for name in ("python", "worker", "binary", "house"):
        p = tmp_path / name
        p.write_text(name)
        files[name] = p
    executor = UnityObservationExecutor(
        **files,
        log_dir=tmp_path / "logs",
        household_id=uuid4(),
        session_id=uuid4(),
        trace_id=uuid4(),
        image_size=size,
    )
    try:
        if size is None:
            assert (
                "--image-size" not in calls[0]
                and "capture_configuration" not in executor.provenance
            )
        else:
            assert calls[0][-2:] == ["--image-size", str(size)]
            assert executor.provenance["capture_configuration"] == content_sha256((size, size, 60))
    finally:
        executor.close()


@pytest.mark.parametrize("size", [0, -1, 1, 1024, 320.0, "640", True])
def test_unsupported_config_rejected_before_reading_paths_or_spawning(size):
    with pytest.raises(ValueError, match="unsupported explicit"):
        UnityObservationExecutor(
            python=Path("missing"),
            worker=Path("missing"),
            binary=Path("missing"),
            house=Path("missing"),
            log_dir=Path("missing"),
            household_id=uuid4(),
            session_id=uuid4(),
            trace_id=uuid4(),
            image_size=size,
        )
