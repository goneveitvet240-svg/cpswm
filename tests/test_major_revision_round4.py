"""Regression tests for the round-4 Major Revision findings.

The three P0s share one shape, which is worth naming because it is the shape
that let every earlier round of fixes still be defeated:

    every field was written by the candidate and checked only against other
    fields the candidate also wrote.

Internal consistency is not authenticity.  P0-1 closes it for the governance
log, P0-2 for run receipts, and P0-3 for the gate topology that decides what
a receipt is allowed to unlock.  Each test below performs the attack rather
than asserting that a guard is present in the source.
"""

from __future__ import annotations

import json
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from ledger_evidence_fixtures import (
    TEST_AUTHORITY,
    build_payload,
    build_receipt,
    make_git_repo,
    make_source_tree,
    write_evidence,
)
from pydantic import ValidationError

from cpswm.contracts import (
    BaseRecordMetadata,
    InputWatermark,
    SourceType,
    ValidTimeInterval,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.system.attestation import (
    DOMAIN_CAPABILITY_GRANT,
    DOMAIN_ORACLE_DECISION,
    AttestationAuthority,
    AttestationError,
)
from cpswm.system.privacy_governance import (
    CapabilityGrant,
    GovernanceConflictError,
    HouseholdGovernance,
    Operation,
    OracleAccessRequest,
    ResourceKind,
)
from cpswm.system.progress_ledger import Maturity, ProgressLedger, validate_ledger
from cpswm.system.progress_ledger.contracts import EvidenceKind

START = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "src" / "cpswm" / "system" / "progress_ledger" / "progress_ledger.json"

OTHER_AUTHORITY = AttestationAuthority(key_id="cpswm-governance-authority", secret=b"\x5a" * 32)


def _ledger_data() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _metadata(household):
    return BaseRecordMetadata(
        schema_name="cpswm.privacy.Record",
        schema_version="0.1.0",
        household_id=household,
        session_id=uuid4(),
        recorded_time=START,
        source_type=SourceType.MODEL,
        source_id="round4",
    )


def _grant(household) -> CapabilityGrant:
    return CapabilityGrant(
        metadata=_metadata(household),
        subject="evaluator.benchmark",
        household_id=household,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        valid_time=ValidTimeInterval(start=START, end=START + timedelta(minutes=60)),
        issuer="totally-legitimate-authority",
    )


def _request(household, seq: int = 1) -> OracleAccessRequest:
    return OracleAccessRequest(
        metadata=_metadata(household),
        caller="evaluator.benchmark",
        household_id=household,
        resource=ResourceKind.GT,
        evaluation_only=True,
        purpose="evaluation_only",
        input_watermark=InputWatermark(
            global_commit_seq=seq, transaction_id=uuid4(), recorded_at=START
        ),
    )


# ==========================================================================
# P0-1  oracle log trustworthiness (Scheme A: authority MAC)
# ==========================================================================


def _forged_chain_log() -> AppendOnlyTransactionLog:
    """A grant -> request -> decision chain written by code with no key."""

    household = uuid4()
    log = AppendOnlyTransactionLog()
    attacker = HouseholdGovernance(log)
    assert attacker.attested is False
    attacker.issue_grant(_grant(household))
    attacker.decide_oracle_access(_request(household), decided_by="attacker", decided_time=START)
    return log


def test_the_forged_chain_that_defeated_round_three_still_restores_without_an_authority():
    """The baseline the fix is measured against, kept explicit.

    Order, fingerprints and field agreement are all satisfied, because the
    attacker produced them.  Nothing in the previous design could tell this
    log from an honest one.
    """

    victim = HouseholdGovernance(_forged_chain_log())
    victim.restore()

    assert len(victim.active_grants) == 1
    assert victim.attested is False


def test_an_authority_holding_service_refuses_the_forged_chain():
    victim = HouseholdGovernance(_forged_chain_log(), authority=TEST_AUTHORITY)

    with pytest.raises(GovernanceConflictError, match="carries no attestation"):
        victim.restore()


def test_a_chain_signed_with_the_wrong_key_is_refused():
    """Same key_id, different secret: the MAC, not the label, is what counts."""

    household = uuid4()
    log = AppendOnlyTransactionLog()
    impostor = HouseholdGovernance(log, authority=OTHER_AUTHORITY)
    impostor.issue_grant(_grant(household))
    impostor.decide_oracle_access(_request(household), decided_by="impostor", decided_time=START)

    victim = HouseholdGovernance(log, authority=TEST_AUTHORITY)

    with pytest.raises(GovernanceConflictError, match="MAC does not match"):
        victim.restore()


def test_an_honest_chain_restores_and_its_receipt_verifies():
    """The positive case: the fix must not simply refuse everything."""

    household = uuid4()
    log = AppendOnlyTransactionLog()
    governance = HouseholdGovernance(log, authority=TEST_AUTHORITY)
    governance.issue_grant(_grant(household))
    decision = governance.decide_oracle_access(
        _request(household), decided_by="governance", decided_time=START
    )

    reborn = HouseholdGovernance(log, authority=TEST_AUTHORITY)
    reborn.restore()

    assert reborn.attested is True
    assert len(reborn.active_grants) == 1
    assert reborn.verify_oracle_receipt(decision) is True


def test_altering_one_field_of_an_attested_decision_breaks_its_receipt():
    household = uuid4()
    log = AppendOnlyTransactionLog()
    governance = HouseholdGovernance(log, authority=TEST_AUTHORITY)
    governance.issue_grant(_grant(household))
    decision = governance.decide_oracle_access(
        _request(household), decided_by="governance", decided_time=START
    )

    tampered = decision.model_copy(update={"caller": "ordinary.module"})

    assert governance.verify_oracle_receipt(tampered) is False


def test_a_grant_attestation_does_not_verify_as_a_decision_attestation():
    """Domain separation: one signature must not be reusable in another slot."""

    payload = {"decision_id": "x", "allowed": True}
    grant_signature = TEST_AUTHORITY.sign(DOMAIN_CAPABILITY_GRANT, payload)

    with pytest.raises(AttestationError, match="domain"):
        TEST_AUTHORITY.verify(DOMAIN_ORACLE_DECISION, payload, grant_signature)


def test_a_short_secret_is_refused_rather_than_making_the_mac_decorative():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        AttestationAuthority(key_id="weak", secret=b"short")


# ==========================================================================
# P0-2  run receipts must attest a real execution, not a claim
# ==========================================================================


def _single_module_ledger(
    artifact: dict | None,
    *,
    maturity: str,
    implementation: list[str],
    tests: list[str],
) -> ProgressLedger:
    data = _ledger_data()
    for module in data["modules"]:
        module["evidence_artifacts"] = []
        module["implementation_paths"] = []
        module["test_paths"] = []
        module["maturity"] = Maturity.ABSENT.value
        module["allowed_claims"] = []
        if module["module_id"] == "M05":
            module["maturity"] = maturity
            module["implementation_paths"] = implementation
            module["test_paths"] = tests
            module["evidence_artifacts"] = [artifact] if artifact else []
    return ProgressLedger.model_validate(data)


def _replay_evidence(repo: Path, **receipt_overrides) -> dict:
    """Evidence whose commit resolves inside ``repo`` itself."""

    make_source_tree(repo)
    commit, snapshot = make_git_repo(repo)
    payload = build_payload(
        kind=EvidenceKind.REPLAY, git_commit_sha=commit, code_snapshot_sha256=snapshot
    )
    return write_evidence(repo, payload, **receipt_overrides)


def test_an_unattested_run_receipt_cannot_support_replay_evidence(tmp_path):
    """A receipt the candidate minted itself is exactly what P0-2 forbids."""

    artifact = _replay_evidence(tmp_path, authority=None)

    ledger = _single_module_ledger(
        artifact,
        maturity=Maturity.REPLAY_VALIDATED.value,
        implementation=["src/mod.py"],
        tests=["tests/test_mod.py"],
    )
    report = validate_ledger(ledger, tmp_path, authority=TEST_AUTHORITY)

    assert any("not attested by the governance authority" in error for error in report.errors)


def test_a_receipt_signed_with_another_key_is_not_attested(tmp_path):
    artifact = _replay_evidence(tmp_path, authority=OTHER_AUTHORITY)

    ledger = _single_module_ledger(
        artifact,
        maturity=Maturity.REPLAY_VALIDATED.value,
        implementation=["src/mod.py"],
        tests=["tests/test_mod.py"],
    )
    report = validate_ledger(ledger, tmp_path, authority=TEST_AUTHORITY)

    assert any("not attested" in error for error in report.errors)


def test_editing_an_attested_receipt_on_disk_invalidates_it(tmp_path):
    """The MAC covers content, so a post-signature edit must not survive."""

    artifact = _replay_evidence(tmp_path)
    receipt_path = tmp_path / "evidence" / "m05_receipt.json"
    raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    raw["module_id"] = "M06"
    receipt_path.write_text(json.dumps(raw), encoding="utf-8")

    ledger = _single_module_ledger(
        artifact,
        maturity=Maturity.REPLAY_VALIDATED.value,
        implementation=["src/mod.py"],
        tests=["tests/test_mod.py"],
    )
    report = validate_ledger(ledger, tmp_path, authority=TEST_AUTHORITY)

    assert any("attests module 'M06'" in error for error in report.errors)
    assert any("not attested" in error for error in report.errors)


def test_an_honest_attested_replay_receipt_is_accepted(tmp_path):
    """The positive case for P0-2: a properly signed run must still pass."""

    artifact = _replay_evidence(tmp_path)

    ledger = _single_module_ledger(
        artifact,
        maturity=Maturity.REPLAY_VALIDATED.value,
        implementation=["src/mod.py"],
        tests=["tests/test_mod.py"],
    )
    report = validate_ledger(ledger, tmp_path, authority=TEST_AUTHORITY)

    assert [error for error in report.errors if "M05" in error] == []


def test_a_receipt_naming_an_unresolvable_commit_is_an_error_for_runtime_evidence(tmp_path):
    """ "Cannot check" must read as unverified, never as fine."""

    make_source_tree(tmp_path)
    make_git_repo(tmp_path)
    # A well-formed sha that no object database has ever seen.
    payload = build_payload(kind=EvidenceKind.REPLAY, git_commit_sha="f" * 40)
    artifact = write_evidence(tmp_path, payload)

    ledger = _single_module_ledger(
        artifact,
        maturity=Maturity.REPLAY_VALIDATED.value,
        implementation=["src/mod.py"],
        tests=["tests/test_mod.py"],
    )
    report = validate_ledger(ledger, tmp_path, authority=TEST_AUTHORITY)

    assert any("cannot be resolved in this repository" in error for error in report.errors)


def test_a_code_snapshot_that_does_not_match_the_named_commit_is_rejected(tmp_path):
    """A real commit paired with someone else's tree digest must not verify."""

    make_source_tree(tmp_path)
    commit, snapshot = make_git_repo(tmp_path)
    if commit == "0" * 40:  # pragma: no cover - only when git is unavailable
        pytest.skip("git is unavailable, so the tree binding cannot be checked")
    payload = build_payload(
        kind=EvidenceKind.REPLAY, git_commit_sha=commit, code_snapshot_sha256="9" * 64
    )
    assert payload.code_snapshot_sha256 != snapshot
    artifact = write_evidence(tmp_path, payload)

    ledger = _single_module_ledger(
        artifact,
        maturity=Maturity.REPLAY_VALIDATED.value,
        implementation=["src/mod.py"],
        tests=["tests/test_mod.py"],
    )
    report = validate_ledger(ledger, tmp_path, authority=TEST_AUTHORITY)

    assert any("code_snapshot_sha256" in error for error in report.errors)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"exit_code": 1}, "exit_code=1"),
        ({"result_status": "failed"}, "exit_code=0"),
        ({"command": "echo definitely-not-what-ran"}, "shlex.join"),
        (
            {"started_at": datetime(2026, 8, 22, 10, 0, tzinfo=UTC)},
            "finished_at precedes started_at",
        ),
    ],
)
def test_an_internally_incoherent_receipt_cannot_be_constructed(overrides, fragment):
    """The contract refuses the incoherent receipt, so no file can hold one."""

    payload = build_payload(kind=EvidenceKind.REPLAY)

    with pytest.raises(ValidationError, match=fragment):
        build_receipt(payload, file_sha256="a" * 64, **overrides)


