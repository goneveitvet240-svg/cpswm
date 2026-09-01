"""Shared JSONL/Parquet import and artifact boundary for D1 and D2 replay.

Rows are complete typed episode/envelope payloads. Dataset-specific collectors
normalize their raw records into these contracts before crossing this boundary;
CHEH/PCHMP/ORRER therefore consume exactly the same episode type at D0-D2.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cpswm.contracts import (
    EventMechanism,
    ProjectTwoDataMaturity,
    ProjectTwoEvaluatorTruthEnvelope,
    ProjectTwoReplayEpisode,
)
from cpswm.system.evaluation_operations.project_two_dataset import (
    ProjectTwoReplayDataset,
    audit_project_two_replay,
    summarize_project_two_evidence_coverage,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D1SimulatorAnnotatedReplayAdapter,
    D2RealPerceptionReplayAdapter,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_payload_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    elif suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Parquet import requires the optional pandas plus pyarrow/fastparquet runtime"
            ) from exc
        try:
            frame = pd.read_parquet(path)
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Parquet import requires pyarrow or fastparquet; JSONL remains dependency-free"
            ) from exc
        rows = frame.to_dict(orient="records")
        if rows and set(rows[0]) == {"payload_json"}:
            rows = [json.loads(row["payload_json"]) for row in rows]
    else:
        raise ValueError("replay input must be JSONL/NDJSON or Parquet")
    if not rows:
        raise ValueError(f"empty replay input: {path}")
    return rows


class ProjectTwoReplayFileImporter:
    """Load physically separated visible and evaluator stores through D1/D2 adapters."""

    def __init__(
        self,
        *,
        maturity: ProjectTwoDataMaturity,
        dataset_version: str,
        adapter_provenance: str,
    ) -> None:
        if maturity not in {
            ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
            ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
        }:
            raise ValueError("file importer is restricted to D1/D2")
        self.maturity = maturity
        self.dataset_version = dataset_version
        self.adapter_provenance = adapter_provenance

    def load(self, visible_path: Path, evaluator_truth_path: Path) -> ProjectTwoReplayDataset:
        visible_path = visible_path.resolve()
        evaluator_truth_path = evaluator_truth_path.resolve()
        if visible_path == evaluator_truth_path:
            raise ValueError("visible replay and evaluator truth must be physically separate files")
        episodes = tuple(
            ProjectTwoReplayEpisode.model_validate(row) for row in _read_payload_rows(visible_path)
        )
        evaluator = tuple(
            ProjectTwoEvaluatorTruthEnvelope.model_validate(row)
            for row in _read_payload_rows(evaluator_truth_path)
        )
        adapter_type = (
            D1SimulatorAnnotatedReplayAdapter
            if self.maturity is ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY
            else D2RealPerceptionReplayAdapter
        )
        return adapter_type(
            dataset_version=self.dataset_version,
            episodes=episodes,
            evaluator_store=evaluator,
            adapter_provenance=self.adapter_provenance,
        ).build()

    @staticmethod
    def normalize_open_world_labels(
        *,
        actor_label: str | None,
        mechanism_label: str | None,
        resident_actor_keys: tuple[str, ...],
    ) -> dict[str, Any]:
        """Normalize raw D1/D2 labels without coercing novelty into a known class."""

        unresolved: list[str] = []
        actor = actor_label or "unknown_actor"
        if actor not in resident_actor_keys:
            actor = "unknown_actor"
            unresolved.append("actor")
        try:
            mechanism = EventMechanism(mechanism_label or "")
        except (TypeError, ValueError):
            mechanism = EventMechanism.UNKNOWN_MECHANISM
            unresolved.append("mechanism")
        return {
            "actor_label": actor,
            "mechanism_label": mechanism,
            "unresolved_axes": tuple(unresolved),
        }


def export_project_two_replay_dataset(
    dataset: ProjectTwoReplayDataset, output_dir: Path, *, write_parquet: bool = False
) -> dict[str, Any]:
    """Write the frozen four-file bundle and optional payload-column Parquet mirrors."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "manifest.json": output_dir / "manifest.json",
        "visible_replay.jsonl": output_dir / "visible_replay.jsonl",
        "evaluator_truth.jsonl": output_dir / "evaluator_truth.jsonl",
        "coverage_report.json": output_dir / "coverage_report.json",
    }
    paths["manifest.json"].write_text(dataset.manifest.model_dump_json(indent=2), encoding="utf-8")
    paths["visible_replay.jsonl"].write_text(
        "\n".join(item.model_dump_json() for item in dataset.episodes) + "\n",
        encoding="utf-8",
    )
    paths["evaluator_truth.jsonl"].write_text(
        "\n".join(item.model_dump_json() for item in dataset.evaluator_store) + "\n",
        encoding="utf-8",
    )
    quality = audit_project_two_replay(dataset)
    coverage = summarize_project_two_evidence_coverage(dataset)
    report: dict[str, Any] = {
        "dataset_version": dataset.manifest.dataset_version,
        "maturity": sorted({item.maturity.value for item in dataset.episodes}),
        "quality": quality.model_dump(mode="json"),
        "coverage": coverage.model_dump(mode="json"),
        "provenance": sorted({entry for item in dataset.episodes for entry in item.provenance}),
        "physical_separation": {
            "visible": "visible_replay.jsonl",
            "evaluator_only": "evaluator_truth.jsonl",
        },
    }
    paths["coverage_report.json"].write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if write_parquet:
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Parquet export requires optional pandas and pyarrow") from exc
        pd.DataFrame(
            {"payload_json": [item.model_dump_json() for item in dataset.episodes]}
        ).to_parquet(output_dir / "visible_replay.parquet", index=False)
        pd.DataFrame(
            {"payload_json": [item.model_dump_json() for item in dataset.evaluator_store]}
        ).to_parquet(output_dir / "evaluator_truth.parquet", index=False)
    report["content_hashes"] = {
        name: _sha256(path) for name, path in paths.items() if name != "coverage_report.json"
    }
    # A report cannot contain its own final byte hash without a recursive
    # contradiction. Hash the three source artifacts inside the report; callers
    # may hash coverage_report.json in an outer run receipt.
    paths["coverage_report.json"].write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


__all__ = ["ProjectTwoReplayFileImporter", "export_project_two_replay_dataset"]
