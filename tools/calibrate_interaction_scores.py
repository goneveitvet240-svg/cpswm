"""Fit and evaluate detector-score calibration against separately supplied labels.

Annotation JSON: {source: URL or document reference, annotator: name/id,
items: [{observation_id, candidate_id, correct: bool}]}.
Both positive and false detections must be labeled. Unlabeled detections are NOT
negatives. Labels never enter method observations. External review must establish
annotation quality; file hashes only protect integrity. No promotion authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from cpswm.perception_mapping.interaction_evidence import (
    CalibrationExample,
    evaluate_calibration,
    fit_calibration,
)
from cpswm.system.reproducibility import content_sha256


def load_examples(
    result_path: Path, annotation_path: Path, annotation_sha256: str
) -> tuple[CalibrationExample, ...]:
    data = annotation_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != annotation_sha256:
        raise ValueError("annotation differs from reviewed bytes")
    annotation = json.loads(data)
    if (
        set(annotation) != {"source", "annotator", "items"}
        or not isinstance(annotation["source"], str)
        or not annotation["source"].strip()
        or not isinstance(annotation["annotator"], str)
        or not annotation["annotator"].strip()
    ):
        raise ValueError("separate annotation source and annotator required")
    result = json.loads(result_path.read_bytes())
    index = {}
    for row in result["records"]:
        visual = row["visual"]
        # Bind detector score definition, weights, filter and library versions.
        signature = content_sha256(
            {
                k: visual[k]
                for k in (
                    "model_id",
                    "weights_sha256",
                    "torch_version",
                    "torchvision_version",
                    "minimum_score",
                )
            }
        )
        for detection in visual["candidates"]:
            key = (visual["observation_id"], detection["candidate_id"])
            if key in index:
                raise ValueError("duplicate prediction identity")
            index[key] = (visual, detection, signature)
    examples = []
    seen = set()
    for item in annotation["items"]:
        if (
            set(item) != {"observation_id", "candidate_id", "correct"}
            or type(item["correct"]) is not bool
        ):
            raise ValueError("annotation must explicitly label candidate correctness")
        key = (item["observation_id"], item["candidate_id"])
        if key in seen or key not in index:
            raise ValueError("duplicate or unmatched annotation")
        seen.add(key)
        visual, detection, signature = index[key]
        examples.append(
            CalibrationExample(
                "/".join(key),
                result["source_sha256"],
                visual["input_sha256"],
                signature,
                detection["detector_score"],
                item["correct"],
                annotation_sha256,
                "independent_annotation",
            )
        )
    if not examples:
        raise ValueError("no explicitly labeled predictions")
    return tuple(examples)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for part in ("fit", "holdout"):
        p.add_argument(f"--{part}-result", type=Path, required=True)
        p.add_argument(f"--{part}-annotations", type=Path, required=True)
        p.add_argument(f"--{part}-annotation-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    fit = load_examples(a.fit_result, a.fit_annotations, a.fit_annotation_sha256)
    holdout = load_examples(a.holdout_result, a.holdout_annotations, a.holdout_annotation_sha256)
    artifact = fit_calibration(fit)
    evaluation = evaluate_calibration(artifact, holdout)
    report = {
        "artifact": asdict(artifact),
        "holdout_metrics": evaluation,
        "holdout_evidence_sha256": content_sha256(holdout),
        "scope": "annotated_detector_candidates_only_not_identity_or_roles",
        "annotation_truth": "externally_supplied_not_verified_by_hash",
        "memory_write_authorized": False,
    }
    with a.output.open("x") as out:
        out.write(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
