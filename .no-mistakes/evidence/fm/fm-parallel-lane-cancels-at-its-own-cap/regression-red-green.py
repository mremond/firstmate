import os, subprocess
from pathlib import Path
root=Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M25NFVQ8EEP6P6ZERGFSAPA4')
out=Path('/Users/mremond/.no-mistakes/evidence/01M25NFVQ8EEP6P6ZERGFSAPA4')
scratch=root/'.test-phase'
env=os.environ.copy()
env.update(TMPDIR=str(scratch/'tmp'),TMP=str(scratch/'tmp'),FM_HOME=str(scratch/'home'),GIT_CONFIG_GLOBAL=str(scratch/'gitconfig'),GIT_CONFIG_NOSYSTEM='1')
# Reuse only the two committed regression functions, executing their CLI assertions.
# Source is loaded as runnable test code, never asserted on as textual evidence.
suite=(root/'tests/fm-test-run.test.sh').read_text()
start=suite.index('test_list_scheduled_proven_isolated_uses_serial_weights() {')
end=suite.index('test_portable_shard_union_and_coverage_guard() {',start)
functions=suite[start:end]
harness=out/'selected-scheduling-regressions.sh'
harness.write_text('set -u\n. "$1/tests/lib.sh"\nRUNNER=$2\n'+functions+'\n"$3"\n')
with (out/'regression-red-green.log').open('w') as log:
 for label,ref,expected in [('base','b1ad702fafdd03d94e5ce47cd4ba86e589ad33d6',0),('before-R1','f18754d7',1),('target','ec5b37133d40d607cd39042940f0d0d831c38f37',0)]:
  fixture=scratch/label
  (fixture/'bin').mkdir(parents=True,exist_ok=True)
  (fixture/'tests').symlink_to(root/'tests',target_is_directory=True)
  runner=fixture/'bin/fm-test-run.sh'
  runner.write_bytes(subprocess.check_output(['git','show',ref+':bin/fm-test-run.sh'],cwd=root))
  runner.chmod(0o755)
  for test in ['test_list_scheduled_proven_isolated_uses_serial_weights','test_list_scheduled_non_lane_selections_use_serial_weights']:
   p=subprocess.run(['/bin/bash',str(harness),str(root),str(runner),test],env=env,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
   log.write(f'{label} {ref} {test} exit={p.returncode}\n{p.stdout}\n'); log.flush()
   print(label,test,'exit='+str(p.returncode),p.stdout.strip(),flush=True)
   assert p.returncode == expected,(label,test,p.returncode)
