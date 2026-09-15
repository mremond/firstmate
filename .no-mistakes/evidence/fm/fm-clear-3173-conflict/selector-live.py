import pathlib,subprocess,shutil,os,json,hashlib
r=pathlib.Path.cwd();lab=r/'.test-phase/selector-live';lab.mkdir();(lab/'bin').mkdir();shutil.copy2(r/'bin/fm-test-run.sh',lab/'bin/fm-test-run.sh');shutil.copytree(r/'tests',lab/'tests')
e=os.environ.copy();e.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',TMPDIR=str(r/'.test-phase/tmp'));e.pop('FM_TASK_ID',None)
records=[]
def cmd(args,expected=0):
 p=subprocess.run(args,cwd=lab,env=e,capture_output=True,text=True);records.append({'command':' '.join(args),'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert p.returncode==expected,records[-1];return p.stdout
cmd(['git','init','-q']);cmd(['git','add','.']);cmd(['git','-c','user.name=Validation','-c','user.email=validation@example.invalid','commit','-qm','Isolated exact target source corpus'])
runner=['bin/fm-test-run.sh','--list','--changed','--base','HEAD']
asset=lab/'tests/assets/board-render-harness.mjs';asset.write_text(asset.read_text()+'\n')
changed=cmd(runner);assert 'tests/fm-bearings-board-render.test.sh' in changed;assert 'tests/fm-test-run.test.sh' not in changed
cmd(['git','checkout','--','tests/assets/board-render-harness.mjs']);asset.unlink()
deleted=cmd(runner);assert changed==deleted
cmd(['git','checkout','--','tests/assets/board-render-harness.mjs'])
unread=lab/'tests/assets/live-unmapped.mjs';unread.write_text('export const unused = true;\n');cmd(runner,2);assert 'no changed-test mapping for source path: tests/assets/live-unmapped.mjs' in records[-1]['stderr'];unread.unlink()
helper=lab/'tests/git-config-helpers.sh';helper.write_text(helper.read_text()+'\n')
or_output=cmd(runner);assert 'tests/fm-bearings-board-render.test.sh' in or_output # its reference is to lib.sh (the second OR needle)
cmd(['git','checkout','--','tests/git-config-helpers.sh'])
# Retire the real asset's sole consumer as a completed input change, then change
# the asset alone: the selector's own synthetic fixtures must not mask refusal.
cmd(['git','rm','-q','tests/fm-bearings-board-render.test.sh']);cmd(['git','-c','user.name=Validation','-c','user.email=validation@example.invalid','commit','-qm','Retire actual reader in isolated corpus'])
asset.write_text(asset.read_text()+'\n');cmd(runner,2);assert 'no changed-test mapping for source path: tests/assets/board-render-harness.mjs' in records[-1]['stderr']
cmd(['git','checkout','--','tests/assets/board-render-harness.mjs']);asset.unlink();out=cmd(runner);assert out.strip()==''
# Explicit byte contract from the intent, supplemental to the executable checks.
base=subprocess.check_output(['git','show','b85e28b5f8aad91a553e33d461da9f238bbdac38:bin/fm-test-run.sh'],cwd=r)
head=(r/'bin/fm-test-run.sh').read_bytes()
def function_bytes(x):
 start=x.index(b'families_for_test_reference()');end=x.index(b'\n}\n',start)+3;return x[start:end]
assert function_bytes(base)==function_bytes(head)
records.append({'explicit_byte_contract':'families_for_test_reference unchanged from base','sha256':hashlib.sha256(function_bytes(head)).hexdigest()})
evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M2J0R8DH0RSQP7P5KYP5P1D5')
(evidence/'selector-live-transcript.json').write_text(json.dumps(records,indent=2))
print('Real selector with exact target test corpus: changed/deleted assets select consumers; unmapped assets refuse with exit 2; OR second needle selects its reader; retiring the actual reader exposes unmapped; deleting an unread asset selects nothing; explicit function byte contract matches base.')
