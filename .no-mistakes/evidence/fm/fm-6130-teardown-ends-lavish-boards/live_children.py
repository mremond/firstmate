from live_scenarios import *
code=RUNTIME/'code'
if not code.exists():
    code.mkdir();shutil.copytree(ROOT/'bin',code/'bin')
    # Every copied executable is byte-identical to the validated worktree.
    assert all(p.read_bytes()==(ROOT/'bin'/p.relative_to(code/'bin')).read_bytes() for p in (code/'bin').rglob('*') if p.is_file())

parent=lab('parent');child=lab('child-home');foreign=lab('child-foreign')
(child/'.fm-secondmate-home').write_text('secondmate\n')
shutil.copytree(ROOT/'bin',child/'bin')
p=project('children-project')
task(parent,'secondmate',kind='secondmate',worktree=child,project=p,home=child)
task(foreign,'reviewer')
boards={};ids={}
for name in ['worker','held-worker','foreign-worker']:
    wt=RUNTIME/(name+'-wt')
    run(['git','-C',p,'worktree','add','-qb','fm-'+name,wt,'main'])
    task(child,name,worktree=wt,project=p,tasktmp=RUNTIME/(name+'-scratch'))
    boards[name]=board(wt/'.lavish/review.html',name+' review')
    boards[name+'-data']=board(child/'data'/name/'review.html',name+' data review')
    boards[name+'-shared']=board(RUNTIME/(name+'-shared.html'),name+' outside roots')
    boards[name+'-scratch']=board(RUNTIME/(name+'-scratch')/'review.html',name+' scratch review')
    if name=='held-worker':hold(child,name)
    if name=='foreign-worker':
        for key in [name,name+'-shared']:
            if key.endswith('-shared'):register(child,name,boards[key])
            ids[key]=arm(foreign,'reviewer',boards[key])
    else:ids[name]=arm(child,name,boards[name+'-shared'])
# A hold in the parent must not protect a finished worker in the child home.
hold(parent,'worker')
before={key:(RUNTIME/'live-claims'/f'{sid}.claim').read_bytes() for key,sid in ids.items() if key.startswith('foreign')}
foreign_sources={key:(foreign/'state/procevent'/f'{sid}.source').read_bytes() for key,sid in ids.items() if key.startswith('foreign')}
snapshot('before-child-cleanup')
out=run([code/'bin/fm-teardown.sh','secondmate','--force'],parent,timeout=180)
for key,file in boards.items():
    expected='open' if key.startswith('held-worker') or key in ['foreign-worker','foreign-worker-shared'] else 'ended'
    assert state(file)['status']==expected,(key,state(file))
for key,claim in before.items():
    sid=ids[key]
    assert (RUNTIME/'live-claims'/f'{sid}.claim').read_bytes()==claim
    assert (foreign/'state/procevent'/f'{sid}.source').read_bytes()==foreign_sources[key]
run(['bin/fm-procevent.sh','list'],foreign)
assert not child.exists()
result('forced child removal',result='pass',own_boards='ended',child_home='removed',child_hold='kept open',parent_hold='did not affect child',foreign_root_and_registered='kept open with unchanged live claims')
snapshot('after-child-cleanup')
