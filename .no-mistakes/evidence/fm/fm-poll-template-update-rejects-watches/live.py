import os, pathlib, subprocess, shutil
root=pathlib.Path.cwd(); base=root/'.test-tmp/live'; base.mkdir(parents=True)
env=os.environ.copy()
for k in list(env):
 if k.startswith(('FM_', 'NO_MISTAKES','TASKS_AXI')): env.pop(k)
env.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_AUTHOR_NAME='Lab',GIT_AUTHOR_EMAIL='lab@example.invalid',GIT_COMMITTER_NAME='Lab',GIT_COMMITTER_EMAIL='lab@example.invalid',TMPDIR=str(root/'.test-tmp'))
url='https://github.com/kunchenguid/firstmate/pull/5427'
def run(args,cwd=None,e=None,ok=True):
 p=subprocess.run([str(x) for x in args],cwd=cwd,env=e or env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if p.returncode and ok: raise RuntimeError(f'{args}: {p.stdout}')
 return p
for route in ['update','fleet','secondmate','secondmate-redundant','fleet-recover-current','fleet-recover-ff']:
 d=base/route; d.mkdir(); r=d/'root'; r.mkdir(); h=d/'home'; s=h/'state'
 for n in ['state','data','config']: (h/n).mkdir(parents=True,exist_ok=True)
 shutil.copytree(root/'bin',r/'bin'); (r/'AGENTS.md').write_text('lab\n'); (r/'.gitignore').write_text('/state/\n/data/\n/config/\n/.fm-secondmate-home\n/.fm-secondmate-parent\n')
 def git(*a, at=r): return run(['git', '-C',at,*a]).stdout.strip()
 git('init','-q','-b','main'); git('add','.'); git('commit','-qm','initial'); git('clone','-q','--bare',r,d/'origin.git'); git('remote','add','origin',d/'origin.git'); git('clone','-q',d/'origin.git',d/'upstream'); u=d/'upstream'
 old=git('rev-parse','HEAD'); e=env|{'FM_HOME':str(h),'FM_ROOT_OVERRIDE':str(r)}
 for ident in ['good-a','good-b','tampered','unregistered','swapped','sidecar','metadata']:
  (s/f'{ident}.meta').write_text(f'worktree={r}\nkind=ship\nmode=no-mistakes\n')
  p=run([r/'bin/fm-pr-check.sh',ident,url],e=e)
  print(f'{route} arm {ident}: {p.stdout.strip()}',flush=True)
 (s/'tampered.check.sh').write_text((s/'tampered.check.sh').read_text()+'\nexit 99\n')
 (s/'unregistered.pr-poll-registration').unlink()
 shutil.copyfile(s/'swapped.check.sh',s/'replacement'); os.replace(s/'replacement',s/'swapped.check.sh')
 with (s/'sidecar.pr-poll').open('a') as f: f.write('unexpected\n')
 with (s/'metadata.meta').open('a') as f: f.write('pr=https://github.com/kunchenguid/firstmate/pull/1\n')
 if route.startswith('secondmate'):
  git('clone','-q',d/'origin.git',d/'parent'); shutil.move(s,r/'state'); s=r/'state'; (h/'state').mkdir(); (h/'state/sentinel').write_text('preserved')
  (r/'.fm-secondmate-home').write_text('child\n'); (r/'.fm-secondmate-parent').write_text(f'schema=fm-secondmate-parent.v1\nroute=local\nparent_home={h}\n')
  (h/'data/secondmates.md').write_text(f'- child - domain supervisor (home: {r}; scope: fixture; projects: p; added 2026-09-26)\n')
 if route=='secondmate-redundant':
  (r/'landed').write_text('landed\n'); git('add','landed'); git('commit','-qm','redundant'); old=git('rev-parse','HEAD'); shutil.copyfile(r/'landed',u/'landed'); git('add','landed',at=u)
 with (u/'bin/fm-pr-poll.sh').open('a') as f: f.write('\n# Live lab template update\n')
 git('add','bin/fm-pr-poll.sh',at=u); git('commit','-qm','template-update',at=u)
 if route.startswith('fleet-recover'):
  git('fetch','-q',u,'main'); git('checkout','-q','--detach',old); git('branch','-f','main','FETCH_HEAD')
  if route=='fleet-recover-ff':
   with (u/'bin/fm-pr-poll.sh').open('a') as f: f.write('\n# Second update\n')
   git('add','.',at=u); git('commit','-qm','second-update',at=u)
 git('push','-q','origin','main',at=u)
 cmd=[r/'bin/fm-update.sh']
 if route.startswith('fleet'): cmd=[r/'bin/fm-fleet-sync.sh',r]
 if route.startswith('secondmate'): cmd=[d/'parent/bin/fm-update.sh']; e=e|{'FM_ROOT_OVERRIDE':str(d/'parent')}
 p=run(cmd,e=e); print(f'\n{route} PUBLIC UPDATE:\n{p.stdout}',flush=True)
 assert git('rev-parse','HEAD')!=old
 auth='source "$1/bin/fm-pr-lib.sh"; fm_pr_poll_artifacts_valid "$2" "$3" "$1/bin/fm-pr-poll.sh"'
 for ident in ['good-a','good-b','tampered','unregistered','swapped','sidecar','metadata']:
  p=run(['bash','-c',auth,'lab',r,s,ident],ok=False); valid=p.returncode==0
  assert valid==ident.startswith('good'),(route,ident,p.stdout)
  print(f'{route} strict authentication {ident}: {valid}',flush=True)
  if valid:
   p=run(['bash',r/'bin/fm-pr-poll.sh','--validated','github',url,'github.com','kunchenguid/firstmate','5427']); assert p.stdout.strip()=='merged'; print(f'{route} real GitHub poll {ident}: {p.stdout.strip()}',flush=True)
 before=(s/'good-a.check.sh').stat().st_ino
 p=run([r/'bin/fm-pr-poll-refresh.sh',old],e=env|{'FM_HOME':str(s.parent),'FM_ROOT_OVERRIDE':str(r)},ok=False)
 assert (s/'good-a.check.sh').stat().st_ino==before
 print(f'{route} repeated refresh preserves valid file identity; invalid controls remain rejected',flush=True)
 if route.startswith('secondmate'): assert (h/'state/sentinel').read_text()=='preserved'; assert not (h/'state/good-a.check.sh').exists()
 print(f'{route}: PASS\n',flush=True)
shutil.rmtree(base)
