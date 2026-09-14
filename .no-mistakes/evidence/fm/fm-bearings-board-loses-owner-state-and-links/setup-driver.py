from pathlib import Path
import subprocess,os,time,json
root=Path.cwd(); lab=root/'.test-lab'; main=lab/'main'; mate=lab/'mate'
for home in [main,mate,lab/'code-root']:
 for d in ['state','data','projects','config','bin']:(home/d).mkdir(parents=True,exist_ok=True)
 (home/'config/backlog-backend').write_text('manual\n')
(mate/'AGENTS.md').write_text((root/'AGENTS.md').read_text())
(mate/'.fm-secondmate-home').write_text('mate\n')
(main/'data/secondmates.md').write_text(f'- mate - isolated review (home: {mate}; scope: firstmate; projects: firstmate; added 2026-09-14)\n')
(main/'state/mate.meta').write_text(f'kind=secondmate\nharness=claude\nhome={mate}\nprojects=firstmate\nwindow=bearings-validation:mate\n')
for home,prefix in [(main,'main'),(mate,'mate')]:
 rows=[]
 for suffix,title,status,pr,age,hold in [
  ('work','In-flight delivery review','done: review ready for captain approval',4019,None,''),
  ('old','Delivery awaiting outside maintainer','paused: waiting on outside maintainer',4019,21,''),
  ('young','Recently delivered request','paused: waiting on outside maintainer',4019,2,''),
  ('approval','Approval remains unanswered','needs-decision [key=approval]: approval required\npaused: declared outside wait',4019,21,''),
  ('held','Waiting for a dependency','paused: release dependency pending',2,None,' (hold: dependency https://github.com/acme/repo/pull/99 remains under review) (hold-kind: external)'),
  ('unrecorded','No recorded request link','paused: dependency https://github.com/acme/repo/pull/99 is pending',None,None,' (hold: dependency https://github.com/acme/repo/pull/99 remains under review) (hold-kind: external)')
 ]:
  task=f'{prefix}-{suffix}'; rows.append(f'- [ ] {task} - {title} (repo: firstmate) (kind: ship){hold} (since 2026-09-14)')
  meta=home/f'state/{task}.meta'
  meta.write_text(f'worktree={home}/projects\nkind=ship\nharness=claude\nmode=local-only\nproject=firstmate\nwindow=bearings-validation:{task}\n'+(f'pr=https://github.com/'+('kunchenguid/firstmate' if pr==4019 else 'acme/repo')+f'/pull/{pr}\n' if pr else ''))
  (home/f'state/{task}.status').write_text(status+'\n')
  if age is not None:
   env={**os.environ,'FM_HOME':str(home),'FM_STATE_OVERRIDE':str(home/'state'),'FM_DATA_OVERRIDE':str(home/'data')}
   subprocess.run([str(root/'bin/fm-pr-check.sh'),task,'https://github.com/kunchenguid/firstmate/pull/4019'],env=env,check=True)
   stamp=time.time()-age*86400
   os.utime(home/f'state/{task}.pr-poll-registration',(stamp,stamp))
 (home/'data/backlog.md').write_text('## In flight\n'+'\n'.join(rows)+'\n\n## Queued\n\n## Done\n')
