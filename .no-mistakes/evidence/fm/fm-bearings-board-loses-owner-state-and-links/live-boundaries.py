import json,pathlib,subprocess,os,time
root=pathlib.Path.cwd();lab=root/'.test-phase';evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M21B2PY8J90QVVWWNDZ2WVGJ');env=json.loads((lab/'board-env.json').read_text());home=lab/'main-home';log=[]
def run(script,*args,extra=None):
 e=env.copy();e.update(extra or {});p=subprocess.run([str(root/'bin'/script),*args],env=e,text=True,capture_output=True);log.append('$ '+script+' '+' '.join(args)+'\n'+p.stdout+p.stderr);assert p.returncode==0,p.stderr;return p.stdout
reg=home/'state/young.pr-poll-registration';before=int(reg.stat().st_mtime)
run('fm-pr-check.sh','young','https://github.com/acme/repo/pull/3');after=int(reg.stat().st_mtime);assert before==after
run('fm-pr-check.sh','young','https://github.com/acme/repo/pull/7');replacement=int(reg.stat().st_mtime);assert replacement>after and abs(replacement-time.time())<30
s=json.loads(run('fm-bearings-snapshot.sh','--json'));row=next(r for r in s['awaiting'] if r['id']=='young');assert row['age_days']==0 and row['pr_url'].endswith('/7')
# Try to smuggle a threshold-aged delivery into Delivered: the public builder
# must reject this before changing the existing board.
p=json.loads((evidence/'live-board-payload.json').read_text());p['awaiting'][0]['age_days']=p['awaiting_nudge_days'];bad=lab/'overdue-payload.json';bad.write_text(json.dumps(p));board=home/'.lavish/bearings-board.html';before_bytes=board.read_bytes()
r=subprocess.run([str(root/'bin/fm-bearings-board.sh'),'build',str(bad)],env=env,text=True,capture_output=True);assert r.returncode!=0 and board.read_bytes()==before_bytes
log.append('$ fm-bearings-board.sh build <age exactly 7 days in Delivered>\n'+r.stdout+r.stderr+'existing board preserved: yes\n')
(evidence/'live-clock-and-exit-guard.log').write_text(f'Same request registration epoch: {before} -> {after}\nReplacement request registration epoch: {replacement}\n'+'\n'.join(log))
# A later pause cannot answer an unresolved approval, even without a backlog hold.
for h in [home,lab/'mate-home']:
 b=h/'data/backlog.md';b.write_text(b.read_text().replace(' (hold: dependency https://github.com/acme/repo/pull/99 is still under review) (hold-kind: captain)',''))
subprocess.run([str(root/'bin/fm-fleet-snapshot.sh'),'--secondmate-home-summary'],env={**env,'FM_HOME':str(lab/'mate-home'),'FM_STATE_OVERRIDE':str(lab/'mate-home/state'),'FM_DATA_OVERRIDE':str(lab/'mate-home/data')},stdout=(lab/'mate-home/state/home-summary.json').open('w'),check=True)
s=json.loads(run('fm-bearings-snapshot.sh','--json'));assert not any(r['id'].endswith('approval') for r in s['awaiting']);assert sum(r['id'].endswith('approval') for r in s['in_flight'])==2
(evidence/'live-status-approval-boundary.json').write_text(json.dumps(s,indent=2))
print('Same-request age preserved; replacement request resets age; threshold-aged Delivered payload rejected without changing board; later pause does not hide either unresolved approval.')
