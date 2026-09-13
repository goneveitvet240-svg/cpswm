# PC-B W3 five-boundary repair baseline

## Binding

- Repair branch: `codex/pc-b-w3-five-boundaries-fix-20260912`
- Baseline handoff SHA: `62870a3a38fce882b25d8d77f1d0526cca6fbc14`
- Baseline production-code SHA: `1d6887206605841074ada0f5ed67db278d1b7958`
- Ownership-registration commit present during the run: `49f80b2a3503b44ebfed2c86897fc8c78bc28fe3`
- Historical R6 evidence source: `9195dd4b3872cbf770bd73ad4c84cca007137c3d`
- Platform: Windows 11 `10.0.22631`, native PowerShell
- Interpreter: CPython `3.13.5`
- pytest: `9.1.1`
- Git line-ending configuration: `core.autocrlf=true`; no explicit `core.eol` or `core.safecrlf` value was returned.

The ownership commit changes only `STATUS_B.md`; the baseline source files are byte-for-byte those delivered at `62870a3a...`. The R7 delivery commit changes status/binding evidence only; its last production-code parent is `1d688720...`.

## Exact command

```powershell
$env:PYTHONPATH='src;tests'
$env:PYTHONHASHSEED='0'
$env:PYTHONPYCACHEPREFIX=(Join-Path (Get-Location) '.evidence-pycache-baseline-seed0')
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider `
  --basetemp '.pytest-baseline-r7-five-seed0' `
  --junitxml 'docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/baseline_r7_five_seed0.junit.xml' `
  'tests/test_structure_two_w3_r6_pc_b_review.py'
```

## Result

- Exit code: `1`
- Result: `1 passed / 5 failed`
- Legal public stage/readout control: `PASS`
- `W3-PCB-01` constructed-world support binding: `FAIL (accepted)`
- `W3-PCB-02` rebound-support readout: `FAIL (accepted)`
- `W3-PCB-03` parent/child support continuity: `FAIL (accepted)`
- `W3-PCB-04` statistic evidence-cluster lineage: `FAIL (accepted)`
- `W3-PCB-05` receipts/statistics input closure: `FAIL (accepted)`

The complete console output and machine-readable test cases are in `baseline_r7_five_seed0.log` and `baseline_r7_five_seed0.junit.xml`. This directory is only for the R7 repair campaign. The historical R6 artifacts remain unchanged under `docs/reviews/data/pc_b_w3_r6_independent_20260912/`.

## Historical observer replay on R7

The original observer was also executed unchanged from a separate detached worktree whose externally verified `HEAD` was `62870a3a38fce882b25d8d77f1d0526cca6fbc14`. Its raw output is `baseline_r7_historical_observer_seed0.json` (SHA-256 `6BD6594144FEA8AFE9C5DF133FB6116F047498E8A3A889BCB9B88EC8A5725FF4`), and all five adversarial calls were returned/accepted while the legal control was accepted.

The observer's embedded `tested_sha` remains the hard-coded R6 value `1bd513f51ab7e54a7290870a5f34b524254d55c6`; it is preserved as historical script behavior and is **not** the binding authority for this R7 replay. The detached-worktree `git rev-parse HEAD`, the outer command, later dynamic metadata, and loaded-source hashes provide the actual R7 binding.
