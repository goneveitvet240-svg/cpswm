"""Label join tests with explicit synthetic files; not empirical calibration."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "calibrate_cli", Path(__file__).resolve().parents[1] / "tools/calibrate_interaction_scores.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "attack", [None, "digest", "unknown", "duplicate", "nonbool", "missing_source"]
)
def test_exact_label_join(tmp_path, attack):
    v = dict(
        observation_id="obs",
        input_sha256="a" * 64,
        model_id="fixture",
        weights_sha256="b" * 64,
        torch_version="fixture",
        torchvision_version="fixture",
        minimum_score=0.5,
        candidates=[
            dict(candidate_id="candidate", detector_score=0.8),
            dict(candidate_id="unlabeled", detector_score=0.9),
        ],
    )
    result = tmp_path / "result.json"
    result.write_text(json.dumps(dict(source_sha256="c" * 64, records=[dict(visual=v)])))
    item = dict(observation_id="obs", candidate_id="candidate", correct=True)
    if attack == "unknown":
        item["candidate_id"] = "unknown"
    if attack == "nonbool":
        item["correct"] = 1
    ann = dict(
        source="synthetic-test-only",
        annotator="fixture",
        items=[item, item] if attack == "duplicate" else [item],
    )
    if attack == "missing_source":
        ann["source"] = ""
    labels = tmp_path / "labels.json"
    data = json.dumps(ann).encode()
    labels.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest() if attack != "digest" else "d" * 64
    if attack:
        with pytest.raises(ValueError):
            module.load_examples(result, labels, digest)
    else:
        examples = module.load_examples(result, labels, digest)
        assert len(examples) == 1 and examples[0].label
        assert examples[0].sequence_id == "c" * 64
