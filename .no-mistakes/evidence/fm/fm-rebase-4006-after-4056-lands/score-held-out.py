import json
from pathlib import Path
E=Path(__file__).parent
plan=json.loads((E/'shard-plan.json').read_text())
measurements={}; old=[]
for p in sorted((E/'held-out').rglob('*.json')):
    d=json.loads(p.read_text()); old.append({'lane':d['selection'].split(';')[0][5:],'sum_ms':sum(s['duration_ms'] for s in d['scripts']),'wall_ms':d['summary']['duration_ms']})
    assert d['summary']['failed']==0
    for s in d['scripts']:
        assert s['path'] not in measurements
        measurements[s['path']]=s['duration_ms']
assert set(measurements)==set(s for scripts in plan.values() for s in scripts)
new=[{'lane':lane,'scripts':len(scripts),'predicted_sum_ms':sum(measurements[s] for s in scripts)} for lane,scripts in plan.items()]
old_values=[x['sum_ms'] for x in old];new_values=[x['predicted_sum_ms'] for x in new]
report={'source_run':34447627189,'kind':'held-out replay and prediction; not a fresh CI performance measurement','measured_scripts':len(measurements),'previous_partition':old,'current_partition_scored_on_same_measurements':new,'previous_worst_minutes':max(old_values)/60000,'new_worst_minutes':max(new_values)/60000,'previous_spread':max(old_values)/min(old_values),'new_spread':max(new_values)/min(new_values)}
assert round(report['previous_worst_minutes'],2)==21.91
# Documentation rounds the observed suite wall (21.93m) and the repacked script sum (16.99m).
assert round(max(x['wall_ms'] for x in old)/60000,2)==21.93
assert round(report['new_worst_minutes'],2)==16.99
assert round(report['previous_spread'],2)==1.66 and round(report['new_spread'],2)==1.17
(E/'held-out-score.json').write_text(json.dumps(report,indent=2)+'\n')
text=f"Held-out GitHub run 34447627189: {len(measurements)} scripts, exact match with current lane inventory.\nPrevious partition: observed worst wall {max(x['wall_ms'] for x in old)/60000:.2f} min; script sums {min(old_values)/60000:.2f}-{max(old_values)/60000:.2f} min; spread {report['previous_spread']:.2f}x.\nCurrent executable partition: predicted script sums {min(new_values)/60000:.2f}-{max(new_values)/60000:.2f} min; spread {report['new_spread']:.2f}x.\nThis replays held-out measurements; it does not measure a new CI run.\n"
(E/'held-out-score.log').write_text(text);print(text)
