from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.direction_three_dataset import DirectionThreeDatasetSplit
from cpswm.system.evaluation_operations.direction_three_prediction_cache import (
    DirectionThreeFrameContentBinding,
    DirectionThreeFrameContentManifest,
    issue_direction_three_frame_manifest,
)
from cpswm.system.evaluation_operations.independent_test_process import (
    run_independent_test_process,
    verify_independent_test_process_receipt,
)
from cpswm.system.evaluation_operations.oam_phm_external_evidence import (
    ExternalMethod,
    ExternalReproductionManifest,
    FidelityRequirement,
    FidelityRequirementStatus,
    ReproductionReadiness,
)
from cpswm.system.evaluation_operations.oam_phm_external_receipts import (
    issue_oam_external_evidence_receipt,
    verify_oam_external_evidence_receipt,
)
from cpswm.system.evaluation_operations.raw_data_signatures import (
    sign_raw_data_file,
    verify_raw_data_file,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _complete_external_manifest() -> ExternalReproductionManifest:
    requirement_ids = (
        "primary-source-frozen",
        "semantic-prior",
        "geometric-grounding",
        "dirichlet-update-core",
        "relaxed-transition-inference",
        "cost-aware-active-search",
        "opportunistic-multi-target-perception",
        "published-result-recheck",
    )
    return ExternalReproductionManifest(
        method=ExternalMethod.O_STAR,
        reproduction_id="o-star-independent@1",
        primary_source_url="https://example.test/o-star.pdf",
        primary_source_sha256=SHA_A,
        requirements=tuple(
            FidelityRequirement(
                requirement_id=requirement_id,
                description=f"Verified canonical requirement: {requirement_id}.",
                status=FidelityRequirementStatus.VERIFIED,
                evidence_artifact_sha256=SHA_B,
                note="Bound to the independent process output.",
            )
            for requirement_id in requirement_ids
        ),
        readiness=ReproductionReadiness.REPRODUCTION_COMPLETE,
    )


def test_raw_data_signature_verifies_bytes_chunks_and_authority(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="raw-custodian")
    source = tmp_path / "raw.bin"
    source.write_bytes(b"frame-0|frame-1|frame-2")
    signature = sign_raw_data_file(
        source,
        dataset_id="findingdory",
        dataset_revision="1" * 40,
        source_split="test",
        media_type="video/mp4",
        signer=signer,
        chunk_size_bytes=7,
    )

    assert verify_raw_data_file(source, signature, verifier=signer.verifier()) == signature
    assert len(signature.chunk_sha256s) == 4

    source.write_bytes(b"frame-0|tampered")
    with pytest.raises(ValueError, match=r"byte length|content digest|chunk digest"):
        verify_raw_data_file(source, signature, verifier=signer.verifier())


def test_raw_data_signature_rejects_wrong_authority_and_locator_copy(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="raw-custodian")
    source = tmp_path / "raw.bin"
    copy = tmp_path / "copy.bin"
    source.write_bytes(b"same bytes")
    copy.write_bytes(source.read_bytes())
    signature = sign_raw_data_file(
        source,
        dataset_id="findingdory",
        dataset_revision="1" * 40,
        source_split="test",
        media_type="video/mp4",
        signer=signer,
    )

    with pytest.raises(AttestationError):
        verify_raw_data_file(
            source,
            signature,
            verifier=Ed25519AttestationSigner.generate(key_id="attacker").verifier(),
        )
    with pytest.raises(ValueError, match="locator"):
        verify_raw_data_file(copy, signature, verifier=signer.verifier())


def test_direction_three_frame_manifest_requires_the_verified_raw_signature(
    tmp_path: Path,
) -> None:
    raw_signer = Ed25519AttestationSigner.generate(key_id="raw-custodian")
    frame_signer = Ed25519AttestationSigner.generate(key_id="frame-custodian")
    source = tmp_path / "video.bin"
    source.write_bytes(b"video")
    raw = sign_raw_data_file(
        source,
        dataset_id="findingdory",
        dataset_revision="2" * 40,
        source_split="test",
        media_type="video/mp4",
        signer=raw_signer,
    )
    manifest = DirectionThreeFrameContentManifest(
        dataset_manifest_hash=SHA_A,
        raw_data_signature_sha256=raw.signature_sha256,
        raw_data_content_sha256=raw.content_sha256,
        split=DirectionThreeDatasetSplit.TEST,
        producer_run_id="decoder-run-1",
        bindings=(
            DirectionThreeFrameContentBinding(
                episode_id="00000000-0000-0000-0000-000000000001",
                frame_index=3,
                source_uri=str(source),
                source_artifact_sha256=raw.content_sha256,
                raw_byte_sha256=hashlib.sha256(b"encoded-frame").hexdigest(),
                preprocessing_sha256=SHA_B,
                decoded_input_sha256=hashlib.sha256(b"decoded-frame").hexdigest(),
            ),
        ),
    )

    issued = issue_direction_three_frame_manifest(
        manifest,
        raw_data_path=source,
        raw_data_signature=raw,
        raw_data_signature_verifier=raw_signer.verifier(),
        materialize_frame=lambda _path, _binding: (
            b"encoded-frame",
            b"decoded-frame",
        ),
        signer=frame_signer,
    )
    assert issued.attestation is not None

    with pytest.raises(ValueError, match="raw-data signature"):
        issue_direction_three_frame_manifest(
            manifest.model_copy(update={"raw_data_signature_sha256": SHA_C}),
            raw_data_path=source,
            raw_data_signature=raw,
            raw_data_signature_verifier=raw_signer.verifier(),
            materialize_frame=lambda _path, _binding: (
                b"encoded-frame",
                b"decoded-frame",
            ),
            signer=frame_signer,
        )

    with pytest.raises(ValueError, match="decoded-input hash"):
        issue_direction_three_frame_manifest(
            manifest,
            raw_data_path=source,
            raw_data_signature=raw,
            raw_data_signature_verifier=raw_signer.verifier(),
            materialize_frame=lambda _path, _binding: (
                b"encoded-frame",
                b"attacker-decoded-frame",
            ),
            signer=frame_signer,
        )
    with pytest.raises(ValueError, match="raw-data content boundary"):
        DirectionThreeFrameContentManifest.model_validate(
            manifest.model_dump()
            | {
                "bindings": (
                    manifest.bindings[0].model_copy(update={"source_artifact_sha256": SHA_C}),
                )
            }
        )


def test_frame_manifest_issue_rechecks_signed_raw_bytes(tmp_path: Path) -> None:
    raw_signer = Ed25519AttestationSigner.generate(key_id="raw-custodian")
    frame_signer = Ed25519AttestationSigner.generate(key_id="frame-custodian")
    source = tmp_path / "video.bin"
    source.write_bytes(b"original")
    raw = sign_raw_data_file(
        source,
        dataset_id="findingdory",
        dataset_revision="3" * 40,
        source_split="test",
        media_type="video/mp4",
        signer=raw_signer,
    )
    manifest = DirectionThreeFrameContentManifest(
        dataset_manifest_hash=SHA_A,
        raw_data_signature_sha256=raw.signature_sha256,
        raw_data_content_sha256=raw.content_sha256,
        split=DirectionThreeDatasetSplit.TEST,
        producer_run_id="decoder-run-stale-source",
        bindings=(
            DirectionThreeFrameContentBinding(
                episode_id="00000000-0000-0000-0000-000000000002",
                frame_index=1,
                source_uri=str(source),
                source_artifact_sha256=raw.content_sha256,
                raw_byte_sha256=SHA_A,
                preprocessing_sha256=SHA_B,
                decoded_input_sha256=SHA_C,
            ),
        ),
    )
    source.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="content digest"):
        issue_direction_three_frame_manifest(
            manifest,
            raw_data_path=source,
            raw_data_signature=raw,
            raw_data_signature_verifier=raw_signer.verifier(),
            materialize_frame=lambda _path, _binding: (b"encoded", b"decoded"),
            signer=frame_signer,
        )


