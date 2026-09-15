import csv,json,math
from pathlib import Path
B=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/25_person_fallen_v7_a0_geometry_verifier'); rows=list(csv.DictReader(open(B/'manifests/full_combined436.csv'))); tax={r['item_id']:r['taxonomy'] for r in rows}; det=list(csv.DictReader(open(B/'detector/persons_full_dev.csv')))
def feat(d):
 kp=json.loads(d['kp_json']); pts=[(x,y,c) for x,y,c in kp if c>.2]
 if len(pts)<5:return None
 # COCO shoulders 5,6 hips 11,12 knees 13,14 ankles 15,16
 def mid(a,b):
  q=[kp[i] for i in (a,b) if i<len(kp) and kp[i][2]>.2]; return (sum(x for x,y,c in q)/len(q),sum(y for x,y,c in q)/len(q)) if q else None
 s=mid(5,6);h=mid(11,12); limbs=[kp[i] for i in (13,14,15,16) if i<len(kp) and kp[i][2]>.2]
 if not s or not h:return None
 H=float(d['y2'])-float(d['y1']); dx=h[0]-s[0];dy=h[1]-s[1]; angle=abs(math.degrees(math.atan2(dy,dx)))
 shdy=abs(dy)/max(H,1)
 ys=[p[1] for p in ([kp[i] for i in (5,6,11,12,13,14,15,16) if i<len(kp) and kp[i][2]>.2])]
 span=(max(ys)-min(ys))/max(H,1)
 conf=sum(p[2] for p in pts)/len(pts)
 return {'torso_angle':angle,'shoulder_hip_dy':shdy,'y_band_ratio':span,'kp_mean_conf':conf,'visible':len(pts),'bbox_ar':(float(d['x2'])-float(d['x1']))/max(H,1)}
def state(d):
 f=feat(d)
 if not f:return 'GEOM_UNCERTAIN',None
 if f['kp_mean_conf']<.45 or f['visible']<8:return 'GEOM_UNCERTAIN',f
 # horizontal torso means angle around 0 or 180; atan2 abs gives 0..180
 horiz=min(f['torso_angle'],abs(180-f['torso_angle']))<25
 if horiz and f['y_band_ratio']<.9:return 'GEOM_LYING',f
 if f['shoulder_hip_dy']>.12:return 'GEOM_UPRIGHT_OR_LIMB_SUPPORTED',f
 return 'GEOM_UNCERTAIN',f
out=[]
for d in det:
 s,f=state(d); d=dict(d);d['geom_state']=s;d['features']=json.dumps(f);out.append(d)
with open(B/'geometry/person_geometry.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
by={}
for r in rows:
 ds=[x for x in out if x['item_id']==r['item_id'] and x['level']=='primary']; st=[x['geom_state'] for x in ds]
 by[r['item_id']]=st
stats={}
cats={'ground_lying':{'prone_ground_lying','side_lying','supine_ground_lying','partially_occluded_lying','small_target_ground_lying','irregular_sprawled_lying','curled_or_sprawled_lying','intentional_ground_lying','multi_person_one_lying'},'floor_sitting':{'floor_sitting'},'auxiliary_attention':{'pushup_plank','crawling_without_explicit_maintenance','crawling_quadruped_support'}}
for category in cats:
 rr=[r for r in rows if r['taxonomy'] in cats[category]]; stats[category]={'n':len(rr),'union':sum(any(s in ('GEOM_LYING','GEOM_UNCERTAIN') for s in by[r['item_id']]) for r in rr),'lying':sum('GEOM_LYING' in by[r['item_id']] for r in rr),'all_up':sum(bool(by[r['item_id']]) and all(s=='GEOM_UPRIGHT_OR_LIMB_SUPPORTED' for s in by[r['item_id']]) for r in rr)}
print(json.dumps(stats,indent=2)); json.dump(stats,open(B/'reports/geometry_stage2.json','w'),indent=2)
