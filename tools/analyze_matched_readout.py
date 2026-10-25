"""Source-bound PR123 replay and fixed-state readout diagnosis, without retuning."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import tarfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/reviews/pc_a/matched_value_2026-10-24"
PROTOCOL = ROOT / "docs/reviews/pc_a/matched_readout_2026-10-25/PROTOCOL.md"
CAUSE = dict(observation=0.45, actor=0.65, identity=0.35, habit=1.0, noise=0.2, unresolved=0.05)
TOL = 1e-10


def norm(values):
    values = dict(sorted(values.items()))
    if not values or any(not math.isfinite(v) or v < 0 for v in values.values()):
        raise ValueError("invalid nonnegative finite masses")
    total = sum(values.values())
    return {k: v / total if total else 1 / len(values) for k, v in values.items()}


def pick(values):
    return min(values, key=lambda k: (-values[k], k))


def margin(values):
    ordered = sorted(values.values(), reverse=True)
    return ordered[0] - ordered[1]


def stats(values):
    return (
        {
            "min": min(values),
            "median": statistics.median(values),
            "mean": statistics.mean(values),
            "max": max(values),
        }
        if values
        else None
    )


def fixed_mass_bound(base, ledger, mass, winner):
    """Worst-case argmax margin when only a simplex of fixed mass can vary."""
    if not 0 <= mass <= 1 or winner not in base:
        raise ValueError("invalid bound inputs")
    for distribution in (base,) if ledger is None else (base, ledger):
        if (
            any(not math.isfinite(v) or v < 0 for v in distribution.values())
            or abs(sum(distribution.values()) - 1) > TOL
        ):
            raise ValueError("bound requires probability distributions")
    w = 1.0 if ledger is None else 0.75
    fixed = {k: w * (1 - mass) * base[k] + (1 - w) * (ledger or {}).get(k, 0) for k in base}
    residual = w * mass
    lower = {k: fixed[winner] - fixed[k] - residual for k in base if k != winner}
    return {
        "winner": winner,
        "fixed": fixed,
        "free_mass": residual,
        "lower_gaps": lower,
        "guaranteed_same_winner": min(lower.values()) > TOL,
    }


def decompose(raw):
    """Independent scalar reconstruction; never calls production readout methods."""
    base = norm(raw["base"])
    locations = raw["locations"]
    if len(locations) != len(set(locations)) or set(locations) != set(base):
        raise ValueError("RB location order/support mismatch")
    if (
        any(not math.isfinite(v) or v < 0 for v in raw["actual"].values())
        or abs(sum(raw["actual"].values()) - 1) > TOL
    ):
        raise ValueError("invalid actual distribution")
    analytic_sum = dict.fromkeys(base, 0.0)
    owner_mass = consumed = analytic_mass = gated_owner_history = 0.0
    weights = []
    live_actors = set()
    for particle in raw["particles"]:
        weight = particle["weight"]
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("invalid particle weight")
        weights.append(weight)
        if weight > 1e-8:
            live_actors.add(particle["actor"])
        cell = particle["owner_cell"]
        admitted = particle["actor"] == raw["owner"] and particle["instance"] == "target_instance"
        if not admitted:
            if cell is not None and cell["observation_count"]:
                gated_owner_history += weight
            continue
        owner_mass += weight
        effective = (
            weight
            * CAUSE[particle["cause"]]
            * (0.55 if particle["unknown_mechanism"] else 1)
            * min(1, 0.55 + 0.08 * particle["run_length"])
        )
        consumed += effective
        if cell is None:
            continue
        dirichlet = norm(dict(zip(locations, cell["location_alpha"], strict=True)))
        ridge = norm(
            dict(
                zip(
                    locations,
                    [
                        n / p
                        for n, p in zip(cell["ridge_natural"], cell["ridge_precision"], strict=True)
                    ],
                    strict=True,
                )
            )
        )
        confidence = min(1, cell["information_natural"] / cell["information_precision"])
        analytic_mass += effective * confidence
        for k in locations:
            analytic_sum[k] += effective * confidence * (dirichlet[k] + ridge[k]) / 2
    preledger = norm({k: (1 - analytic_mass) * base[k] + analytic_sum[k] for k in base})
    ledger = raw["ledger"]
    final = (
        preledger
        if ledger is None
        else norm({k: 0.75 * preledger[k] + 0.25 * ledger.get(k, 0) for k in base})
    )
    if set(final) != set(raw["actual"]):
        raise ValueError("readout support mismatch")
    error = max(abs(final[k] - raw["actual"][k]) for k in final)
    if error > TOL or not math.isfinite(error):
        raise ValueError("independent readout reconstruction mismatch")
    total = sum(weights)
    ess = total * total / sum(w * w for w in weights)
    return {
        "base": base,
        "preledger": preledger,
        "final": final,
        "base_action": pick(base),
        "action": pick(final),
        "base_margin": margin(base),
        "owner_target_mass": owner_mass,
        "consumed_mass": consumed,
        "analytic_mass": analytic_mass,
        "direct_base_mass": (1 - analytic_mass) * (0.75 if ledger is not None else 1),
        "gated_existing_owner_history_mass": gated_owner_history,
        "ledger_active": ledger is not None,
        "ledger_changes_action": pick(preledger) != pick(final),
        "ess": ess,
        "effective_actor_count": len(live_actors),
        "reconstruction_error": error,
        "fixed_mass_bound": fixed_mass_bound(base, ledger, analytic_mass, pick(final)),
    }


def capture(state):
    from cpswm.contracts import EventMechanism

    runtime = state.runtime
    observation = runtime._last_observation
    particles = []
    for p in runtime.particles:
        world = p.world
        cell = world.rb_cells.get((observation.owner_actor_key, world.active_regime))
        particles.append(
            {
                "weight": p.posterior_probability,
                "actor": world.placement_actor,
                "instance": world.instance_association_history[-1],
                "cause": world.change_cause_history[-1].value,
                "unknown_mechanism": world.event_chain[-1].startswith(
                    EventMechanism.UNKNOWN_MECHANISM.value
                ),
                "run_length": world.typed_state.run_length,
                "owner_cell": None if cell is None else asdict(cell),
            }
        )
    ledger = runtime.rgrc_ledger.active_distribution
    if any(op.value == "rgrc" for op in runtime.neutralized_operators):
        ledger = None
    receipts = runtime.importance_revision_receipts[-1]
    parents = [r.proposal.source_particle_id for r in receipts]
    priors = [math.exp(r.prior_log_weight) for r in receipts]
    prior_sum = sum(priors)
    return {
        "owner": observation.owner_actor_key,
        "locations": list(map(str, observation.known_location_ids)),
        "base": {str(k): v for k, v in observation.base_location_distribution.items()},
        "ledger": None if ledger is None else {str(k): v for k, v in ledger.items()},
        "actual": {str(k): v for k, v in runtime.action_distribution().items()},
        "particles": particles,
        "distinct_parents": len(set(parents)) if runtime.step_index > 1 else None,
        "low_prior_draws": sum(w / prior_sum < 1e-8 for w in priors)
        if runtime.step_index > 1
        else 0,
    }


def read_archive():
    manifest = json.loads((ARCHIVE / "MANIFEST.json").read_text())["primary"]
    path = ARCHIVE / "evidence/primary.tar.gz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("PR123 archive hash mismatch")
    result = {}
    with tarfile.open(path, "r:gz") as archive:
        if set(archive.getnames()) != set(manifest["members"]):
            raise ValueError("archive member inventory mismatch")
        for member in archive.getmembers():
            data = archive.extractfile(member).read()
            expected = manifest["members"][member.name]
            if (
                len(data) != expected["bytes"]
                or hashlib.sha256(data).hexdigest() != expected["sha256"]
            ):
                raise ValueError("PR123 member hash mismatch")
            result[member.name] = json.loads(data)
    # All inherited production, input generator and matched runner bytes must match.
    for name, expected in result["manifest.json"]["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("PR123 bound source differs: " + name)
    return result


def paired_gap(joint, ablation):
    a, b = joint["final"], ablation["final"]
    delta = max(abs(a[k] - b[k]) for k in a)
    return {
        "tv": sum(abs(a[k] - b[k]) for k in a) / 2,
        "linf": delta,
        "ablation_margin": margin(b),
        "strict_margin_certificate": 2 * delta < margin(b),
        "same_put_back": pick(a) == pick(b),
    }


def observed_locations(step):
    """Public prefix includes both endpoint observations, not just after frames."""
    return {
        str(observation.detected_location_id)
        for observation in (step.before, step.after)
        if observation is not None and observation.detected_location_id is not None
    }


def summarize(points):
    result = {"points": len(points), "arms": {}, "errors": []}
    for method in ("native_joint", "native_six_potential_ablation"):
        rows = [x["analysis"][method] for x in points]
        result["arms"][method] = {
            "errors": sum(
                r["action"] != x["truth_owner_habit"] for x, r in zip(points, rows, strict=True)
            ),
            "same_base_action": sum(r["action"] == r["base_action"] for r in rows),
            "fixed_mass_cannot_flip": sum(
                r["fixed_mass_bound"]["guaranteed_same_winner"] for r in rows
            ),
            "ess_below_2": sum(r["ess"] < 2 for r in rows),
            "ledger_changes_action": sum(r["ledger_changes_action"] for r in rows),
            **{
                key: stats([r[key] for r in rows])
                for key in (
                    "owner_target_mass",
                    "analytic_mass",
                    "direct_base_mass",
                    "base_margin",
                    "ess",
                    "gated_existing_owner_history_mass",
                )
            },
            "one_descendant_per_parent": sum(
                x["raw"][method]["distinct_parents"] == 24 for x in points
            ),
            "low_prior_draws": sum(x["raw"][method]["low_prior_draws"] for x in points),
        }
    result["paired"] = {
        "changed_distributions": sum(x["pair"]["tv"] > 1e-12 for x in points),
        "same_actions": sum(x["pair"]["same_put_back"] for x in points),
        "strict_margin_certificates": sum(x["pair"]["strict_margin_certificate"] for x in points),
    }
    for point in points:
        if point["analysis"]["native_joint"]["action"] != point["truth_owner_habit"]:
            result["errors"].append(
                {
                    k: point[k]
                    for k in (
                        "condition",
                        "episode_id",
                        "step",
                        "observed_location",
                        "public_owner_probability",
                        "truth_owner_habit",
                        "steps_since_habit_change",
                        "latest_owner_location",
                        "steps_since_latest_owner",
                        "truth_location_seen_in_public_prefix",
                    )
                }
            )
    return result


def bound_sources():
    from run_matched_value import sources

    return {
        **sources(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        str(PROTOCOL.relative_to(ROOT)): hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
    }


def collect(output, quick=False):
    from run_matched_value import NATIVE, action_payload, dataset_for, make_state, save, state_audit

    from cpswm.contracts import ProjectTwoDatasetSplit as Split
    from cpswm.system.reproducibility import _canonical_value, content_sha256

    source = bound_sources()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status.strip() and not quick:
        raise ValueError("formal diagnosis requires clean source")
    original = read_archive()
    output.mkdir(parents=True, exist_ok=False)
    points = []
    for condition in ("complete32", "sparse32", "long64"):
        dataset = dataset_for(condition)
        parameter = original[condition + "/selection.json"]["methods"]["latest_owner"]
        parameter = parameter["trials"][parameter["selected_index"]]["parameter"]
        for episode in dataset.visible_episodes(Split.TEST):
            archived = original[f"{condition}/evaluation-{episode.episode_id}.json"]
            if content_sha256(episode) != archived["episode_sha256"]:
                raise ValueError("original public episode mismatch")
            states = {name: make_state(episode, name) for name in NATIVE}
            simple = make_state(episode, "latest_owner", parameter)
            last_owner_step = None
            previous_habit = None
            habit_change_step = 0
            seen = set()
            for index, step in enumerate(episode.steps[:4] if quick else episode.steps):
                simple.observe(step.model_copy(deep=True))
                admitted = simple.records[step.step_id]
                if admitted is not None and admitted[1] >= parameter:
                    last_owner_step = index
                raw, analysis = {}, {}
                for method, state in states.items():
                    state.observe(step.model_copy(deep=True))
                    action = action_payload(state.predict(), episode.known_location_ids)
                    expected = archived["rows"][method][index]
                    if (
                        action != expected["action"]
                        or content_sha256(step) != expected["input_sha256"]
                    ):
                        raise ValueError("PR123 action/input mismatch")
                    before = state_audit(state)
                    raw[method] = capture(state)
                    analysis[method] = decompose(raw[method])
                    if state_audit(state) != before:
                        raise ValueError("diagnostic mutated native state")
                    if raw[method]["actual"] != expected["habit_distribution"]:
                        raise ValueError("PR123 posterior mismatch")
                    state.feedback(step.model_copy(deep=True))
                    if _canonical_value(state_audit(state)) != expected["after_feedback"]:
                        raise ValueError("PR123 feedback state mismatch")
                # Diagnostics/actions fixed before evaluator-only outcomes are read.
                truth = dataset.truth_for(episode.episode_id).truth_by_step[step.step_id]
                habit = str(truth.true_owner_habit_location)
                if habit != previous_habit:
                    previous_habit = habit
                    habit_change_step = index
                location = None if step.after is None else step.after.detected_location_id
                seen.update(observed_locations(step))
                points.append(
                    {
                        "condition": condition,
                        "episode_id": str(episode.episode_id),
                        "step": index + 1,
                        "raw": raw,
                        "analysis": analysis,
                        "pair": paired_gap(
                            analysis["native_joint"], analysis["native_six_potential_ablation"]
                        ),
                        "truth_owner_habit": habit,
                        "observed_location": None if location is None else str(location),
                        "public_owner_probability": None
                        if step.actor_evidence is None
                        else step.actor_evidence.actor_posterior.get(episode.owner_actor_key, 0),
                        "steps_since_habit_change": index - habit_change_step,
                        "latest_owner_location": None
                        if simple.latest_owner is None
                        else str(simple.latest_owner),
                        "steps_since_latest_owner": None
                        if last_owner_step is None
                        else index - last_owner_step,
                        "truth_location_seen_in_public_prefix": habit in seen,
                    }
                )
            print(condition, episode.episode_id, "replayed", flush=True)
            if quick:
                break
    if bound_sources() != source:
        raise ValueError("source changed during diagnosis")
    save(output / "points.json", points)
    save(output / "summary.json", summarize(points))
    save(
        output / "manifest.json",
        {
            "source_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "files": source,
            "git_status": status,
            "quick": quick,
            "original_run_source": original["manifest.json"]["source_sha"],
            "source_unchanged": True,
            "scientific_acceptance": False,
            "artifact_sha256": {
                name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                for name in ("points.json", "summary.json")
            },
        },
    )


def verify(output):
    from run_matched_value import save

    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["files"] != bound_sources() or not manifest["source_unchanged"]:
        raise ValueError("diagnostic source mismatch")
    for name, expected in manifest["artifact_sha256"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != expected:
            raise ValueError("diagnostic artifact hash mismatch")
    points = json.loads((output / "points.json").read_text())
    for point in points:
        for method, raw in point["raw"].items():
            if decompose(raw) != point["analysis"][method]:
                raise ValueError("stored decomposition differs from raw")
        expected = paired_gap(
            point["analysis"]["native_joint"], point["analysis"]["native_six_potential_ablation"]
        )
        if expected != point["pair"]:
            raise ValueError("stored paired bound mismatch")
    if summarize(points) != json.loads((output / "summary.json").read_text()):
        raise ValueError("stored summary mismatch")
    save(
        output / "verification.json",
        {
            "status": "RAW_READOUT_RECONSTRUCTION_MATCH",
            "points": len(points),
            "scope": (
                "independent scalar formula, same stored state; "
                "not independent posterior correctness"
            ),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
    else:
        collect(args.output, args.quick)