def test_a_runtime_receipt_without_a_dataset_manifest_is_refused():
    payload = build_payload(kind=EvidenceKind.REAL_DATA)

    with pytest.raises(ValidationError, match="dataset_manifest_sha256"):
        build_receipt(payload, file_sha256="a" * 64, dataset_manifest_sha256=None)


@pytest.mark.parametrize(
    "kind", [EvidenceKind.REPLAY, EvidenceKind.REAL_DATA, EvidenceKind.EMBODIED]
)
def test_each_runtime_kind_requires_its_own_evidence_fields(kind):
    """One flat schema made "embodied" cost exactly as much as "synthetic"."""

    with pytest.raises(ValidationError, match="requires"):
        build_payload(kind=kind, dataset_manifest_sha256=None)


def test_an_embodied_report_cannot_be_a_replay_manifest_in_disguise():
    with pytest.raises(ValidationError, match="must not declare"):
        build_payload(kind=EvidenceKind.EMBODIED, replay_log_sha256="7" * 64)


def test_a_replay_that_diverged_is_not_replay_evidence():
    with pytest.raises(ValidationError, match="divergence_count"):
        build_payload(kind=EvidenceKind.REPLAY, divergence_count=3)


# ==========================================================================
# P0-3  the gate topology is frozen, not declared
# ==========================================================================


