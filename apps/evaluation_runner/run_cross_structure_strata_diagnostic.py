"""Run the frozen four-strata causal diagnostic for structures one and two."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.evaluation_operations.cross_structure_strata_diagnostic import (  # noqa: E402
    run_cross_structure_strata_diagnostic,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds-per-stratum", type=int, default=50)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_cross_structure_strata_diagnostic(
        seed_count=args.seeds_per_stratum,
        bootstrap_samples=args.bootstrap_samples,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.output}")
    print(json.dumps(report["diagnosis"], ensure_ascii=False))


if __name__ == "__main__":
    main()
