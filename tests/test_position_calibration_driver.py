"""Complete positive-path and fully rehashed malformed-panel checks."""

from copy import deepcopy

import numpy as np
import pytest
import run_position_calibration as driver
from test_calibrated_position import rows

from cpswm.perception_mapping.calibrated_position import (
    CameraCoordinates,
    PositionCalibration,
    posterior,
)


@pytest.fixture
def case(tmp_path):
    data = tmp_path / "training.json"
    public = tmp_path / "public.json"
    labels = tmp_path / "labels.json"
    models = tmp_path / "models.json"
    predictions = tmp_path / "predictions.json"
    pose = rows()[0].camera.model_dump(mode="json")
    driver.save(
        data,
        dict(
            parent_sha256="c" * 64,
            rows={
                f"{e}/{r}": [x.model_dump(mode="json") for x in rows()]
                for e in driver.ESTIMATORS
                for r in driver.REFERENCES
            },
        ),
    )
    frames, truth = [], []
    for index in range(96):
        entries, annotations = [], []
        if index in (0, 64):
            for e in driver.ESTIMATORS:
                for i, point in enumerate(([1.0, 2.0, 3.0], None)):
                    key = f"{e}:{index}:{i}"
                    entries.append(
                        dict(
                            key=key,
                            estimator=e,
                            point_m=point,
                            fixed_first_seed=True,
                            readout_sha256="d" * 64,
                        )
                    )
                    annotations.append(
                        dict(
                            key=key,
                            eligible=i == 0,
                            object_id="object" if i == 0 else None,
                            targets={r: [1.0, 2.0, 3.0] for r in driver.REFERENCES},
                            bounds=dict(lower=[1.0, 2.0, 3.0], upper=[2.0, 3.0, 4.0]),
                        )
                    )
        frames.append(dict(index=index, camera=pose, entries=entries))
        truth.append(
            dict(
                index=index,
                house_index=index // 8 + 1,
                partition="train" if index < 64 else "validation",
                eligible_visible_objects=1,
                rows=annotations,
            )
        )
    driver.save(public, frames)
    driver.save(labels, truth)
    driver.train(data, driver.digest(data), models)
    driver.predict(public, driver.digest(public), models, driver.digest(models), predictions)
    return dict(
        data=data,
        public=public,
        labels=labels,
        models=models,
        predictions=predictions,
        root=tmp_path,
    )


def test_separate_fit_predict_score_with_unknown_empty_and_inclusive_boundary(case):
    output = case["root"] / "report.json"
    driver.evaluate(
        case["predictions"],
        driver.digest(case["predictions"]),
        case["labels"],
        driver.digest(case["labels"]),
        output,
    )
    report = driver.load(output)
    assert report["frames"] == 96 and report["no_public_seed_frames"] == 94
    key = "validation/bare_seed/sdk_aabb_center_m/raw/fixed_first_seed"
    assert report["summaries"][key]["inside"] == 1
    assert report["summaries"][key]["public_rows"] == 2
    assert report["summaries"][key]["unadjudicated"] == 1
    assert len(report["frame_manifest"]) == 96
    bundle = driver.load(case["models"])
    prediction = driver.load(case["predictions"])["frames"][0]["rows"][0]
    for ref in driver.REFERENCES:
        item = bundle["results"][f"bare_seed/{ref}"]
        model = PositionCalibration.model_validate(item["model"])
        for arm, (use_prior, use_error) in driver.ARMS.items():
            direct = posterior(
                model,
                item["pin"],
                (rows()[0].camera,),
                ((1.0, 2.0, 3.0),),
                use_prior=use_prior,
                use_error=use_error,
                rho=0.5,
            )
            np.testing.assert_allclose(prediction["predictions"][ref][arm], direct.mean)


