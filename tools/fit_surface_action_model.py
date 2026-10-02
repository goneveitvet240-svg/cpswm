"""Fit development joint outcomes from separately evaluated fixed trajectories."""

import argparse
import json
from pathlib import Path

from cpswm.perception_mapping.surface_action_model import fit
from cpswm.system.reproducibility import content_sha256


def build(pairs, output):
    if output.exists():
        raise ValueError("model output must be new")
    rows, sources = [], []
    for root, evaluation in pairs:
        result = json.loads((root / "result.json").read_text())
        scored = json.loads(evaluation.read_text())
        sources.append(
            dict(root=str(root), result=content_sha256(result), evaluation=content_sha256(scored))
        )
        labels = {
            (r["step_index"], content_sha256(r["query"])): r["score"]["joint_success"]
            for r in scored["rows"]
        }
        sensors = {}
        for step in result["steps"]:
            raw = json.loads((root / "public" / f"{step['index']:03d}" / "raw.json").read_text())
            # RGB and depth, plus pose without dynamic action/time metadata.
            import base64

            pose = json.loads(base64.b64decode(raw["observations"][2]["payload_base64"]))
            for key in ("action_id", "capture_time"):
                pose.pop(key, None)
            sensors[step["index"]] = content_sha256(
                (
                    raw["observations"][0]["payload_base64"],
                    raw["observations"][1]["payload_base64"],
                    pose,
                )
            )
        for i, step in enumerate(result["steps"]):
            for query, report in zip(result["queries"], step["reports"], strict=True):
                current = labels[(step["index"], content_sha256(query))]
                common = dict(**query, status=report["status"])
                if current is not None:
                    rows.append(
                        dict(
                            **common,
                            action="Stop",
                            degrees=0.0,
                            joint_success=current,
                            source_pair=sensors[step["index"]],
                        )
                    )
                if i + 1 < len(result["steps"]):
                    nxt = result["steps"][i + 1]
                    label = labels[(nxt["index"], content_sha256(query))]
                    if label is not None:
                        rows.append(
                            dict(
                                **common,
                                **result["schedule"][nxt["index"]],
                                joint_success=label,
                                source_pair=content_sha256(
                                    (sensors[step["index"]], sensors[nxt["index"]])
                                ),
                            )
                        )
    model = fit(rows, training_manifest=content_sha256(sources))
    output.write_text(
        json.dumps(
            dict(model=model, pin=content_sha256(model), sources=sources, rows=rows),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pair", nargs=2, type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    build(a.pair, a.output)
