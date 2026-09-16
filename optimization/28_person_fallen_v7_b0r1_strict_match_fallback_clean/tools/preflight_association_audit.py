import csv,json,sys
from pathlib import Path
D=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(D/'policy'))
from person_association import match
geo={}
for x in csv.DictReader((D/'../26_person_fallen_v7_b0_hard_veto_crossview/geometry/person_geometry.csv').open()):geo.setdefault(x['item_id'],[]).append(x)
b0=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/26_person_fallen_v7_b0_hard_veto_crossview/eval/pilot/output.jsonl')
rows=[json.loads(x) for x in b0.open()]
report={'rows':len(rows),'current_iou_only_unmatched':0,'new_match_unmatched':0,'floor_sitting':{},'multi_person_groups':{},'known_failure':{}}
for r in rows:
 gs=geo.get(r['item_id'],[]); p2=(r.get('p2') or {}).get('vlm',{}).get('people',[])
 if not p2: continue
 # legacy unmatched approximate based on stored p2 associations unavailable; count new matching only
 try:
  import PIL.Image as I
  with I.open(gs[0]['full_view_path']) as im: W,H=im.size
 except Exception: continue
 det=[[float(g['x1'])/W*1000,float(g['y1'])/H*1000,float(g['x2'])/W*1000,float(g['y2'])/H*1000] for g in gs]
 boxes=[p.get('bbox_1000') for p in p2 if isinstance(p.get('bbox_1000'),list)]
 a=match(det,boxes); report['new_match_unmatched']+=len(boxes)-len(a)
 if r.get('taxonomy')=='floor_sitting':report['floor_sitting'][r['item_id']]={'matches':len(a),'geom_states':[gs[x['detector_index']]['geom_state_a2'] for x in a]}
 if 'multi' in str(r.get('taxonomy','')).lower():report['multi_person_groups'][r['item_id']]={'matches':len(a),'p2_people':len(boxes),'geometry':len(gs)}
 if r['item_id']=='P4D_PLAN::PF_P4D_POS_CURLED_G003_V05':report['known_failure']={'matches':len(a),'p2_people':len(boxes),'geometry':len(gs)}
json.dump(report,(D/'reports/preflight_association_audit.json').open('w'),indent=2)
(D/'reports/preflight_association_audit.md').write_text('# B0R1 association preflight\n\n'+json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
