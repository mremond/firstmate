"""Supplemental mutation proof of the developer-facing stop diagnostic.

This deliberately uses the existing security fixture; it is NOT live product
evidence. All mutation copies and fixture data stay in the phase workspace.
"""
from pathlib import Path
import os
import re
import shutil
import signal
import subprocess as sp
import time

root = Path.cwd()
ev = Path(__file__).parent
mutant = root / '.phase-test/diagnostic-mutant'
shutil.copytree(root / 'bin', mutant / 'bin', dirs_exist_ok=True)
watch = mutant / 'bin/fm-watch.sh'
text = watch.read_text()
text = text.replace("trap 'exit 1' HUP INT TERM", "trap '' HUP INT TERM")
text = text.replace('fm_active_check_stop() {', 'fm_active_check_stop() {\n  return 0 # deliberate no-drain mutation')
watch.write_text(text)

source = (root / 'tests/fm-pr-check-security.test.sh').read_text().split('\ntest_parser_matrix\n', 1)[0]
source = source.replace('WATCH="$ROOT/bin/fm-watch.sh"', 'WATCH="' + str(watch) + '"')
source = source.replace('select undef, undef, undef, 4;', '''my $g=fork; die unless defined $g; if (!$g) { sleep 60; exit 0; } open my $gf, ">", "$ENV{FM_TEST_DESCENDANT_PID}.grandchild" or die $!; print {$gf} "$g\\n"; close $gf; select undef, undef, undef, 60;''')
test = root / 'tests/.phase-diagnostic-proof.sh'
test.write_text(source + '\nset -e\ntest_returned_custom_check_descendants_are_drained\n')
env = os.environ.copy()
env['TMPDIR'] = str(root / '.phase-test/tmp')
seen = {}
out = ev / 'diagnostic-proof.log'
with out.open('w') as log:
    p = sp.Popen(['bash', str(test)], env=env, stdout=log, stderr=sp.STDOUT, start_new_session=True)
try:
    end = time.monotonic() + 90
    while p.poll() is None and time.monotonic() < end:
        for path in (root / '.phase-test/tmp').glob('fm-pr-check-security.*/returned-custom-descendant-installed-timeout/descendant.pid*'):
            value = path.read_text().strip()
            if value.isdigit():
                seen[path.name] = int(value)
        time.sleep(.05)
    assert p.poll() is not None, 'mutated diagnostic case exceeded outer watchdog'
    result = out.read_text()
    assert p.returncode == 1, (p.returncode, result)
    assert 'installed-timeout watcher did not stop after the direct check returned' in result
    match = re.search(r'descendant tree \(watcher pid (\d+); recorded child pid (\d+)\)', result)
    assert match, result
    watcher, child = map(int, match.groups())
    grandchild = seen['descendant.pid.grandchild']
    rows = {}
    for line in result.splitlines():
        fields = line.split()
        if len(fields) >= 6 and all(x.isdigit() for x in fields[:3]):
            rows[int(fields[0])] = int(fields[1])
    assert watcher in rows and child in rows and grandchild in rows, (rows, seen)
    assert rows[child] != watcher and rows[grandchild] == child, rows
    with out.open('a') as log:
        log.write(f'\nExpected mutation RED: exit={p.returncode}. Diagnostic observed watcher={watcher}, reparented child={child} (ppid={rows[child]}), grandchild={grandchild} (ppid={rows[grandchild]}).\n')
    print('Expected RED; actual failure diagnostic includes watcher, reparented recorded child, and grandchild.')
finally:
    for pid in seen.values():
        try: os.kill(pid, signal.SIGKILL)
        except ProcessLookupError: pass
    try: os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    p.wait()
    test.unlink(missing_ok=True)
