import os, subprocess, sys, time, json
from pathlib import Path
root = Path.cwd()
evidence = Path('/Users/mremond/.no-mistakes/evidence/01M20T4ZN7H0BNK630CKNGV56A')
scratch = root / '.no-mistakes/local-test-alpha'
source = (root / 'tests/fm-remote-secondmate-lifecycle-e2e.test.sh').read_text()
checkpoint = 'pass "remote seed registers the route and provisions the whole home and project clone on that host"'
observation = r'''printf 'ALPHA_EVIDENCE origin_HEAD=%s checkout_HEAD=%s\n' "$(git --git-dir="$TMP_ROOT/alpha.git" symbolic-ref HEAD)" "$(git -C "$REMOTE_HOME/projects/alpha" symbolic-ref HEAD)"
if [ -d "$REMOTE_HOME/projects/alpha/.git" ]; then printf 'ALPHA_EVIDENCE .git=present\n'; fi
if [ -f "$REMOTE_HOME/projects/alpha/README.md" ]; then
  printf 'ALPHA_EVIDENCE README.md='; cat "$REMOTE_HOME/projects/alpha/README.md"
  git -C "$REMOTE_HOME/projects/alpha" diff --exit-code HEAD -- README.md || fail "checkout README differs from committed README"
else
  printf 'ALPHA_EVIDENCE README.md=absent\n'
fi
printf 'BETA_EVIDENCE origin_HEAD=%s checkout_HEAD=%s README.md=' "$(git --git-dir="$TMP_ROOT/beta.git" symbolic-ref HEAD)" "$(git -C "$TMP_ROOT/seed-noclone-home/projects/beta" symbolic-ref HEAD)"
cat "$TMP_ROOT/seed-noclone-home/projects/beta/README.md"
'''
assertion = 'assert_present "$REMOTE_HOME/projects/alpha/README.md"'
mode, default = sys.argv[1:]
tmp = scratch / (mode + '-' + default)
tmp.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
for key in list(env):
    if key.startswith('FM_') or key.startswith('GIT_CONFIG_'):
        env.pop(key)
if mode == 'current-full-isolated':
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(tmp)], check=True)
if mode != 'current-full-native-temp':
    env['TMPDIR'] = str(tmp)
env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='init.defaultBranch', GIT_CONFIG_VALUE_0=default)
if mode.startswith('current-full'):
    test = root / 'tests/fm-remote-secondmate-lifecycle-e2e.test.sh'
else:
    test = root / ('tests/.local-alpha-' + mode + '-' + default + '.sh')
    body = source.split(checkpoint, 1)[0] + checkpoint + '\nprintf "TARGETED_ALPHA_PREFIX_COMPLETE\\n"\n'
    body = body.replace(assertion, observation + assertion, 1)
    if mode == 'unpinned-strong':
        body = body.replace('git init -q --bare -b main "$TMP_ROOT/alpha.git"', 'git init -q --bare "$TMP_ROOT/alpha.git"', 1)
    elif mode != 'pinned-prefix':
        raise ValueError(mode)
    test.write_text(body)
    (evidence / (mode + '-' + default + '.driver.sh')).write_text(body)
label = mode + '-' + default
command = ['bash', str(test.relative_to(root))]
start = time.monotonic()
try:
    with (evidence / (label + '.log')).open('w') as log:
        log.write('Process-local Git default: ' + default + '\nCommand: ' + ' '.join(command) + '\n')
        log.flush()
        child = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
        print(json.dumps({'run':label, 'pid':child.pid, 'log':str(evidence / (label + '.log'))}), flush=True)
        rc = child.wait()
        elapsed = round(time.monotonic()-start, 2)
        log.write('\nRUN_RESULT exit_code=' + str(rc) + ' elapsed_seconds=' + str(elapsed) + '\n')
    print(json.dumps({'run':label, 'exit_code':rc, 'elapsed_seconds':elapsed}), flush=True)
finally:
    if not mode.startswith('current-full'):
        test.unlink(missing_ok=True)
