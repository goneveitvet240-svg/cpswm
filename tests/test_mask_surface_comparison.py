"""Complete evaluator pairing/pinning checks, independent of real model inference."""

import gzip
from copy import deepcopy
from hashlib import sha256

import pytest

pytest.importorskip("torch")
import run_mask_surface_comparison as driver


@pytest.fixture
def case(tmp_path):
    source, inference = tmp_path / "source", tmp_path / "inference"
    source.mkdir()
    inference.mkdir()
    manifest, predictions = [], []
    for trial, count in driver.TRIALS.items():
        for index in range(count):
            key = f"{trial}-{index}"
            sdk = dict(
                owner=key,
                metadata=dict(
                    objects=[
                        dict(
                            objectId="object",
                            axisAlignedBoundingBox=dict(
                                cornerPoints=[
                                    [x, y, z]
                                    for x in (0.0, 2.0)
                                    for y in (0.0, 2.0)
                                    for z in (0.0, 2.0)
                                ]
                            ),
                        )
                    ]
                ),
            )
            sdkpath, boxpath = source / f"{key}.json", source / f"{key}-boxes.json"
            driver.save(sdkpath, sdk)
            driver.save(boxpath, {"object": [0, 0, 2, 2]})
            manifest.append(
                dict(
                    trial=trial,
                    index=index,
                    sdk=sdkpath.name,
                    sdk_sha256=driver.digest(sdkpath),
                    boxes=boxpath.name,
                    boxes_sha256=driver.digest(boxpath),
                )
            )
            point = [2.0, 1.0, 1.0] if index == 0 else None
            frame = dict(
                detector=dict(
                    camera=dict(action_id=key),
                    masks_npy_sha256=sha256(b"mask fixture").hexdigest(),
                    candidates=[
                        dict(
                            candidate_id="candidate",
                            category="bottle",
                            status="SURFACE_CANDIDATE" if point else "UNKNOWN_NO_MASK",
                            box_xyxy=[0, 0, 2, 2],
                            world_point_m=point,
                        )
                    ],
                ),
                tracks=[
                    dict(
                        anchor_id="anchor",
                        category="bottle",
                        status="FLOW_AND_MASK_SUPPORTED" if point else "LOST_NO_REINITIALIZATION",
                        world_point_m=point,
                    )
                ],
                old_box_tracks=[
                    dict(
                        anchor_id="old",
                        status="SURFACE_CANDIDATE" if point else "LOST",
                        first_seed_m=point,
                        soft_m=point,
                    )
                ],
            )
            p = inference / key / "public.json"
            driver.save(p, frame)
            m = p.with_name("masks.npy.gz")
            m.write_bytes(gzip.compress(b"mask fixture", mtime=0))
            predictions.append(
                dict(
                    trial=trial,
                    index=index,
                    public=str(p.relative_to(inference)),
                    public_sha256=driver.digest(p),
                    masks_sha256=driver.digest(m),
                )
            )
    driver.save(source / "manifest.json", manifest)
    driver.save(
        inference / "result.json",
        dict(status="COMPLETED", unprocessed=[], failures=[], frames=predictions),
    )
    return source, inference, tmp_path


def score(case, output):
    source, inference, _ = case
    return driver.evaluate(
        source,
        inference,
        driver.digest(inference / "result.json"),
        source / "manifest.json",
        driver.digest(source / "manifest.json"),
        output,
    )


def test_complete_positive_panel_boundary_and_all_unknown_rows_retained(case):
    output = case[2] / "score.json"
    score(case, output)
    result = driver.load(output)
    assert len(result["frames"]) == 16
    for frame in result["frames"]:
        expected = ["object"] if frame["index"] == 0 else []
        assert frame["tracks"][0]["point"]["inside_aabbs"] == expected
    with pytest.raises(ValueError, match="must be new"):
        score(case, output)


@pytest.mark.parametrize("attack", ["paired_omission", "duplicate", "owner", "dimension", "mask"])
def test_fully_rehashed_complete_bad_pair_rejected_and_legal_retry(case, attack):
    source, inference, root = case
    report_path, manifest_path = inference / "result.json", source / "manifest.json"
    report, manifest = driver.load(report_path), driver.load(manifest_path)
    originals = {p: p.read_bytes() for p in [report_path, manifest_path]}
    if attack == "paired_omission":
        report["frames"].pop()
        manifest.pop()
    elif attack == "duplicate":
        report["frames"][1] = deepcopy(report["frames"][0])
        manifest[1] = deepcopy(manifest[0])
    elif attack == "owner":
        p = source / manifest[0]["sdk"]
        originals[p] = p.read_bytes()
        sdk = driver.load(p)
        sdk["owner"] = "wrong exposure"
        driver.save(p, sdk)
        manifest[0]["sdk_sha256"] = driver.digest(p)
    elif attack == "dimension":
        p = inference / report["frames"][0]["public"]
        originals[p] = p.read_bytes()
        frame = driver.load(p)
        frame["tracks"][0]["world_point_m"] = [0.0, 0.0]  # Complete rehashed malformed point.
        driver.save(p, frame)
        report["frames"][0]["public_sha256"] = driver.digest(p)
    else:
        p = (inference / report["frames"][0]["public"]).with_name("masks.npy.gz")
        originals[p] = p.read_bytes()
        p.write_bytes(gzip.compress(b"replacement", mtime=0))
        report["frames"][0]["masks_sha256"] = driver.digest(p)
    driver.save(report_path, report)
    driver.save(manifest_path, manifest)
    output = root / "score.json"
    with pytest.raises(ValueError):
        score(case, output)
    assert not output.exists()
    for path, data in originals.items():
        path.write_bytes(data)
    score(case, output)
    assert len(driver.load(output)["frames"]) == 16


def test_external_result_pin_rejects_coherently_replaced_record(case):
    source, inference, root = case
    path = inference / "result.json"
    pin = driver.digest(path)
    report = driver.load(path)
    report["status"] = "FAILED"
    driver.save(path, report)
    with pytest.raises(ValueError, match="external pin"):
        driver.evaluate(
            source,
            inference,
            pin,
            source / "manifest.json",
            driver.digest(source / "manifest.json"),
            root / "score.json",
        )
