import json, os, pathlib, subprocess
root=pathlib.Path.cwd()
evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M2J0R8DH0RSQP7P5KYP5P1D5')
risks=[('fr-composed','faible. La vue reste dérivée. Aucun état de travail ne change.'),('en-low','  LOW  '),('fr-bare','  Faible  '),('unknown','élevé. Une migration de données exige une vérification.'),('substring','low-ish. Ce niveau ne doit pas perdre son alerte.'),('blank','   '),('long-level','x'*180),('long-detail','faible. '+'y'*180),('empty-level','. Justification sans niveau.'),('multi-period','low. First sentence. Second sentence.')]
payload={'schema':'fm-bearings-board.v1','home':'Isolated board validation','generated':'2026-09-15T08:00Z','prs_live':False,'captains_call':[{'key':k,'type':'merge','repo':'sample','title':k+': inspect the risk level and its justification','risk':r,'options':[{'value':'merge','label':'Merge'}]} for k,r in risks], 'underway':[{'id':'underway-validation','repo':'sample','name':'Keep the task title readable while the implementation is running: '+ 'readable title segment '*20,'state':'working','doing':'Preserve the live run status and useful context: '+'secondary context '*20,'kind':'ship'}], 'landed':[{'id':'landed-validation','repo':'sample','what':'A completed task with enough context to explain the delivered work: '+'readable title segment '*20,'owner':'validation'}], 'charted':[{'id':'charted-long','repo':'sample','title':'Understand the queued work before deciding to dispatch it: '+'readable title segment '*24,'reason':'Read the reason without opening another screen: '+'secondary context '*24,'dispatchable':True},{'id':'charted-token','repo':'sample','title':'z'*220,'reason':'w'*220,'dispatchable':True}],'charted_more':0,'charted_warning_more':0}
(evidence/'live-input.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
home=root/'.test-phase/live-home'
(home/'payload.json').write_text(json.dumps(payload,ensure_ascii=False))
env=os.environ.copy()
env.update(FM_HOME=str(home),FM_STATE_OVERRIDE=str(home/'state'),FM_DATA_OVERRIDE=str(home/'data'),FM_PROCEVENT_CLAIM_ROOT=str(home/'claims'),FM_GATE_REFUSE_BYPASS='1',LAVISH_AXI_STATE_DIR=str(root/'.test-phase/lavish-state'),LAVISH_AXI_PORT='14387',LAVISH_AXI_HOST='127.0.0.1',LAVISH_AXI_NO_OPEN='1',TMPDIR=str(root/'.test-phase/tmp'))
p=subprocess.run(['bin/fm-bearings-board.sh','build',str(home/'payload.json')],env=env,capture_output=True,text=True)
(evidence/'live-build.log').write_text(p.stdout+p.stderr)
print(p.stdout+p.stderr)
raise SystemExit(p.returncode)
