import os, sys, json, subprocess, tempfile, pathlib, shutil, resource, traceback, shlex, base64, tarfile, io
ROOT = pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M3W33QQYV7FCM041WC2819ZB')
EVID = pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M3W33QQYV7FCM041WC2819ZB')
results=json.loads((EVID/"live-results.json").read_text()) if (EVID/"live-results.json").exists() else []
lab_root=pathlib.Path(tempfile.mkdtemp(prefix='.fm5712-live-',dir=ROOT))
base_env={k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'TASKS_AXI_', 'HERDR_', 'TMUX'))}
log=None

def run(args, home, *, expect=0, extra=None, limit=None, cwd=None):
    env=dict(base_env, FM_HOME=str(home), TMPDIR=str(home/'tmp'), TMUX_TMPDIR=str(home/'tmux'))
    if extra: env.update(extra)
    def constrain(): resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
    shown=[str(x) for x in args]
    log.write('$ '+shlex.join(shown)+'\n')
    if extra: log.write('environment additions: '+repr(extra)+'\n')
    if limit is not None: log.write('process RLIMIT_FSIZE='+str(limit)+' bytes\n')
    p=subprocess.run(shown,cwd=cwd or ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,preexec_fn=constrain if limit is not None else None)
    log.write(p.stdout)
    if p.stderr: log.write('stderr:\n'+p.stderr)
    log.write('[exit '+str(p.returncode)+']\n\n');log.flush()
    if expect=='nonzero': assert p.returncode != 0, 'unexpected success'
    elif expect is not None: assert p.returncode==expect, f'exit {p.returncode}; expected {expect}'
    return p

def home(name):
    h=lab_root/name
    run([ROOT/'bin/fm-lab-home.sh','create',h], h)
    (h/'tmp').mkdir();(h/'tmux').mkdir()
    shutil.copyfile(ROOT/'.tasks.toml',h/'.tasks.toml')
    (h/'data/backlog.md').write_text('## In flight\n\n## Queued\n\n## Done\n')
    (h/'config/backend').write_text('tmux\n')
    (h/'config/supervision-host-off').touch()
    return h

def tasks(h,*args,**kw):return run([ROOT/'bin/fm-tasks-axi.sh',*args],h,**kw)
def hold(h,*args,**kw):return run([ROOT/'bin/fm-captain-hold.sh',*args],h,**kw)
def raw(h,*args,**kw):return run(['tasks-axi',*args],h,cwd=h,**kw)
def field(output,key):
    for line in output.splitlines():
        if line.startswith('  '+key+': '):
            v=line[len(key)+4:]
            return json.loads(v) if v.startswith('"') else v
    raise AssertionError('missing field '+key)
def meta(h,id):
    (h/'state'/f'{id}.meta').write_text('kind=scout\nmode=scout\n')
def assertlog(message):log.write('ASSERTION: '+message+'\n\n');log.flush()
def scenario(name,fn):
    global log
    path=EVID/(name+'.log')
    with path.open('w') as log:
        log.write('Target: fadcf45b24e4ea3d9103e6d118431222c8e2e6bf\nReal tasks-axi 0.2.6; no fake CLI or backend.\n\n')
        try:
            fn()
            result='pass';reason=''
        except Exception as e:
            traceback.print_exc(file=log)
            result='fail';reason=str(e)
    results[:] = [r for r in results if r['name'] != name]
    results.append(dict(name=name,result=result,live=True,evidence=str(path),reason=reason))
    print(name+': '+result+(' '+reason if reason else ''),flush=True)
    (EVID/'live-results.json').write_text(json.dumps(results,indent=2)+'\n')

def circular():
    h=home('circular');tasks(h,'add','origin','Origin investigation','--kind','scout');meta(h,'origin')
    before=(h/'state/origin.meta').read_bytes()
    hold(h,'hold','origin','--reason','',expect='nonzero')
    for phase in ['failed hold','durably held origin']:
        p=hold(h,'complete','origin','origin',expect='nonzero')
        assert 'cannot be its own captain-call inventory entry' in p.stderr
        assert (h/'state/origin.meta').read_bytes()==before
        assertlog(phase+': circular completion refused without recording an attestation')
        if phase=='failed hold':hold(h,'hold','origin','--reason','Choose a route')
    (h/'state/origin.meta').write_text('kind=scout\nmode=scout\ndecisions_reviewed=1\ndecision_keys=origin\n')
    hold(h,'verify','origin',expect='nonzero')
    hold(h,'hold','separate','--title','Separate captain call','--reason','Choose route','--origin','origin')
    p=hold(h,'complete','origin','separate',expect='nonzero')
    assert 'historical decision_keys' in p.stderr
    # Apply the product's stated recovery to this deliberately historical fixture.
    (h/'state/origin.meta').write_text('kind=scout\nmode=scout\ndecisions_reviewed=1\ndecision_keys=separate\n')
    hold(h,'complete','origin','separate');hold(h,'verify','origin')
    assertlog('Historical self-inventory stayed refused until its entry was replaced with a separate held call, then completion and verify succeeded')

