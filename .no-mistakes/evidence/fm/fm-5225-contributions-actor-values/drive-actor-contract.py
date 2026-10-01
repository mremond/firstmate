import copy
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M3VG1X6F50QPEEWXVJPGFS9T')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M3VG1X6F50QPEEWXVJPGFS9T')
SCRATCH = Path((ROOT / '.actor-validation-path').read_text())
BASE = '589ccec821bf6310ce888e2a702e4fc9258eb1e8'
TARGET = 'b72ebc0f0c304a9246ef2f44fe970dfcea61870d'
URL = 'https://github.com/o/r/pull/8'
HEAD = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
SOURCE = URL + '#issuecomment-99'
ACTORS = ['captain', 'fleet', 'maintainer', 'nobody']
NOW = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
report = {'base': BASE, 'target': TARGET, 'commands': [], 'checks': []}
log = open(EVIDENCE / 'actor-cli-transcript.txt', 'w')

def say(message):
    print(message, file=log, flush=True)

def verify(condition, label):
    report['checks'].append({'name': label, 'passed': bool(condition)})
    say(('PASS: ' if condition else 'FAIL: ') + label)
    if not condition:
        raise AssertionError(label)

def seed(name):
    home = SCRATCH / name
    for sub in ['data/delivery', 'state', 'config', 'projects', 'tmp', 'xdg']:
        (home/sub).mkdir(parents=True, exist_ok=True)
    (home/'data/backlog.md').write_text('# Backlog\n\n## Queued\n- [ ] delivery - Synthetic contribution https://github.com/o/r/pull/8 (repo: sample) (kind: ship)\n')
    record = {'schema': 'fm-contributions.v1', 'task': 'delivery', 'records': [{
        'url': URL, 'kind': 'pr', 'checked_at': NOW, 'error': None,
        'pending': [], 'seen': [], 'notified': [], 'verdict': None,
        'observation': {'head': HEAD, 'state': 'open', 'draft': False,
            'mergeable': 'mergeable', 'review_decision': 'APPROVED', 'can_merge': False,
            'checks': [{'name': 'test', 'id': 1, 'status': 'completed', 'conclusion': 'success', 'started_at': NOW}],
            'reviews': [], 'events': []}}]}
    (home/'data/delivery/contributions.json').write_text(json.dumps(record, indent=2)+'\n')
    return home

def environment(home, code_root):
    env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(home/'tmp'), 'XDG_CONFIG_HOME': str(home/'xdg'),
        'FM_HOME': str(home), 'FM_ROOT_OVERRIDE': str(code_root),
        'FM_STATE_OVERRIDE': str(home/'state'), 'FM_DATA_OVERRIDE': str(home/'data'),
        'FM_CONFIG_OVERRIDE': str(home/'config'), 'FM_PROJECTS_OVERRIDE': str(home/'projects'),
        'FM_CONTRIBUTIONS_NOW': NOW, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}
    if 'NO_MISTAKES_GATE' in os.environ:
        env['NO_MISTAKES_GATE'] = os.environ['NO_MISTAKES_GATE']
    return env

