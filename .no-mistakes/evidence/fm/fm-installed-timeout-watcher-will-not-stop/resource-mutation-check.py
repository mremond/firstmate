from pathlib import Path
import os,shutil,subprocess,json,time
root=Path.cwd(); ev=Path('/Users/mremond/.no-mistakes/evidence/01M2JEJPE43XFXJCGYM3KFAX75')
copy=root/'.nm-test-phase/resource-mutant/bin'
shutil.copytree(root/'bin',copy,dirs_exist_ok=True)
source=(root/'bin/fm-wake-lib.sh').read_text()
mutated=source.replace('ownerdir=$(fm_lock_owner_dir "$lockdir") || return 2','ownerdir=$(fm_lock_owner_dir "$lockdir") || return 1').replace('  [ "$rc" -eq 1 ] || return 1\n','')
(copy/'fm-wake-lib.sh').write_text(mutated)
s=(root/'tests/fm-watcher-lock.test.sh').read_text(); s=s[:s.rindex('\ntest_singleton_start\n')]
selections=['test_lock_resource_failure_returns','test_shutdown_is_bounded_when_state_is_unwritable']
results=[]
env=os.environ.copy();env['TMPDIR']=str(root/'.nm-test-phase/tmp')
for mode in ('mutant','restored'):
    if mode=='restored': (copy/'fm-wake-lib.sh').write_text(source)
    for case in selections:
        p=root/'tests/.nm-phase-resource-mutation.sh'
        p.write_text(s+'\nWATCH="'+str(copy/'fm-watch.sh')+'"\nLIB="'+str(copy/'fm-wake-lib.sh')+'"\n'+case+' || exit $?\n')
        t=time.monotonic(); r=subprocess.run(['bash',str(p)],env=env,capture_output=True,text=True,timeout=70)
        output=r.stdout+r.stderr
        (ev/(mode+'-'+case+'.log')).write_text(output)
        expected='lock acquisition did not return on owner-directory creation failure' if case==selections[0] else 'signaled watcher did not stop after owner-directory creation failed'
        assert (r.returncode!=0 and expected in output) if mode=='mutant' else r.returncode==0, output
        row={'mode':mode,'case':case,'exit':r.returncode,'seconds':round(time.monotonic()-t,3),'output':output.strip()}
        results.append(row); print(json.dumps(row),flush=True)
        (ev/'resource-mutation-results.json').write_text(json.dumps(results,indent=2)+'\n')
