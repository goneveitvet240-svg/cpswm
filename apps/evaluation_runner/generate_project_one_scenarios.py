"""Emit the controlled project-one scenarios as JSONL (阶段 3).

    PYTHONPATH=src python apps/evaluation_runner/generate_project_one_scenarios.py \
        --output artifacts/project_one/scenarios

Records and truth are written to *separate* files per scenario, so a training
pipeline that only reads ``*.records.jsonl`` cannot pick up a label by accident.
The core algorithm never generates its own data; this script is the only place
scenarios are materialized.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from cpswm.system.evaluation_operations.project_one_scenarios import (
    SCENARIO_NAMES,
    build_scenario,
    build_stream,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/project_one/scenarios"))
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIO_NAMES))
    arguments = parser.parse_args()

    output: Path = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []

    for name in arguments.scenarios:
        scenario = build_scenario(name)
        stream, truth = build_stream(name)

        records_path = output / f"{name}.records.jsonl"
        with records_path.open("w", encoding="utf-8") as handle:
            for record in stream:
                handle.write(json.dumps(asdict(record), sort_keys=True, default=str))
                handle.write("\n")

        truth_path = output / f"{name}.truth.jsonl"
        with truth_path.open("w", encoding="utf-8") as handle:
            for record in stream:
                entry = truth.get(record.event_id)
                if entry is not None:
                    handle.write(json.dumps(asdict(entry), sort_keys=True, default=str))
                    handle.write("\n")

        index.append(
            {
                "name": name,
                "capability": scenario.capability,
                "records": records_path.name,
                "truth": truth_path.name,
                "manifest": asdict(stream.manifest),
            }
        )
        print(f"{name:<22} {len(stream):>3} events  {stream.manifest.content_hash[:12]}")

    (output / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"wrote {len(index)} scenarios to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
