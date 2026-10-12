"""Retrospective, stdlib-only reconstruction of PR113 held-out action readouts.

No inference, tuning, or policy intervention is performed. Existing outcomes are
paired, and particle RB cells are reconstructed from ancestry and checked by hash.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from score_current_event import verify_run
from score_particle_support import verify_sampling

TOL = 1e-10
CAUSE = dict(observation=0.45, actor=0.65, identity=0.35, habit=1.0, noise=0.2, unresolved=0.05)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def norm(dist):
    total = sum(dist.values())
    return {k: v / total if total else 1 / len(dist) for k, v in dist.items()}


def pick(dist):
    return min(dist, key=lambda k: (-dist[k], k))


def tv(a, b):
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in a.keys() | b.keys()) / 2


def stats(values):
    return (
        dict(
            min=min(values),
            median=statistics.median(values),
            mean=statistics.mean(values),
            max=max(values),
        )
        if values
        else None
    )


def new_cell(width):
    return dict(
        location_alpha=[0.5] * width,
        ridge_precision=[1.0] * width,
        ridge_natural=[0.0] * width,
        information_precision=1.0,
        information_natural=0.0,
        observation_count=0,
    )


def reconstruct(run, truth):
    ledger = {"GENESIS": None}
    active = None
    head = "GENESIS"
    for record in run["native_audit"]["rgrc_ledger_records"]:
        assert record["previous_hash"] == head
        if record["operation"] in ("promote", "corrected_revision"):
            active = record["action_distribution"]
        elif record["operation"] == "retract":
            active = None
        else:
            assert record["operation"] == "quarantine"
        head = record["record_hash"]
        ledger[head] = active
    previous = {}
    result = []
    for step, (row, native) in enumerate(zip(run["actions"], run["native_evidence"], strict=True)):
        obs = native["observation"]
        locs = obs["known_location_ids"]
        base = norm(obs["base_location_distribution"])
        accum = dict.fromkeys(locs, 0.0)
        owner_mass = consumed = analytic_mass = 0.0
        particles = {}
        term_mass = [0.0] * 6
        live_actors = Counter()
        live_causes = Counter()
        components = []
        for weight, actor, receipt in zip(
            native["weights"], native["placement_actors"], native["receipts"], strict=True
        ):
            s = receipt["proposal"]["proposed_state"]
            parent_id = s["parent_particle_id"]
            if parent_id is None:
                assert step == 0
                cells, regime = {}, obs["active_regime"]
            else:
                cells, regime = previous[parent_id]
                cells = copy.deepcopy(cells)
            regime = s["regime_id"] if s["regime_id"] is not None else regime
            if (
                s["instance_association_key"] == "target_instance"
                and obs["observed_location_id"] is not None
            ):
                key = f"{actor}|{regime}"
                cell = cells.setdefault(key, new_cell(len(locs)))
                idx = locs.index(obs["observed_location_id"])
                update = max(0.05, obs["actor_posterior"].get(actor, 0.0))
                for field in ("location_alpha", "ridge_precision", "ridge_natural"):
                    cell[field][idx] += update
                cell["information_precision"] += update
                cell["information_natural"] += update
                cell["observation_count"] += 1
            assert s["statistic_state_ref"] == "full-rb:" + digest(cells), (
                step,
                s["particle_id"],
                "RB hash",
            )
            particles[s["particle_id"]] = (cells, regime)
            roles = {r["role"]: r["actor_key"] for r in s["ordered_actor_roles"]}
            handoff = "handoff_receiver" in roles
            unknown = "responsible_actor" in roles
            terms = [
                s["change_cause"] == "actor" and handoff,
                s["change_cause"] == "identity"
                and s["instance_association_key"] != "target_instance",
                s["change_cause"] == "habit" and s["regime_decision"] in ("create", "reactivate"),
                handoff and roles["handoff_receiver"] == actor,
                actor == obs["owner_actor_key"]
                and s["instance_association_key"] == "target_instance"
                and s["change_cause"] == "habit",
                actor == "unknown_actor" and s["regime_decision"] in ("create", "reactivate"),
            ]
            for i, term in enumerate(terms):
                term_mass[i] += weight * term
            if weight > 1e-8:
                live_actors[actor] += weight
            live_causes[s["change_cause"]] += weight
            if (
                actor != obs["owner_actor_key"]
                or s["instance_association_key"] != "target_instance"
            ):
                continue
            owner_mass += weight
            cell = cells.get(f"{actor}|{regime}")
            confidence = 0.0
            analytic = base
            component = base
            if cell is not None:
                d = norm(dict(zip(locs, cell["location_alpha"], strict=True)))
                ridge = norm(
                    dict(
                        zip(
                            locs,
                            [
                                n / p
                                for n, p in zip(
                                    cell["ridge_natural"], cell["ridge_precision"], strict=True
                                )
                            ],
                            strict=True,
                        )
                    )
                )
                analytic = {k: (d[k] + ridge[k]) / 2 for k in locs}
                confidence = min(1.0, cell["information_natural"] / cell["information_precision"])
                component = norm(
                    {k: confidence * analytic[k] + (1 - confidence) * base[k] for k in locs}
                )
            w = (
                weight
                * CAUSE[s["change_cause"]]
                * (0.55 if unknown else 1.0)
                * min(1.0, 0.55 + 0.08 * s["run_length"])
            )
            consumed += w
            analytic_mass += w * confidence
            for k in locs:
                accum[k] += w * component[k]
            components.append((w * confidence, analytic))
        previous = particles
        preledger = norm({k: accum[k] + max(0.0, 1 - consumed) * base[k] for k in locs})
        active = ledger[row["ledger_head"]]
        final = (
            preledger
            if active is None
            else norm({k: 0.75 * preledger[k] + 0.25 * active.get(k, 0.0) for k in locs})
        )
        error = max(abs(final[k] - row["after"][k]) for k in locs)
        assert error < TOL, (step, error, "readout reconstruction")
        assert pick(final) == row["put_back"]
        target = truth["truth_by_step"][row["step_id"]]["true_owner_habit_location"]
        ws = norm(dict(enumerate(native["weights"])))
        likelihood = dict(obs.get("location_likelihood", []))
        parent_ids = [r["proposal"]["source_particle_id"] for r in native["receipts"]]
        prior = norm(dict(enumerate(math.exp(r["prior_log_weight"]) for r in native["receipts"])))
        parent_ess = 1 / sum(v * v for v in prior.values()) if step else None
        rb_only = (
            norm({k: sum(w * d[k] for w, d in components) for k in locs})
            if analytic_mass > TOL
            else None
        )
        result.append(
            dict(
                step=step + 1,
                step_id=row["step_id"],
                new_evidence=row["location_source_id"] is not None,
                target=target,
                action=row["put_back"],
                wrong=row["put_back"] != target,
                base=base,
                after=final,
                actor=row["actor_after"],
                actor_before=row["actor_before"],
                base_action=pick(base),
                base_wrong=pick(base) != target,
                base_margin=sorted(base.values(), reverse=True)[0]
                - sorted(base.values(), reverse=True)[1],
                owner_target_mass=owner_mass,
                consumed_mass=consumed,
                analytic_mass=analytic_mass,
                direct_base_mass=(1 - analytic_mass) * (0.75 if active is not None else 1),
                ledger_active=active is not None,
                ledger_changes_action=pick(preledger) != pick(final),
                preledger_action=pick(preledger),
                readout_error=error,
                rb_only_action=pick(rb_only) if rb_only else None,
                rb_only_wrong=(pick(rb_only) != target) if rb_only else None,
                distinct_parents=len(set(parent_ids)) if step else None,
                parent_ess=parent_ess,
                low_prior_draws=sum(v < 1e-8 for v in prior.values()) if step else 0,
                ess=1 / sum(w * w for w in ws.values()),
                positive_weight_count=sum(w > 1e-8 for w in native["weights"]),
                effective_actor_count=len(live_actors),
                max_particle_weight=max(ws.values()),
                sampled_actor_count=len(set(native["placement_actors"])),
                terms=term_mass,
                causes=dict(live_causes),
                likelihood=likelihood,
                regime_change_probability=obs["regime_change_probability"],
            )
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="Extracted raw-main root")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = (
        args.repo / "docs/reviews/pc_a/particle_support_repair_2026-10-12/evidence/MANIFEST.json"
    )
    manifest = json.loads(manifest_path.read_text())["raw-main.tar.gz"]["members"]
    inputs = {}

    def read(relative):
        data = (args.raw / relative).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        assert manifest[relative] == dict(sha256=sha, size=len(data)), relative
        inputs[relative] = sha
        return json.loads(data)

    prefix = "test/stratified/"
    index = read(prefix + "index.json")
    source = read(prefix + "source.json")
    # The archived source manifest predates this added retrospective analysis tool.
    checked = 0
    for file, sha in source["files"].items():
        assert hashlib.sha256((args.repo / file).read_bytes()).hexdigest() == sha, file
        checked += 1
    runs = {}
    details = {}
    for entry in index:
        key = (entry["condition"], entry["episode"], entry["label"])
        run = read(prefix + entry["file"])
        truth = read(prefix + entry["truth"])
        visible = read(prefix + entry["visible"])
        verify_run(run, visible, truth)
        verify_sampling(run)
        runs[key] = run
        details[key] = reconstruct(run, truth)
    pairs = []
    for condition, episode, label in details:
        if label != "joint":
            continue
        joint, factor = (
            details[condition, episode, "joint"],
            details[condition, episode, "matched_factor"],
        )
        nj, nf = (
            details[condition, episode, "joint_no_new"],
            details[condition, episode, "matched_factor_no_new"],
        )
        jr, fr = runs[condition, episode, "joint"], runs[condition, episode, "matched_factor"]
        for i, (j, f, j0, f0) in enumerate(zip(joint, factor, nj, nf, strict=True)):
            assert j["step_id"] == f["step_id"] == j0["step_id"] == f0["step_id"]
            assert (
                j["base"] == f["base"] == j0["base"] == f0["base"]
                and j["likelihood"] == f["likelihood"]
            )
            assert jr["actions"][i]["search"] == fr["actions"][i]["search"]
            delta = max(abs(j["after"][k] - f["after"][k]) for k in j["after"])
            probabilities = sorted(f["after"].values(), reverse=True)
            pairs.append(
                dict(
                    condition=condition,
                    episode=episode,
                    step=j["step"],
                    step_id=j["step_id"],
                    joint=j,
                    factor=f,
                    action_tv=tv(j["after"], f["after"]),
                    actor_tv=tv(j["actor"], f["actor"]),
                    factor_margin=probabilities[0] - probabilities[1],
                    max_probability_delta=delta,
                    margin_bound_holds=2 * delta < probabilities[0] - probabilities[1],
                    joint_new_action_changed=j["action"] != j0["action"],
                    joint_new_error_delta=int(j["wrong"]) - int(j0["wrong"]),
                    factor_new_error_delta=int(f["wrong"]) - int(f0["wrong"]),
                )
            )
    summary = dict(
        paired_steps=len(pairs),
        source_files_verified=checked,
        all_reconstructed_steps=sum(map(len, details.values())),
        rb_hashes_verified=sum(map(len, details.values())) * 24,
        identical_put_actions=sum(p["joint"]["action"] == p["factor"]["action"] for p in pairs),
        equal_base_distributions_all_four_arms=True,
        equal_search_logs=True,
        base_margin=stats([p["joint"]["base_margin"] for p in pairs]),
        evidence_changes_after_first_step=sum(
            p["joint_new_action_changed"] for p in pairs if p["step"] > 1
        ),
        shared_errors=sum(p["joint"]["wrong"] and p["factor"]["wrong"] for p in pairs),
        correction_cases=[
            dict(
                condition=p["condition"],
                episode=p["episode"],
                step=p["step"],
                step_id=p["step_id"],
                base=p["joint"]["base"],
                target=p["joint"]["target"],
            )
            for p in pairs
            if p["joint_new_error_delta"] != 0
        ],
        distinct_actor_distributions=sum(p["actor_tv"] > TOL for p in pairs),
        distinct_action_distributions=sum(p["action_tv"] > TOL for p in pairs),
        actor_tv=stats([p["actor_tv"] for p in pairs]),
        action_tv=stats([p["action_tv"] for p in pairs]),
        margin_bound_holds=sum(p["margin_bound_holds"] for p in pairs),
        factor_margin=stats([p["factor_margin"] for p in pairs]),
        arms={},
    )
    for label in ("joint", "matched_factor", "joint_no_new", "matched_factor_no_new"):
        rows = [r for key, seq in details.items() if key[2] == label for r in seq]
        new = [r for r in rows if r["new_evidence"]]
        counts = dict(
            steps=len(rows),
            errors=sum(r["wrong"] for r in rows),
            base_errors=sum(r["base_wrong"] for r in rows),
            actions_match_base=sum(r["base_action"] == r["action"] for r in rows),
            one_hot_base=sum(r["base_margin"] > 1 - TOL for r in rows),
            ledger_active=sum(r["ledger_active"] for r in rows),
            ledger_changes_action=sum(r["ledger_changes_action"] for r in rows),
            native_helps_base=sum(r["base_wrong"] and not r["wrong"] for r in rows),
            native_hurts_base=sum(not r["base_wrong"] and r["wrong"] for r in rows),
            effective_single_actor=sum(r["effective_actor_count"] == 1 for r in rows),
            ess_below_two=sum(r["ess"] < 2 for r in rows),
            new_evidence=len(new),
            new_likelihood_owner_guest_equal=sum(
                abs(r["likelihood"]["owner"] - r["likelihood"]["guest"]) < TOL for r in new
            ),
            new_actor_changed=sum(tv(r["actor"], r["actor_before"]) > TOL for r in new),
            new_effective_single_actor=sum(r["effective_actor_count"] == 1 for r in new),
            new_sampled_multi_actor=sum(r["sampled_actor_count"] > 1 for r in new),
            nonzero_regime_change_steps=sum(r["regime_change_probability"] > TOL for r in rows),
            rb_only_defined=sum(r["rb_only_action"] is not None for r in rows),
            rb_only_errors=sum(r["rb_only_wrong"] is True for r in rows),
            actual_errors_on_rb_defined=sum(
                r["wrong"] for r in rows if r["rb_only_action"] is not None
            ),
            nonroot_steps=sum(r["step"] > 1 for r in rows),
            one_child_per_parent_steps=sum(r["distinct_parents"] == 24 for r in rows),
            low_prior_draws=sum(r["low_prior_draws"] for r in rows),
            parent_ess=stats([r["parent_ess"] for r in rows if r["parent_ess"] is not None]),
            rb_only_fixes_actual=sum(r["wrong"] and r["rb_only_wrong"] is False for r in rows),
            rb_only_breaks_actual=sum(not r["wrong"] and r["rb_only_wrong"] is True for r in rows),
        )
        for field in (
            "ess",
            "owner_target_mass",
            "consumed_mass",
            "analytic_mass",
            "direct_base_mass",
            "max_particle_weight",
            "positive_weight_count",
            "readout_error",
        ):
            counts[field] = stats([r[field] for r in rows])
        counts["mean_interaction_term_mass"] = [
            statistics.mean(r["terms"][i] for r in rows) for i in range(6)
        ]
        counts["mean_cause_mass"] = {
            c: statistics.mean(r["causes"].get(c, 0) for r in rows) for c in CAUSE
        }
        summary["arms"][label] = counts
    args.output.mkdir(parents=True, exist_ok=True)
    for name, obj in [
        ("summary", summary),
        ("paired_steps", pairs),
        (
            "inputs",
            dict(
                files=inputs,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                source_code_sha=source["code_sha"],
            ),
        ),
    ]:
        (args.output / (name + ".json")).write_text(
            json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
