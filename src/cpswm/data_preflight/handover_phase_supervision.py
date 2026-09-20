"""Author motion-threshold phase proxies, isolated from runtime evidence production."""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import math
import re
from dataclasses import dataclass
from typing import Any

PHASES = frozenset({"reach", "transfer", "retreat", "unknown"})


@dataclass(frozen=True)
class PhaseSample:
    index: int
    time_seconds: float
    giver: str
    receiver: str


@dataclass(frozen=True)
class AuthorPhaseSeries:
    source_sha256: str
    sequence_name: str
    giver_id: str
    receiver_id: str
    samples: tuple[PhaseSample, ...]

    def __post_init__(self) -> None:
        match = re.fullmatch(r"(P\d{2})_(P\d{2})_(double|single)_[a-z]+", self.sequence_name)
        if (
            match is None
            or (self.giver_id, self.receiver_id) != match.group(1, 2)
            or self.giver_id == self.receiver_id
            or not self.samples
            or len(self.source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.source_sha256)
        ):
            raise ValueError("invalid author sequence/role/source identity")
        for i, row in enumerate(self.samples):
            if (
                row.index != i
                or not math.isfinite(row.time_seconds)
                or row.time_seconds < 0
                or row.giver not in PHASES
                or row.receiver not in PHASES
                or (i > 0 and row.time_seconds <= self.samples[i - 1].time_seconds)
            ):
                raise ValueError("invalid phase row or nonmonotone author timeline")


def parse_author_phases(
    payload: bytes, *, expected_sha256: str, sequence_name: str
) -> AuthorPhaseSeries:
    if len(payload) > 4 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("phase source digest/budget mismatch")
    if b"\0" in payload:
        raise ValueError("null bytes in author CSV")
    try:
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig")), strict=True))
    except csv.Error as exc:
        raise ValueError("malformed author CSV") from exc
    reader = iter(rows)
    header = next(reader, [])
    if len(set(header)) != len(header) or not {"Index", "Time", "Giver", "Receiver"} <= set(header):
        raise ValueError("unique required author columns missing")
    positions = {name: header.index(name) for name in ("Index", "Time", "Giver", "Receiver")}
    participants = {
        match.group(1)
        for name in header
        if (match := re.match(r"Bone(?: Marker)?:(P\d{2}):", name))
    }
    if participants != set(sequence_name.split("_")[:2]):
        raise ValueError("author trajectory participants differ from role metadata")
    samples: list[PhaseSample] = []
    for fields in reader:
        if len(fields) != len(header) or len(samples) >= 100000:
            raise ValueError("CSV row width/count mismatch")
        values = {k: fields[v] for k, v in positions.items()}
        samples.append(
            PhaseSample(
                int(values["Index"]),
                float(values["Time"]),
                values["Giver"] or "unknown",
                values["Receiver"] or "unknown",
            )
        )
    roles = sequence_name.split("_")[:2]
    if len(roles) != 2:
        raise ValueError("missing author role identifiers")
    return AuthorPhaseSeries(expected_sha256, sequence_name, roles[0], roles[1], tuple(samples))


def project_nominal_phase(series: AuthorPhaseSeries, video_time_seconds: float) -> dict[str, Any]:
    """Bracket on nominal author-synchronized time; never infer a sync error bound.

    A phase crossing has BOTH labels. Outside the authored time range is unknown,
    never an extrapolated last state. One candidate remains a proxy, not gold.
    """
    if not math.isfinite(video_time_seconds) or video_time_seconds < 0:
        raise ValueError("finite nonnegative video time required")
    times = [r.time_seconds for r in series.samples]
    index = bisect.bisect_left(times, video_time_seconds)
    bracket: tuple[PhaseSample, ...]
    if index < len(times) and times[index] == video_time_seconds:
        bracket = (series.samples[index],)
    elif index == 0 or index == len(times):
        bracket = ()
    else:
        bracket = (series.samples[index - 1], series.samples[index])
    roles = {}
    for role in ("giver", "receiver"):
        candidates = sorted({getattr(r, role) for r in bracket})
        roles[role] = {
            "author_participant_id": getattr(series, role + "_id"),
            "visual_identity_binding": "UNRESOLVED",
            "phase_candidates": candidates,
            "status": (
                "OUTSIDE_AUTHOR_RANGE"
                if not bracket
                else "UNKNOWN_AUTHOR_PHASE"
                if "unknown" in candidates
                else "BOUNDARY_AMBIGUOUS"
                if len(candidates) > 1
                else "AUTHOR_PROXY"
            ),
        }
    return {
        "lane": "evaluator_only",
        "source_sha256": series.source_sha256,
        "sequence_name": series.sequence_name,
        "video_time_seconds": video_time_seconds,
        "author_rows": [r.index for r in bracket],
        "author_times_seconds": [r.time_seconds for r in bracket],
        "roles": roles,
        "synchronization": "AUTHOR_T_POSE_NOMINAL_NO_MEASURED_ERROR_BOUND",
        "contact_or_release_gold": False,
        "runtime_evidence_authorized": False,
    }


def phase_boundaries(series: AuthorPhaseSeries) -> list[dict[str, Any]]:
    rows = []
    for previous, current in zip(series.samples[:-1], series.samples[1:], strict=True):
        for role in ("giver", "receiver"):
            before, after = getattr(previous, role), getattr(current, role)
            if before != after:
                rows.append(
                    {
                        "role": role,
                        "author_participant_id": getattr(series, role + "_id"),
                        "visual_identity_binding": "UNRESOLVED",
                        "from_phase": before,
                        "to_phase": after,
                        "bracket_rows": [previous.index, current.index],
                        "nominal_time_bracket_seconds": [
                            previous.time_seconds,
                            current.time_seconds,
                        ],
                        "meaning": "AUTHOR_PROXY_PHASE_CHANGE_NOT_VERIFIED_PHYSICAL_CONTACT",
                    }
                )
    return rows
