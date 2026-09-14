import json,sys
s=json.load(open(sys.argv[1]))
nudges={r['pr_url']:r for r in s['awaiting'] if r['nudge']}
calls=[dict(key=r['key'],type='decision',repo='firstmate',title=r['summary'],about='Approval from '+r['owner'],options=[dict(value='wait',label='Keep waiting')]) for r in s['decisions_open']]
calls += [dict(key=r['pr_url'],type='nudge',repo=r['repo'],title='Nudge the outside maintainer',detail=f"{r['owner']} · delivered {r['age_days']} days ago",pr_url=r['pr_url'],age_days=r['age_days'],options=[dict(value='wait',label='Leave it waiting'),dict(value='nudge',label='Nudge the maintainer')]) for r in nudges.values()]
p=dict(schema='fm-bearings-board.v1',home='Isolated Bearings verification',generated=s['generated'],prs_live=False,captains_call=calls,underway=s['in_flight'],awaiting=[{k:v for k,v in r.items() if k!='nudge'} for r in s['awaiting'] if not r['nudge']],awaiting_nudge_days=s['awaiting_nudge_days'],landed=[],charted=[dict(id=r['id'],repo='firstmate',owner=r['owner'],title=r['title'],reason=r['reason'],pr_url=r['pr_url'],filed=r.get('filed'),dispatchable=False) for r in s['gates'] if r['id'] in ['main-held','main-unrecorded','mate-held','mate-unrecorded']])
p['charted']=[{k:v for k,v in r.items() if v is not None} for r in p['charted']]
json.dump(p,sys.stdout,indent=2)
