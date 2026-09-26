import os, pathlib, shutil, subprocess, tempfile, json, sys
root=pathlib.Path.cwd()
evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M3EC24T63HR32WT30NNZS917')
work=pathlib.Path(tempfile.mkdtemp(prefix='.origin-live-',dir=root))
code=work/'code'
code.mkdir()
shutil.copytree(root/'bin',code/'bin')
baseline='--baseline' in sys.argv
if baseline:
 for name in ['fm-home-seed.sh','fm-remote-home-seed.sh']:
  old=subprocess.check_output(['git','show','9b52cf5e9eed6af70648bc5445b786ece2d22cdc:bin/'+name])
  (code/'bin'/name).write_bytes(old)
env={k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_','GIT_'))}
env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0',GIT_AUTHOR_NAME='QA',GIT_AUTHOR_EMAIL='qa@example.invalid',GIT_COMMITTER_NAME='QA',GIT_COMMITTER_EMAIL='qa@example.invalid',TMPDIR=str(work))
parts=['qa-fiction-user','qa-fiction-password','example.invalid','/fiction.git']
origin=f'https://{parts[0]}:{parts[1]}@{parts[2]}{parts[3]}'
refused=origin.replace('example.invalid/','example.invalid:notaport/')
def run(args, e=env):
 return subprocess.run(list(map(str,args)),env=e,text=True,capture_output=True)
def git(*args):
 p=run(['git',*args]); assert p.returncode==0,p.stderr
 return p.stdout.strip()
def init(p):
 p.mkdir(parents=True);git('init','-q',p);git('-C',p,'commit','--allow-empty','-qm','fixture')
results=[]
try:
 for case in ['mismatch','missing','remote-argument','remote-clone','destination-credential','matching']:
  home=work/(case+'-parent');dst=work/(case+'-child')
  (home/'data').mkdir(parents=True)
  (home/'data/projects.md').write_text('- alpha [direct-PR] - QA project (added 2026-09-26)\n')
  src=home/'projects/alpha';init(src)
  source_origin=refused if case=='remote-clone' else origin
  git('-C',src,'remote','add','origin',source_origin)
  e=env|{'FM_HOME':str(home),'FM_SECONDMATE_CHARTER':'Disposable origin diagnostic validation','FM_BACKEND':'tmux'}
  if case.startswith('remote-'):
   args=[code/'bin/fm-remote-home-seed.sh','design','unused-qa-host','/srv/qa-root','/srv/qa-home','alpha='+refused if case=='remote-argument' else 'alpha']
  else:
   (dst/'bin').mkdir(parents=True);shutil.copy(root/'AGENTS.md',dst/'AGENTS.md')
   target=dst/'projects/alpha';init(target)
   if case!='missing': git('-C',target,'remote','add','origin',origin if case in ['matching','destination-credential'] else 'https://other.invalid/other.git')
   if case=='destination-credential':git('-C',src,'remote','set-url','origin','https://other.invalid/other.git')
   args=[code/'bin/fm-home-seed.sh','design',dst,'alpha']
  p=run(args,e)
  text=p.stdout+p.stderr
  expected={'mismatch':'has a different origin','missing':'has no origin remote','remote-argument':'check the origin you passed','remote-clone':'inspect the origin of the clone','destination-credential':'has a different origin'}
  ok=(p.returncode==0 if case=='matching' else p.returncode!=0 and expected[case] in text) and not any(part in text for part in parts)
  if case=='matching':ok=ok and (dst/'.fm-secondmate-home').exists() and git('-C',dst/'projects/alpha','remote','get-url','origin')==origin
  else:ok=ok and not (home/'data/secondmates.md').exists()
  log=f'Executable: {args[0].name}\nScenario: {case}\nExit: {p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}\nCredential components absent: {not any(part in text for part in parts)}\nAssertions passed: {ok}\n'
  (evidence/(('baseline-' if baseline else '')+case+'.txt')).write_text(log)
  results.append({'scenario':case,'pass':ok,'exit':p.returncode})
 print(json.dumps(results,indent=2))
finally:shutil.rmtree(work)
