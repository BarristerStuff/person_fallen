import csv,json
from pathlib import Path
B=Path(__file__).parents[1]; out=[]; targets=['SIT_G001_V03','SIT_G002_V04','SIT_G005_V03','SIT_G007_V03','SIT_G007_V04']
def iou(a,b):
 x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3]);z=max(0,x2-x1)*max(0,y2-y1);aa=(a[2]-a[0])*(a[3]-a[1]);bb=(b[2]-b[0])*(b[3]-b[1]);return z/(aa+bb-z+1e-9)
G=list(csv.DictReader(open(B/'geometry/a2/person_geometry.csv'))); M={r['item_id']:r for r in csv.DictReader(open(B/'manifests/pilot156.csv'))}
for line in open('/home/yanbo/net_vlm_person_fallen_v2_optimization/24_person_fallen_v6_a0_direct_evaluation/eval/pilot/output.jsonl'):
 d=json.loads(line)
 if any(t in d.get('item_id','') for t in targets):
  iid=d['item_id']; ps=d['parsed']['people']; gs=[x for x in G if x['item_id']==iid and x['level']=='primary']; matches=[]
  for p in ps:
   b=p['bbox_1000']
   for g in gs:
    bb=[float(g['x1'])/1.92,float(g['y1'])/1.08,float(g['x2'])/1.92,float(g['y2'])/1.08];v=iou(b,bb)
    if v>=.3:matches.append({'person_id':p['person_id'],'iou':v,'geom_state':g['geom_state_a2'],'det_box':[g['x1'],g['y1'],g['x2'],g['y2']]})
  out.append({'item_id':iid,'request_id':d['request_id'],'matches':matches,'all_upright':all(x['geom_state']=='GEOM_UPRIGHT' for x in matches) and bool(matches)})
json.dump(out,open(B/'reports/a3/g2_fp_recheck.json','w'),indent=2)
print(json.dumps(out,indent=2))
