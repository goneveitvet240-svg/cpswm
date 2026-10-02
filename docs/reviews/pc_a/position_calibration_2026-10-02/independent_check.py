"""Independent moments and covariance-form posterior arithmetic on pinned outputs.

Reuses sealed public/label artifacts, not their generation or natural identity.
Does not import the implementation under test.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from math import cos, radians, sin
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def rotation(c):
    a, b = radians(c["yaw_degrees"]), radians(c["pitch_degrees"])
    return np.array([[cos(a), 0, sin(a)], [0, 1, 0], [-sin(a), 0, cos(a)]]) @ np.array(
        [[1, 0, 0], [0, cos(b), -sin(b)], [0, sin(b), cos(b)]]
    )


def moments(rows, error):
    frames = defaultdict(list)
    for row in rows:
        ref = np.array(row["reference_world_m"])
        value = (
            np.array(row["observed_world_m"]) - ref if error else ref - row["camera"]["position_m"]
        )
        x = rotation(row["camera"]).T @ value
        frames[(row["house_index"], row["object_key"], row["frame_key"])].append(
            np.r_[x, np.outer(x, x).ravel()]
        )
    objects = defaultdict(list)
    for (house, obj, _), values in frames.items():
        objects[house, obj].append(np.mean(values, axis=0))
    houses = defaultdict(list)
    for (house, _), values in objects.items():
        houses[house].append(np.mean(values, axis=0))
    total = np.mean([np.mean(values, axis=0) for values in houses.values()], axis=0)
    return total[:3], total[3:].reshape(3, 3) - np.outer(total[:3], total[:3])


def main(root, ledger_pin, output):
    ledger_path = root / "execution-ledger.json"
    assert digest(ledger_path) == ledger_pin
    ledger = load(ledger_path)
    assert len(ledger) == 6 and all(r["exit_code"] == 0 for r in ledger)
    for phase in ("run", "fresh"):
        expected = next(
            r["output_sha256"] for r in ledger if r["trial"] == phase and r["phase"] == "evaluate"
        )
        assert {p.name: digest(p) for p in (root / phase).glob("*.json")} == expected
    manifest = load(root / "frozen-data/inputs.json")
    for name, pin in manifest["files"].items():
        assert digest(root / "frozen-data" / name) == pin
    training = load(root / "frozen-data/training.json")
    bundle = load(root / "run/models.json")
    assert bundle["training_file_sha256"] == manifest["files"]["training.json"]
    for key, item in bundle["results"].items():
        assert item["status"] == "FITTED"
        for kind, error in (("prior", False), ("residual", True)):
            mean, cov = moments(training["rows"][key], error)
            np.testing.assert_allclose(mean, item["model"][kind]["mean"], atol=1e-12)
            np.testing.assert_allclose(cov, item["model"][kind]["covariance"], atol=1e-12)
    public = load(root / "frozen-data/public.json")
    predictions = load(root / "run/predictions.json")
    truth = load(root / "frozen-data/evaluation.json")
    assert predictions["public_sha256"] == manifest["files"]["public.json"]
    assert predictions["models_sha256"] == digest(root / "run/models.json")
    counts, n = defaultdict(lambda: [0, 0, 0]), 0
    for frame, prediction, labels in zip(public, predictions["frames"], truth, strict=True):
        assert frame["index"] == prediction["index"] == labels["index"]
        camera = frame["camera"]
        q, t = rotation(camera), np.array(camera["position_m"])
        for entry, row, label in zip(
            frame["entries"], prediction["rows"], labels["rows"], strict=True
        ):
            assert entry["key"] == row["key"] == label["key"]
            for ref, arms in row["predictions"].items():
                model = bundle["results"][f"{entry['estimator']}/{ref}"]["model"]
                assert model["readout_sha256"] == entry["readout_sha256"]
                for arm, point in arms.items():
                    if entry["point_m"] is None:
                        assert point is None
                        continue
                    prior = arm in ("prior_only", "both")
                    error = arm in ("error_only", "both")
                    mu = t + q @ model["prior"]["mean"] if prior else np.zeros(3)
                    p = q @ model["prior"]["covariance"] @ q.T if prior else np.eye(3)
                    bias = q @ model["residual"]["mean"] if error else np.zeros(3)
                    r = q @ model["residual"]["covariance"] @ q.T if error else np.eye(3)
                    expected = mu + p @ np.linalg.solve(
                        p + r, np.array(entry["point_m"]) - bias - mu
                    )
                    np.testing.assert_allclose(point, expected, atol=1e-11)
                    n += 1
                for arm, point in dict(raw=row["raw_point_m"], **arms).items():
                    for selection in ("all_seeds", "fixed_first_seed"):
                        if selection == "fixed_first_seed" and not row["fixed_first_seed"]:
                            continue
                        key = "/".join(
                            (labels["partition"], entry["estimator"], ref, arm, selection)
                        )
                        count = counts[key]
                        count[0] += 1
                        if label["eligible"] and point is not None:
                            count[1] += 1
                            count[2] += int(
                                all(
                                    lo <= v <= hi
                                    for lo, v, hi in zip(
                                        label["bounds"]["lower"],
                                        point,
                                        label["bounds"]["upper"],
                                        strict=True,
                                    )
                                )
                            )
    report = load(root / "run/report.json")
    assert report["prediction_sha256"] == digest(root / "run/predictions.json")
    assert report["evaluation_sha256"] == manifest["files"]["evaluation.json"]
    for key, values in counts.items():
        assert [
            report["summaries"][key][k] for k in ("public_rows", "adjudicated", "inside")
        ] == values
    result = dict(
        status="MATCHED",
        model_count=6,
        moments=12,
        posterior_means=n,
        summary_counts=len(counts),
        ledger_sha256=ledger_pin,
        scope="independent arithmetic on sealed inputs, not raw capture or identity adjudication",
    )
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--ledger-pin", required=True)
    a = p.parse_args()
    main(a.root, a.ledger_pin, a.output)