def test_deleting_the_workstream_requirement_does_not_make_the_gate_easier():
    data = _ledger_data()
    for gate in data["gates"]:
        if gate["gate_id"] == "STRUCTURE_ONE_COMPLETE":
            gate["required_workstream_ids"] = []

    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    gate = next(item for item in report.gate_results if item.gate_id == "STRUCTURE_ONE_COMPLETE")

    assert not gate.passed
    assert any("frozen specification" in blocker for blocker in gate.blockers)
    assert any("required_workstream_ids" in error for error in report.errors)


def test_adding_a_workstream_requirement_to_a_module_gate_is_also_rejected():
    data = _ledger_data()
    for gate in data["gates"]:
        if gate["gate_id"] == "B1_SYNTHETIC_READINESS":
            gate["required_workstream_ids"] = ["WS1"]

    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)

    assert any(
        "required_workstream_ids" in error and "B1_SYNTHETIC_READINESS" in error
        for error in report.errors
    )


def test_refiling_a_mature_module_into_a_short_workstream_is_rejected():
    """WS7 has one module; moving a mature one in must not satisfy the gate."""

    data = _ledger_data()
    for module in data["modules"]:
        if module["module_id"] == "M28":
            module["workstream_ids"] = ["WS10", "WS7", "WS3"]

    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)

    assert any("M28" in error and "frozen mapping" in error for error in report.errors)


