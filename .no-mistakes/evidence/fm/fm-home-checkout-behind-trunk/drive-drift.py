import os, pathlib, subprocess, tempfile, shutil, json
root=pathlib.Path.cwd(); evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M3FC3DZXGE2K566HW6RB4MRK')
lab=pathlib.Path(tempfile.mkdtemp(prefix='.drift-live-',dir=root)); primary=lab/'primary'; home=lab/'secondmate'; parent=lab/'parent'
env={k:v for k,v in os.environ.items() if not k.startswith(('FM_','GIT_','TMUX','HERDR','STATE','CONFIG'))}
env.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_AUTHOR_NAME='Lab',GIT_AUTHOR_EMAIL='lab@example.invalid',GIT_COMMITTER_NAME='Lab',GIT_COMMITTER_EMAIL='lab@example.invalid',GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='commit.gpgsign',GIT_CONFIG_VALUE_0='false')
def run(*args,check=True):
 p=subprocess.run([str(a) for a in args],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=35)
 if check and p.returncode: raise RuntimeError((args,p.stdout,p.stderr))
 return p.stdout.strip()
def git(where,*args): return run('git','-C',where,*args)
log=[]; results=[]
def snapshot():
 return {str(p.relative_to(home)):p.read_bytes().hex() for p in home.rglob('*') if p.is_file()}
def drain(name,expect=None,absent=None):
 before=snapshot(); ph=git(primary,'rev-parse','HEAD')
 p=subprocess.run([str(root/'bin/fm-wake-drain.sh')],env=env,text=True,capture_output=True,timeout=35)
 log.append(f'### {name}\n$ bin/fm-wake-drain.sh\nexit={p.returncode}\n{p.stdout}\nSTDERR:\n{p.stderr}')
 assert p.returncode==0,(name,p.stderr)
 if expect: assert expect in p.stdout,(name,p.stdout)
 if absent: assert absent not in p.stdout,(name,p.stdout)
 assert before==snapshot(),f'{name}: home file bytes changed'
 assert ph==git(primary,'rev-parse','HEAD')
 assert run('git','-C',home,'symbolic-ref','-q','HEAD',check=False)==''
 results.append(name); log.append('Verified: every home file (including index, refs, objects and local work) unchanged; primary HEAD unchanged; home remains detached.\n')
try:
 primary.mkdir(); (parent/'state').mkdir(parents=True); (parent/'config').mkdir(); (parent/'data').mkdir()
 git(primary,'init','-q','-b','main'); (primary/'bin').mkdir(); (primary/'bin/tool').write_text('tool\n'); (primary/'AGENTS.md').write_text('v1\n'); (primary/'.gitignore').write_text('.fm-secondmate-home\n')
 git(primary,'add','.');git(primary,'commit','-qm','initial'); initial=git(primary,'rev-parse','HEAD')
 run('git','clone','-q',primary,home);git(home,'checkout','-q','--detach');(home/'.fm-secondmate-home').write_text('sm\n')
 meta=parent/'state/sm.meta'; meta.write_text(f'kind=secondmate\nhome={home}\n')
 env.update(FM_HOME=str(parent),FM_ROOT_OVERRIDE=str(primary),FM_STATE_OVERRIDE=str(parent/'state'),FM_DATA_OVERRIDE=str(parent/'data'),FM_CONFIG_OVERRIDE=str(parent/'config'),FM_PROJECTS_OVERRIDE=str(parent/'projects'),FM_BACKEND='tmux',TMUX=f'{lab}/nonexistent-socket,1,0',TMUX_TMPDIR=str(lab))
 drain('Current detached home stays quiet',absent='SECONDMATE CHECKOUT DRIFT')
 (primary/'AGENTS.md').write_text('v2\n');git(primary,'commit','-qam','advance');target=git(primary,'rev-parse','HEAD')
 drain('Missing target object reports uncertainty without fetching',expect='commit unavailable locally')
 git(home,'fetch','-q','origin')
 drain('Behind detached home warns on empty queue',expect='sm: 1 behind, 0 unique relative to primary local main')
 drain('Warning repeats while drift remains',expect='sm: 1 behind, 0 unique')
 (home/'AGENTS.md').write_text('dirty tracked work\n');(home/'untracked').write_text('preserve me\n')
 drain('Dirty tracked and untracked work are preserved',expect='sm: 1 behind, 0 unique')
 git(home,'add','AGENTS.md','untracked');git(home,'commit','-qm','unique work');unique=git(home,'rev-parse','HEAD')
 drain('Diverged detached home preserves unique commit',expect='sm: 1 behind, 1 unique')
 git(primary,'checkout','-q','--detach');git(primary,'update-ref','refs/heads/main',initial)
 drain('Cached origin warns even when primary main is stale',expect='cached origin/main (not fetched)',absent='relative to primary local main')
 run('bash','-c','. "$1"; fm_wake_append check lab "check: lab"','_',root/'bin/fm-wake-lib.sh')
 drain('Queued wake still presents drift',expect='SECONDMATE CHECKOUT DRIFT')
 assert 'check: lab' in log[-2]
 git(home,'branch','saved-unique',unique);git(home,'checkout','-q','--detach',target)
 drain('Converged home clears warning',absent='SECONDMATE CHECKOUT DRIFT');assert git(home,'rev-parse','saved-unique')==unique
 git(home,'checkout','-q','--detach',initial)
 for kind,content in [('ship',f'kind=ship\nhome={home}\n'),('remote',f'kind=secondmate\nhome={home}\nremote_host=unreachable.invalid\n'),('invalid marker',f'kind=secondmate\nhome={home}\n')]:
  meta.write_text(content)
  if kind=='invalid marker': (home/'.fm-secondmate-home').write_text('another-home\n')
  drain(f'Exclude {kind} home',absent='SECONDMATE CHECKOUT DRIFT')
 print(json.dumps({'passed':results},indent=2))
finally:
 (evidence/'drift-cli-transcript.txt').write_text('\n'.join(log))
 shutil.rmtree(lab)
