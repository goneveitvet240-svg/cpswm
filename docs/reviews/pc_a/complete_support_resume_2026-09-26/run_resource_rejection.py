"""Retain the actual failed complete graph and prove low-profile rollback/retry."""

import argparse
import hashlib
import json
import resource
from pathlib import Path

import torch

from cpswm.data_preflight.proposal_samples import ProposalContext
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession
from cpswm.data_preflight.typed_proposal_networks import ARMS


def run(training, inputs, output):
    torch.set_num_threads(2)
    output.mkdir(parents=True, exist_ok=False)
    bundle = json.loads((training / "summary.json").read_bytes())
    data = {
        name: json.loads((inputs / (name + ".support.json")).read_bytes())
        for name in ("before_delivery", "after_delivery")
    }
    contexts = {name: ProposalContext.model_validate(d["context"]) for name, d in data.items()}
    ledger = data["before_delivery"]["targets"][0]["candidate"]["state"]["ledger_lineage_ref"]
    rows = []
    for arm in ARMS:
        pin = next(r["checkpoint_manifest_sha256"] for r in bundle["runs"] if r["arm"] == arm)
        session = RuntimeCandidateSession(training / arm, manifest_sha256=pin, seed=11)
        first = session.process(
            request_id="first",
            context=contexts["before_delivery"],
            bootstrap_ledger_lineage_ref=ledger,
        )
        assert len(first.support.targets) == 216
        before = session.snapshot()
        try:
            session.process(
                request_id="late",
                context=contexts["after_delivery"],
                bootstrap_ledger_lineage_ref=ledger,
            )
        except ValueError as exc:
            assert "node budget" in str(exc)
        else:
            raise AssertionError("old explicit 32768-node profile unexpectedly accepted full graph")
        assert session.snapshot() == before
        reference = RuntimeCandidateSession.restore(
            training / arm,
            manifest_sha256=pin,
            snapshot=before,
            snapshot_sha256=hashlib.sha256(before).hexdigest(),
        )
        retry = dict(
            request_id="late",
            context=contexts["before_delivery"],
            bootstrap_ledger_lineage_ref=ledger,
        )
        assert session.process(**retry) == reference.process(**retry)
        assert session.snapshot() == reference.snapshot()
        rows.append(
            {
                "arm": arm,
                "original_complete_candidates": 783,
                "initial_candidates": 216,
                "rejected_without_truncation": True,
                "snapshot_unchanged": True,
                "next_rng_and_legal_retry_equal": True,
            }
        )
        print(json.dumps(rows[-1]), flush=True)
    report = {
        "rows": rows,
        "input_sha256s": {
            name: hashlib.sha256((inputs / (name + ".support.json")).read_bytes()).hexdigest()
            for name in data
        },
        "scope": "archived real-pixel generated context; no new front end, labels or authority",
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.training, args.inputs, args.output)
