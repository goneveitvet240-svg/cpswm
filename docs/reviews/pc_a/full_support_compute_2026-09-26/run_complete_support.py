"""Full 303-target controlled history, actual original weights, no new optimizer.

The source context is deliberately a test fixture. Dense reference temporarily
raises its explicit resource cap; it is never exported as a trained checkpoint.
"""

import argparse
import gc
import hashlib
import json
import math
import resource
import sys
import time
from dataclasses import replace
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_runtime_candidates import (  # noqa: E402
    LEDGER,
    context,
    generate,
    pixel,
    posterior_context,
)

from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution  # noqa: E402
from cpswm.data_preflight.proposal_inference_session import encoded  # noqa: E402
from cpswm.data_preflight.proposal_trainer import load_checkpoint  # noqa: E402
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402


def run(original, derived, arm, output):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    started = time.monotonic()
    parents = json.loads((original / "summary.json").read_bytes())
    variants = json.loads((derived / "summary.json").read_bytes())
    parent_pin = next(r["checkpoint_manifest_sha256"] for r in parents["runs"] if r["arm"] == arm)
    pin = next(r["checkpoint_manifest_sha256"] for r in variants["runs"] if r["arm"] == arm)
    ctx = posterior_context()
    support = generate(ctx)
    assert len(support.targets) == 303
    (output / "input.json").write_bytes(
        encoded(
            {
                "context": ctx.model_dump(mode="json"),
                "support": [t.model_dump(mode="json") for t in support.targets],
                "generation": support.report,
            }
        )
    )
    old = RuntimeCandidateSession(original / arm, manifest_sha256=parent_pin, seed=11)
    unchanged = old.snapshot()
    try:
        old.process(request_id="full", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    except ValueError as exc:
        assert "resource limit" in str(exc)
    else:
        raise AssertionError("original default budget must still refuse the complete graph")
    assert old.snapshot() == unchanged
    rows, numeric = {}, {}
    for kind, path, digest in (
        ("dense_reference", original, parent_pin),
        ("blocked", derived, pin),
    ):
        model, manifest = load_checkpoint(path / arm, manifest_sha256=digest)
        if kind == "dense_reference":
            model.config = replace(model.config, max_nodes=32768)
        phase = time.monotonic()
        with torch.no_grad():
            scorer = model.prepare(support.context, support.targets)
            distribution = TypedProposalDistribution(
                context=support.context, runtime_candidates=support.targets, scorer=scorer
            )
            logs = torch.stack(
                [distribution.factor_log_probabilities(k) for k in distribution.target_sha256s]
            )
            numeric[kind] = {
                "memory": scorer.memory.clone(),
                "vectors": scorer.vectors.clone(),
                "logs": logs.clone(),
                "keys": distribution.target_sha256s,
            }
            mass = float(logs.sum(1).exp().sum())
            assert math.isclose(mass, 1.0, abs_tol=1e-12)
            assert scorer.node_count == 10246
            rows[kind] = {
                "seconds": time.monotonic() - phase,
                "node_count": scorer.node_count,
                "candidate_count": len(distribution.target_sha256s),
                "probability_mass": mass,
                "weights_sha256": manifest["weights_sha256"],
                "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
            (output / f"{kind}.probabilities.json").write_bytes(
                encoded(
                    {
                        "targets": distribution.target_sha256s,
                        "factor_log_probabilities": logs.tolist(),
                    }
                )
            )
        print(json.dumps({"arm": arm, "phase": kind, **rows[kind]}), flush=True)
        del distribution, scorer, model
        gc.collect()
    assert numeric["dense_reference"]["keys"] == numeric["blocked"]["keys"]
    differences = {}
    for field in ("memory", "vectors", "logs"):
        a, b = numeric["dense_reference"][field], numeric["blocked"][field]
        torch.testing.assert_close(a, b, atol=1e-5, rtol=1e-5)
        differences[field] = float((a - b).abs().max())
    assert rows["dense_reference"]["weights_sha256"] == rows["blocked"]["weights_sha256"]
    del numeric
    gc.collect()
    live = RuntimeCandidateSession(derived / arm, manifest_sha256=pin, seed=11)
    first = live.process(request_id="full", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    blob = live.snapshot()
    (output / "full.snapshot.json").write_bytes(blob)
    assert first == live.process(
        request_id="full", context=ctx, bootstrap_ledger_lineage_ref=LEDGER
    )
    assert live.snapshot() == blob
    restored = RuntimeCandidateSession.restore(
        derived / arm,
        manifest_sha256=pin,
        snapshot=blob,
        snapshot_sha256=hashlib.sha256(blob).hexdigest(),
    )
    assert live.snapshot() == restored.snapshot()
    # A resource rejection must leave the already successful history and next RNG intact.
    try:
        live.process(
            request_id="overflow",
            context=ctx,
            bootstrap_ledger_lineage_ref=LEDGER,
            max_candidates=302,
        )
    except ValueError as exc:
        assert "budget" in str(exc) or "limit" in str(exc)
    else:
        raise AssertionError("complete support must never be truncated to fit")
    assert live.snapshot() == blob
    kwargs = dict(
        request_id="next", context=context([pixel(0)]), bootstrap_ledger_lineage_ref=LEDGER
    )
    assert live.process(**kwargs) == restored.process(**kwargs)
    assert live.snapshot() == restored.snapshot()
    (output / "continued.snapshot.json").write_bytes(live.snapshot())
    assert not first.receipt.ledger_authorized and not first.receipt.native_publication_authorized
    report = {
        "arm": arm,
        "track": "CONTROLLED_FULL_SUPPORT_COMPUTE_ONLY",
        "rows": rows,
        "operation_counts": support.report["operation_counts"],
        "max_abs_difference": differences,
        "tolerance": {"atol": 1e-5, "rtol": 1e-5},
        "exact_same_backend_restore": True,
        "no_truncation": True,
        "rejection_preserves_rng_history": True,
        "optimizer_steps_added": 0,
        "natural_transitions": 0,
        "native_publications": 0,
        "seconds": time.monotonic() - started,
    }
    (output / "report.json").write_bytes(encoded(report))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--derived", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.original, args.derived, args.arm, args.output)
