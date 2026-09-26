"""Fixed first HFD windows -> same-weight proposal consumption and exact recovery.

All trials are retained; no success/hand-count selection. With/without/shifted-hand
controls hold the complete generated target set and every target UUID fixed. The
weights remain component-fixture trained; responses are not calibrated task gains.
"""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from time import monotonic

import torch

from cpswm.data_preflight.hocap_joint_supervision import pinned_bytes, strict_json
from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
from cpswm.data_preflight.proposal_samples import ProposalContext, ProposalTarget, export_context
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession
from cpswm.data_preflight.runtime_candidates import (
    bootstrap_pixel_context,
    generate_runtime_candidates,
)
from cpswm.data_preflight.typed_proposal_networks import ARMS, leaves
from cpswm.system.reproducibility import content_sha256


def load_frontend(frontend, pin):
    raw = pinned_bytes(frontend, "result.json", pin)
    report = strict_json(raw)
    contexts, dependencies, measurements, hands, pair_count = {}, {"result.json": pin}, 0, 0, 0
    records = {}
    for row in report["records"]:
        records.setdefault(row["window"], []).append(row)
    for window in report["windows"]:
        key = window["sequence"]
        if not re.fullmatch(r"[0-9a-f]{64}/window-[0-9]{6}", key) or key in contexts:
            raise ValueError("invalid or duplicate frontend window")
        if not (
            window["core_ledger_unchanged"]
            and window["perception_restore_equal"]
            and window["execution_traces"] == 0
            and window["support"]["status"] == "COMPLETE_SUPPORT_GENERATED"
        ):
            raise ValueError("requires complete diagnostic frontend window")
        name, support_name = key + "/context.json", key + "/support.json"
        ctx = ProposalContext.model_validate_json(
            pinned_bytes(frontend, name, window["context_sha256"])
        )
        saved = strict_json(pinned_bytes(frontend, support_name, window["support_sha256"]))
        dependencies.update(
            {name: window["context_sha256"], support_name: window["support_sha256"]}
        )
        # Rebuild the complete context from source-bound detector records. A metadata
        # flag in the summary is never a substitute for checking the actual features.
        observations = tuple(
            ProposalPixelObservation.model_validate({**r["visual"], "hand_observation": r["hands"]})
            for r in records[key]
        )
        rebuilt = bootstrap_pixel_context(
            observations, cutoff=ctx.visible.cutoff, source_snapshot_id=ctx.source_snapshot_id
        )
        if rebuilt != ctx:
            raise ValueError("context differs from recorded visual and hand prefix")
        targets = tuple(ProposalTarget.model_validate(t) for t in saved["targets"])
        ledger = targets[0].candidate.state.ledger_lineage_ref
        support = generate_runtime_candidates(ctx, bootstrap_ledger_lineage_ref=ledger)
        if (
            support.targets != targets
            or support.report != saved["generation"]
            or len(targets) != window["support"]["candidate_count"]
        ):
            raise ValueError("saved full support differs from regenerated context")
        for row in ctx.visible.prefix().model_input()["pixel_observations"]:
            hands += len(row["hands"]["candidates"])
            measurements += len(row["hand_object_measurements"])
            pair_count += len(row["person_identity_pairs"])
        contexts[key] = (ctx, ledger)
    if set(contexts) != set(records) or not contexts:
        raise ValueError("frontend record/window coverage differs")
    for name, digest in dependencies.items():
        pinned_bytes(frontend, name, digest)
    return (
        contexts,
        dependencies,
        {
            "windows": len(contexts),
            "frames": sum(len(c.visible.pixel_observations) for c, _ in contexts.values()),
            "regional_hands_in_model_input": hands,
            "hand_object_measurements_in_model_input": measurements,
            "identity_pairs_in_model_input": pair_count,
        },
    )


def hand_control(ctx, mode):
    data = ctx.model_dump()
    for row in data["visible"]["pixel_observations"]:
        hand = row["hand_observation"]
        if mode == "without_hands":
            row["hand_observation"] = None
        elif mode == "shift_x_plus_1px":
            if hand is not None:
                for candidate in hand["candidates"]:
                    candidate["landmarks_xy_pixels"] = tuple(
                        (x + 1, y) for x, y in candidate["landmarks_xy_pixels"]
                    )
        else:
            raise ValueError("unknown controlled ablation")
    return ProposalContext.model_validate(data)


def plan_windows(contexts, window_scope):
    if window_scope not in {"first", "all"}:
        raise ValueError("unknown window scope")
    first = {}
    for key in sorted(contexts):
        source = key.split("/")[0]
        if source not in first:
            if not key.endswith("window-000000"):
                raise ValueError("fixed first window unavailable; no replacement selection")
            first[source] = key
    return (
        tuple(sorted(contexts)) if window_scope == "all" else tuple(first.values()),
        frozenset(first.values()),
    )