def test_workstream_membership_for_gates_comes_from_the_frozen_mapping():
    """Even if the declared mapping were accepted, the gate ignores it."""

    data = _ledger_data()
    for module in data["modules"]:
        # Claim every module belongs to every workstream.
        module["workstream_ids"] = [f"WS{i}" for i in range(1, 11)]
        module["maturity"] = Maturity.REPLAY_VALIDATED.value

    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)

    assert not report.required_gates_passed


# ==========================================================================
# The overall attack the review asked for
# ==========================================================================


def test_empty_implementation_empty_tests_and_a_forged_receipt_pass_nothing(tmp_path):
    """The end-to-end claim: nothing but real, attested work opens a gate.

    Everything a candidate controls is set to the most favourable value --
    maturity ``embodied_validated`` everywhere, an evidence file that hashes
    correctly, a receipt that says ``passed`` -- and the implementation is an
    empty directory with an empty test file.
    """

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "empty").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_nothing.py").write_text("", encoding="utf-8")

    data = _ledger_data()
    for index, module in enumerate(data["modules"]):
        payload = build_payload(
            module_id=module["module_id"],
            kind=EvidenceKind.EMBODIED,
            run_id=f"run-{index}",
        )
        artifact = write_evidence(
            tmp_path,
            payload,
            authority=None,  # the candidate holds no key
            evidence_name=f"{module['module_id']}.json",
            receipt_name=f"{module['module_id']}_receipt.json",
        )
        module["maturity"] = Maturity.EMBODIED_VALIDATED.value
        module["implementation_paths"] = ["src/empty"]
        module["test_paths"] = ["tests/test_nothing.py"]
        module["evidence_artifacts"] = [artifact]

    report = validate_ledger(
        ProgressLedger.model_validate(data), tmp_path, authority=TEST_AUTHORITY
    )

    assert not report.required_gates_passed
    assert all(not gate.passed for gate in report.gate_results if gate.required)
    # And each individual lie is named rather than lumped into one verdict.
    assert any("directory with no Python source" in error for error in report.errors)
    assert any("not attested by the governance authority" in error for error in report.errors)


