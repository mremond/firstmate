#!/usr/bin/env python3
"""Supplemental local workflow tests; not a live GitHub Actions execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2HV450TTYZ7HY9HBZA00GYK')
OUT = Path('/Users/mremond/.no-mistakes/evidence/01M2HV450TTYZ7HY9HBZA00GYK')
LAB = ROOT / '.voice-guard-live-check' / 'workflow'
LAB.mkdir()

def load_yaml(path):
    parser = 'puts JSON.generate(Psych.safe_load(File.read(ARGV.fetch(0))))'
    return json.loads(subprocess.check_output(['ruby','-rpsych','-rjson','-e',parser,str(path)],text=True,cwd=ROOT))

doc = load_yaml(ROOT/'.github/workflows/internal-voice-guard.yml')
# Psych uses YAML 1.1, so normalize its boolean interpretation of the 'on' key.
trigger = doc.get('on', doc.get('true'))['pull_request']
assert set(trigger['types']) == {'opened','edited','synchronize','reopened'}
assert trigger['branches'] == ['main']
assert doc['permissions'] == {'contents':'read'}
steps = doc['jobs']['check']['steps']
checkout, scan = steps
assert checkout['uses'] == 'actions/checkout@v6'
assert checkout['with'] == {'ref':'${{ github.event.pull_request.base.ref }}','path':'trusted-scanner'}
assert scan['env'] == {'PR_TITLE':'${{ github.event.pull_request.title }}','PR_BODY':'${{ github.event.pull_request.body }}'}
assert load_yaml(ROOT/'.no-mistakes.yaml')['commands']['lint'] == 'bin/fm-lint.sh'
trusted = LAB / 'trusted-scanner/bin'
trusted.mkdir(parents=True)
shutil.copy2(ROOT/'bin/fm-prepush-voice-guard.sh',trusted/'fm-prepush-voice-guard.sh')
# A pull-request-controlled scanner would return clean if the job selected it.
pr = LAB / 'bin'
pr.mkdir()
(pr/'fm-prepush-voice-guard.sh').write_text('#!/usr/bin/env bash\nprintf selected-untrusted-scanner\nexit 0\n')
marker = LAB/'injection-marker'
cases = [
    ('clean', 'fix: bound the scan', 'Describe captain intent and session-scoped caching.', 0),
    ('title-leak', 'Captain, this is ready', 'Describe the result.', 1),
    ('body-leak', 'fix: bound the scan', 'See https://claude.ai/code/session_0123456789abcdef', 1),
    ('literal-input', 'fix: document shell syntax', 'Literal $(touch '+str(marker)+') and `touch '+str(marker)+'`', 0),
]
with (OUT/'workflow-shell-transcript.log').open('w') as log:
    log.write('Local supplemental execution of the workflow run step. GitHub event routing and actions/checkout were NOT executed.\n')
    log.write('Normalized semantic checks: PR events, target branch, read-only permission, trusted base checkout, environment inputs, and canonical lint pin agree with the contract.\n')
    for name,title,body,expected in cases:
        summary=LAB/(name+'.md')
        env=os.environ | {'PR_TITLE':title,'PR_BODY':body,'GITHUB_STEP_SUMMARY':str(summary),'TMPDIR':str(LAB)}
        result=subprocess.run(['bash','--noprofile','--norc','-eo','pipefail','-c',scan['run']],cwd=LAB,env=env,text=True,capture_output=True)
        log.write('\n## '+name+'\nPR_TITLE: '+title+'\nPR_BODY: '+body+'\n'+result.stdout+result.stderr+f'[exit {result.returncode}; expected {expected}]\n')
        assert result.returncode==expected,(name,result)
        assert 'selected-untrusted-scanner' not in result.stdout
        assert not marker.exists()
    (trusted/'fm-prepush-voice-guard.sh').unlink()
    summary=OUT/'workflow-bootstrap-summary.md'
    env=os.environ | {'PR_TITLE':'Captain, this is ready','PR_BODY':'Description','GITHUB_STEP_SUMMARY':str(summary),'TMPDIR':str(LAB)}
    result=subprocess.run(['bash','--noprofile','--norc','-eo','pipefail','-c',scan['run']],cwd=LAB,env=env,text=True,capture_output=True)
    log.write('\n## trusted scanner absent\n'+result.stdout+result.stderr+f'[exit {result.returncode}; expected 0 with explicit NOT APPLIED notice]\n')
    assert result.returncode==0
    assert '::warning title=Voice guard did not scan this pull request::' in result.stdout
    assert 'NOT APPLIED' in summary.read_text()
    assert 'selected-untrusted-scanner' not in result.stdout
print('Workflow semantic and local shell cases passed; GitHub execution remains untested.')
