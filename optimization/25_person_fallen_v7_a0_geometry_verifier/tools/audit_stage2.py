import csv,json
from pathlib import Path
B=Path(__file__).parents[1]; M=list(csv.DictReader(open(B/'manifests/full_combined436.csv'))); G=list(csv.DictReader(open(B/'geometry/a2/person_geometry.csv')))
by={}
for r in G: by.setdefault(r['item_id'],[]).append(r)
lying={'prone_ground_lying','side_lying','supine_ground_lying','partially_occluded_lying','small_target_ground_lying','irregular_sprawled_lying','curled_or_sprawled_lying','intentional_ground_lying','multi_person_one_lying'}
g=[r for r in M if r['taxonomy'] in lying];det=[r for r in g if any(x['level']=='primary' for x in by.get(r['item_id'],[]))];zero=[r['item_id'] for r in g if not by.get(r['item_id'])]
allup=[r['item_id'] for r in det if all(x['geom_state_a2']=='GEOM_UPRIGHT' for x in by[r['item_id']] if x['level']=='primary')]
pilot={r['item_id'] for r in csv.DictReader(open(B/'manifests/pilot156.csv'))}; p=[i for i in allup if i in pilot]
floor=[r for r in M if r['taxonomy']=='floor_sitting'];fu=[r['item_id'] for r in floor if all(x['geom_state_a2']=='GEOM_UPRIGHT' for x in by[r['item_id']] if x['level']=='primary')]
out={'ground_detected':len(det),'ground_all_primary_upright':len(allup),'pilot_ground_all_primary_upright':len(p),'zero_detection_ground':zero,'ground_all_primary_upright_items':allup,'floor_all_primary_upright':len(fu),'floor_items':fu,'stage2_gate':'PASS' if len(allup)<=2 and len(p)==0 and len(fu)>=50 else 'FAIL'}
json.dump(out,open(B/'reports/a3/stage2_audit.json','w'),indent=2);print(json.dumps(out,indent=2))
