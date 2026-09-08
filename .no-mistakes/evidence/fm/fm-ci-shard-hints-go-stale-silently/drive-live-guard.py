import json, os, signal, subprocess, time, shlex
from pathlib import Path
ROOT = Path.cwd()
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M20P1RQF711N8XQS8YPKN43T')
env = os.environ.copy()
env['TMPDIR'] = str(ROOT / '.local-shard-validation/tmp')
env['FM_HOME'] = str(ROOT / '.local-shard-validation/home')
families = subprocess.check_output(['bin/fm-test-run.sh', '--list-families'], text=True, env=env).splitlines()
selection = ['--lane', 'portable-serial-5of6']
for family in families:
    if family != 'pure-contract-unit':
        selection += ['--exclude-family', family]
transcript = EVIDENCE / 'live-guard-transcript.txt'

def note(message):
    entry = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ' ' + message
    print(entry, flush=True)
    with transcript.open('a') as out: out.write(entry + '\n')

def run(label, pause):
    artifact = EVIDENCE / (label + '.json')
    args = ['bin/fm-test-run.sh', *selection, '--json', str(artifact)]
    note('$ ' + shlex.join(args))
    start = time.monotonic()
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
    stopped = False
    try:
        with (EVIDENCE / (label + '.log')).open('w') as log:
            for line in proc.stdout:
                log.write(line); log.flush()
                if pause and not stopped and line.startswith('FM_TEST_BEGIN '):
                    note('SIGSTOP isolated runner process group at first script BEGIN; simulate scheduler starvation without modifying code, artifact, or clock')
                    os.killpg(proc.pid, signal.SIGSTOP)
                    stopped = True
                    deadline = time.monotonic() + 1081
                    while time.monotonic() < deadline:
                        time.sleep(min(30, deadline-time.monotonic()))
                        note('Starvation probe remaining seconds: %.0f' % max(0, deadline-time.monotonic()))
                    os.killpg(proc.pid, signal.SIGCONT)
                    note('SIGCONT isolated runner process group')
            rc = proc.wait(timeout=180)
        note(f'{label} runner exit={rc} independent elapsed={time.monotonic()-start:.3f}s')
        assert rc == 0
        data = json.loads(artifact.read_text())
        note('Fresh runner summary: ' + json.dumps(data['summary'], sort_keys=True))
        note('Fresh runner script measurements: ' + json.dumps([{k:s[k] for k in ['path','duration_ms','exit']} for s in data['scripts']]))
        assert len(data['scripts']) == 2
        args = ['bin/fm-test-run.sh', '--check-shard-balance', str(artifact)]
        note('$ ' + shlex.join(args))
        checked = subprocess.run(args, env=env, text=True, capture_output=True)
        (EVIDENCE / (label + '-guard.txt')).write_text(checked.stdout + checked.stderr + f'\nexit={checked.returncode}\n')
        note(checked.stdout + checked.stderr + f'exit={checked.returncode}')
        assert checked.returncode == (1 if pause else 0)
        assert 'partial 1 of 6' in checked.stdout
        if pause:
            assert data['summary']['duration_ms'] > 1080000
            assert 're-measure' in checked.stderr
            assert 'tests/fm-subagent-pretool-check.test.sh' in checked.stderr
        return str(artifact)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGCONT)
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=15)

note('Target ' + subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip())
run('fresh-healthy-shard', False)
run('fresh-starved-shard', True)
note('Fresh healthy, partial-coverage, and pre-cap rejection scenarios completed')
