# Reproduction

Choose the code version before installing dependencies. `main` contains the earlier foundation; current experiments use development branches with additional modules and assets.

## Foundation code

The foundation snapshot before this documentation update is `f73b4b35d52fc21224f41226d8cd3f3a90f18acd`. Its `.python-version` selects Python 3.13.

```bash
git clone https://github.com/goneveitvet240-svg/cpswm.git
cd cpswm
git checkout f73b4b35d52fc21224f41226d8cd3f3a90f18acd
uv sync --frozen --extra dev
uv run --frozen python -m pytest tests/test_base_contracts.py
```

This is a contract-test entry point, not a demo of the full research system. The environment command requires uv and access to the dependency sources recorded by the project. This documentation revision checks the referenced files; it does not certify a new clean-machine installation.

## Recent perception experiment

To inspect the September 15 delivery:

```bash
git fetch origin
git checkout 7e00bf81ea5671228ba6be32d3d550bbc1a29cba
```

Use the version-specific [commands](https://github.com/goneveitvet240-svg/cpswm/blob/7e00bf81ea5671228ba6be32d3d550bbc1a29cba/docs/reviews/pc_a/real_semantic_input_2026-09-15/COMMANDS.md) and [report](https://github.com/goneveitvet240-svg/cpswm/blob/7e00bf81ea5671228ba6be32d3d550bbc1a29cba/docs/reviews/pc_a/real_semantic_input_2026-09-15/REPORT.md). The tested production source is `521d4f17c8538116b30a7c3c6c5e5a8f894141`; later commits retain evidence and documentation.

Raw datasets, detector weights and simulator installations are separate prerequisites. Follow the source and license information in that report; cloning this repository alone does not provide a complete simulator or trained world model.

## Interpreting a run

Record the commit, interpreter, dependencies, inputs and command with its output. Keep expected rejection tests distinct from unexpected failures, and retain failed runs. For simulator or cross-machine work, use the [environment notes](https://github.com/goneveitvet240-svg/cpswm/blob/codex/dual-pc-handoff-20260912/docs/collaboration/WINDOWS_SETUP.md) alongside the selected experiment's report.