def checked_scores(scored, support):
    expected = sorted(content_sha256(t.model_dump(mode="json")) for t in support)
    rows = []
    for decoded in scored:
        probability = decoded.probability
        if content_sha256(decoded.target.model_dump(mode="json")) != probability.proposal_sha256:
            raise RuntimeError("score target differs from claimed probability identity")
        if (
            not math.isfinite(probability.joint_log_probability)
            or probability.joint_log_probability > 0
        ):
            raise RuntimeError("invalid proposal log probability")
        rows.append(
            {
                "target_sha256": probability.proposal_sha256,
                "joint_log_probability": probability.joint_log_probability,
            }
        )
    if [r["target_sha256"] for r in rows] != expected:
        raise RuntimeError("scorer omitted, duplicated or changed full support")
    mass = math.fsum(math.exp(r["joint_log_probability"]) for r in rows)
    if abs(mass - 1) > 1e-10:
        raise RuntimeError("incomplete normalized support")
    return rows, mass


def partition_windows(chosen, shard_index=0, shard_count=1):
    """Disjoint deterministic work allocation, independent of labels or outcomes."""
    if (
        type(shard_count) is not int
        or type(shard_index) is not int
        or not 1 <= shard_count <= 8
        or not 0 <= shard_index < shard_count
        or len(set(chosen)) != len(chosen)
    ):
        raise ValueError("invalid or duplicate fixed-window shard plan")
    groups = {}
    for key in sorted(chosen):
        groups.setdefault(key.split("/")[0], []).append(key)
    return tuple(
        key
        for source_index, source in enumerate(sorted(groups))
        for window_index, key in enumerate(groups[source])
        if (source_index + window_index) % shard_count == shard_index
    )


