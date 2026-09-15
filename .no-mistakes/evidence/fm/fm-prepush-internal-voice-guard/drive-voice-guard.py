#!/usr/bin/env python3
"""Drive the actual scanner and real isolated Git histories; no tools are mocked."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2HV450TTYZ7HY9HBZA00GYK')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M2HV450TTYZ7HY9HBZA00GYK')
LAB = ROOT / '.voice-guard-live-check' / 'manual'
GUARD = ROOT / 'bin/fm-prepush-voice-guard.sh'
LAB.mkdir(parents=True)
ENV = os.environ.copy()
for key in list(ENV):
    if key.startswith('GIT_'):
        ENV.pop(key)
ENV.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null',
           GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0',
           GIT_AUTHOR_NAME='Scanner verification', GIT_AUTHOR_EMAIL='scanner@example.invalid',
           GIT_COMMITTER_NAME='Scanner verification', GIT_COMMITTER_EMAIL='scanner@example.invalid',
           TMPDIR=str(LAB), LC_ALL='C')
records = []
log = (EVIDENCE / 'live-cli-transcript.log').open('w')

def command(args, cwd=LAB, data=None, expected=0, extra_env=None, label=None):
    env = ENV | (extra_env or {})
    args = [str(a) for a in args]
    log.write('\n' + ('## ' + label + '\n' if label else '') + '$ ' + shlex.join(args) + '\n')
    log.write('cwd: ' + str(cwd.relative_to(ROOT)) + '\n')
    if data is not None:
        log.write('stdin:\n' + data + ('\n' if not data.endswith('\n') else ''))
    run = subprocess.run(args, cwd=cwd, env=env, input=data, text=True, capture_output=True)
    log.write(run.stdout + run.stderr + f'[exit {run.returncode}; expected {expected}]\n')
    log.flush()
    assert run.returncode == expected, (label, args, run.returncode, expected, run.stdout, run.stderr)
    if label:
        records.append({'name':label, 'result':'pass', 'live':True, 'exit':run.returncode})
    return run.stdout + run.stderr

def git(cwd, *args, **kw):
    return command(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', *args], cwd=cwd, **kw)

def commit(cwd, message):
    git(cwd, 'commit', '--allow-empty', '-F', '-', data=message)
    return git(cwd, 'rev-parse', 'HEAD').strip()

def scan(label, cwd, expected=1, args=(), data=None, extra_env=None, contains=(), absent=()):
    out = command([GUARD, *args], cwd=cwd, expected=expected, data=data, extra_env=extra_env, label=label)
    for value in contains:
        assert value in out, (label, 'missing', value, out)
    for value in absent:
        assert value not in out, (label, 'unexpected', value, out)
    return out

try:
    origin = LAB / 'publication'
    work = LAB / 'branch'
    git(LAB, 'init', '-b', 'main', origin)
    commit(origin, 'fix: Captain, historical default-branch message')
    published = commit(origin, 'docs: describe the supported configuration')
    git(LAB, 'clone', '--no-local', origin, work)
    git(work, 'checkout', '-b', 'feature')
    commit(work, 'fix(holds): keep captain-held tasks pending\n\nA session-scoped negative cache keeps the conclusion.\nDescribe captain intent, the /ahoy skill, and shipshape acknowledgements.\ndocs: touch tests/data/fixtures/x.txt\ndocs: update data/backlog.md\ndocs: see `https://example.com/data/api/schema.json` in the guide')
    scan('Clean technical commits pass and published default-branch leaks stay excluded', work, expected=0)
    first = commit(work, 'fix(ci): Captain, bound the scan\n\nChanges remain uncommitted for the outer executor')
    session = 'https://claude.ai/code/session_0123456789abcdef'
    second = commit(work, 'fix: retain the result\n\nClaude-Session: ' + session)
    third = commit(work, 'docs: retire `/Users/alice/firstmate/data/task/report.md` now\n\nReview .lavish/board/summary.html')
    commit(work, 'fix: keep the feature tip clean')
    expected_rules = ('captain-address-opening', 'delivery-machinery-handoff', 'internal-session-pointer',
                      'internal-session-link', 'private-task-work-document', 'private-review-artifact')
    scan('A clean tip cannot hide forbidden text in earlier commit subjects and bodies', work,
         contains=(*expected_rules, first[:12], second[:12], third[:12], 'git commit --amend', 'git rebase -i'),
         absent=('historical default-branch message',))
    commit(origin, 'fix: Captain, newly published history remains outside the scan')
    git(work, 'fetch', 'origin', 'main')
    git(work, 'merge', '--no-ff', 'origin/main', '-m', 'Merge main into feature')
    scan('Merging a newer default branch preserves refusal of the feature history', work,
         contains=expected_rules, absent=('newly published history', 'historical default-branch message'))
    git(work, 'branch', '-f', 'main', first)
    scan('An ahead local main cannot hide an unpublished ancestor when origin/main resolves', work,
         contains=(first[:12],))
    scan('An environment base equal to HEAD cannot silence the default scan', work,
         extra_env={'FM_VOICE_GUARD_BASE':'HEAD'}, contains=expected_rules)
    git(origin, 'fetch', work, 'feature:refs/heads/feature')
    git(work, 'fetch', 'origin')
    scan('A feature branch already stored remotely is still scanned until main contains it', work,
         contains=expected_rules)
    git(work, 'update-ref', '-d', 'refs/remotes/origin/main')
    scan('Missing origin/main refuses an unestablished range despite contaminated local main', work,
         expected=3, contains=('no authoritative publication ref', 'git fetch origin main', '--range <publication-ref>..HEAD'),
         absent=('REFUSING - firstmate internal voice',))
    scan('An explicitly authorized publication commit recovers the offline scan', work,
         args=('--range', published + '..HEAD'), contains=expected_rules)
    scan('An explicitly selected clean tip passes while an older selected commit refuses', work,
         expected=0, args=('--commit','HEAD'))
    scan('Selecting the older leaking commit names that commit and refuses', work,
         args=('--commit',first), contains=(first[:12], 'captain-address-opening'))
    # Local main is usable only after an operator explicitly designates the bound.
    git(work, 'branch', '-f', 'main', 'HEAD')
    commit(work, 'docs: explain configuration defaults')
    scan('Explicit local main bound scans only its clean descendant', work, expected=0, args=('--range','main..HEAD'))
    scan('Local main is still not implicitly authoritative after a clean descendant', work, expected=3,
         contains=('no authoritative publication ref',))

    refusals = [
        'docs: retire `/Users/alice/firstmate/data/task/report.md` now',
        'docs: retire `~/firstmate/data/alpha/report.md` now',
        'docs: retire /Users/A Person/firstmate/data/alpha/report.md',
        'docs: retire ../data/alpha/report.md',
        'docs: retire data/alpha/report.md after completion',
        'fix(ci): Captain—bound the scan',
        'fix(ci): Captain – bound the scan',
        'The operation completed, captain',
        'Hello captain, the change is ready',
        'feat: retain the result\n\nClaude-Session: ' + session,
        'feat: retain the result\n\nSee ' + session + ' for details.',
        'docs: refresh .lavish/board/summary.html',
    ]
    for n, value in enumerate(refusals,1):
        scan(f'Text refusal {n}: {value.splitlines()[0]}', work, args=('--text','-'), data=value+'\n',
             contains=('REFUSING', 'Reword the text above'), absent=('git rebase -i',))
    accepted = [
        'docs: see `https://example.com/data/api/schema.json` in the guide',
        'docs: describe /data/api/schema.json',
        'docs: point at https://example.com/data/api/schema.json for the schema',
        'docs: see https://gitlab.com/org/repo/-/blob/main/data/alpha/report.md',
        'docs: see https://github.com/kunchenguid/firstmate/pull/3837',
        'docs: touch tests/data/fixtures/x.txt',
        'docs: update data/backlog.md',
        'docs: captain.md now records the fleet owner',
        'fix: the pane still reaches the captain - once per window',
        'Thread-Safety-Docs: https://example.com/session/architecture.html',
    ]
    for n, value in enumerate(accepted,1):
        scan(f'Text acceptance {n}: {value}', work, expected=0, args=('--text','-'), data=value+'\n')
    body = LAB / 'description.md'
    marker = LAB / 'unexpected-shell-execution'
    body.write_text('Bounds the scan to the changed set.\n\nLiteral shell documentation: $(touch ' + str(marker) + ')\n')
    scan('A saved clean PR description is read as data without shell execution', work, expected=0, args=('--text',body))
    assert not marker.exists()
    body.write_text('Bounds the scan to the changed set.\n\nCaptain, this PR rewrites the throttle.\n')
    scan('A saved PR description refuses a body-only address', work, args=('--text',body),
         contains=('line 3 matched captain-address-line', 'Reword the text above'))
    scan('An unavailable temporary-storage directory reports an incomplete scan', work, expected=3,
         args=('--text','-'), data='fix: clean text\n', extra_env={'TMPDIR':str(LAB/'missing-temp-dir')},
         contains=('cannot create temporary scan storage', 'The scan did not complete'))
    scan('An unknown option is an explicit usage error', work, expected=2, args=('--nope',), contains=('unknown argument',))
    scan('A missing text file is an explicit usage error', work, expected=2,
         args=('--text',LAB/'missing-description.md'), contains=('no such text file',))
    # This deliberate mutant is supporting regression evidence, never a live-product pass.
    mutant_dir = LAB / 'without-backtick'
    mutant_dir.mkdir()
    mutant = mutant_dir / GUARD.name
    source = GUARD.read_text()
    old = next(line for line in source.splitlines() if line.startswith('FM_VOICE_RULES+=("private-task-work-document'))
    new = old.replace('\\`','')
    assert new != old
    mutant.write_text(source.replace(old,new,1))
    for value in refusals[:2]:
        command(['bash',mutant,'--text','-'],cwd=work,data=value+'\n',expected=0,
                label=None)
        log.write('COUNTERFACTUAL: removing the backtick delimiter makes the required refusal assertion fail (exit 0 instead of 1).\n')
    command(['bash',mutant,'--text','-'],cwd=work,data=refusals[4]+'\n',expected=1)
    log.write('COUNTERFACTUAL CONTROL: the same mutant still refuses the bare relative path.\n')
    result = {'result':'pass', 'live_cases':records,
              'counterfactual':{'live':False, 'backticked_cases_without_delimiter':[0,0], 'bare_relative_control':1}}
    (EVIDENCE/'live-cli-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Completed {len(records)} live CLI checks. Transcript: {EVIDENCE}/live-cli-transcript.log')
finally:
    log.close()
