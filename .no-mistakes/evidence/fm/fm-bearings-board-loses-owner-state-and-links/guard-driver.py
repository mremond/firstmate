from pathlib import Path
import json,os,subprocess,hashlib,copy
root=Path.cwd();board=root/'.test-lab/main/.lavish/bearings-board.html';base=json.load(open('.test-lab/payload.json'));before=hashlib.sha256(board.read_bytes()).hexdigest();out=[]
old=json.load(open('/Users/mremond/.no-mistakes/evidence/01M2GAWMSDQK4B5EA9GZW35RXE/snapshot-off.json'))['awaiting'][0];old.pop('nudge')
for mode in ['overdue','missing-pr','null-age']:
 p=copy.deepcopy(base);p['awaiting_nudge_days']=7;p['awaiting']=[dict(old)]
 if mode=='missing-pr':p['awaiting'][0]['age_days']=2;p['awaiting'][0].pop('pr_url')
 if mode=='null-age':p['awaiting'][0]['age_days']=None
 path=root/'.test-lab/rejected.json';path.write_text(json.dumps(p))
 result=subprocess.run([str(root/'bin/fm-bearings-board.sh'),'build',str(path)],text=True,capture_output=True)
 assert result.returncode!=0,(mode,result.stdout)
 assert hashlib.sha256(board.read_bytes()).hexdigest()==before
 out.append(dict(input=mode,exit_code=result.returncode,error=result.stderr.strip(),existing_board_preserved=True))
print(json.dumps(out,indent=2))
