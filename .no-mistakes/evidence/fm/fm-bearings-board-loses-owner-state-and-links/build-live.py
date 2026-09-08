import os,json,subprocess,pathlib
root=pathlib.Path.cwd();lab=root/'.test-phase';home=lab/'main-home';evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M21B2PY8J90QVVWWNDZ2WVGJ')
s=json.loads((evidence/'live-bearings-snapshot.json').read_text())
assert {r['owner'] for r in s['in_flight']}=={'(main)','review-mate'}
assert all(r['pr_url']=='https://github.com/acme/repo/pull/2' for r in s['gates'] if r['id']=='recorded')
assert all(r['pr_url'] is None for r in s['gates'] if r['id']=='unrecorded')
assert not any(r['id'].endswith('approval') for r in s['awaiting'])
assert len(s['decisions_open'])==2
calls=[dict(key=r['pr_url'],type='nudge',repo=r['repo'],title='Nudge the outside maintainer',age_days=r['age_days'],pr_url=r['pr_url'],detail=r['owner']+' · '+r['what'],options=[dict(value='leave',label='Leave it',hint='Keep the original waiting clock'),dict(value='nudge',label='Nudge maintainer')]) for r in s['awaiting'] if r['nudge']]
# Holds are composed as credential cards here because routing these disposable
# records is outside this visual scenario; nudge routing is exercised live.
for r in s['decisions_open']:
    calls.append(dict(key=r['id'].replace('/','.'),type='credential',repo='firstmate',title='Approval still owed',detail=r['owner']+' · '+r['summary'],options=[dict(value='review',label='Review request')]))
p=dict(schema='fm-bearings-board.v1',home='Isolated Bearings validation',generated=s['generated'],prs_live=False,captains_call=calls,underway=s['in_flight'],awaiting=[r for r in s['awaiting'] if not r['nudge']],landed=[],charted=[dict(id=r['owner'].replace('(','').replace(')','')+'.'+r['id'],repo='firstmate',owner=r['owner'],title=r['title'],reason=r['reason'],pr_url=r['pr_url'],dispatchable=False) for r in s['gates']],awaiting_nudge_days=s['awaiting_nudge_days'])
for r in p['charted']:
    if r.get('pr_url') is None: r.pop('pr_url',None)
(evidence/'live-board-payload.json').write_text(json.dumps(p,indent=2))
env=json.loads((lab/'live-env.json').read_text());env.update(FM_HOME=str(home),FM_STATE_OVERRIDE=str(home/'state'),FM_DATA_OVERRIDE=str(home/'data'),FM_PROCEVENT_CLAIM_ROOT=str(home/'claims'),GIT_CEILING_DIRECTORIES=str(root))
result=subprocess.run([str(root/'bin/fm-bearings-board.sh'),'build',str(evidence/'live-board-payload.json')],env=env,text=True,capture_output=True)
(evidence/'live-board-build.log').write_text(result.stdout+result.stderr)
print(result.stdout+result.stderr)
if result.returncode: raise SystemExit(result.returncode)
(evidence/'bearings-board.html').write_bytes((home/'.lavish/bearings-board.html').read_bytes())
(lab/'board-env.json').write_text(json.dumps(env))
