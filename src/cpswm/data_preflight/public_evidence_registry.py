"""Frozen byte enrollment for the public artifacts actually fetched in PR36.

This binds the inspection to that reviewed source snapshot, not to a receipt
supplied alongside a new payload. It does not certify annotation truth or grant
runtime/training authority. New sources require an explicit registry change.
"""

from pathlib import Path

from cpswm.data_preflight.hocap_joint_supervision import pinned_bytes

ENROLLMENT_REVIEW = "cf5f1f873681772574d18c1787c73cb121ae9db1"
ENROLLED_SOURCE_SHA256S = {
    "ope-receipts.json": "86e79ea3754c1d1e27140b85e05bbc7a890d453ab78cd111c678a667013e9142",
    "ope_gt.json": "ec5a39654670d2d861af5e4e44829886043e1b399d2bdff80404fe1e39a03a48",
    "ope_demo.json": "a74cf3c7fdd5712111ea5f73c7aeeab9aaaf3a95737d9218994c23a2ad278047",
    "rpl/receipts.json": "d59f0964a23382dd6faf8fd01a4955748c79d4cc9598c0839264a6e3109905cd",
    "rpl/one_saved_handover_New.zip": "946c2909adce0e86cb1a12d91182a921544a902c770805d97af043bce74c929f",  # noqa: E501
    "rpl/README.md": "7774331aade7dcb4ccdc5736a35e4c938b0ca39ff0a00a92f9aa00241446e2b6",
    "rpl/LICENSE": "7df5b891155a94028c1b388849281077788a2d6820d4e9116bb9c154da5f8925",
    "rpl/Readme_text.txt": "52ac0213e51c1bb451a9c9a9dfe5e312a9db8cf33af9475ac1715ae54fdb2b40",
    "rpl/Readme_description_handover.txt": "d6853ac706ce891a28f5ea8ef61526e64a9a01585a8faa864131c649dfe233d0",  # noqa: E501
    "handover-record.json": "11b251e9b1520675cf7db6e0e7224a45324ddf427989dfe3fb56afc839818235",
    "datasheet.pdf": "faee6c57ce920fb845d5a3be5a7485b94a18c9489915018eadecf286659a17d1",
    "training_labels.tar.gz": "4cfbdd9ee4b7b1b22fe38dc456b60a1be4d4b62e6deeae33b98ac8c75a26019b",
    "class_names.json": "a529dd91b4605fad26745f591f05b68a4511d91560c4c0b75d526ab5c4f8a656",
    "sample_training_set.verified.tar.gz": "4203bc5685002ba959cc6356a5d0b3231a161d6259e6335727b766e30afeee93",  # noqa: E501
}


def enrolled_source_snapshot(root: Path) -> dict[str, bytes]:
    try:
        return {
            name: pinned_bytes(root, name, digest)
            for name, digest in ENROLLED_SOURCE_SHA256S.items()
        }
    except ValueError as error:
        raise ValueError("public source differs from enrolled author registry") from error
