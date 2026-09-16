import csv,collections,json,sys
from pathlib import Path
D=Path(__file__).resolve().parents[1]
geo=list(csv.DictReader((D/'geometry/person_geometry.csv').open())); man=list(csv.DictReader((D/'manifests/full_combined436.csv').open())); g=collections.defaultdict(list)
for x in geo:g[x['item_id']].append(x)
def is_ground(r): return ('lying' in r['taxonomy']) or r['taxonomy'] in {'multi_person_one_lying','intentional_ground_lying'}
rows=[r for r in man if is_ground(r)]; floor=[r for r in man if r['taxonomy']=='floor_sitting']
assert len(rows)==145 and sum(bool(g[r['item_id']]) for r in rows)==141
assert sum(1 for r in rows if [x for x in g[r['item_id']] if x['level']=='primary'] and all(x['geom_state_a2']=='GEOM_UPRIGHT' for x in g[r['item_id']] if x['level']=='primary'))==0
assert sum(1 for r in floor if [x for x in g[r['item_id']] if x['level']=='primary'] and all(x['geom_state_a2']=='GEOM_UPRIGHT' for x in g[r['item_id']] if x['level']=='primary'))==53
print('GEOMETRY_BINDING_PASS')
