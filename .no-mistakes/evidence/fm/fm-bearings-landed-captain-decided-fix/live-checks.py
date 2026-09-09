from pathlib import Path
import os, subprocess, json, shlex, shutil, hashlib
ROOT=Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J3ZVNCRVXG5Q4HD5QXABZ')
E=Path('/Users/mremond/.no-mistakes/evidence/01M22J3ZVNCRVXG5Q4HD5QXABZ')
LAB=ROOT/'.test-local/live'
LAB.mkdir(parents=True,exist_ok=True)
if not (E/'live-cli-transcript.txt').exists(): (E/'live-cli-transcript.txt').write_text('Real Firstmate CLI checks; isolated data, real tasks-axi 0.2.5 and Git; no external-command stubs.\n')
results=[]
def log(s):
    with (E/'live-cli-transcript.txt').open('a') as f: f.write(s+'\n')
def run(args, home=None, expect=0, env_extra=None, out=None, cwd=None):
    args=[str(x) for x in args]
    env=os.environ.copy()
    for k in list(env):
        if k.startswith(('FM_','TASKS_AXI_')) or k in ('TMUX','GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE'): env.pop(k,None)
    if home:
        env.update(FM_HOME=str(home),FM_ROOT_OVERRIDE=str(LAB/'code-root'),FM_STATE_OVERRIDE=str(home/'state'),FM_DATA_OVERRIDE=str(home/'data'),FM_CONFIG_OVERRIDE=str(home/'config'),FM_PROJECTS_OVERRIDE=str(home/'projects'),HOME=str(LAB/'user-home'),TMPDIR=str(ROOT/'.test-local/tmp'),TMUX_TMPDIR=str(ROOT/'.test-local/tmp'),FM_GATE_REFUSE_BYPASS='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_AUTHOR_NAME='Firstmate Validation',GIT_AUTHOR_EMAIL='test@example.invalid',GIT_COMMITTER_NAME='Firstmate Validation',GIT_COMMITTER_EMAIL='test@example.invalid')
    if env_extra: env.update({k:str(v) for k,v in env_extra.items()})
    p=subprocess.run(args,cwd=cwd or home or ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
    log('$ '+shlex.join(args)+'\n'+('FM_HOME='+str(home)+'\n' if home else '')+'exit='+str(p.returncode)+'\n'+p.stdout+p.stderr)
    if out: (E/out).write_text(p.stdout)
    if expect is not None: assert p.returncode==expect, (args,p.returncode,p.stdout,p.stderr)
    return p

def make_home(name):
    h=LAB/name
    for d in ['data','state','config','projects']: (h/d).mkdir(parents=True,exist_ok=True)
    (h/'state').chmod(0o700)
    (h/'.tasks.toml').write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 100\n')
    (h/'data/backlog.md').write_text('## In flight\n\n## Queued\n\n## Done\n')
    return h

def tasks(h,*args): return run(['tasks-axi',*args],h)
def hold(h,id): return run([ROOT/'bin/fm-captain-hold.sh','hold',id,'--reason','Review this isolated validation task'],h)
def answer(h,id,release=False,words='Choose the documented option.'):
    f=h/(id+'-answer.txt');f.write_text(words+'\n')
    return run([ROOT/'bin/fm-captain-hold.sh','answer',id,'--decision-file',f,*(['--release'] if release else [])],h)
def snapshot(h,name):
    p=run([ROOT/'bin/fm-bearings-snapshot.sh','--json','--all-landed'],h,out=name+'.json')
    run([ROOT/'bin/fm-bearings-snapshot.sh','--all-landed'],h,out=name+'.toon')
    return json.loads(p.stdout)
def passed(name,evidence):
    results.append(dict(name=name,result='pass',live=True,evidence=evidence,reason=''))
    (E/'live-results.json').write_text(json.dumps(results,indent=2)+'\n')
    log('ASSERTED: '+name)

(LAB/'user-home').mkdir(exist_ok=True)
(LAB/'code-root').mkdir(exist_ok=True)
run(['git','init','-q','-b','main',LAB/'code-root'])
if not (LAB/'code-root/bin').exists(): (LAB/'code-root/bin').symlink_to(ROOT/'bin',target_is_directory=True)
pr='https://github.com/kunchenguid/firstmate/pull/4048'
p=run(['gh-axi','pr','view','4048','--repo','kunchenguid/firstmate'],out='verified-merged-pr.txt')
assert '  state: merged' in p.stdout
main=make_home('main')
tasks(main,'add','verified-pr','Track the merged AFK posture delivery','--kind','ship','--start')
hold(main,'verified-pr');answer(main,'verified-pr',True,'Approve recording this already merged delivery.')
before=snapshot(main,'before-delivery')
assert not any(x['id']=='verified-pr' for x in before['landed'])
tasks(main,'done','verified-pr','--pr',pr)

# The local project is real Git, wholly within the current source worktree.
proj=main/'projects/local-project'; wt=main/'projects/local-work'
run(['git','init','-q','-b','main',proj],main)
(proj/'README.md').write_text('Local delivery baseline.\n')
run(['git','-C',proj,'add','README.md'],main);run(['git','-C',proj,'commit','-qm','Baseline'],main)
run(['git','-C',proj,'worktree','add','-q','-b','fm/local-delivery',wt],main)
(wt/'delivery.txt').write_text('This file is the locally delivered artifact.\n')
run(['git','-C',wt,'add','delivery.txt'],main);run(['git','-C',wt,'commit','-qm','Deliver local artifact'],main)
tasks(main,'add','local-delivery','Deliver the local artifact','--kind','ship','--start')
meta=main/'state/local-delivery.meta'
meta.write_text(f'window=firstmate:fm-local-delivery\nworktree={wt}\nproject={proj}\nkind=ship\nharness=codex\nmode=local-only\nspawn_gen=live-local-delivery\n')
meta.chmod(0o600)
run([ROOT/'bin/fm-merge-local.sh','local-delivery'],main,out='local-merge.txt')
assert (proj/'delivery.txt').read_text()=='This file is the locally delivered artifact.\n'
# Exercise interrupted-cleanup recovery after the operator removes the already-landed Git worktree.
run(['git','-C',proj,'worktree','remove',wt],main)
run([ROOT/'bin/fm-teardown.sh','local-delivery'],main,out='local-cleanup.txt')
assert not meta.exists()
show=tasks(main,'show','local-delivery','--full').stdout
assert 'local main' in show and 'state: done' in show

# A real report is delivered and retained while the question remains captain-owned.
for id,title in [('scout-colon','SCOUT: inspect local delivery'),('scout-unicode','SCOUTé inspect local delivery')]:
    report=main/'data'/id/'report.md';report.parent.mkdir();report.write_text('# Local delivery inspection\n\nObserved a fast-forward and delivery.txt in the local default branch.\n')
    tasks(main,'add',id,title,'--start')
    if id=='scout-colon': hold(main,id)
    tasks(main,'done',id,'--report',f'data/{id}/report.md')
    if id=='scout-colon': answer(main,id,words='Retain the completed inspection report.')

for id,title,kind in [('answer-pr','Decide about '+pr,'ship'),('answer-local','Decide about local main','ship'),('scout-empty','Inspect without producing a report','scout')]:
    tasks(main,'add',id,title,'--kind',kind)
    if id.startswith('answer-'):
        hold(main,id);answer(main,id,words='local main')
    else: tasks(main,'done',id)
tasks(main,'add','legacy-empty','Legacy completion');tasks(main,'done','legacy-empty')
for id,title in [('longer-scout','SCOUTING investigation'),('underscore-scout','SCOUT_investigation'),('digit-scout','SCOUT7 investigation'),('lower-scout','scout: investigation')]:
    tasks(main,'add',id,title)
    tasks(main,'done',id,'--report',f'data/{id}/report.md')
final=snapshot(main,'main-deliveries')
landed={r['id']:r['artifact'] for r in final['landed']}
assert landed['verified-pr']==pr
assert landed['local-delivery']=='local main'
assert landed['scout-colon']=='data/scout-colon/report.md'
assert landed['scout-unicode']=='data/scout-unicode/report.md'
assert landed['legacy-empty']=='-'
for id in ['answer-pr','answer-local','scout-empty','longer-scout','underscore-scout','digit-scout','lower-scout']: assert id not in landed, (id,landed)
(E/'main-backlog.md').write_text((main/'data/backlog.md').read_text())
passed('Recording a verified merged PR after releasing a past captain hold includes it in Recently Landed; approval alone does not','verified-merged-pr.txt; before-delivery.json; main-deliveries.toon')
passed('Fast-forwarding a local delivery and finishing interrupted cleanup records local main and displays the delivery','local-merge.txt; local-cleanup.txt; main-backlog.md; main-deliveries.toon')
passed('Answering questions that mention a PR or local main does not create a delivery','main-backlog.md; main-deliveries.json')
passed('Completed SCOUT: and SCOUTé reports remain visible; longer words and reportless explicit scouts stay excluded while kindless legacy completions remain','main-backlog.md; main-deliveries.json')

mate=make_home('mate')
(mate/'AGENTS.md').write_text((ROOT/'AGENTS.md').read_text())
(mate/'bin').mkdir(exist_ok=True)
(mate/'.fm-secondmate-home').write_text('mate\n')
tasks(mate,'add','mate-pr','Track a verified delivery in the delegated home','--kind','ship','--start')
hold(mate,'mate-pr');answer(mate,'mate-pr',True);tasks(mate,'done','mate-pr','--pr',pr)
tasks(mate,'add','mate-question','Choose local main','--kind','ship');hold(mate,'mate-question');answer(mate,'mate-question',words='local main')
run([ROOT/'bin/fm-home-summary-refresh.sh'],mate)
(E/'mate-home-summary.json').write_text((mate/'state/home-summary.json').read_text())
(main/'data/secondmates.md').write_text(f'# Secondmates\n\n- mate - Local validation home (home: {mate}; scope: validation; projects: sample; added 2026-09-09)\n')
parent=snapshot(main,'fleet-deliveries')
assert any(r['id']=='mate-pr' and r['owner']=='mate' and r['artifact']==pr for r in parent['landed']),parent
assert not any(r['id']=='mate-question' for r in parent['landed'])
passed('Reading a delegated home includes its released merged delivery and excludes its answered captain question','mate-home-summary.json; fleet-deliveries.toon')

# R1/R2: actual unreadable and dangling files, same task ID in two separate stores.
for state in ['dangling','unreadable-project','unreadable-user','absent','readable']:
    h=make_home('config-'+state); records=h/'records';records.mkdir()
    hcfg=h/'.tasks.toml';hcfg.unlink()
    for f in [records/'backlog.md',h/'data/backlog.md']:
        f.write_text('## In flight\n\n## Queued\n\n## Done\n')
        run(['tasks-axi','add','duplicate-id','Task in '+f.parent.name,'--file',f],h,env_extra={'TASKS_AXI_BACKEND':'markdown'})
    uc=LAB/'user-home/.tasks-axi/config.toml';uc.parent.mkdir(exist_ok=True)
    if state=='dangling': hcfg.symlink_to('missing-config.toml')
    if state=='unreadable-project': hcfg.write_text('backend = "markdown"\n');hcfg.chmod(0)
    if state=='unreadable-user': uc.write_text('backend = "beads"\n');uc.chmod(0)
    if state=='readable': hcfg.write_text('backend = "markdown"\n')
    before_default=(h/'data/backlog.md').read_bytes(); before_config=(records/'backlog.md').read_bytes()
    p=run([ROOT/'bin/fm-captain-hold.sh','hold','duplicate-id','--title','Task in records','--reason','Choose safely'],h,expect=None,env_extra={'FM_DATA_OVERRIDE':records},out='config-'+state+'.txt')
    if state in ['dangling','unreadable-project','unreadable-user']:
        assert p.returncode!=0 and 'cannot be read' in p.stderr+p.stdout
        assert (records/'backlog.md').read_bytes()==before_config
        opened=run([ROOT/'bin/fm-captain-hold.sh','open','duplicate-id','--distinguish-absent'],h,expect=2,env_extra={'FM_DATA_OVERRIDE':records})
    else:
        assert p.returncode==0
        assert 'hold-kind: captain' in (records/'backlog.md').read_text()
    assert (h/'data/backlog.md').read_bytes()==before_default
    (E/('config-'+state+'-state.json')).write_text(json.dumps({'exit':p.returncode,'stderr':p.stderr,'default_unchanged':True,'configured_unchanged':(records/'backlog.md').read_bytes()==before_config},indent=2)+'\n')
    if uc.exists(): uc.chmod(0o600);uc.unlink()
    if hcfg.exists() and not hcfg.is_symlink(): hcfg.chmod(0o600)
passed('Holding a task with unreadable or dangling backend configuration refuses without changing either backlog; absent and readable configurations still address the relocated backlog','live-cli-transcript.txt; config-*-state.json')
print(json.dumps(results,indent=2))
