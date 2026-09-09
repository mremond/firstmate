from pathlib import Path
import subprocess as sp,os,json,shutil,time
R=Path.cwd();E=Path('/Users/mremond/.no-mistakes/evidence/01M2414ECRE7T77CAXN49RSA2F');W=R/'.test-phase-tmp'/'mutations';W.mkdir(parents=True,exist_ok=True)
s=(R/'tests/fm-procevent.test.sh').read_text();current=(R/'bin/fm-procevent.sh').read_text()
header=s[:s.index('# --- inert with nothing configured')]
header=header.replace('. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"',f'. "{R}/tests/lib.sh"')
header=header.replace('ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)','ROOT="$PROCEVENT_CODE_ROOT"')
setup=s[s.index('# --- an accidentally orphaned runner is bounded by its owner'):s.index('HORPHAN="$TMP_ROOT/orphan-dead-owner"')]
setup+='\nnow_ms() { perl -MTime::HiRes=time -e \'printf "%d\\n", time * 1000\'; }\n'
sections={
 'bound':s[s.index('# --- the guard\'s bound is one check interval, not two'):s.index('# --- a zero-prefixed interval still starts a listener')],
 'decimal':s[s.index('# --- a zero-prefixed interval still starts a listener'):s.index('# --- one unreadable read still does not end a live runner')],
 'debounce':s[s.index('# --- one unreadable read still does not end a live runner'):s.index('# --- the ordinary stop signal is what stops a runner')],
 'healthy':s[s.index('# --- the ordinary stop signal is what stops a runner'):s.index('# --- a crashed leader\'s group is still refused')]
}
def replace_once(s,a,b):
    assert s.count(a)==1,(a,s.count(a));return s.replace(a,b,1)
full=replace_once(current,'    sleep "$half"','    sleep "$tick"')
one=replace_once(current,'[ "$misses" -ge 2 ] || continue','[ "$misses" -ge 1 ] || continue')
dec=replace_once(current,'  tick=$((10#$tick))','  : # decimal normalization removed for counterfactual')
def delayed(code):return replace_once(code,'  start_owner_guard "$id" || die','  sleep 2.5\n  start_owner_guard "$id" || die')
base=sp.check_output(['git','show','78318e2c5746189c04d19b6148124ed99ecc5495:bin/fm-procevent.sh'],text=True)
cases=[
 ('base-healthy','healthy',base,False,'runner did not exit on TERM'),
 ('no-decimal','decimal',dec,False,'zero-prefixed decimal interval (08) prevented'),
 ('full-interval','bound',full,False,'guard exceeded its bound'),
 ('full-interval-delayed','bound',delayed(full),False,'guard exceeded its bound'),
 ('correct-delayed','bound',delayed(current),True,'guard bound:'),
 ('missing-phase','bound',current,False,'could not establish the required pre-expiry guard-read phase'),
 ('single-read-debounce','debounce',one,False,'one unreadable lease read ended'),
 ('single-read-bound','bound',one,True,'guard bound:')]
results=[]
try:
 for name,section,code,expected,reason in cases:
    cr=W/name;(cr/'bin').mkdir(parents=True)
    for f in (R/'bin').iterdir():
        if f.name=='fm-procevent.sh':continue
        (cr/'bin'/f.name).symlink_to(f)
    target=cr/'bin/fm-procevent.sh';target.write_text(code);target.chmod(0o755)
    body=sections[section]
    if name=='missing-phase':
        body=replace_once(body,"perl - \"$BOUND_STATE/reads\"",": > \"$BOUND_STATE/reads\" # intentionally withhold phase observations\nperl - \"$BOUND_STATE/reads\"")
    driver=E/(name+'.sh');driver.write_text(header+setup+body)
    print('RUN '+name,flush=True);log=E/(name+'.log');env=dict(os.environ,TMPDIR=str(W),PROCEVENT_CODE_ROOT=str(cr))
    start=time.monotonic()
    with log.open('w') as output:
        p=sp.run(['/bin/bash',str(driver)],env=env,stdout=output,stderr=sp.STDOUT,timeout=100)
    text=log.read_text();good=((p.returncode==0)==expected and reason in text)
    row=dict(name=name,exit=p.returncode,expected='GREEN' if expected else 'RED',matched=good,elapsed=round(time.monotonic()-start,2),evidence=log.name)
    results.append(row);print(json.dumps(row),flush=True)
    for line in text.splitlines():
        if 'not ok' in line or 'guard bound:' in line or 'guard phase:' in line:print(line,flush=True)
    assert good, row
finally:
 (E/'mutation-results.json').write_text(json.dumps(results,indent=2)+'\n')
 # Test-library cleanup already swept each owned process-event home.
 # Keep mutant material until the final process inventory confirms cleanup.
