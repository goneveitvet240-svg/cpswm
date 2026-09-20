import hashlib
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.data_preflight.handover_phase_supervision import (
    parse_author_phases,
    phase_boundaries,
    project_nominal_phase,
)

HEADER = "Index,Giver,Receiver,Time,Bone:P07:Hip:Position:X,Bone:P08:Hip:Position:X\n"
ROWS = "0,reach,reach,0,0,1\n1,transfer,reach,0.1,0,1\n2,retreat,transfer,0.2,0,1\n"


def load(text=HEADER + ROWS, sequence="P07_P08_double_bag"):
    data = text.encode()
    return parse_author_phases(
        data, expected_sha256=hashlib.sha256(data).hexdigest(), sequence_name=sequence
    )


def test_separate_roles_boundaries_and_no_gold_or_visual_identity():
    series = load()
    r = project_nominal_phase(series, 0.05)
    assert r["author_rows"] == [0, 1]
    assert r["roles"]["giver"]["phase_candidates"] == ["reach", "transfer"]
    assert r["roles"]["giver"]["status"] == "BOUNDARY_AMBIGUOUS"
    assert r["roles"]["receiver"]["phase_candidates"] == ["reach"]
    assert r["roles"]["giver"]["visual_identity_binding"] == "UNRESOLVED"
    assert not r["contact_or_release_gold"] and not r["runtime_evidence_authorized"]
    assert len(phase_boundaries(series)) == 3


def test_exact_row_unknown_and_no_endpoint_extrapolation():
    assert project_nominal_phase(load(), 0.1)["author_rows"] == [1]
    assert project_nominal_phase(load(), 0.3)["roles"]["giver"]["status"] == "OUTSIDE_AUTHOR_RANGE"
    series = load(HEADER + ROWS.replace("1,transfer", "1,"))
    assert project_nominal_phase(series, 0.05)["roles"]["giver"]["status"] == "UNKNOWN_AUTHOR_PHASE"


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("0.1", "nan"),
        lambda s: s.replace("0.1", "-1"),
        lambda s: s.replace("0.1", "0"),
        lambda s: s.replace("1,transfer", "3,transfer"),
        lambda s: s.replace("transfer", "contact_gold"),
        lambda s: s.replace("Index,Giver", "Index,Index"),
        lambda s: s + "\0",
        lambda s: s.replace("1,transfer,reach,0.1,0,1", "1,transfer"),
    ],
)
def test_bad_author_rows_rejected(change):
    with pytest.raises(ValueError):
        load(change(HEADER + ROWS))


def test_source_and_participant_mismatch_rejected():
    with pytest.raises(ValueError):
        parse_author_phases(
            (HEADER + ROWS).encode(), expected_sha256="a" * 64, sequence_name="P07_P08_double_bag"
        )
    with pytest.raises(ValueError):
        load(sequence="P09_P10_double_bag")
    with pytest.raises(ValueError):
        replace(load(), giver_id="P08")


@pytest.mark.parametrize("time", [-1, math.inf, math.nan])
def test_invalid_query_rejected(time):
    with pytest.raises(ValueError):
        project_nominal_phase(load(), time)


def test_corrupt_raw_and_depth_are_explicit(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from inspect_bimanual_phase_subset import depth_timestamp_status, inspect_video, read_member

    assert inspect_video(b"\0" * 100)["status"] == "INVALID_ALL_ZERO"
    assert depth_timestamp_status(b"\0" * 10)["status"] == "INVALID_NULL_BYTES"
    assert (
        depth_timestamp_status(b"Index,Time\n0,-.01\n1,.02\n")["status"]
        == "PARSED_NO_DEPTH_FRAMES_ACQUIRED"
    )
    assert depth_timestamp_status(b"Index,Time\n0,0\n1,0\n")["status"] == "INVALID_TABLE"
    p = tmp_path / "source"
    p.write_bytes(b"abc")
    receipt = {"local_path": "source", "bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
    assert read_member(tmp_path, receipt) == b"abc"
    p.write_bytes(b"abd")
    with pytest.raises(ValueError):
        read_member(tmp_path, receipt)
    with pytest.raises(ValueError):
        read_member(tmp_path, {**receipt, "local_path": "../escape"})
