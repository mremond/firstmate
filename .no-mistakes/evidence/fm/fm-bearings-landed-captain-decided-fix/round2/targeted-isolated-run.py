from pathlib import Path
import os,subprocess,json,time
R=Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J3ZVNCRVXG5Q4HD5QXABZ')
E=Path('/Users/mremond/.no-mistakes/evidence/01M22J3ZVNCRVXG5Q4HD5QXABZ/round2')
env=os.environ.copy();env['TMPDIR']=str(R/'.test-phase-r2/tmp');env['TMUX_TMPDIR']=env['TMPDIR']
results=[]
for suite in ['legacy-isolated','fm-backlog-atomicity','fm-captain-hold-lifecycle']:
 command=['bash',str(R/'tests'/('.phase-r2-'+suite+'.sh'))]
 started=time.monotonic()
 with (E/(suite+'-selected.log')).open('w') as log:
  p=subprocess.run(command,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
 results.append({'suite':suite,'exit':p.returncode,'seconds':round(time.monotonic()-started,2),'command':command})
 (E/'targeted-isolated-results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(json.dumps(results[-1]),flush=True)
 if p.returncode: break