def origins():
    h=home('origins')
    for o in ['origin-a','origin-b']:tasks(h,'add',o,o,'--kind','scout');meta(h,o)
    hold(h,'hold','call-a','--title','Call for A','--reason','Pick A','--origin','origin-a')
    shown=tasks(h,'show','call-a','--full').stdout
    assert 'Captain hold origin: origin-a' in field(shown,'body')
    before=(h/'state/origin-b.meta').read_bytes()
    p=hold(h,'complete','origin-b','call-a',expect='nonzero')
    assert 'was held for origin origin-a, not origin-b' in p.stderr
    assert (h/'state/origin-b.meta').read_bytes()==before
    (h/'state/origin-b.meta').write_text('kind=scout\ndecisions_reviewed=1\ndecision_keys=call-a\n')
    hold(h,'verify','origin-b',expect='nonzero')
    hold(h,'complete','origin-a','call-a');hold(h,'verify','origin-a')
    (h/'decision.txt').write_text('Use A. Synthetic validation answer.\n')
    hold(h,'answer','call-a','--decision-file',h/'decision.txt','--release')
    hold(h,'hold','call-a','--reason','Now decide for B','--origin','origin-b','--until','2099-01-01')
    body=field(tasks(h,'show','call-a','--full').stdout,'body')
    assert 'Captain hold origin: origin-b' in body and 'Captain hold origin: origin-a' not in body
    hold(h,'complete','origin-b','call-a');hold(h,'verify','origin-b')
    hold(h,'complete','origin-a','call-a',expect='nonzero');hold(h,'verify','origin-a',expect='nonzero')
    assertlog('Correct-origin completion passes; wrong-origin complete/verify refuse; a released call re-held for B replaces A and verifies only for B')
    hold(h,'hold','call-a','--reason','Active hold now belongs to A','--origin','origin-a')
    body=field(tasks(h,'show','call-a','--full').stdout,'body')
    assert 'Captain hold origin: origin-a' in body and 'Captain hold origin: origin-b' not in body
    hold(h,'complete','origin-a','call-a');hold(h,'verify','origin-a');hold(h,'verify','origin-b',expect='nonzero')
    assertlog('An active re-hold also overwrites the old association')

def legacy():
    h=home('legacy');tasks(h,'add','origin','Origin','--kind','scout');meta(h,'origin')
    tasks(h,'add','legacy','Old call','--kind','captain')
    raw(h,'hold','legacy','--reason','Legacy URL https://example.test/%28literal%29','--kind','captain')
    p=hold(h,'complete','origin','legacy');assert 'no recorded origin on: legacy; not checked against origin' in p.stdout
    hold(h,'verify','origin')
    tasks(h,'add','unheld','No recorded call','--kind','captain')
    hold(h,'complete','origin','unheld',expect='nonzero')
    assertlog('A genuinely old held row is accepted with an explicit no-origin warning; an unheld row cannot satisfy the fallback')

