import os, pathlib, shutil, subprocess, sys, time
root = pathlib.Path.cwd()
evidence = pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M41GZ8K0CW9VW3DVRVCQTVTP')
version, tag, test = sys.argv[1:]
lab = root / '.no-mistakes/test-lab'
prefix = lab / ('pi-' + version)
tmp = root / '.v' / tag
tmp.mkdir(parents=True, exist_ok=True)
config = tmp / 'isolated-pi-config'
config.mkdir()
outdir = evidence / tag
outdir.mkdir(exist_ok=True)
env = os.environ.copy()
for k in ['FM_HOME', 'FM_ROOT_OVERRIDE', 'FM_STATE_OVERRIDE', 'FM_DATA_OVERRIDE', 'FM_CONFIG_OVERRIDE', 'FM_PROJECTS_OVERRIDE', 'TMUX', 'TMUX_PANE', 'FM_TASK_ID']:
    env.pop(k, None)
env.update(PATH=str(prefix / 'bin') + ':' + env['PATH'], FM_PI_PACKAGE_DIR=str(prefix / 'lib/node_modules/@earendil-works/pi-coding-agent'), TMPDIR=str(tmp), TMUX_TMPDIR='/tmp', PI_CODING_AGENT_DIR=str(config), PI_OFFLINE='1', FM_TEST_SKIP_ORPHAN_REAP='1')
command = ['bash', 'bin/fm-test-run.sh', test]
with (outdir / 'test.log').open('w') as log:
    log.write('command: ' + ' '.join(command) + '\n')
    log.write('target: ' + subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True))
    log.write('Pi: ' + subprocess.check_output(['pi', '--version'], env=env, text=True))
    log.write('Node: ' + subprocess.check_output(['node', '--version'], text=True))
    log.flush()
    p = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    start = time.monotonic()
    while p.poll() is None:
        for fixture in tmp.glob('fm-calm-pi-extension.*'):
            for name in ['calm-export.html', 'calm-export-dom.html', 'calm-session.jsonl', 'default.txt', 'active-hidden.txt', 'export.txt', 'export-settled.txt', 'restored.txt', 'renderer-output.txt', 'working.txt', 'remapped-enter.txt']:
                source = fixture / name
                if source.is_file():
                    try:
                        shutil.copyfile(source, outdir / name)
                    except FileNotFoundError:
                        pass
        if time.monotonic() - start > 180:
            p.terminate()
            raise RuntimeError('targeted suite exceeded 180s')
        time.sleep(.05)
    log.write('\nprocess_exit=' + str(p.returncode) + '\n')
print((outdir / 'test.log').read_text())
sys.exit(p.returncode)
