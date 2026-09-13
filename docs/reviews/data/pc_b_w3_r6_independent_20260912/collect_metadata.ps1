$ErrorActionPreference = "Stop"

$r6 = "1bd513f51ab7e54a7290870a5f34b524254d55c6"
$r6Parent = "281e88894fca527df1d54018b5053469e8c422d5"
$w1 = "b6202bec015679461b06056571bd47a5446045b8"
$w1Parent = "f5089d94ba217b377f88067bc36fdb976e12a4cf"
$lfRoot = "F:\庞惟\codex\cpswm-w3-r6-lf-control"
$python = Join-Path $PWD ".venv\Scripts\python.exe"
$keyFiles = @(
    "src/cpswm/system/prototype_spine.py",
    "src/cpswm/system/structure_two_particle_workspace.py",
    "src/cpswm/system/evaluation_operations/structure_two_selected_method.py",
    "src/cpswm/system/structure_two_semantic_identity.py",
    "tests/test_structure_two_formal_revision_lineage.py",
    "tests/test_structure_two_w3_native_particles.py",
    "tests/test_structure_two_w3_round6_prepared_boundary.py"
)

function Section([string]$Title) {
    Write-Output ""
    Write-Output "=== $Title ==="
}

Section "R6 Git identity"
Write-Output "command: git rev-parse HEAD"
git rev-parse HEAD
Write-Output "command: git rev-parse 'HEAD^{tree}'"
git rev-parse "HEAD^{tree}"
Write-Output "command: git show -s --format=fuller $r6"
git show -s --format=fuller $r6
Write-Output "command: git diff --name-status $r6Parent $r6"
git diff --name-status $r6Parent $r6

Section "Runtime interpreter and imports"
Write-Output "command: git --version"
git --version
Write-Output "command: .venv\\Scripts\\python.exe -VV"
& $python -VV
Write-Output "command: .venv\\Scripts\\python.exe -m pytest --version"
& $python -m pytest --version
Write-Output "command: Python platform/import probe"
& $python -c 'import json,platform,sys,pytest,cpswm; print(json.dumps({"executable":sys.executable,"version":sys.version,"platform":platform.platform(),"pytest":pytest.__version__,"cpswm":cpswm.__file__}, ensure_ascii=False, indent=2))'
Write-Output "command: SHA-256 of interpreter, pyproject.toml and uv.lock"
Get-FileHash -Algorithm SHA256 -LiteralPath $python, "pyproject.toml", "uv.lock" | ForEach-Object {
    "{0}  {1}" -f $_.Hash, $_.Path
}

Section "Installed distributions"
Write-Output "command: importlib.metadata distributions"
& $python -c 'import importlib.metadata as m; print("\n".join(sorted((d.metadata["Name"] or "")+"=="+d.version for d in m.distributions())))'

Section "Git EOL configuration"
Write-Output "command: git config --list --show-origin | Select-String core.autocrlf/core.eol/safecrlf"
git config --list --show-origin | Select-String -Pattern 'core\.autocrlf|core\.eol|safecrlf'
Write-Output "repository .gitattributes exists: $(Test-Path -LiteralPath '.gitattributes')"
Write-Output "command: git check-attr text eol -- key files"
git check-attr text eol -- $keyFiles

Section "Windows checkout EOL and actual byte SHA-256"
git ls-files --eol -- $keyFiles
Get-FileHash -Algorithm SHA256 -LiteralPath $keyFiles | ForEach-Object {
    "{0}  {1}" -f $_.Hash, $_.Path
}

Section "Git-normalized SHA-256 recorded by snapshot manifest"
$snapshot = Get-Content -Raw -LiteralPath "docs/collaboration/SNAPSHOT_SCOPE.json" | ConvertFrom-Json -AsHashtable
foreach ($path in $keyFiles) {
    "{0}  {1}" -f $snapshot.files_sha256[$path], $path
}

Section "LF control checkout EOL and actual byte SHA-256"
Write-Output "LF checkout root: $lfRoot"
Write-Output "LF checkout HEAD: $(git -C $lfRoot rev-parse HEAD)"
git -C $lfRoot config --list --show-origin | Select-String -Pattern 'core\.autocrlf|core\.eol|safecrlf'
git -C $lfRoot ls-files --eol -- $keyFiles
$lfFiles = $keyFiles | ForEach-Object { Join-Path $lfRoot $_ }
Get-FileHash -Algorithm SHA256 -LiteralPath $lfFiles | ForEach-Object {
    "{0}  {1}" -f $_.Hash, $_.Path
}