def test_frame_manifest_rejects_locator_outside_signed_raw_source(tmp_path: Path) -> None:
    raw_signer = Ed25519AttestationSigner.generate(key_id="raw-custodian")
    frame_signer = Ed25519AttestationSigner.generate(key_id="frame-custodian")
    source = tmp_path / "video.bin"
    source.write_bytes(b"video")
    raw = sign_raw_data_file(
        source,
        dataset_id="findingdory",
        dataset_revision="4" * 40,
        source_split="test",
        media_type="video/mp4",
        signer=raw_signer,
    )
    manifest = DirectionThreeFrameContentManifest(
        dataset_manifest_hash=SHA_A,
        raw_data_signature_sha256=raw.signature_sha256,
        raw_data_content_sha256=raw.content_sha256,
        split=DirectionThreeDatasetSplit.TEST,
        producer_run_id="decoder-run-wrong-locator",
        bindings=(
            DirectionThreeFrameContentBinding(
                episode_id="00000000-0000-0000-0000-000000000003",
                frame_index=1,
                source_uri=str(tmp_path / "other-video.bin"),
                source_artifact_sha256=raw.content_sha256,
                raw_byte_sha256=SHA_A,
                preprocessing_sha256=SHA_B,
                decoded_input_sha256=SHA_C,
            ),
        ),
    )

    with pytest.raises(ValueError, match="source locator"):
        issue_direction_three_frame_manifest(
            manifest,
            raw_data_path=source,
            raw_data_signature=raw,
            raw_data_signature_verifier=raw_signer.verifier(),
            materialize_frame=lambda _path, _binding: (b"encoded", b"decoded"),
            signer=frame_signer,
        )