def test_one_evidence_file_shared_by_two_modules_blocks_the_gate_line_too(tmp_path):
    """A cross-module error names its modules mid-sentence, not as a prefix.

    The overall verdict already caught this, but every gate line still read
    "passed", which is the artefact a reader actually looks at.
    """

    make_source_tree(tmp_path)
    artifact = write_evidence(tmp_path, build_payload())

    data = _ledger_data()
    for module in data["modules"]:
        module["evidence_artifacts"] = []
        if module["module_id"] in {"M05", "M06"}:
            module["maturity"] = Maturity.SYNTHETIC_VERTICAL_SLICE.value
            module["implementation_paths"] = ["src/mod.py"]
            module["test_paths"] = ["tests/test_mod.py"]
            module["evidence_artifacts"] = [artifact]

    report = validate_ledger(
        ProgressLedger.model_validate(data), tmp_path, authority=TEST_AUTHORITY
    )
    b1 = next(gate for gate in report.gate_results if gate.gate_id == "B1_SYNTHETIC_READINESS")

    assert any("claimed by both" in error for error in report.errors)
    assert not b1.passed


def test_no_gate_reports_passed_while_its_own_modules_have_errors(tmp_path):
    """The invariant behind the previous test, stated once for every gate."""

    make_source_tree(tmp_path)
    data = _ledger_data()
    for module in data["modules"]:
        module["maturity"] = Maturity.SYNTHETIC_VERTICAL_SLICE.value
        module["implementation_paths"] = ["src/does-not-exist.py"]
        module["test_paths"] = ["tests/test_mod.py"]
        module["evidence_artifacts"] = []

    report = validate_ledger(
        ProgressLedger.model_validate(data), tmp_path, authority=TEST_AUTHORITY
    )

    assert report.errors
    assert all(not gate.passed for gate in report.gate_results if gate.required)


def test_without_an_authority_no_gate_above_synthetic_can_pass():
    """A missing verifier reads as unverified, not as fine."""

    data = _ledger_data()
    for module in data["modules"]:
        module["maturity"] = Maturity.EMBODIED_VALIDATED.value

    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    formal = [
        gate
        for gate in report.gate_results
        if gate.gate_id in {"FORMAL_B1_REAL_VALIDATION", "STRUCTURE_ONE_COMPLETE"}
    ]

    assert formal
    assert all(not gate.passed for gate in formal)
    assert all(
        any("no authority was supplied" in blocker for blocker in gate.blockers) for gate in formal
    )


def test_the_real_ledger_is_still_internally_consistent_and_still_blocks():
    """The fixes must not silently break the ledger that is actually shipped."""

    report = validate_ledger(
        ProgressLedger.model_validate(_ledger_data()), REPO_ROOT, authority=TEST_AUTHORITY
    )

    assert report.internally_consistent is True
    assert report.required_gates_passed is False


def test_shlex_round_trip_is_the_only_accepted_command_spelling():
    """Documents why ``command`` is derived rather than free text."""

    argv = ("pytest", "-k", "not slow", "tests/")

    assert shlex.join(argv) == "pytest -k 'not slow' tests/"
