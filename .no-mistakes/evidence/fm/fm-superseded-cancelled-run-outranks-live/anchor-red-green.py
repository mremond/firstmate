from pathlib import Path
import os,subprocess
ROOT=Path("/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2GV0N1CJ7TGNYN3P76KK9TS")
EVIDENCE=Path("/Users/mremond/.no-mistakes/evidence/01M2GV0N1CJ7TGNYN3P76KK9TS")
SCRATCH=ROOT/".test-3215"
(SCRATCH/"tmp").mkdir(parents=True,exist_ok=True)
text=(ROOT/"tests/fm-crew-state.test.sh").read_text().split("\ntest_captured_axi_status_shapes\n",1)[0]
text=text.replace('. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"','. "$FM3215_REPO/tests/lib.sh"',1)
runner=SCRATCH/"anchored-regression.sh"
runner.write_text(text+'\nCREW_STATE="$FM3215_PRODUCT"\n"$FM3215_CASE"\n')
cases={
"80556bca2d728071cc14476b9bee60a8edf4159e":["test_captured_axi_status_shapes","test_captured_inventory_replay"],
"5588b3ea1f86e662ef505aaf30d5ec03da9c4c31":["test_captured_authority_transition","test_captured_completed_history","test_uninitialized_busy_worker_uses_pane","test_uninitialized_idle_worker_uses_status"]}
failed=[]
with (EVIDENCE/"anchor-red-green.log").open("w") as log:
    log.write("NON-LIVE REPLAY: genuine captured inputs with documented fixture compositions.\n")
    for ref,names in cases.items():
        archive=SCRATCH/("historical-"+ref[:8])
        archive.mkdir(exist_ok=True)
        data=subprocess.check_output(["git","archive",ref,"bin"],cwd=ROOT)
        subprocess.run(["tar","-x","-C",str(archive)],input=data,check=True)
        for name in names:
            for phase,product in [("RED",archive/"bin/fm-crew-state.sh"),("GREEN",ROOT/"bin/fm-crew-state.sh")]:
                env=dict(os.environ,TMPDIR=str(SCRATCH/"tmp"),FM3215_REPO=str(ROOT),FM3215_PRODUCT=str(product),FM3215_CASE=name)
                r=subprocess.run(["bash",str(runner)],env=env,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                ok=(r.returncode!=0 if phase=="RED" else r.returncode==0)
                log.write(f"\n{phase} {name} at {ref if phase=='RED' else '7feb0272 plus captured-input tests'}\n{r.stdout}exit: {r.returncode}\n")
                log.flush()
                print(f"{phase} {name}: {'expected outcome' if ok else 'UNEXPECTED'}",flush=True)
                if not ok:failed.append(name+":"+phase)
if failed:raise SystemExit(str(failed))
