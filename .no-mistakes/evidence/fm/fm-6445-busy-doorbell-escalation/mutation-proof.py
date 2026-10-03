from pathlib import Path
import shutil,subprocess,re,json
r=Path.cwd(); scratch=r/'.test-busy-lab/mutation'; evidence=Path('/Users/mremond/.no-mistakes/evidence/01M41JF8PZQEQWCHFEW097SGNE'); scratch.mkdir()
for part in ['bin','tests']: shutil.copytree(r/part,scratch/part)
sources={name:(r/name).read_text() for name in ['bin/fm-watch.sh','bin/fm-task-inbox-lib.sh','bin/fm-supervise-daemon.sh','tests/fm-task-inbox.test.sh','tests/fm-daemon.test.sh']}
cases=[]
for mode in ['busy','dead','missing','unwritable']: cases.append(('R1-'+mode,'tests/fm-task-inbox.test.sh','test_watcher_successor_escalation_stays_quiet '+mode,'R1'))
for mode in ['protected','failed']: cases.append(('R2-'+mode,'tests/fm-task-inbox.test.sh','test_watcher_nonbusy_attempt_resets_busy_streak '+mode,'R2'))
for variant in ['stuck','write','reset']:
 for mode in ['away','quiet']: cases.append(('R4-'+variant+'-'+mode,'tests/fm-daemon.test.sh','test_busy_inbox_escalation_reaches_supervision '+variant+' '+mode,'R4'))
cases.append(('R4-scope','tests/fm-daemon.test.sh','test_busy_inbox_dispatch_preserves_other_stale_reasons','scope'))
results=[]
for name,test,selector,mutation in cases:
 for path,src in sources.items(): (scratch/path).write_text(src)
 text=sources[test]
 # Select executable test calls, preserving all helper and function definitions.
 text='\n'.join(line for line in text.splitlines() if not re.fullmatch(r'test_[A-Za-z0-9_]+(?: [A-Za-z0-9_-]+)*',line))+'\n'+selector+'\n'
 (scratch/test).write_text(text)
 def run(variant):
  proc=subprocess.run(['bash',str(scratch/test)],capture_output=True,text=True,timeout=45)
  (evidence/f'mutation-{name}-{variant}.log').write_text(proc.stdout+proc.stderr)
  return {'exit':proc.returncode,'output':(proc.stdout+proc.stderr).strip()}
 good=run('target')
 if mutation=='R1':
  path='bin/fm-task-inbox-lib.sh'; src=sources[path]; old='    count=0\n    last=0\n  fi\n'; assert src.count(old)==1; src=src.replace(old,'    count=0\n    last=0\n    rm -f "$dir/.escalated" 2>/dev/null || true\n  fi\n')
 elif mutation=='R2':
  path='bin/fm-watch.sh'; src=sources[path]; start=src.index('  elif ! fm_task_inbox_clear_busy "$STATE" "$task"; then'); end=src.index('\n  fi\n  case "$verb"',start); src=src[:start]+src[end:]; old='      triage_log "steer-inbox delivery attempt:'; src=src.replace(old,'      [ "$ring_rc" -ne 0 ] || fm_task_inbox_clear_busy "$STATE" "$task"\n'+old)
 elif mutation=='R4':
  path='bin/fm-supervise-daemon.sh'; src=sources[path]; start=src.index('    stale:*" (unread firstmate instruction: stuck-busy '); end=src.index('    stale:*)',start); src=src[:start]+src[end:]
 else:
  path='bin/fm-supervise-daemon.sh'; src=sources[path]; start=src.index('    stale:*" (unread firstmate instruction: stuck-busy '); end=src.index('\n',start); src=src[:start]+'    stale:*)'+src[end:]
 (scratch/path).write_text(src)
 bad=run('mutant')
 result={'name':name,'selector':selector,'target':good,'mutant':bad,'mutation_detected':good['exit']==0 and bad['exit']!=0}; results.append(result)
 print(json.dumps(result),flush=True)
(evidence/'mutation-results.json').write_text(json.dumps(results,indent=2)+'\n')
assert all(x['mutation_detected'] for x in results)
