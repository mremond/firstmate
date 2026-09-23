import os, subprocess, sys, time, shlex, json
from pathlib import Path
root=Path.cwd()
ev=Path('/Users/mremond/.no-mistakes/evidence/01M376W5NAHHKMBQ2ZYP9Z988Y')
label=sys.argv[1]
cmd=sys.argv[2:]
env=os.environ.copy()
env.update(TMPDIR=str(root/'.claim-test-runtime/tmp'),GH_PAGER='cat',GH_PROMPT_DISABLED='1')
if label!='behavioral-baseline':
    env['PATH']=str(root/'.claim-test-runtime/bin')+os.pathsep+env['PATH']
    env['CLAIM_API_LOG']=str(ev/(label+'-api.jsonl'))
start=time.monotonic()
p=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
output='$ '+shlex.join(cmd)+'\n'+p.stdout+'\nExit: '+str(p.returncode)+'\nElapsed: '+str(round(time.monotonic()-start,2))+'s\n'
(ev/(label+'.txt')).write_text(output)
print(output,flush=True)
sys.exit(p.returncode)
