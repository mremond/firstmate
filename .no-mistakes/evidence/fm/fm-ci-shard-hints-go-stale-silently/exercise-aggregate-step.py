import json, os, shutil, subprocess
from pathlib import Path
E=Path('/Users/mremond/.no-mistakes/evidence/01M20P1RQF711N8XQS8YPKN43T')
W=Path.cwd()/'.local-shard-validation'
workflow=json.loads((E/'workflow-semantics.json').read_text())
assert workflow['serial']['timeout-minutes']==20
assert workflow['serial']['strategy']['matrix']['shard']==list(range(1,7))
assert workflow['serial']['strategy']['fail-fast'] is False
assert 'tests-portable-serial' in workflow['aggregate']['needs']
assert workflow['aggregate']['if']=='always()'
steps={s.get('name'):s for s in workflow['aggregate']['steps']}
check=steps['Check portable serial shard balance']['run']
aggregate=steps['Build aggregate timing summary']['run']
env=os.environ.copy();env['TMPDIR']=str(W/'tmp')

def case(name,healthy):
    root=W/name
    incoming=root/'fm-test-aggregate';incoming.mkdir(parents=True,exist_ok=True)
    env['RUNNER_TEMP']=str(root)
    if healthy: shutil.copyfile(E/'fresh-healthy-shard.json',incoming/'fm-test-timing-portable-serial-5.json')
    with (E/(name+'.txt')).open('w') as out:
        out.write('Local execution of YAML-parsed aggregate/check shell steps; GitHub download/upload actions are not simulated.\n')
        for label,script in [('Build aggregate timing summary',aggregate),('Check portable serial shard balance',check)]:
            r=subprocess.run(['/bin/bash','-c',script],capture_output=True,text=True,env=env)
            out.write(label+'\n'+r.stdout+r.stderr+f'exit={r.returncode}\n\n')
            assert r.returncode==0
            if label.startswith('Check'):
                assert ('partial 1 of 6' if healthy else '::warning::no portable serial timing JSON found; shard balance unchecked') in r.stdout
        if healthy:
            data=json.loads((root/'fm-test/fm-test-timing-aggregate.json').read_text())
            assert data['summary']['lanes']==1
            shutil.copyfile(root/'fm-test/fm-test-timing-aggregate.json',E/'fresh-aggregate.json')
    print(name+' completed')
case('workflow-zero-artifacts',False)
case('workflow-fresh-partial',True)
