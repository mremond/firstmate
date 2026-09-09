from pathlib import Path
import os,subprocess,time,json,signal
R=Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J3ZVNCRVXG5Q4HD5QXABZ')
E=Path('/Users/mremond/.no-mistakes/evidence/01M22J3ZVNCRVXG5Q4HD5QXABZ')
L=R/'.test-local/live'
trans=[]
for name,args in [('local',['fm-merge-local.sh','same-id']),('pr',['fm-pr-merge.sh','same-id','https://github.com/kunchenguid/firstmate/pull/4048'])]:
 h=L/('lock-'+name)
 for d in ['state','data','config','projects']: (h/d).mkdir(parents=True,exist_ok=True)
 (h/'state').chmod(0o700)
 m=h/'state/same-id.meta'
 # A missing project is deliberate: even a broken guard cannot reach a forge mutation.
 m.write_text(f'window=firstmate:fm-same-id\nproject={h}/projects/unavailable\nworktree={h}/projects/unavailable-work\nmode=local-only\nkind=ship\nharness=codex\nspawn_gen=original-incarnation\n');m.chmod(0o600)
 env=os.environ.copy()
 for k in list(env):
  if k.startswith(('FM_','TASKS_AXI_')) or k=='TMUX': env.pop(k,None)
 env.update(FM_HOME=str(h),FM_ROOT_OVERRIDE=str(L/'code-root'),FM_STATE_OVERRIDE=str(h/'state'),FM_DATA_OVERRIDE=str(h/'data'),FM_CONFIG_OVERRIDE=str(h/'config'),FM_PROJECTS_OVERRIDE=str(h/'projects'),HOME=str(L/'user-home'),TMPDIR=str(R/'.test-local/tmp'),TMUX_TMPDIR=str(R/'.test-local/tmp'),FM_GATE_REFUSE_BYPASS='1')
 lock=h/'state/.control-same-id.lock';ready=h/'ready';release=h/'release'
 script='. "$1/bin/fm-wake-lib.sh"; fm_lock_acquire_wait "$2"; trap \'fm_lock_release "$2"\' EXIT; : > "$3"; while [ ! -e "$4" ]; do sleep 0.1; done'
 holder=subprocess.Popen(['bash','-c',script,'_',str(R),str(lock),str(ready),str(release)],env=env,cwd=h,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 merge=None
 try:
  deadline=time.monotonic()+20
  while not ready.exists():
   assert holder.poll() is None
   assert time.monotonic()<deadline,'lock acquisition timed out'
   time.sleep(.1)
  merge=subprocess.Popen([str(R/'bin'/args[0]),*args[1:]],env=env,cwd=h,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  # Observe the actual merge's direct sleep child while the genuine lock is held.
  deadline=time.monotonic()+30;blocked=False
  while time.monotonic()<deadline:
   assert merge.poll() is None,'merge returned before waiting'
   lines=subprocess.check_output(['ps','-axo','pid,ppid,comm'],text=True).splitlines()[1:]
   for line in lines:
    f=line.split(None,2)
    if len(f)==3 and f[1]==str(merge.pid) and Path(f[2]).name=='sleep': blocked=True
   if blocked: break
   time.sleep(.1)
  assert blocked,'could not observe lock wait'
  m.write_text(m.read_text().replace('original-incarnation','replacement-incarnation'))
  release.touch();holder.communicate(timeout=20)
  out,err=merge.communicate(timeout=30)
  assert merge.returncode==1 and 'changed incarnation while waiting to merge' in err,(merge.returncode,out,err)
  assert 'spawn_gen=replacement-incarnation' in m.read_text()
  assert not lock.exists()
  trans.append({'entrypoint':args[0],'observed_real_lock_wait':True,'record_change':'original-incarnation -> replacement-incarnation','exit':merge.returncode,'stdout':out,'stderr':err,'replacement_metadata_preserved':True,'lock_released':True})
 finally:
  release.touch()
  if holder.poll() is None: holder.terminate();holder.communicate(timeout=20)
  if merge is not None and merge.poll() is None: merge.terminate();merge.communicate(timeout=20)
(E/'incarnation-refusals.json').write_text(json.dumps(trans,indent=2)+'\n')
print(json.dumps(trans,indent=2))
