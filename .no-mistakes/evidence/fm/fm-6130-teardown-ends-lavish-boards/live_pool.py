from live_scenarios import *
p=RUNTIME/'pool-project'
allocation=json.loads(next(x for x in (RUNTIME/'pool-allocation.json').read_text().splitlines() if x.startswith('{')))
wt=pathlib.Path(allocation['path'])
assert wt.is_relative_to(RUNTIME)
h=lab('pool-worker');task(h,kind='scout',worktree=wt,project=p,decisions_reviewed='1',decision_keys='')
(h/'data/finished/report.md').write_text('Synthetic completed scout report. No captain calls.\n')
(wt.parent/'.fm-slot-owner').write_text(f'task=finished\nhome={h}\n')
b=board(wt/'.lavish/review.html','Pooled worktree review')
assert b.exists()
snapshot('before-pool-return')
teardown(h)
assert state(b)['status']=='ended'
run(['treehouse','status'],cwd=p)
assert not (wt.parent/'.fm-slot-owner').exists()
result('ordinary pooled worktree return',result='pass',board='ended',lease='returned',board_exists_after_return=b.exists())
snapshot('after-pool-return')
# Exercise the same successful pool-return path for a forced child cleanup.
allocation=run(['treehouse','get','--lease','--no-fetch','--json'],cwd=p).stdout
wt=pathlib.Path(json.loads(next(x for x in allocation.splitlines() if x.startswith('{')))['path'])
parent=lab('pool-parent');child=lab('pool-child');(child/'.fm-secondmate-home').write_text('pool-secondmate\n')
shutil.copytree(ROOT/'bin',child/'bin')
task(parent,'pool-secondmate',kind='secondmate',worktree=child,project=p,home=child)
task(child,'worker',worktree=wt,project=p)
(wt.parent/'.fm-slot-owner').write_text(f'task=worker\nhome={child}\n')
b=board(wt/'.lavish/child-review.html','Pooled child worktree review')
run([RUNTIME/'code/bin/fm-teardown.sh','pool-secondmate','--force'],parent,timeout=180)
assert state(b)['status']=='ended'
assert not child.exists()
run(['treehouse','status'],cwd=p)
result('forced child pooled worktree return',result='pass',board='ended',lease='returned',home='removed',board_exists_after_return=b.exists())
snapshot('after-child-pool-return')