def reasons():
    h=home('reasons')
    title='Investigate literal %28, "fm-hold-v1:bm9ydGg="'
    legacy='Visit https://example.test/%28literal%29 and %0A; fm-hold-v1:bm9ydGg='
    body='fm-hold-v1:bm9ydGg=\n  hold_reason: "%28"\n'
    reason='  Pick route (north); say "yes" or \'no\' - 100% sure %28x%29, café\t\\slash\r\nSecond line\n\n'
    tasks(h,'add','legacy',title,'--kind','captain','--body',body)
    raw(h,'hold','legacy','--reason',legacy,'--kind','captain')
    for id,value,extra in [('prose',reason,[]),('marker','fm-hold-v1:bm9ydGg=',['--until','2099-01-01'])]:
        hold(h,'hold',id,'--title',title,'--reason',value,*extra)
        stored=field(raw(h,'show',id,'--full').stdout,'hold_reason')
        assert stored.startswith('fm-hold-v1:') and base64.b64decode(stored.split(':',1)[1]).decode()==value
        for verb in ['show','view']:
            out=tasks(h,verb,id,'--full').stdout
            assert field(out,'hold_reason')==value and field(out,'title')==title
        for fields in ['hold_reason,body','body,hold_reason,hold_until']:
            out=tasks(h,'list','--fields',fields).stdout
            encoded=json.dumps(value,ensure_ascii=False,separators=(',',':'))
            assert encoded in out
            expected=next(x for x in raw(h,'list','--fields',fields).stdout.splitlines() if x.startswith('  legacy,'))
            assert expected in out
        assertlog(id+': marked stored reason decodes byte-for-byte at show/view/list, including trailing newlines; titles and legacy fields unchanged')
    assert tasks(h,'show','legacy','--full').stdout==raw(h,'show','legacy','--full').stdout
    assert tasks(h,'list').stdout==raw(h,'list').stdout
    for verb in ['show','list']: assert tasks(h,verb,'--help').stdout==raw(h,verb,'--help').stdout
    err=tasks(h,'show','absent',expect='nonzero');direct=raw(h,'show','absent',expect='nonzero')
    assert (err.returncode,err.stdout,err.stderr)==(direct.returncode,direct.stdout,direct.stderr)
    snap=run([ROOT/'bin/fm-fleet-snapshot.sh','--json'],h).stdout
    (EVID/'fleet-snapshot.json').write_text(snap)
    records={r['id']:r for r in json.loads(snap)['backlog']['records']}
    assert records['prose']['hold_reason']==reason and records['prose']['title']==title
    assert records['marker']['hold_reason']=='fm-hold-v1:bm9ydGg='
    assert records['legacy']['hold_reason']==legacy and records['legacy']['body_lines'][0]=='fm-hold-v1:bm9ydGg='
    assertlog('Fleet JSON preserves Unicode and exact multiline reason, legacy percent text, marker-looking reason, title and unrelated body')
    # Keep this lab for reader checks in this same evidence run.
    return h,reason,title,legacy

def failed_write():
    h=home('failed-origin-write')
    tasks(h,'add','origin','Origin','--kind','scout');meta(h,'origin')
    stamp='2026-10-01T12:00:00Z'
    for id,extra in [('plain',[]),('dated',['--until','2099-01-01'])]:
        tasks(h,'add',id,'Call','--kind','captain','--body','Captain hold set: '+stamp)
        before=(h/'data/backlog.md').read_bytes()
        # Rewriting the unchanged timestamp fits; appending the origin does not.
        limit=len(before)+1
        p=hold(h,'hold',id,'--reason','Choose','--origin','origin',*extra,expect='nonzero',limit=limit,extra={'FM_CAPTAIN_HOLD_NOW':stamp})
        assert 'could not record the hold origin' in p.stderr, 'failure occurred before origin write'
        out=tasks(h,'show',id,'--full').stdout
        assert field(out,'held')=='no'
        assert 'Captain hold origin:' not in field(out,'body')
        hold(h,'complete','origin',id,expect='nonzero')
        assertlog(id+': genuine origin-update storage failure leaves row unheld and cannot satisfy completion')
        hold(h,'hold',id,'--reason','Choose','--origin','origin',*extra)
        hold(h,'complete','origin',id);hold(h,'verify','origin')
        assertlog(id+': removing the local resource restriction lets the same hold complete and verify')


def readers():
    h=home('summary-readers')
    reason='Pick route (north); say "yes"\nNext line'
    title='Investigate literal %28 and fm-hold-v1:bm9ydGg='
    legacy='Visit https://example.test/%28literal%29 and %0A'
    hold(h,'hold','prose','--title',title,'--reason',reason)
    hold(h,'hold','marker','--title','Marker-like input','--reason','fm-hold-v1:bm9ydGg=')
    tasks(h,'add','legacy','Legacy title %28','--kind','captain')
    raw(h,'hold','legacy','--reason',legacy,'--kind','captain')
    quoted=json.dumps(reason,ensure_ascii=False)
    # A genuinely unwritable disposable state directory selects startup's
    # supported read-only digest; it cannot acquire the lock or start network work.
    (h/'state').chmod(0o555)
    try:
        for mode in ['tasks-axi','manual']:
            if mode=='manual': (h/'config/backlog-backend').write_text('manual\n')
            p=run([ROOT/'bin/fm-session-start.sh'],h,extra={'FM_SESSION_START_TIMEOUT':'45'})
            (EVID/f'startup-{mode}.txt').write_text(p.stdout+p.stderr)
            assert 'READ-ONLY SESSION' in p.stdout
            assert 'The digest above is complete for this session start.' in p.stdout
            assert quoted in p.stdout and title in p.stdout and legacy in p.stdout
            assert '"fm-hold-v1:bm9ydGg="' in p.stdout, 'marker-shaped reason decoded twice'
            assertlog('Startup '+mode+' digest preserves prose, literal percent text and marker-like text exactly')
    finally:
        (h/'state').chmod(0o755)
    (h/'config/backlog-backend').unlink()
    p=run([ROOT/'bin/fm-afk-return.sh','check'],h)
    (EVID/'return-summary.txt').write_text(p.stdout+p.stderr)
    assert quoted in p.stdout and title in p.stdout and legacy in p.stdout
    assert '"fm-hold-v1:bm9ydGg="' in p.stdout
    assertlog('Real return check renders the same reason and leaves legacy, title and marker-like text unchanged')

