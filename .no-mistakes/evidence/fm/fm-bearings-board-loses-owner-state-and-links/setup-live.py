import os,json,subprocess,pathlib,time
root=pathlib.Path.cwd(); lab=root/'.test-phase'; evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M21B2PY8J90QVVWWNDZ2WVGJ')
env=os.environ.copy(); env.update(TMPDIR=str(lab/'tmp'),FM_ROOT_OVERRIDE=str(lab/'runtime-root'),FM_GUARD_READ_ONLY='1',LAVISH_AXI_STATE_DIR=str(lab/'lavish-state'),LAVISH_AXI_PORT='4499',LAVISH_AXI_HOST='127.0.0.1',LAVISH_AXI_NO_OPEN='1',LAVISH_AXI_TELEMETRY='off')
(lab/'runtime-root').mkdir(exist_ok=True)
(lab/'runtime-root'/'bin').symlink_to(root/'bin',target_is_directory=True)
for name in ['main-home','mate-home']:
    home=lab/name
    for d in ['state','data','config','projects','bin']: (home/d).mkdir(parents=True,exist_ok=True)
    (home/'AGENTS.md').write_text('# Isolated Bearings verification home\n')
mate=lab/'mate-home'; home=lab/'main-home'
(mate/'.fm-secondmate-home').write_text('review-mate\n')
(home/'data'/'secondmates.md').write_text(f'- review-mate - Verification home (home: {mate}; scope: test validation; projects: firstmate; added 2026-09-08)\n')
(home/'state'/'review-mate.meta').write_text(f'window=nm-test-no-session:mate\nworktree={mate}\nproject={mate}\nharness=claude\nkind=secondmate\nmode=secondmate\nhome={mate}\nprojects=firstmate\n')
log=open(evidence/'live-cli-transcript.log','w')
def run(h,*args):
    e=env.copy();e.update(FM_HOME=str(h),FM_STATE_OVERRIDE=str(h/'state'),FM_DATA_OVERRIDE=str(h/'data'),FM_PROCEVENT_CLAIM_ROOT=str(h/'claims'))
    p=subprocess.run([str(root/'bin'/args[0]),*args[1:]],env=e,text=True,capture_output=True)
    log.write(f'$ FM_HOME={h} bin/'+ ' '.join(args)+'\n'+p.stdout+p.stderr+f'exit: {p.returncode}\n');log.flush()
    if p.returncode: raise RuntimeError(p.stderr)
    return p.stdout
for h in [home,mate]:
    records=[]
    for ident,title,hold,url,status,age in [
        ('in-flight','Second mate: misleading title',None,'https://github.com/acme/repo/pull/1','done: publication ready; captain approval has not been requested',None),
        ('young','Delivered to outside maintainer',None,'https://github.com/acme/repo/pull/3','paused: declared external maintainer wait',3),
        ('overdue','Long outside maintainer wait',None,'https://github.com/acme/repo/pull/'+('4' if h==home else '5'),'paused: declared external maintainer wait',8),
        ('approval','Approval still owed','captain','https://github.com/acme/repo/pull/6','needs-decision [key=approval]: captain approval required\npaused: external wait',30),
        ('recorded','Held delivery','external','https://github.com/acme/repo/pull/2','paused: waiting for dependency',None),
        ('unrecorded','Held without own request','external',None,'paused: dependency https://github.com/acme/repo/pull/99',None),
    ]:
        holdtext='' if hold is None else (' (hold: dependency https://github.com/acme/repo/pull/99 is still under review) (hold-kind: '+hold+')')
        records.append(f'- [ ] {ident} - {title} (repo: firstmate) (kind: ship){holdtext} (since 2026-09-01)')
        (h/'state'/f'{ident}.meta').write_text(f'window=nm-test-no-session:{ident}\nworktree={h}/projects\nproject=firstmate\nharness=claude\nkind=ship\nmode=ship\n'+(f'pr={url}\n' if url else ''))
        (h/'state'/f'{ident}.status').write_text(status+'\n')
        if age is not None:
            run(h,'fm-pr-check.sh',ident,url)
            reg=h/'state'/f'{ident}.pr-poll-registration'; stamp=int(time.time())-age*86400;os.utime(reg,(stamp,stamp))
    (h/'data'/'backlog.md').write_text('## In flight\n'+'\n'.join(records)+'\n\n## Queued\n\n## Done\n')
    (h/'data'/'projects.md').write_text('')
    raw=run(h,'fm-fleet-snapshot.sh','--secondmate-home-summary')
    (evidence/f'{h.name}-ledger.json').write_text(raw)
    (h/'state'/'home-summary.json').write_text(raw)
raw=run(home,'fm-bearings-snapshot.sh','--json');(evidence/'live-bearings-snapshot.json').write_text(raw)
(lab/'live-env.json').write_text(json.dumps(env))
print(raw)
