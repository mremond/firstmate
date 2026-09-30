import os, sys, json, subprocess, pathlib, socket, time, hashlib, shutil
ROOT=pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M3RP354ZWC7R9HH16YWXQDGZ')
EVID=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M3RP354ZWC7R9HH16YWXQDGZ')
RUNTIME=ROOT/'.gate-test-runtime'
CTX=RUNTIME/'live-context.json'
BASE={k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ['TASKS_AXI_FILE','TASKS_AXI_BACKEND','TMUX','TREEHOUSE_ROOT','TREEHOUSE_LEASE_HOLDER']}
BASE.update(TMPDIR=str(RUNTIME/'tmp'),GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null',GIT_AUTHOR_NAME='Lab',GIT_AUTHOR_EMAIL='lab@example.invalid',GIT_COMMITTER_NAME='Lab',GIT_COMMITTER_EMAIL='lab@example.invalid',LAVISH_AXI_NO_OPEN='1',LAVISH_AXI_HOST='127.0.0.1',LAVISH_AXI_LINK_HOST='127.0.0.1',LAVISH_AXI_TELEMETRY='off',LAVISH_AXI_STATE_DIR=str(RUNTIME/'lavish'),FM_PROCEVENT_CLAIM_ROOT=str(RUNTIME/'live-claims'),TREEHOUSE_ROOT=str(RUNTIME/'pool'))
if CTX.exists():
    C=json.loads(CTX.read_text()); BASE.update(LAVISH_AXI_PORT=str(C['port']),TMUX_TMPDIR=C['tmuxdir'],TMUX=C['tmux'])
else: C={}
def run(args,home=None,check=True,cwd=ROOT,extra=None,timeout=60):
    env=BASE.copy()
    if home: env['FM_HOME']=str(home)
    if extra: env.update(extra)
    p=subprocess.run([str(x) for x in args],cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    text=f'$ {" ".join(str(x) for x in args)}'+(f' [FM_HOME={home}]' if home else '')+f'\n{p.stdout}\nexit={p.returncode}\n'
    with (EVID/'live-transcript.log').open('a') as f: f.write(text)
    print(text,flush=True)
    if check and p.returncode: raise RuntimeError(text)
    return p
def lab(name):
    h=RUNTIME/name;run(['bin/fm-lab-home.sh','create',h]);return h
def task(h,name='finished',kind='ship',worktree=None,project=None,**kwargs):
    values=dict(window='fm-lab:fm-'+name,endpoint_task_id=name,worktree=worktree or h/('gone-'+name),project=project or h/'projects/demo',kind=kind,mode='local-only',spawn_gen='lab-'+name,**kwargs)
    (h/'data'/name).mkdir(parents=True,exist_ok=True)
    (h/'state'/f'{name}.meta').write_text(''.join(f'{k}={v}\n' for k,v in values.items()))
    (h/'state'/'.last-watcher-beat').touch()
    return name
def board(file,title='Teardown lifecycle lab'):
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>'+title+'</title><body><h1>'+title+'</h1><p>Synthetic review board for isolated teardown validation.</p></body></html>')
    run(['lavish-axi',file,'--no-open'])
    return file
def state(file):
    s=json.loads((RUNTIME/'lavish/state.json').read_text())
    return next(v for v in s['sessions'].values() if v['file']==str(file))
def snapshot(label):
    src=RUNTIME/'lavish/state.json'
    if src.exists(): shutil.copyfile(src,EVID/(label+'-sessions.json'))
def arm(h,t,file):
    run(['bin/fm-procevent-lavish.sh','arm',file,'--for',t],h)
    return run(['bin/fm-procevent-lavish.sh','source-id',file],h).stdout.strip()
def register(h,t,file):
    sid=run(['bin/fm-procevent-lavish.sh','source-id',file],h).stdout.strip()
    run(['bin/fm-procevent.sh','register-task','lavish',sid,t,'--',ROOT/'bin/fm-procevent-lavish.sh','poll',file],h)
    return sid
def teardown(h,t='finished',force=False,check=True):
    return run(['bin/fm-teardown.sh',t]+(['--force'] if force else []),h,check=check,timeout=120)
def save(): CTX.write_text(json.dumps(C,indent=2))
def result(name,**data):
    with (EVID/'live-results.jsonl').open('a') as f:f.write(json.dumps(dict(name=name,**data))+'\n')
if __name__=='__main__' and sys.argv[1]=='setup':
    sock=socket.socket();sock.bind(('127.0.0.1',0));C['port']=sock.getsockname()[1];sock.close();BASE['LAVISH_AXI_PORT']=str(C['port'])
    h=lab('controller');C['controller']=str(h)
    C['tmuxdir']=run(['bin/fm-lab-home.sh','tmux-dir',h]).stdout.strip();BASE['TMUX_TMPDIR']=C['tmuxdir']
    run(['tmux','-L','fm-lab','new-session','-d','-s','fm-lab','-x','100','-y','30','-c',ROOT,'sleep','3600'])
    C['tmux']=run(['tmux','-L','fm-lab','display-message','-p','#{socket_path},#{pid},0']).stdout.strip();BASE['TMUX']=C['tmux']
    task(h,tasktmp=h/'scratch')
    C['data_board']=str(board(h/'data/finished/board.html','Finished task review'))
    C['scratch_board']=str(board(h/'scratch/board.html','Scratch review'))
    C['registered_board']=str(board(h/'shared/review.html','Registered outside task roots'))
    C['bystander']=str(board(h/'data/another-task/board.html','Unrelated review stays open'))
    C['already_ended']=str(board(h/'data/finished/already-ended.html','Previously ended review'))
    run(['lavish-axi','end',C['already_ended']])
    C['source']=arm(h,'finished',pathlib.Path(C['registered_board']))
    C['hashes']={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in [C['data_board'],C['registered_board']]}
    snapshot('before-cleanup');save()