Section "W1 Git-object static audit"
Write-Output "command: git show -s --format=fuller $w1"
git show -s --format=fuller $w1
Write-Output "W1 tree: $(git rev-parse "$w1^{tree}")"
Write-Output "command: git diff --name-status $w1Parent $w1"
git diff --name-status $w1Parent $w1
Write-Output "command: git diff --check $w1Parent $w1"
git diff --check $w1Parent $w1
Write-Output "command: parse the three W1 Python deltas directly from Git objects"
& $python -c 'import ast,subprocess; sha="b6202bec015679461b06056571bd47a5446045b8"; paths=("tests/test_structure_two_unified_dependencies.py","tools/structure_two_pytest_runtime.py","tools/structure_two_unified_acceptance.py"); [(ast.parse(subprocess.check_output(["git","show",sha+":"+path], text=True, encoding="utf-8")), print("AST_OK "+path)) for path in paths]'
Write-Output "W1 five changed-file Git-object SHA-256:"
Write-Output "aa6b2fca7fd6ad3c1ab06ea0ec0aa93045a197cb84f2eaaca304fdffca1726ae  AGENTS.md"
Write-Output "2564b774a9b2eefd23200ac5a693e2000cbb38067f9bd84d0dc24b955b658182  docs/collaboration/SNAPSHOT_SCOPE.json"
Write-Output "b2aed0837d499e1086e55ad9141c67a379c3b302b9ccb2808379b62a531eb6c8  tests/test_structure_two_unified_dependencies.py"
Write-Output "876b54448c8fa39dd5fd526dbc1ac06882cfa8297dbcc0d34b6ca741f8030cdb  tools/structure_two_pytest_runtime.py"
Write-Output "0e38a3e85a3300b7db18e2780c648034307f8491a7030dba487a7f3c497a8fae  tools/structure_two_unified_acceptance.py"
Write-Output "W1 uv.lock Git-object SHA-256: 8ff0275d2b10eef8c258f14c82a050358ceee6443a5d0fa4c9ddfcc3832291b1"
Write-Output "Trust boundary: Git-object/read-only static inspection only; no W1 runtime execution and no internal state mutation."

Section "W1 missing declared unified closure"
Write-Output "W2 tests missing 5/5:"
Write-Output "tests/test_structure_two_comparison_audit.py"
Write-Output "tests/test_structure_two_comparison_audit_verification.py"
Write-Output "tests/test_structure_two_comparison_execution_source.py"
Write-Output "tests/test_structure_two_comparison_fairness.py"
Write-Output "tests/test_structure_two_comparison_dynamic.py"
Write-Output "W2 producer/summary entry points missing 2/2:"
Write-Output "apps/evaluation_runner/run_structure_two_comparison_audit.py"
Write-Output "apps/evaluation_runner/summarize_structure_two_comparison_audit.py"
Write-Output "W3 tests missing 14/29:"
Write-Output "tests/test_structure_two_backbone_operator_wiring.py"
Write-Output "tests/test_structure_two_backbone_counterexample_regressions.py"
Write-Output "tests/test_structure_two_late_counter_evidence_chain.py"
Write-Output "tests/test_structure_two_operator_causal_matrix.py"
Write-Output "tests/test_structure_two_ciav_negative_observation_layers.py"
Write-Output "tests/test_structure_two_p0_maintenance_fault_injection.py"
Write-Output "tests/test_structure_two_formal_revision_lineage.py"
Write-Output "tests/test_structure_two_operator_coverage_matrix.py"
Write-Output "tests/test_structure_two_w3_revision_acceptance.py"
Write-Output "tests/test_structure_two_w3_operator_acceptance.py"
Write-Output "tests/test_structure_two_w3_supplement.py"
Write-Output "tests/test_structure_two_w3_round5_boundaries.py"
Write-Output "tests/test_structure_two_w3_native_particles.py"
Write-Output "tests/test_structure_two_w3_native_bundle.py"