def invoke(label, home, code_root, *args):
    command = [str(code_root/'bin/fm-contributions.sh'), *args]
    result = subprocess.run(command, cwd=ROOT, env=environment(home, code_root), text=True, capture_output=True, timeout=30)
    entry = {'label': label, 'command': command, 'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    report['commands'].append(entry)
    say('\n$ ' + shlex.join(command))
    say('isolated FM_HOME=' + str(home))
    say('exit=' + str(result.returncode))
    if result.stdout: say(result.stdout.rstrip())
    if result.stderr: say(result.stderr.rstrip())
    return result

def saved(home):
    return json.loads((home/'data/delivery/contributions.json').read_text())

def record_bytes(home):
    return (home/'data/delivery/contributions.json').read_bytes()

say('Live execution of the real contributions CLI; synthetic durable input only, no product stubs, forge calls, or lifecycle operations.')
say('Target: ' + TARGET + '\nBase: ' + BASE)
try:
    home = seed('target-home')
    original = saved(home)
    for flag in ['--help', '-h']:
        result = invoke('help '+flag, home, ROOT, flag)
        match = re.search(r'fm-contributions\.sh verdict <task> <url> <judged-head> <source-url> <([^>]+)> <summary>', result.stdout)
        verify(result.returncode == 0 and match is not None and match.group(1).split('|') == ACTORS, flag+' advertises exactly the four accepted actors')
    verify(saved(home) == original, 'help leaves contribution data unchanged')
    for actor in ACTORS:
        before = saved(home)
        summary = 'Recorded through the public CLI for ' + actor
        result = invoke('accepted '+actor, home, ROOT, 'verdict', 'delivery', URL, HEAD, SOURCE, actor, summary)
        expected = copy.deepcopy(before)
        expected['records'][0]['verdict'] = {'head': HEAD, 'source': SOURCE, 'actor': actor, 'summary': summary}
        verify(result.returncode == 0 and saved(home) == expected, actor+' is accepted and persists only the exact requested verdict')
        say('Persisted verdict: ' + json.dumps(saved(home)['records'][0]['verdict'], sort_keys=True))
        (EVIDENCE/('persisted-'+actor+'.json')).write_text(json.dumps(saved(home), indent=2)+'\n')
    for actor in ['bogus', '', 'Captain', 'FLEET', 'none', 'all', 'maintainer ', 'captain|fleet|maintainer|nobody']:
        before = record_bytes(home)
        result = invoke('invalid '+repr(actor), home, ROOT, 'verdict', 'delivery', URL, HEAD, SOURCE, actor, 'Must be refused')
        expected_message = "fm-contributions: invalid required actor '"+actor+"'; expected one of: captain, fleet, maintainer, nobody\n"
        verify(result.returncode == 1 and result.stderr == expected_message and record_bytes(home) == before, 'invalid actor '+repr(actor)+' is explained and causes no stored mutation')
    guards = [
        ('omitted actor', ['verdict', 'delivery', URL, HEAD, SOURCE, 'Summary without actor'], 'verdict needs judged-head, source-url, actor and summary'),
        ('bad head', ['verdict', 'delivery', URL, 'short', SOURCE, 'fleet', 'Guard check'], 'an exact judged commit is required'),
        ('foreign source', ['verdict', 'delivery', URL, HEAD, 'https://github.com/o/r/pull/9#issuecomment-1', 'fleet', 'Guard check'], 'verdict source must be a comment or review on this contribution'),
        ('unowned contribution', ['verdict', 'delivery', 'https://github.com/o/r/pull/9', HEAD, SOURCE, 'fleet', 'Guard check'], 'contribution is not owned by this durable task')]
    for label, args, message in guards:
        before = record_bytes(home)
        result = invoke(label, home, ROOT, *args)
        verify(result.returncode == 1 and result.stderr == 'fm-contributions: '+message+'\n' and record_bytes(home) == before, label+' still refuses with no default or persisted mutation')
    baseline = SCRATCH/'baseline-code'
    shutil.copytree(ROOT/'bin', baseline/'bin')
    old_script = subprocess.check_output(['git', 'show', BASE+':bin/fm-contributions.sh'], cwd=ROOT)
    (baseline/'bin/fm-contributions.sh').write_bytes(old_script)
    old_home = seed('baseline-home')
    result = invoke('baseline help', old_home, baseline, '--help')
    old_usage = next(line for line in result.stdout.splitlines() if 'fm-contributions.sh verdict ' in line)
    verify(result.returncode == 0 and '<actor>' in old_usage and not all(actor in old_usage for actor in ACTORS), 'base reproduces help discoverability failure')
    result = invoke('baseline invalid actor', old_home, baseline, 'verdict', 'delivery', URL, HEAD, SOURCE, 'bogus', 'Must be refused')
    verify(result.returncode == 1 and result.stderr == 'fm-contributions: invalid required actor\n', 'base reproduces opaque invalid-actor refusal')
    for actor in ACTORS:
        result = invoke('baseline accepted '+actor, old_home, baseline, 'verdict', 'delivery', URL, HEAD, SOURCE, actor, 'Baseline actor')
        verify(result.returncode == 0 and saved(old_home)['records'][0]['verdict']['actor'] == actor, 'base already accepts '+actor)
    report['result'] = 'pass'
finally:
    (EVIDENCE/'actor-cli-results.json').write_text(json.dumps(report, indent=2)+'\n')
    log.close()
print(json.dumps({'result': report.get('result', 'fail'), 'commands': len(report['commands']), 'checks': len(report['checks'])}))
