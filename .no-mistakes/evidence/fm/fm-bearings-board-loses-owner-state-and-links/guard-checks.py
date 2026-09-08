import pathlib,subprocess,json,re,os
root=pathlib.Path.cwd(); lab=root/'.test-phase'; evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M21B2PY8J90QVVWWNDZ2WVGJ')
body=json.loads((lab/'workflow-step.json').read_text())['run']
prefix=body[body.index('expected_tests()'):body.index('snapshot_expected=')]
blocks={}
blocks['snapshot']=body[body.index('snapshot_expected='):body.index('bearings_expected=')]
blocks['bearings']=body[body.index('bearings_expected='):body.index('command -v npm')]
env=os.environ.copy();env.update(TMPDIR=str(lab/'tmp'),GIT_CEILING_DIRECTORIES=str(root))
summary=[]
for label,suite in [('snapshot','fm-fleet-snapshot-view.test.sh'),('bearings','fm-bearings-snapshot.test.sh')]:
    source=root/'tests'/suite; contents=source.read_text(); declared=len(re.findall(r'^test_[a-z_]*$',contents,re.M))
    for fault in ['early-stop','runs-nothing','empty-derivation']:
        text=contents.replace('. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"',f'. "{root}/tests/lib.sh"')
        lines=text.splitlines(True); indices=[i for i,line in enumerate(lines) if re.fullmatch('test_[a-z_]*\n',line)]
        if fault=='early-stop': lines.insert(indices[5],'exit 0 # injected successful early stop\n')
        if fault=='runs-nothing': lines.insert(indices[0],'exit 0 # injected successful empty run\n')
        if fault=='empty-derivation': lines=[line for i,line in enumerate(lines) if i not in indices]
        path=lab/f'{label}-{fault}.test.sh';path.write_text(''.join(lines))
        script='set -eu\n'+prefix+blocks[label].replace('tests/'+suite,str(path))
        p=subprocess.run(['/bin/bash','-c',script],env=env,capture_output=True,text=True)
        out=p.stdout+p.stderr
        (evidence/f'guard-{label}-{fault}.log').write_text(out+f'\nexit: {p.returncode}\n')
        if p.returncode!=1 or '::error::expected' not in out: raise RuntimeError(f'{label} {fault}: {out}')
        summary.append(dict(guard=label,fault=fault,expected=(0 if fault=='empty-derivation' else declared),observed=len(re.findall('^ok - ',out,re.M)),exit=p.returncode,error=[l for l in out.splitlines() if l.startswith('::error::')][0]))
        print(summary[-1],flush=True)
(evidence/'guard-fault-results.json').write_text(json.dumps(summary,indent=2))