def run(
    frontend,
    frontend_sha256,
    training,
    output,
    arm,
    prefix_frames,
    window_scope="first",
    restore_scope="all",
    shard_index=0,
    shard_count=1,
):
    if prefix_frames not in (2, 4) or arm not in ARMS or restore_scope not in {"first", "all"}:
        raise ValueError("predeclared prefix, recovery scope and unselected architecture required")
    contexts, dependencies, features = load_frontend(frontend, frontend_sha256)
    planned, first_windows = plan_windows(contexts, window_scope)
    chosen = partition_windows(planned, shard_index, shard_count)
    summary_bytes = (training / "summary.json").read_bytes()
    training_summary = strict_json(summary_bytes)
    if (
        training_summary["track"] != "COMPONENT_FIXTURE_WEIGHTS_EXECUTION_DERIVATION"
        or training_summary["new_optimizer_steps"] != 0
        or training_summary["production_authorized"] is not False
        or training_summary["architecture_selected"] is not None
    ):
        raise ValueError("requires original fixture weights and unselected execution derivation")
    entries = training_summary["runs"]
    if len(entries) != 3 or {r["arm"] for r in entries} != set(ARMS):
        raise ValueError("requires all three original architecture arms")
    pin = next(r["checkpoint_manifest_sha256"] for r in entries if r["arm"] == arm)
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    results = []
    for key in chosen:
        source = key.split("/")[0]
        do_restore = restore_scope == "all" or key in first_windows
        started = monotonic()
        original, ledger = contexts[key]
        pixels = original.visible.pixel_observations[:prefix_frames]
        if len(pixels) != prefix_frames:
            raise ValueError("incomplete fixed prefix")
        ctx = bootstrap_pixel_context(
            pixels, cutoff=pixels[-1].arrival_time, source_snapshot_id=original.source_snapshot_id
        )
        session = RuntimeCandidateSession(training / arm, manifest_sha256=pin, seed=11)
        generated = generate_runtime_candidates(ctx, bootstrap_ledger_lineage_ref=ledger)
        support = generated.targets
        result = restored = None
        if do_restore:
            result = session.process(
                request_id="with-hands", context=ctx, bootstrap_ledger_lineage_ref=ledger
            )
            if result.support != generated:
                raise RuntimeError("sampling changed complete support")
            snapshot = session.snapshot()
            restored = RuntimeCandidateSession.restore(
                training / arm,
                manifest_sha256=pin,
                snapshot=snapshot,
                snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),
            )
            if (
                restored.snapshot() != snapshot
                or restored.process(
                    request_id="with-hands", context=ctx, bootstrap_ledger_lineage_ref=ledger
                )
                != result
            ):
                raise RuntimeError("hand-aware inference restore differs")
        blob = session.snapshot()
        controls = {
            "with_hands": ctx,
            **{n: hand_control(ctx, n) for n in ("without_hands", "shift_x_plus_1px")},
        }
        conditions = {}
        base_keys = None
        for name, controlled in controls.items():
            scored = session._engine.score_support(context=controlled, support=support)
            rows, mass = checked_scores(scored, support)
            keys = [r["target_sha256"] for r in rows]
            if base_keys is not None and keys != base_keys:
                raise RuntimeError("ablation changed target set or target identity")
            base_keys = keys
            conditions[name] = {
                "probability_mass": mass,
                "scores": rows,
                "feature_sha256": content_sha256(export_context(controlled)),
                "graph_nodes": 1
                + len(leaves(export_context(controlled)))
                + sum(len(leaves(t.model_dump(mode="json"))) for t in support),
            }
        if session.snapshot() != blob:
            raise RuntimeError("scoring consumed RNG or wrote inference history")
        repeat_equal = None
        if do_restore:
            repeat, _ = checked_scores(
                session._engine.score_support(context=ctx, support=support), support
            )
            repeat_equal = repeat == conditions["with_hands"]["scores"]
            if not repeat_equal:
                raise RuntimeError("identical input produced a different complete distribution")
            sampled = result.receipt.decoded.probability
            matches = [r for r in repeat if r["target_sha256"] == sampled.proposal_sha256]
            if (
                len(matches) != 1
                or matches[0]["joint_log_probability"] != sampled.joint_log_probability
            ):
                raise RuntimeError("sampled probability differs from full scored distribution")
            next_request = dict(
                request_id="next-draw", context=ctx, bootstrap_ledger_lineage_ref=ledger
            )
            if (
                session.process(**next_request) != restored.process(**next_request)
                or session.snapshot() != restored.snapshot()
            ):
                raise RuntimeError("restored hand-aware next draw differs")
        deltas = {}
        for name in ("without_hands", "shift_x_plus_1px"):
            deltas[name] = max(
                abs(math.exp(a["joint_log_probability"]) - math.exp(b["joint_log_probability"]))
                for a, b in zip(
                    conditions["with_hands"]["scores"], conditions[name]["scores"], strict=True
                )
            )
        detail = {
            "source": source,
            "window": key,
            "arm": arm,
            "prefix_frames": prefix_frames,
            "candidates": len(support),
            "regional_hand_candidates": sum(len(p.hand_observation.candidates) for p in pixels),
            "conditions": conditions,
            "max_probability_delta": deltas,
            "target_ids_fixed_across_controls": True,
            "restore_and_next_draw_equal": True if do_restore else None,
            "repeated_complete_distribution_equal": repeat_equal,
            "scoring_left_rng_and_requests_unchanged": True,
            "event_kinds_in_support": sorted({e.kind for t in support for e in t.candidate.events}),
            "new_optimizer_steps": 0,
            "native_publication_authorized": False,
            "ledger_authorized": False,
            "seconds": monotonic() - started,
        }
        stem = source if window_scope == "first" else key.replace("/", "__")
        (output / (stem + ".json")).write_text(json.dumps(detail, indent=2) + "\n")
        if do_restore:
            (output / (stem + ".snapshot.json")).write_bytes(session.snapshot())
        compact = {k: v for k, v in detail.items() if k != "conditions"}
        results.append(compact)
        print(json.dumps(compact), flush=True)
    for name, digest in dependencies.items():
        pinned_bytes(frontend, name, digest)
    if (training / "summary.json").read_bytes() != summary_bytes:
        raise ValueError("training summary changed during experiment")
    summary = {
        "track": "REAL_HAND_FEATURE_CONSUMPTION_WITH_FIXTURE_TRAINED_WEIGHTS",
        "arm": arm,
        "frontend_sha256": frontend_sha256,
        "training_summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        "checkpoint_manifest_sha256": pin,
        "feature_coverage": features,
        "runs": results,
        "selection": {
            "window_scope": window_scope,
            "prefix_frames": prefix_frames,
            "restore_scope": restore_scope,
            "planned_windows": list(chosen),
            "all_planned_windows": list(planned),
            "shard_index": shard_index,
            "shard_count": shard_count,
        },
        "contact_or_identity_truth_established": False,
        "independent_auditors": 0,
        "new_optimizer_steps": 0,
        "natural_semantic_publications": 0,
        "memory_writes": 0,
        "executed_actions": 0,
        "limitation": (
            "Feature and q sensitivity, not accuracy, calibrated posterior "
            "or natural control-loop benefit."
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frontend", "training", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frontend-sha256", required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--prefix-frames", type=int, choices=(2, 4), default=2)
    parser.add_argument("--window-scope", choices=("first", "all"), default="first")
    parser.add_argument("--restore-scope", choices=("first", "all"), default="all")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    run(**vars(parser.parse_args()))
