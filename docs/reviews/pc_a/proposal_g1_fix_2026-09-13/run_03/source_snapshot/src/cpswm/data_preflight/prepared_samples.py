"""Partitioned, keyed proposal envelopes. Never grants training/custody authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from cpswm.data_preflight.proposal_samples import ProposalSample, audit_samples, export_sample
from cpswm.system.reproducibility import content_sha256

FILES = {
    "model_input": "features.jsonl",
    "training_targets": "targets.jsonl",
    "audit_only": "audit.jsonl",
}


def write_prepared_samples(
    samples: tuple[ProposalSample, ...], output: Path, *, input_sha256: str
) -> dict[str, Any]:
    samples = tuple(ProposalSample.model_validate(s.model_dump(mode="json")) for s in samples)
    report = audit_samples(samples)
    projections = [(sample, export_sample(sample)) for sample in samples]
    output.mkdir(parents=True, exist_ok=False)
    partitions = {}
    for partition in sorted({sample.partition for sample in samples}):
        directory = output / partition
        directory.mkdir()
        rows = [(s, p) for s, p in projections if s.partition == partition]
        hashes = {}
        for field, filename in FILES.items():
            envelopes = []
            for sample, projection in rows:
                pair = {"sample_id": str(sample.sample_id), "partition": partition, **projection}
                envelopes.append(
                    {
                        "schema": "proposal-row@2",
                        "sample_id": str(sample.sample_id),
                        "partition": partition,
                        "field": field,
                        "pair_sha256": content_sha256(pair),
                        "payload": projection[field],
                    }
                )
            raw = "".join(
                json.dumps(e, sort_keys=True, allow_nan=False) + "\n" for e in envelopes
            ).encode()
            with (directory / filename).open("xb") as handle:
                handle.write(raw)
            hashes[filename] = hashlib.sha256(raw).hexdigest()
        partitions[partition] = {
            "sample_ids": [str(s.sample_id) for s, _ in rows],
            "files_sha256": hashes,
        }
    report.update(
        schema="prepared-proposals@2",
        input_sha256=input_sha256,
        partitions=partitions,
        training_started=False,
        generated_model_artifact=False,
    )
    # Last publication marker. Any interrupted directory has no usable readiness receipt.
    with (output / "readiness.json").open("x") as handle:
        json.dump(report, handle, sort_keys=True, indent=2, allow_nan=False)
    return report


def load_prepared_partition(
    directory: Path, partition: Literal["train", "development"], *, expected_manifest_sha256: str
) -> tuple[dict[str, Any], ...]:
    """Join by immutable sample IDs and verify complete row pairing.

    The owner must obtain the expected manifest digest independently, not from the
    same untrusted directory. Returned model_input is the ONLY proposer feature.
    Hash consistency is not annotator authentication or permission to train.
    """
    if partition not in {"train", "development"} or directory.is_symlink():
        raise ValueError("explicit non-heldout partition and real directory required")
    marker = directory / "readiness.json"
    if marker.is_symlink():
        raise ValueError("manifest symlink forbidden")
    raw = marker.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("manifest differs from independently retained receipt")
    manifest = json.loads(raw)
    if manifest.get("schema") != "prepared-proposals@2" or partition not in manifest["partitions"]:
        raise ValueError("unsupported preparation or missing partition")
    specification = manifest["partitions"][partition]
    ids = specification["sample_ids"]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("nonempty unique sample identities required")
    folder = directory / partition
    if folder.is_symlink():
        raise ValueError("partition symlink forbidden")
    tables = {}
    for field, filename in FILES.items():
        path = folder / filename
        if path.is_symlink():
            raise ValueError("row file symlink forbidden")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != specification["files_sha256"][filename]:
            raise ValueError("partition file differs from preparation receipt")
        table = {}
        for line in raw.splitlines():
            row = json.loads(line)
            if set(row) != {"schema", "sample_id", "partition", "field", "pair_sha256", "payload"}:
                raise ValueError("unexpected row envelope fields")
            if (
                row["schema"] != "proposal-row@2"
                or row["partition"] != partition
                or row["field"] != field
            ):
                raise ValueError("row schema/partition/field mismatch")
            if row["sample_id"] in table:
                raise ValueError("duplicate sample row")
            table[row["sample_id"]] = row
        if set(table) != set(ids):
            raise ValueError("orphan or missing joined sample")
        tables[field] = table
    joined = []
    for sample_id in ids:
        item = {field: tables[field][sample_id]["payload"] for field in FILES}
        pair = {"sample_id": sample_id, "partition": partition, **item}
        if any(tables[field][sample_id]["pair_sha256"] != content_sha256(pair) for field in FILES):
            raise ValueError("features, targets and audit have mismatched sample binding")
        if (
            item["audit_only"]["sample_id"] != sample_id
            or item["audit_only"]["partition"] != partition
        ):
            raise ValueError("audit identity differs from row identity")
        joined.append(pair)
    return tuple(joined)
