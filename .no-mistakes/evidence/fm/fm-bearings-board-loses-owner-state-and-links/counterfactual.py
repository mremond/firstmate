import pathlib,subprocess,re,os
root=pathlib.Path.cwd();lab=root/'.test-phase';evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M21B2PY8J90QVVWWNDZ2WVGJ');oldbin=lab/'pre-fix-bin';oldbin.mkdir(exist_ok=True)
for file in (root/'bin').iterdir():
    if file.name in ['fm-fleet-snapshot.sh','fm-bearings-snapshot.sh']:
        old=oldbin/file.name;old.write_bytes(subprocess.check_output(['git','show','4996127f:bin/'+file.name]));old.chmod(0o755)
    else: (oldbin/file.name).symlink_to(file)
s=(root/'tests/fm-bearings-snapshot.test.sh').read_text()
s=s.replace('. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"',f'. "{root}/tests/lib.sh"')
s=''.join(line for line in s.splitlines(True) if not re.fullmatch('test_[a-z_]*\n',line))
s+='\ntest_backlog_reason_urls_never_become_child_request_links\n'
env=os.environ.copy();env.update(GIT_CEILING_DIRECTORIES=str(root),TMPDIR=str(lab/'tmp'))
for name,directory in [('before',oldbin),('after',root/'bin')]:
    changed=s.replace('$ROOT/bin/fm-fleet-snapshot.sh',str(directory/'fm-fleet-snapshot.sh')).replace('$ROOT/bin/fm-bearings-snapshot.sh',str(directory/'fm-bearings-snapshot.sh'))
    path=lab/('backlog-reason-'+name+'.sh');path.write_text(changed)
    p=subprocess.run(['/bin/bash',str(path)],env=env,text=True,capture_output=True)
    (evidence/f'backlog-reason-{name}.log').write_text(p.stdout+p.stderr+f'\nexit: {p.returncode}\n')
    print(name,'exit',p.returncode,flush=True)
    assert p.returncode==(1 if name=='before' else 0)