def baseline():
    h=home('baseline')
    base=lab_root/'base-code';base.mkdir()
    archive=subprocess.check_output(['git','archive','8f756bbc287c5bdfacc64a7cc09e8516c64fc919','bin','.tasks.toml'],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as t:t.extractall(base,filter='data')
    log.write('$ git archive 8f756bbc287c5bdfacc64a7cc09e8516c64fc919 bin .tasks.toml (extracted only into disposable workspace)\n')
    tasks(h,'add','origin','Origin','--kind','scout');meta(h,'origin')
    script=base/'bin/fm-captain-hold.sh'
    run([script,'hold','origin','--reason','Choose a route'],h)
    p=run([script,'hold','origin','--reason','Choose (north); "yes"'],h,expect='nonzero')
    assert 'reason must not contain parentheses' in p.stderr
    p=run([script,'hold','origin','--reason','Choose (north); "yes"\nNext'],h,expect='nonzero')
    assert 'reason must be one line' in p.stderr or 'reason must not contain parentheses' in p.stderr
    p=run([script,'complete','origin','origin'],h)
    assert 'captain-call inventory reviewed' in p.stdout
    assertlog('The base rejects ordinary prose then accepts circular completion on the durable origin; target scenarios reject that completion and accept the prose')


def fallback_reader():
    h=home('reader-fallback')
    reason='Choose (north); "yes"\nNext line'
    hold(h,'hold','call','--title','Keep %28 unchanged','--reason',reason)
    # Select an unavailable adapter in the disposable environment; startup
    # must render its manual fallback from the still-readable backlog.
    unavailable={"TASKS_AXI_BACKEND":"unsupported-validation-backend"}
    tasks(h,"list",expect="nonzero",extra=unavailable)
    (h/'state').chmod(0o555)
    try:
        p=run([ROOT/'bin/fm-session-start.sh'],h,extra={'FM_SESSION_START_TIMEOUT':'45',**unavailable})
        (EVID/'startup-fallback.txt').write_text(p.stdout+p.stderr)
        assert json.dumps(reason) in p.stdout and 'Keep %28 unchanged' in p.stdout
        assert any(line.lstrip().startswith('- [ ] call ') for line in p.stdout.splitlines())
        assertlog('A genuine adapter configuration failure selects manual fallback and the held prose remains decoded correctly')
    finally:(h/'state').chmod(0o755)

def closed_inventory():
    h=home('closed-inventory')
    for id in ['origin-a','origin-b']: tasks(h,'add',id,id,'--kind','scout');meta(h,id)
    hold(h,'hold','recorded','--title','Recorded call','--reason','Choose (north)','--origin','origin-a')
    (h/'answer.txt').write_text('Use north. Synthetic validation answer.\n')
    hold(h,'answer','recorded','--decision-file',h/'answer.txt')
    shown=tasks(h,'show','recorded','--full').stdout
    assert field(shown,'state')=='done' and 'Captain hold origin: origin-a' in field(shown,'body')
    hold(h,'complete','origin-a','recorded');hold(h,'verify','origin-a')
    p=hold(h,'complete','origin-b','recorded',expect='nonzero')
    assert 'was held for origin origin-a, not origin-b' in p.stderr
    tasks(h,'add','legacy','Old call','--kind','captain')
    raw(h,'hold','legacy','--reason','Old hold','--kind','captain')
    hold(h,'answer','legacy','--decision-file',h/'answer.txt')
    p=hold(h,'complete','origin-b','legacy')
    assert 'no recorded origin on: legacy' in p.stdout
    hold(h,'verify','origin-b')
    assertlog('Answered closed calls retain origin enforcement; an answered legacy call remains accepted with explicit fallback disclosure')

cases={
    'circular-inventory':circular,
    'origin-association-and-rehold':origins,
    'legacy-origin-fallback':legacy,
    'reason-roundtrip-and-public-readers':reasons,
    'origin-write-failure':failed_write,
    'startup-and-return-readers':readers,
    'baseline-reproduction':baseline,
    'startup-fallback-reader':fallback_reader,
    'answered-inventory':closed_inventory,
}
try:
    for name in (sys.argv[1:] or list(cases)):
        scenario(name,cases[name])
finally:
    shutil.rmtree(lab_root)
    print('Disposed all lab homes: '+str(lab_root),flush=True)
