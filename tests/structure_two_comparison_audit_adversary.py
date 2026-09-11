"""Complete attacker-controlled bundles; no validation reference or replay is mocked."""

from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path

from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit
from cpswm.system.reproducibility import content_sha256

CASES = (
    "r1_commits_999",
    "fast_slow_memory",
    "actions_scores_groups",
    "learned_joint",
    "truth_and_labels",
    "support_and_input",
    "step_missing",
    "step_duplicate",
    "step_reorder",
    "step_replacement",
    "episode_missing",
    "episode_duplicate",
    "episode_reorder",
    "data_hash",
    "config_selection",
    "seed_split",
    "source_binding",
    "source_rebound_state",
    "source_version",
    "attribution_only",
    "forged_verification_receipt",
)


def load_analyzer(root: Path):
    spec = importlib.util.spec_from_file_location(
        "w2_attribution_attack_target",
        root / "apps/evaluation_runner/summarize_structure_two_comparison_audit.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def change_action(row, arm):
    values = row["arms"][arm]
    support = row["support"]
    target = next(v for v in support if v != values["put_back"])
    values["habit"] = {v: float(v == target) for v in support}
    values["put_back"] = target
    values["put_back_error"] = int(target != row["truth"]["true_owner_habit_location"])
    row["category"] = audit.category(
        row["arms"][audit.P5]["put_back_error"], row["arms"][audit.AMG]["put_back_error"]
    )


def build_attack(source: Path, target: Path, case: str, root: Path):
    snapshot = audit.load_bundle(source)
    payload, rows = copy.deepcopy(snapshot.payload), copy.deepcopy(snapshot.rows)
    # Use real episode boundaries, not a hardcoded number of steps.
    first_id = rows[0]["episode_id"]
    first_episode = [r for r in rows if r["episode_id"] == first_id]
    remainder = [r for r in rows if r["episode_id"] != first_id]
    if case in {"r1_commits_999", "source_rebound_state", "forged_verification_receipt"}:
        for row in rows:
            row["raw_state"]["p5_readouts"]["state_counts"]["_committed_events"] = 999
        if case == "source_rebound_state":
            payload["source_bindings"] = audit.source_bindings(root)
    elif case == "fast_slow_memory":
        for row in rows:
            raw = row["raw_state"]["p5_readouts"]
            raw["state_counts"] = dict.fromkeys(raw["state_counts"], 999)
            change_action(row, audit.P5)
            for name in ("fast", "surviving", "regime", "pooled"):
                raw[name] = copy.deepcopy(row["arms"][audit.P5]["habit"])
                alternative = row["alternative_readouts_development_only"][name]
                alternative["put_back"] = row["arms"][audit.P5]["put_back"]
                alternative["put_back_error"] = row["arms"][audit.P5]["put_back_error"]
    elif case == "actions_scores_groups":
        for row in rows:
            change_action(row, audit.P5)
            change_action(row, audit.AMG)
            row["tags"]["phase"] = "forged_phase"
    elif case == "learned_joint":
        for row in rows:
            row["raw_state"]["learned_joint"] = [1.0] + [0.0] * 8
    elif case == "truth_and_labels":
        for row in rows:
            row["truth"]["true_owner_habit_location"] = row["arms"][audit.P5]["put_back"]
            row["derived_cause_event_labels"] = [0, 0]
            for arm in audit.ARMS:
                row["arms"][arm]["put_back_error"] = int(
                    row["arms"][arm]["put_back"] != row["truth"]["true_owner_habit_location"]
                )
            row["category"] = audit.category(
                row["arms"][audit.P5]["put_back_error"], row["arms"][audit.AMG]["put_back_error"]
            )
    elif case == "support_and_input":
        for row in rows:
            row["support"].reverse()
            row["future_support_count"] = 0
    elif case == "step_missing":
        rows.pop()
    elif case == "step_duplicate":
        rows.append(copy.deepcopy(rows[-1]))
    elif case == "step_reorder":
        rows[-1], rows[-2] = rows[-2], rows[-1]
    elif case == "step_replacement":
        rows[-1] = copy.deepcopy(rows[-2])
    elif case == "episode_missing":
        rows = remainder
    elif case == "episode_duplicate":
        rows.extend(copy.deepcopy(first_episode))
    elif case == "episode_reorder":
        rows = remainder + first_episode
    elif case == "data_hash":
        # Non-cold input was never checked by the old standalone analyzer.
        rows[-1]["visible_step_sha256"] = "f" * 64
        rows[-1]["packet_sha256"] = "e" * 64
        rows[-1]["actor_posterior"] = {"unknown_actor": 1.0}
    elif case == "config_selection":
        payload["selection"]["selected_amg_parameter"] = 0.33
    elif case == "seed_split":
        payload["split_episode_ids"]["test"] = payload["split_episode_ids"]["train"]
    elif case == "source_binding":
        payload["source_bindings"][str(audit.DATA_CONFIG)] = "f" * 64
    elif case == "source_version":
        payload["verification_schema_version"] = 999
    elif case != "attribution_only":
        raise ValueError(case)
    payload["summary"] = audit.aggregate(rows)
    payload["semantic_steps_sha256"] = content_sha256(audit._semantic_rows(rows))
    if "content_sha256" in payload["selection"]:
        payload["selection"]["content_sha256"] = content_sha256(
            {k: v for k, v in payload["selection"].items() if k != "content_sha256"}
        )
    target.mkdir()
    (target / "audit.json").write_text(json.dumps(payload))
    (target / "steps.jsonl.gz").write_bytes(
        gzip.compress(("\n".join(json.dumps(row) for row in rows) + "\n").encode(), mtime=0)
    )
    analyzer = load_analyzer(root)
    attribution = analyzer.analyze(target, root)
    if case == "attribution_only":
        attribution["p5_state_count_histograms"]["_committed_events"] = {"999": len(rows)}
    (target / "attribution.json").write_text(json.dumps(attribution))
    if case == "forged_verification_receipt":
        (target / "verified.json").write_text(
            json.dumps(
                {
                    "verified": True,
                    "source_bindings": payload["source_bindings"],
                    "semantic_steps_sha256": payload["semantic_steps_sha256"],
                }
            )
        )
    return {
        "case": case,
        "steps": len(rows),
        "hashes_recomputed": True,
        "attribution_regenerated": case != "attribution_only",
        "semantic_steps_sha256": payload["semantic_steps_sha256"],
    }