def _run_external_process(tmp_path: Path, signer: Ed25519AttestationSigner):
    result = tmp_path / "result.json"
    command = (
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(result)!r}).write_text('result')",
    )
    receipt = run_independent_test_process(
        command,
        process_role="oam_external:o_star",
        working_directory=tmp_path,
        signer=signer,
        hard_timeout_seconds=5.0,
        output_artifacts=(result,),
    )
    return result, receipt


def test_independent_process_receipt_binds_child_and_outputs(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    result, receipt = _run_external_process(tmp_path, signer)

    assert receipt.passed
    assert receipt.child_pid != receipt.parent_pid
    verify_independent_test_process_receipt(receipt, verifier=signer.verifier())

    result.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="no longer matches"):
        verify_independent_test_process_receipt(receipt, verifier=signer.verifier())


def test_independent_process_timeout_cannot_pass(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    receipt = run_independent_test_process(
        (sys.executable, "-c", "import time; time.sleep(2)"),
        process_role="timeout-attack",
        working_directory=tmp_path,
        signer=signer,
        hard_timeout_seconds=0.05,
        termination_grace_seconds=0.05,
    )

    assert receipt.timed_out
    with pytest.raises(ValueError, match="did not pass"):
        verify_independent_test_process_receipt(receipt, verifier=signer.verifier())


def test_independent_process_refuses_to_claim_preexisting_output(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    existing = tmp_path / "existing.json"
    existing.write_text("not produced by child", encoding="utf-8")

    with pytest.raises(FileExistsError, match="pre-existing"):
        run_independent_test_process(
            (sys.executable, "-c", "pass"),
            process_role="artifact-claim-attack",
            working_directory=tmp_path,
            signer=signer,
            hard_timeout_seconds=1.0,
            output_artifacts=(existing,),
        )


def test_independent_process_rejects_output_symlink_escape(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "result-link.json"
    command = (
        sys.executable,
        "-c",
        f"import os; os.symlink({str(outside)!r}, {str(link)!r})",
    )

    with pytest.raises(ValueError, match="working tree"):
        run_independent_test_process(
            command,
            process_role="symlink-escape-attack",
            working_directory=tmp_path,
            signer=signer,
            hard_timeout_seconds=2.0,
            output_artifacts=(link,),
        )


def test_independent_process_rejects_surviving_descendant(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    command = (
        sys.executable,
        "-c",
        "import subprocess,sys; "
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)'])",
    )

    with pytest.raises(RuntimeError, match="surviving descendant"):
        run_independent_test_process(
            command,
            process_role="daemon-escape-attack",
            working_directory=tmp_path,
            signer=signer,
            hard_timeout_seconds=2.0,
            termination_grace_seconds=0.05,
        )


def test_oam_receipt_rejects_generic_false_complete_manifest(tmp_path: Path) -> None:
    process_signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    receipt_signer = Ed25519AttestationSigner.generate(key_id="oam-custodian")
    _, process_receipt = _run_external_process(tmp_path, process_signer)
    result_hash = next(iter(process_receipt.output_artifact_sha256s.values()))
    generic = ExternalReproductionManifest(
        method=ExternalMethod.O_STAR,
        reproduction_id="false-complete",
        primary_source_url="https://example.test/o-star.pdf",
        primary_source_sha256=SHA_A,
        requirements=(
            FidelityRequirement(
                requirement_id="everything",
                description="A vague self-declared completion claim.",
                status=FidelityRequirementStatus.VERIFIED,
                evidence_artifact_sha256=SHA_B,
                note="Does not enumerate the canonical method requirements.",
            ),
        ),
        readiness=ReproductionReadiness.REPRODUCTION_COMPLETE,
    )

    with pytest.raises(ValueError, match="canonical fidelity requirements"):
        issue_oam_external_evidence_receipt(
            reproduction_manifest=generic,
            raw_dataset_signature_sha256=SHA_A,
            frame_source_manifest_sha256=SHA_B,
            process_receipt=process_receipt,
            independently_tuned_selection_sha256=SHA_C,
            result_artifact_sha256s=(result_hash,),
            process_verifier=process_signer.verifier(),
            signer=receipt_signer,
        )


def test_oam_external_receipt_binds_complete_reproduction_process_and_artifact(
    tmp_path: Path,
) -> None:
    process_signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    receipt_signer = Ed25519AttestationSigner.generate(key_id="oam-custodian")
    _, process_receipt = _run_external_process(tmp_path, process_signer)
    result_hash = next(iter(process_receipt.output_artifact_sha256s.values()))
    reproduction = _complete_external_manifest()
    receipt = issue_oam_external_evidence_receipt(
        reproduction_manifest=reproduction,
        raw_dataset_signature_sha256=SHA_A,
        frame_source_manifest_sha256=SHA_B,
        process_receipt=process_receipt,
        independently_tuned_selection_sha256=SHA_C,
        result_artifact_sha256s=(result_hash,),
        process_verifier=process_signer.verifier(),
        signer=receipt_signer,
    )

    assert (
        verify_oam_external_evidence_receipt(
            receipt,
            reproduction_manifest=reproduction,
            process_receipt=process_receipt,
            raw_dataset_signature_sha256=SHA_A,
            frame_source_manifest_sha256=SHA_B,
            independently_tuned_selection_sha256=SHA_C,
            process_verifier=process_signer.verifier(),
            verifier=receipt_signer.verifier(),
        )
        == receipt
    )

    with pytest.raises(ValueError, match="signed raw dataset"):
        verify_oam_external_evidence_receipt(
            receipt,
            reproduction_manifest=reproduction,
            process_receipt=process_receipt,
            raw_dataset_signature_sha256=SHA_C,
            frame_source_manifest_sha256=SHA_B,
            independently_tuned_selection_sha256=SHA_C,
            process_verifier=process_signer.verifier(),
            verifier=receipt_signer.verifier(),
        )


def test_oam_external_receipt_rejects_incomplete_reproduction(tmp_path: Path) -> None:
    process_signer = Ed25519AttestationSigner.generate(key_id="process-custodian")
    receipt_signer = Ed25519AttestationSigner.generate(key_id="oam-custodian")
    _, process_receipt = _run_external_process(tmp_path, process_signer)
    result_hash = next(iter(process_receipt.output_artifact_sha256s.values()))
    incomplete = _complete_external_manifest().model_copy(
        update={"readiness": ReproductionReadiness.EQUATION_CORE_ONLY}
    )

    with pytest.raises(ValueError, match="incomplete external reproduction"):
        issue_oam_external_evidence_receipt(
            reproduction_manifest=incomplete,
            raw_dataset_signature_sha256=SHA_A,
            frame_source_manifest_sha256=SHA_B,
            process_receipt=process_receipt,
            independently_tuned_selection_sha256=SHA_C,
            result_artifact_sha256s=(result_hash,),
            process_verifier=process_signer.verifier(),
            signer=receipt_signer,
        )
