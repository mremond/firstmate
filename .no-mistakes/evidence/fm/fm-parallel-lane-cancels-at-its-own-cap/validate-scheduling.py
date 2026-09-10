import hashlib, json, os, shlex, subprocess
from pathlib import Path
ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M25NFVQ8EEP6P6ZERGFSAPA4')
OUT = Path('/Users/mremond/.no-mistakes/evidence/01M25NFVQ8EEP6P6ZERGFSAPA4')
BASE = 'b1ad702fafdd03d94e5ce47cd4ba86e589ad33d6'
assert Path.cwd() == ROOT
scratch = ROOT / '.test-phase'
ignore = scratch / 'ignore'
ignore.write_text('.test-phase/\nbin/.nm-test-base.sh\n')
env = os.environ.copy()
env.update(TMPDIR=str(scratch/'tmp'), TMP=str(scratch/'tmp'), FM_HOME=str(scratch/'home'), GIT_CONFIG_GLOBAL=str(scratch/'gitconfig'), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.excludesFile', GIT_CONFIG_VALUE_0=str(ignore))
base_runner = ROOT/'bin/.nm-test-base.sh'
base_runner.write_bytes(subprocess.check_output(['git','show',BASE+':bin/fm-test-run.sh'],cwd=ROOT))
rows = []
log = (OUT/'scheduling-cli.log').open('w')
def run(runner, args, expect=0):
    command = ['/bin/bash', str(runner), *args]
    p = subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    log.write('$ '+shlex.join(command)+'\n'+p.stdout.decode()+p.stderr.decode()+f'[exit={p.returncode}]\n\n'); log.flush()
    assert p.returncode == expect, (command,p.returncode,p.stderr.decode())
    return p.stdout
head = ROOT/'bin/fm-test-run.sh'
def compare(args):
    before = run(base_runner,args)
    after = run(head,args)
    row = dict(args=args,byte_identical=before==after,sha256=hashlib.sha256(after).hexdigest(),output=after.decode())
    rows.append(row)
    assert before == after, args
    print('IDENTICAL', shlex.join(args), 'first='+repr(after.decode().splitlines()[:3]),flush=True)
try:
    families=run(head,['--list-families']).decode().splitlines()
    lanes=run(head,['--list-lanes']).decode().splitlines()
    for args in [
        ['--proven-isolated'], ['--all'], ['--changed','--base',BASE], ['--changed','--base','HEAD'],
        ['tests/fm-operational-input.test.sh','tests/fm-lint.test.sh','tests/fm-muse-harness.test.sh','tests/fm-captain-hold-lifecycle.test.sh','tests/fm-kimi-harness.test.sh','tests/fm-brief.test.sh'],
        ['--family=pure-contract-unit'], ['--all','--exclude-family','real-herdr-gated'],
    ] + [['--family',x] for x in families] + [['--lane',x] for x in lanes if not x.startswith('portable-parallel-')]:
        compare(['--list-scheduled',*args])
    for lane in lanes:
        if not lane.startswith('portable-parallel-'):
            compare(['--list','--lane',lane])
    p=[]
    for lane in ['portable-parallel-1','portable-parallel-2']:
        stored=run(head,['--list','--lane',lane])
        scheduled=run(head,['--list-scheduled','--lane',lane])
        equals_form=run(head,['--list-scheduled','--lane='+lane])
        assert stored == scheduled == equals_form
        p.append(stored.decode().splitlines())
        print(lane, 'stored order equals scheduled order:',json.dumps(p[-1]),flush=True)
    proven=run(head,['--list','--proven-isolated']).decode().splitlines()
    assert len(p[0]+p[1]) == len(set(p[0]+p[1]))
    assert set(p[0]+p[1]) == set(proven)
    assert 'tests/fm-pi-primary-types.test.sh' in p[0]
    cov=run(head,['--check-coverage']).decode()
    fields=dict(x.split('=',1) for x in cov.split() if '=' in x)
    assert fields['parallel_max_ms']=='414299'
    assert fields['parallel_imbalance_ms']=='30'
    assert fields['parallel_unhinted']=='0'
    assert fields['serial_shards']=='5'
    print(cov.strip(),flush=True)
    for invalid in [
        ['--lane','portable-parallel-3'],
        ['--lane','portable-parallel-1','--proven-isolated'],
        ['--proven-isolated','--lane','portable-parallel-1'],
        ['--lane','portable-parallel-1','--family','pure-contract-unit'],
        ['--lane','portable-parallel-1','tests/fm-brief.test.sh'],
    ]:
        output=run(head,['--list-scheduled',*invalid],expect=2)
        assert not output
        print('REFUSED',shlex.join(invalid),'exit=2, no scheduled output',flush=True)
    (OUT/'scheduling-results.json').write_text(json.dumps(dict(base=BASE,target=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),comparisons=rows,parallel_lanes=p,coverage=fields),indent=2)+'\n')
finally:
    log.close()
    base_runner.unlink()
