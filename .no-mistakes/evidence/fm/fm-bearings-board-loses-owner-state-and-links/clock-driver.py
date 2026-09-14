from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import subprocess,os,json,time
root=Path.cwd();home=root/'.test-lab/clock';state=home/'state';state.mkdir(parents=True,exist_ok=True)
(home/'data').mkdir(exist_ok=True);(home/'config').mkdir(exist_ok=True)
(state/'clock.meta').write_text('kind=ship\nharness=claude\nproject=firstmate\n')
env={**os.environ,'FM_HOME':str(home),'FM_STATE_OVERRIDE':str(state),'FM_DATA_OVERRIDE':str(home/'data'),'TZ':'Europe/Paris'}
url='https://github.com/kunchenguid/firstmate/pull/4019'
def record(u):
 r=subprocess.run([str(root/'bin/fm-pr-check.sh'),'clock',u],env=env,text=True,capture_output=True);assert r.returncode==0,r.stderr;return r.stdout
record(url);reg=state/'clock.pr-poll-registration';results=[]
for fold in [0,1]:
 dt=datetime(2025,10,26,2,30,0,tzinfo=ZoneInfo('Europe/Paris'),fold=fold);epoch=int(dt.timestamp());os.utime(reg,(epoch,epoch));output=record(url);observed=int(reg.stat().st_mtime)
 assert observed==epoch,(epoch,observed)
 results.append(dict(action='Re-record same PR during repeated daylight-saving hour',local_time=dt.isoformat(),before_epoch=epoch,after_epoch=observed,pr_url=url,output=output.strip()))
other='https://github.com/kunchenguid/firstmate/pull/4444';before=time.time();output=record(other);observed=int(reg.stat().st_mtime);assert observed>=int(before)
results.append(dict(action='Record a different PR and start a new delivery clock',pr_url=other,after_epoch=observed,output=output.strip()))
print(json.dumps(results,indent=2))
