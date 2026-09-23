from pathlib import Path
import json
E=Path(__file__).parent
reported=(E/'live-reported-cases.txt').read_text()
sweep=(E/'live-sweep.txt').read_text()
failed=(E/'live-incomplete-reads.txt').read_text()
main=(E/'live-title-and-main-fix.txt').read_text()
def block(n):
    return reported.split('=== #'+str(n)+' ',1)[1].split('\n=== #',1)[0]
def line(n,text=sweep):
    return next(x for x in text.splitlines() if x.startswith('sweep: #'+str(n)+' '))
assert 'verdict: claimed' in block(3966)
assert 'claim: PR #3977 open' in block(3966)
assert 'claim: PR #3978 open' in block(3942)
assert 'stamp,fixes]' in block(3942)
assert 'verdict: fixed-on-main' in block(3926)
assert 'merged: PR #3944 merged base=main' in block(3926)
for n in (4412,4482,4316):
    assert 'hint: PR #4775 merged base=main' in block(n)
    assert 'hint: commit 9bc051ff' in block(n)
    assert 'merged: PR #4775' not in block(n)
for n in (3966,3942,4316,5349):
    assert 'leave-open state=open verdict=claimed' in line(n)
assert 'no-action state=open verdict=open coverage=complete link=- evidence=-' in line(5415)
assert 'no-action state=open verdict=open coverage=complete link=-' in line(3370)
assert 'hint: suspected fix to verify: commit baede47d' in line(3370)
assert '[history:-S st_dev]' in line(3370)
assert 'hint: suspected fix to verify: commit 9bc051ff' in line(4412)
assert 'link=-' in line(4412)
assert 'no-action state=closed verdict=fixed-on-main' in line(3926)
assert failed.count('verdict: unknown')==3
assert 'history=failed' in failed and 'HTTP 404' in failed and 'is a pull request, not an issue' in failed
assert 'Exit: 1' in failed
assert 'claim: PR #5376 open [corpus:title]' in main
assert 'leave-open state=open verdict=claimed' in line(4559,main)
assert 'merged: commit baede47d' in line(4260,main)
assert 'verdict=fixed-on-main' in line(4260,main)
assert 'no-action state=closed' in line(4260,main)
summary=[]
for f in sorted(E.glob('live-*-api.jsonl')):
    calls=[json.loads(s) for s in f.read_text().splitlines()]
    assert all(c['read_allowed'] for c in calls)
    corpus=sum(c['argv'][1:2]==['repos/kunchenguid/firstmate/pulls?state=open&per_page=100'] for c in calls)
    assert corpus==1
    summary.append({'run':f.stem,'forge_reads':len(calls),'corpus_fetch_invocations':corpus,'mutating_calls':0})
(E/'live-evidence-checks.json').write_text(json.dumps({'target':'07a5ada4516cdd957763b17345f9f5c2ad23dbfa','checks':'Observed CLI transcript assertions passed','api_audit':summary},indent=2)+'\n')
print(json.dumps(summary,indent=2))
