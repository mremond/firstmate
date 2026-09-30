from live_driver import *
# Stop each lab's real sources through their public ownership-aware retirement.
for marker in sorted(RUNTIME.glob('*/.fm-lab-home')):
    h=marker.parent
    if (h/'state/procevent').exists():
        run(['bin/fm-procevent.sh','sweep-home'],h,timeout=120)
claims=list((RUNTIME/'live-claims').glob('*.claim'))
assert not claims,claims
snapshot('final-before-lab-cleanup')
# The saved store contains only sessions created by this driver.
store=json.loads((RUNTIME/'lavish/state.json').read_text())
for row in store['sessions'].values():
    assert pathlib.Path(row['file']).is_relative_to(RUNTIME)
    if row.get('status')!='ended':
        file=pathlib.Path(row['file'])
        if not file.exists():
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text('<html><body>Disposable fixture restored only to close this lab session after forced removal.</body></html>')
            print('Cleanup only: restored removed synthetic file for Lavish CLI end:',file,flush=True)
        run(['lavish-axi','end',file])
assert all(v.get('status')=='ended' for v in json.loads((RUNTIME/'lavish/state.json').read_text())['sessions'].values())
snapshot('all-lab-sessions-ended')
run(['lavish-axi','stop'])
run(['tmux','-L','fm-lab','kill-server'])
run(['bin/fm-lab-home.sh','teardown',C['controller']])
assert not pathlib.Path(C['tmuxdir']).exists()
result('lab cleanup',result='pass',claims_remaining=0,all_sessions='ended',private_tmux='stopped and removed')
# Retain runtime evidence before removing the transient fixtures.
log=RUNTIME/'lavish/server.log'
if log.exists():shutil.copyfile(log,EVID/'lavish-server.log')
