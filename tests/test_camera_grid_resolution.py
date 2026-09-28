"""Grid resolution is explicit, validated, and measured from public pixels only."""

import hashlib
import io
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
import run_camera_measurement_grid as grid
from test_structure_two_adaptive_runtime import _adaptive_system_and_transition
from test_structure_two_continuous_input import raw_for

from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationDelivery


def raw_record(transition, size):
    raw = raw_for(transition)
    buffer = io.BytesIO()
    np.save(buffer, np.zeros((size, size, 3), dtype=np.uint8), allow_pickle=False)
    data = buffer.getvalue()
    env = raw.envelope()
    env = env.model_copy(
        update={
            "payload": env.payload.model_copy(
                update={"payload_sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
            )
        }
    )
    raw = replace(raw, envelope_json=env.model_dump_json(), payload_bytes=data)
    return None, ObservationDelivery(uuid4(), (raw,), True, "", env.arrival_time)


@pytest.mark.parametrize("size", [320, 640])
def test_measurement_sources_bind_actual_pixels_without_private_scene_input(monkeypatch, size):
    _, transition = _adaptive_system_and_transition()
    records = (raw_record(transition, size),)
    seen = []

    class Decoder:
        binding_sha256 = "e" * 64

        def __init__(self, **kwargs):
            assert set(kwargs) == {
                "weights_path",
                "category",
                "sources",
                "detector_kind",
                "household_id",
                "session_id",
                "trace_id",
            }
            assert kwargs["sources"].observation_artifact_sha256 == content_sha256(
                grid.configuration(size)
            )

        def measurements(self, observations, *, cutoff):
            seen.append(observations)
            return ()

    monkeypatch.setattr(grid, "PixelCategoryOutcomeDecoder", Decoder)
    grid.measure_public(records, weights={"ssdlite": Path("a"), "fasterrcnn": Path("b")})
    assert seen[0] is seen[1] and seen[0] == records[0][1].observations
    assert grid.configuration(size)["shape"] == (size, size, 3)
    assert grid.measurement_sources(320) != grid.measurement_sources(640)


@pytest.mark.parametrize("size", [0, 128, 1024, True, 320.0, "640"])
def test_invalid_capture_size_rejected_before_directory_or_process(tmp_path, size):
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="unsupported fixed-grid"):
        grid.capture_case(
            output, sdk_python=None, binary=None, site="north", x=1.25, image_size=size
        )
    assert not output.exists()


def test_mixed_public_dimensions_rejected_before_loading_models():
    _, transition = _adaptive_system_and_transition()
    records = (raw_record(transition, 320), raw_record(transition, 640))
    with pytest.raises(ValueError, match="mixed or invalid"):
        grid.measure_public(records, weights={})


def test_summary_does_not_mix_resolution_conditions():
    with pytest.raises(ValueError, match="another resolution"):
        grid.summarize([{"image_size": 640}], image_size=320)