def test_validation_mutation_cannot_change_fitted_model_or_public_predictions(case):
    # Complete evaluation truth changes; inference still has only training/public inputs.
    labels = driver.load(case["labels"])
    for frame in labels[64:]:
        for row in frame["rows"]:
            row["targets"] = {r: [999.0, 999.0, 999.0] for r in driver.REFERENCES}
    driver.save(case["labels"], labels)
    models2, pred2 = case["root"] / "models2.json", case["root"] / "pred2.json"
    driver.train(case["data"], driver.digest(case["data"]), models2)
    driver.predict(
        case["public"], driver.digest(case["public"]), models2, driver.digest(models2), pred2
    )
    assert models2.read_bytes() == case["models"].read_bytes()
    assert pred2.read_bytes() == case["predictions"].read_bytes()


@pytest.mark.parametrize(
    "attack", ["duplicate", "missing_frame", "missing_arm", "nan", "box", "partition"]
)
def test_fully_rehashed_bad_evaluation_pair_rejected_then_legal_retry(case, attack):
    pred = driver.load(case["predictions"])
    truth = driver.load(case["labels"])
    if attack == "duplicate":
        pred["frames"][0]["rows"].append(deepcopy(pred["frames"][0]["rows"][0]))
        truth[0]["rows"].append(deepcopy(truth[0]["rows"][0]))
    elif attack == "missing_frame":
        pred["frames"].pop()
        truth.pop()
    elif attack == "missing_arm":
        del pred["frames"][0]["rows"][0]["predictions"][driver.REFERENCES[0]]["old"]
    elif attack == "nan":
        # Finite JSON string that float conversion would otherwise turn into NaN.
        pred["frames"][0]["rows"][0]["raw_point_m"][0] = "nan"
    elif attack == "box":
        truth[0]["rows"][0]["bounds"]["lower"][0] = 100.0
    else:
        truth[64]["partition"] = "train"
    badp, badt = case["root"] / "bad-p.json", case["root"] / "bad-t.json"
    driver.save(badp, pred)
    driver.save(badt, truth)
    output = case["root"] / "result.json"
    with pytest.raises(ValueError):
        driver.evaluate(badp, driver.digest(badp), badt, driver.digest(badt), output)
    assert not output.exists()
    driver.evaluate(
        case["predictions"],
        driver.digest(case["predictions"]),
        case["labels"],
        driver.digest(case["labels"]),
        output,
    )
    assert output.is_file()


def test_external_pin_rejects_replaced_training_and_model_bundle(case):
    pin = driver.digest(case["data"])
    data = driver.load(case["data"])
    first_key = next(iter(data["rows"]))
    data["rows"][first_key][0]["reference_world_m"] = [100.0, 100.0, 100.0]
    driver.save(case["data"], data)
    with pytest.raises(ValueError, match="digest"):
        driver.train(case["data"], pin, case["root"] / "bad-model.json")
    bundle = driver.load(case["models"])
    first_key = next(iter(bundle["results"]))
    bundle["results"][first_key]["model"]["reference"] = "sdk_transform_position_m"
    driver.save(case["models"], bundle)
    with pytest.raises(ValueError, match="key differs"):
        driver.predict(
            case["public"],
            driver.digest(case["public"]),
            case["models"],
            driver.digest(case["models"]),
            case["root"] / "bad-pred.json",
        )


def test_public_camera_rotation_schema_validates():
    with pytest.raises(ValueError):
        CameraCoordinates(position_m=(0, 0, 0), yaw_degrees=float("nan"), pitch_degrees=0)


def test_complete_public_readout_profile_swap_rejected(case):
    frames = driver.load(case["public"])
    frames[0]["entries"][0]["readout_sha256"] = "e" * 64
    driver.save(case["public"], frames)
    output = case["root"] / "bad-profile.json"
    with pytest.raises(ValueError, match="readout differs"):
        driver.predict(
            case["public"],
            driver.digest(case["public"]),
            case["models"],
            driver.digest(case["models"]),
            output,
        )
    assert not output.exists()


def test_scoring_never_overwrites_an_existing_row_ledger(case):
    existing = case["root"] / "scored-rows.json"
    existing.write_text("existing evidence\n")
    output = case["root"] / "new-report.json"
    with pytest.raises(ValueError, match="both be new"):
        driver.evaluate(
            case["predictions"],
            driver.digest(case["predictions"]),
            case["labels"],
            driver.digest(case["labels"]),
            output,
        )
    assert existing.read_text() == "existing evidence\n" and not output.exists()
