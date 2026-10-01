#!/usr/bin/env python3
"""Real CLI validation; all repositories and remotes are disposable and local."""
import json, os, platform, shlex, shutil, subprocess, tempfile, traceback
from pathlib import Path
ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M3VG1WNJCRPWGC9TKGH83XQZ')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M3VG1WNJCRPWGC9TKGH83XQZ')
BASE = '589ccec821bf6310ce888e2a702e4fc9258eb1e8'
TARGET = 'f1694d030773dd3f2d41f38a8e7f5f3dc89fdb81'
ENV = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'GIT_', 'GH_', 'GITHUB_', 'TASKS_AXI_', 'TMUX', 'HERDR_'))}
ENV.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
           GIT_AUTHOR_NAME='Fleet Sync Lab', GIT_AUTHOR_EMAIL='fleet-lab@example.invalid',
           GIT_COMMITTER_NAME='Fleet Sync Lab', GIT_COMMITTER_EMAIL='fleet-lab@example.invalid',
           GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='file')
LOG = []
RESULTS = []
def note(value):
    print(value, flush=True); LOG.append(value)
def run(args, env=None, visible=False):
    args=list(map(str,args))
    p=subprocess.run(args,cwd=ROOT,env=env or ENV,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    if visible:
        note('$ '+shlex.join(args)); note('stdout:\n'+p.stdout.rstrip()); note('stderr:\n'+p.stderr.rstrip()); note('exit='+str(p.returncode))
    if p.returncode: raise RuntimeError(shlex.join(args)+'\n'+p.stdout+p.stderr)
    return p.stdout.strip()
def git(repo,*args): return run(['git','-C',repo,*args])
def commit(repo, text):
    (repo/'payload.txt').write_text(text+'\n')
    git(repo,'add','payload.txt'); git(repo,'commit','-qm',text)
def create_pair(parent,name,clone):
    work=parent/(name+'-writer'); remote=parent/(name+'.git')
    run(['git','init','-q','-b','main',work]); commit(work,'version 0')
    run(['git','clone','--bare','--quiet',work,remote])
    git(work,'remote','add','origin',remote.as_uri())
    run(['git','clone','--quiet',remote.as_uri(),clone])
    return {'work':work,'remote':remote,'clone':clone}
def advance(pair,text):
    commit(pair['work'],text); git(pair['work'],'push','--quiet','origin','main')
    return git(pair['work'],'rev-parse','HEAD')
def state(pair):
    c=pair['clone']
    return {'HEAD':git(c,'rev-parse','HEAD'), 'origin/main':git(c,'rev-parse','origin/main'),
            'branch':git(c,'symbolic-ref','--short','HEAD'), 'status':git(c,'status','--porcelain'),
            'payload':(c/'payload.txt').read_text().strip()}
def sync(home,*args,script=None):
    env=ENV|{'FM_HOME':str(home)}
    note('FM_HOME='+str(home))
    return run([script or ROOT/'bin/fm-fleet-sync.sh',*args],env=env,visible=True)
def passed(name):
    RESULTS.append({'name':name,'result':'pass','live':True}); note('SCENARIO PASS: '+name)
def marked_home(path):
    run([ROOT/'bin/fm-lab-home.sh','create',path]); return path
def identity(path):
    top=git(path,'rev-parse','--show-toplevel')
    pwd=run(['bash','-c','cd "$1" && pwd -P','_',path])
    note(json.dumps({'access':str(path),'git_toplevel':top,'pwd_P':pwd,
                     'same_spelling':top==pwd,'same_filesystem_object':os.path.samefile(top,pwd)},indent=2))
    return top,pwd
old_path=None
try:
    assert run(['git','rev-parse','HEAD']) == TARGET
    note('Product target: '+TARGET+'; tree: '+run(['git','rev-parse','HEAD^{tree}']))
    note('Baseline: '+BASE+'; OS: '+platform.system()+' '+platform.release())
    note(run(['git','--version'])); note('Git executable: '+shutil.which('git'))
    with tempfile.TemporaryDirectory(prefix='.FleetSyncLive-',dir=ROOT) as td:
        lab=Path(td); (lab/'tmp').mkdir(); (lab/'gh').mkdir(); (lab/'xdg').mkdir()
        ENV.update(TMPDIR=str(lab/'tmp'),GH_CONFIG_DIR=str(lab/'gh'),XDG_CONFIG_HOME=str(lab/'xdg'))
        fd,oldname=tempfile.mkstemp(prefix='.fm-fleet-before-',suffix='.sh',dir=ROOT/'bin')
        old_path=Path(oldname)
        with os.fdopen(fd,'w') as f: f.write(run(['git','show',BASE+':bin/fm-fleet-sync.sh'])+'\n')
        old_path.chmod(0o700)

        note('\n=== 1. Case-mismatched home, whole-fleet refresh, original then fixed ===')
        home=marked_home(lab/'RecordedHome'); alias=lab/'recordedhome'
        assert alias.is_dir() and os.path.samefile(home,alias)
        pairs=[create_pair(lab,n,home/'projects'/n) for n in ['alpha','beta']]
        before=[state(p) for p in pairs]; tips=[advance(p,'version 1') for p in pairs]
        for p in pairs:
            top,pwd=identity(alias/'projects'/p['clone'].name)
            assert top != pwd and os.path.samefile(top,pwd)
        note('Before original:\n'+json.dumps(before,indent=2))
        oldout=sync(alias,script=old_path)
        assert oldout.count('skipped: not a clone root') == 2
        assert [state(p) for p in pairs] == before
        note('Original guard reproduced: both valid clones skipped; HEAD and remote tracking refs stayed stale.')
        newout=sync(alias)
        assert newout.count(': synced ') == 2 and 'not a clone root' not in newout
        after=[state(p) for p in pairs]; note('After fixed:\n'+json.dumps(after,indent=2))
        assert all(s['HEAD']==s['origin/main']==tip and s['payload']=='version 1' and not s['status'] for s,tip in zip(after,tips))
        passed('Case-mismatched home refreshes every clone; original guard reproduced first')

        note('\n=== 2. Single-project selection and current-clone behavior ===')
        p=pairs[0]
        for arg,label in [('alpha','bare project name'),('projects/alpha','projects-relative name'),(str(alias/'projects'/'alpha'),'absolute alternate-case path')]:
            tip=advance(p,'single '+label); out=sync(alias,arg)
            assert ': synced ' in out and state(p)['HEAD']==tip
            note('Persisted state:\n'+json.dumps(state(p),indent=2))
        prior=state(p); out=sync(alias,'alpha')
        assert 'alpha: already current' in out and state(p)==prior
        passed('Single-project name, projects-relative and absolute paths sync; repeated refresh is unchanged')

        note('\n=== 3. A symlinked clone and symlinked home still sync ===')
        home=marked_home(lab/'LinkHome'); real=lab/'PhysicalClone'
        p=create_pair(lab,'symlink-origin',real)
        (home/'projects'/'linked').symlink_to(real,target_is_directory=True)
        home_alias=lab/'HomeAlias'; home_alias.symlink_to(home,target_is_directory=True)
        tip=advance(p,'symlink update'); identity(home_alias/'projects'/'linked')
        out=sync(home_alias)
        assert 'linked: synced ' in out and state(p)['HEAD']==tip
        note('Persisted state:\n'+json.dumps(state(p),indent=2))
        passed('Symlinked home and clone retain fast-forward behavior')

        note('\n=== 4. Nested directories cannot fetch, prune or update an enclosing repository ===')
        outer=create_pair(lab,'enclosing',lab/'EnclosingHome'); home=outer['clone']
        for name in ['state','data','config','projects']: (home/name).mkdir()
        (home/'.git'/'info'/'exclude').write_text('/state/\n/data/\n/config/\n/projects/\n')
        sub=home/'projects'/'not-a-clone'; sub.mkdir()
        (home/'projects'/'linked-subdir').symlink_to(sub,target_is_directory=True)
        git(outer['work'],'push','--quiet','origin','main:refs/heads/merged-feature')
        git(home,'fetch','--quiet','origin'); git(home,'branch','--track','merged-feature','origin/merged-feature')
        git(outer['work'],'push','--quiet','origin','--delete','merged-feature')
        advance(outer,'enclosing pending update')
        alias=lab/'enclosinghome'; prior=state(outer); refs=git(home,'show-ref')
        assert not prior['status']; note('Protected enclosing state:\n'+json.dumps(prior,indent=2)); note('Protected refs:\n'+refs)
        for args in [(),('not-a-clone',),('projects/not-a-clone',),(str(alias/'projects'/'not-a-clone'),),('linked-subdir',)]:
            out=sync(alias,*args)
            assert 'skipped: not a clone root' in out and ': synced ' not in out
            assert state(outer)==prior and git(home,'show-ref')==refs
        note('After every attempted refresh, HEAD, origin/main, merged-feature and origin/merged-feature were byte-for-byte unchanged.')
        passed('Fleet and direct refresh reject nested directories and symlinks without touching the enclosing repository')

        note('\n=== 5. Other protections remain active through alternate-case homes ===')
        home=marked_home(lab/'SafetyHome'); alias=lab/'safetyhome'
        dirty=create_pair(lab,'dirty',home/'projects'/'dirty')
        topic=create_pair(lab,'topic',home/'projects'/'topic')
        local=create_pair(lab,'local',home/'projects'/'local')
        for p in [dirty,topic,local]: advance(p,'origin update')
        (dirty['clone']/'payload.txt').write_text('uncommitted operator work\n')
        git(topic['clone'],'checkout','-qb','in-progress'); commit(topic['clone'],'unlanded work')
        (home/'data'/'projects.md').write_text('- local [local-only] - isolated local project (added 2026-10-01)\n')
        prior=[state(p) for p in [dirty,topic,local]]; note('Before safeguards:\n'+json.dumps(prior,indent=2))
        out=sync(alias)
        assert 'dirty: STUCK:' in out and 'topic: STUCK:' in out and 'local: skipped: local-only project' in out
        after=[state(p) for p in [dirty,topic,local]]; note('After safeguards:\n'+json.dumps(after,indent=2))
        for a,b in zip(prior,after):
            for key in ['HEAD','branch','status','payload']: assert a[key]==b[key]
        assert prior[2]==after[2]
        passed('Alternate-case access preserves dirty work, non-default branches and local-only exclusion')
        old_path.unlink(); old_path=None
    note('Cleanup complete: all disposable homes, local origins, writer clones and original-script copy removed.')
except Exception:
    note(traceback.format_exc()); raise
finally:
    if old_path: old_path.unlink(missing_ok=True)
    (EVIDENCE/'fleet-sync-live.log').write_text('\n'.join(LOG)+'\n')
    (EVIDENCE/'fleet-sync-live-results.json').write_text(json.dumps({'target':TARGET,'baseline':BASE,'scenarios':RESULTS},indent=2)+'\n')
