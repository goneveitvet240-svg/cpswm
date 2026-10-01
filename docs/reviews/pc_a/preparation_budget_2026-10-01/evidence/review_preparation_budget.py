from pathlib import Path
import hashlib, importlib.util, json, os, shlex, subprocess, sys, time
import yaml

root=Path('/private/tmp/cpswm-pc-a-validation-budget-20261001')
out=Path(__file__).parent/'preparation-budget'
out.mkdir(exist_ok=True)
phase=sys.argv[1]
def snapshot():
    paths=[root/'.github/workflows/ci.yml',root/'uv.lock',root/'pyproject.toml']
    for directory in ('src','apps','tools','tests'):
        paths.extend((root/directory).rglob('*.py'))
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before=snapshot(); rows=[]; start=time.monotonic()
workflow=yaml.safe_load((root/'.github/workflows/ci.yml').read_text())
preparation=workflow['jobs']['current-inputs']; regression=workflow['jobs']['test']
prep_command=next(s['run'] for s in preparation['steps'] if s.get('name')=='Generate and independently replay current test inputs')
test_command=next(s['run'] for s in regression['steps'] if s.get('name')=='Full regression (65 minute execution budget)')
prep_args=shlex.split(prep_command);test_args=shlex.split(test_command)
assert prep_args[prep_args.index('--budget-seconds')+1]=='7200'
assert prep_args[prep_args.index('--grace-seconds')+1]=='60'
assert preparation['timeout-minutes']==140
assert test_args[test_args.index('--budget-seconds')+1]=='3900'
assert regression['timeout-minutes']==85 and regression['needs']=='current-inputs'
assert next(s for s in preparation['steps'] if 'uses' in s and s['uses'].startswith('actions/upload-artifact'))['if']=='always()'
assert subprocess.check_output(['git','diff','--name-only','3644873f74c34e3ace340d544a3f25faa189493e','HEAD'],cwd=root,text=True).splitlines()==['.github/workflows/ci.yml']
try:
    if phase=='review1':
        command=[sys.executable,'-m','pytest','-o','addopts=','-q','tests/test_current_validation_inputs.py','tests/test_ci_regression_runner.py','--basetemp='+str(out/'review1-cases')]
        with (out/'review1.log').open('w') as log:
            result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'))
        rows.append(dict(command=command,exit_code=result.returncode));assert result.returncode==0
    elif phase=='review2':
        spec=importlib.util.spec_from_file_location('real_budget_runner',root/'tools/run_ci_regression.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name,code,budget,expected in [('legal','print("completed")',7200,0),('failed','raise SystemExit(7)',7200,7),('timeout','import time; time.sleep(30)',0.2,124)]:
            result=module.run([sys.executable,'-c',code],cwd=root,output=out/('review2-'+name),budget_seconds=budget,grace_seconds=1)
            rows.append(dict(name=name,result=result));assert result['exit_code']==expected
        assert (out/'review1.json').is_file(), 'R1 must complete before R2'
    else:raise ValueError(phase)
finally:
    record=dict(scope='CI_BUDGET_CONFIGURATION_AND_RUNNER_ONLY_NOT_LINUX_COMPLETION',phase=phase,
                commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
                source_unchanged=before==snapshot(),source_files=before,elapsed_seconds=time.monotonic()-start,
                preparation_budget_seconds=7200,regression_budget_seconds=3900,rows=rows)
    (out/(phase+'.json')).write_text(json.dumps(record,indent=2)+'\n');assert record['source_unchanged']
print(phase,'passed')
