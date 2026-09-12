"""Inspect non-noop conclusion mutations in archived *actual* R6 attacks.

Reads immutable Git objects and a historical reference; never runs a comparison,
creates an attack, or issues a current-source/scientific acceptance certificate.
The same selector checks can precede future real-CLI attacks after source freeze.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

REVIEW = "97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274"
PREFIX = "docs/reviews/pc_a/round6_2026-09-12/"
# Deliberately select conclusion dependencies, not merely a recomputed hash.
SELECTORS = {
    "r1_commits_999": "steps.*.raw_state.p5_readouts.state_counts._committed_events",
    "fast_slow_memory": "steps.*.raw_state.p5_readouts.fast",
    "actions_scores_groups": "steps.*.arms",
    "learned_joint": "steps.*.raw_state.learned_joint",
    "truth_and_labels": "steps.*.truth",
    "support_and_input": "steps.*.support",
    "step_missing": "steps",
    "step_duplicate": "steps",
    "step_reorder": "steps.*.step_id",
    "step_replacement": "steps.*.step_id",
    "episode_missing": "steps.*.episode_id",
    "episode_duplicate": "steps.*.episode_id",
    "episode_reorder": "steps.*.episode_id",
    "data_hash": "steps.*.actor_posterior",
    "config_selection": "audit.selection.selected_amg_parameter",
    "seed_split": "audit.split_episode_ids.test",
    "source_binding": "audit.source_bindings",
    "source_rebound_state": "steps.*.raw_state.p5_readouts.state_counts._committed_events",
    "source_version": "audit.verification_schema_version",
    "attribution_only": "attribution.p5_state_count_histograms._committed_events",
    "forged_verification_receipt": "steps.*.raw_state.p5_readouts.state_counts._committed_events",
    "future_support": "steps.*.future_support_count",
    "missing_owner": "steps.*.fairness_step.amg_owner_missing",
    "costs": "steps.*.fairness_step.costs",
    "selection_access": "audit.fairness_execution.selection.access_events",
    "consumer_features": "audit.fairness_execution.consumer_probe.returns",
    "fairness_claim": "audit.fairness.comparison_fairness",
    "nonempty_commit": "audit.dynamic_development.scenes.0.max_direct_p5_committed",
    "action_consequence": "audit.dynamic_development.execution",
    "corrected_memory": (
        "audit.dynamic_development.production_boundary_probes.correct.new_committed"
    ),
    "contract_freeze": "audit.comparison_contract.scientific_fairness_established",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def select(value, path):
    if not path:
        return value
    head, *tail = path.split(".")
    rest = ".".join(tail)
    if head == "*":
        if not isinstance(value, list):
            raise ValueError("selector wildcard requires a list")
        return [select(item, rest) for item in value]
    return select(value[int(head)] if isinstance(value, list) else value[head], rest)


def first_delta(before, after, path):
    """Retain an inspectable changed value, not just two different hashes."""
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return {"path": path + ".length", "before": len(before), "after": len(after)}
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            if digest(left) != digest(right):
                return first_delta(left, right, f"{path}[{index}]")
    if isinstance(before, dict) and isinstance(after, dict):
        if set(before) != set(after):
            return {"path": path + ".keys", "before": sorted(before), "after": sorted(after)}
        for key in sorted(before):
            if digest(before[key]) != digest(after[key]):
                return first_delta(before[key], after[key], path + "." + key)
    return {"path": path, "before": before, "after": after}


def mutation_witness(reference, attack, case):
    """No-op/unknown/missing dependencies fail; not an authenticity verifier."""
    selector = SELECTORS[case]
    before, after = select(reference, selector), select(attack, selector)
    if digest(before) == digest(after):
        raise ValueError(f"NO_CONCLUSION_MUTATION: {case}: {selector}")
    same_source = reference["audit"]["source_bindings"] == attack["audit"]["source_bindings"]
    if case != "source_binding" and not same_source:
        raise ValueError(f"STALE_SOURCE_CANNOT_PROVE_SEMANTIC_REJECTION: {case}")
    return {
        "case": case,
        "selector": selector,
        "before_sha256": digest(before),
        "after_sha256": digest(after),
        "first_changed_value": first_delta(before, after, selector),
        "reference_source_bindings_unchanged": same_source,
        "kind": "source_metadata_attack" if case == "source_binding" else "conclusion_dependency",
    }


def check_cli_batch(output, reference, attacks):
    """Check captured real-CLI batch semantics, never certify supplied JSON alone."""
    if output.get("fresh_replay_performed") is not True:
        raise ValueError("REAL_REPLAY_REQUIRED")
    rows = output["results"]
    expected = {str(reference), *map(str, attacks.values())}
    if len(rows) != len(expected) or {r["bundle"] for r in rows} != expected:
        raise ValueError("MISSING_DUPLICATE_OR_FOREIGN_PACKAGE")
    by_path = {r["bundle"]: r for r in rows}
    if by_path[str(reference)]["status"] != "CURRENT_SOURCE_FRESH_REPLAY_MATCH":
        raise ValueError("LEGAL_REFERENCE_MUST_PASS")
    for case, path in attacks.items():
        row = by_path[str(path)]
        if row["status"] != "REJECTED" or not row.get("error"):
            raise ValueError(f"ATTACK_NOT_REJECTED: {case}")
        if case != "source_binding" and "SOURCE_BINDING_MISMATCH" in row["error"]:
            raise ValueError(f"STALE_SOURCE_CANNOT_PROVE_SEMANTIC_REJECTION: {case}")
    return len(attacks)


def bundle(read):
    return {
        "audit": json.loads(read("audit.json")),
        "steps": [
            json.loads(line) for line in gzip.decompress(read("steps.jsonl.gz")).splitlines()
        ],
        "attribution": json.loads(read("attribution.json")),
    }


def git_blob(repo, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", REVIEW + ":" + PREFIX + path])


def inspect(repo, reference_path):
    reference = bundle(lambda name: (reference_path / name).read_bytes())
    archive_bytes = git_blob(repo, "w2_actual_attack_packages.tar.gz")
    tree = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", REVIEW, PREFIX + "w2_evidence"],
        text=True,
    ).splitlines()
    matrices = [
        p
        for p in tree
        if p.endswith(("/adversarial_matrix.json", "/fairness_forgery_matrix.json", "/matrix.json"))
    ]
    records = {}
    for path in matrices:
        data = json.loads(git_blob(repo, path.removeprefix(PREFIX)))
        rows = data["result"]["results"]
        attacks = {Path(r["bundle"]).name: r["bundle"] for r in rows[1:]}
        check_cli_batch(data["result"], rows[0]["bundle"], attacks)
        records.update({Path(r["bundle"]).name: {"row": r, "matrix": path} for r in rows[1:]})
    witnesses = []
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        packages = [
            m.name.rsplit("/", 1)[0] for m in archive.getmembers() if m.name.endswith("/audit.json")
        ]
        if len(packages) != len(SELECTORS) or {Path(p).name for p in packages} != set(SELECTORS):
            raise ValueError("ARCHIVE_CASE_COVERAGE_MISMATCH")
        for package in packages:

            def read(name, package=package):
                stream = archive.extractfile(package + "/" + name)
                if stream is None:
                    raise ValueError("ARCHIVE_MEMBER_NOT_REGULAR")
                return stream.read()

            case = Path(package).name
            attack = bundle(read)
            witness = mutation_witness(reference, attack, case)
            witness.update(archive_member=package, historical_cli=records[case])
            witnesses.append(witness)
    return {
        "scope": "archive inspection; historical CLI results read, NOT rerun this round",
        "review_sha": REVIEW,
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "reference": str(reference_path),
        "reference_files_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in reference_path.iterdir()
            if p.is_file()
        },
        "nonempty_mutations": len(witnesses),
        "records": witnesses,
        "new_comparison_generated": False,
        "current_unified_acceptance": "BLOCKED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--historical-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.repository, args.historical_reference)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"scope": result["scope"], "nonempty_mutations": len(result["records"])}))


if __name__ == "__main__":
    main()
