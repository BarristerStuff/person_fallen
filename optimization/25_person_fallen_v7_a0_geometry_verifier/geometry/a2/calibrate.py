import csv,json,math,itertools,statistics
from pathlib import Path
B=Path(__file__).parents[2]
M=list(csv.DictReader(open(B/'manifests/full_combined436.csv'))); meta={r['item_id']:r for r in M}
R=list(csv.DictReader(open(B/'detector/persons_full_dev.csv')))
lying={'prone_ground_lying','side_lying','supine_ground_lying','partially_occluded_lying','small_target_ground_lying','irregular_sprawled_lying','curled_or_sprawled_lying','intentional_ground_lying','multi_person_one_lying'}
aux={'pushup_plank','crawling_without_explicit_maintenance','crawling_quadruped_support'}
def iou(a,b):
 x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3]);z=max(0,x2-x1)*max(0,y2-y1);aa=(a[2]-a[0])*(a[3]-a[1]);bb=(b[2]-b[0])*(b[3]-b[1]);return z/(aa+bb-z+1e-9)
# same-class NMS by detector confidence
by={}
for r in R:by.setdefault(r['item_id'],[]).append(r)
kept=[]
for iid,rs in by.items():
 sel=[]
 for r in sorted(rs,key=lambda x:float(x['conf']),reverse=True):
  a=list(map(float,[r['x1'],r['y1'],r['x2'],r['y2']]))
  if all(iou(a,list(map(float,[q['x1'],q['y1'],q['x2'],q['y2']])))<.6 for q in sel):sel.append(r)
 kept+=sel
def weighted(kp,idx):
 q=[kp[i] for i in idx if i<len(kp) and kp[i][2]>0]
 if not q:return None
 sw=sum(p[2] for p in q);return (sum(p[0]*p[2] for p in q)/sw,sum(p[1]*p[2] for p in q)/sw)
def features(r):
 kp=json.loads(r['kp_json']);
 if not kp:return {'missing':True}
 sh=weighted(kp,[5,6]); hip=weighted(kp,[11,12]); H=max(float(r['y2'])-float(r['y1']),1)
 if not sh or not hip:return {'missing':True}
 raw=abs(math.degrees(math.atan2(hip[1]-sh[1],hip[0]-sh[0])));ang=min(raw,180-raw)
 return {'missing':False,'torso_angle_folded':ang,'shoulder_hip_dy':(hip[1]-sh[1])/H,'sh_conf':min(kp[5][2],kp[6][2]),'hip_conf':min(kp[11][2],kp[12][2]),'visible':sum(p[2]>.2 for p in kp),'bbox_ar':(float(r['x2'])-float(r['x1']))/H}
P=[]
for r in kept:
 if float(r['area_ratio'])>=.01:
  x=dict(r);x['f']=features(r);P.append(x)
def cls(f,t):
 if f.get('missing') or min(f['sh_conf'],f['hip_conf'])<t[2]:return 'GEOM_UNCERTAIN'
 if f['torso_angle_folded']>=t[0] and f['shoulder_hip_dy']>=t[1]:return 'GEOM_UPRIGHT'
 return 'GEOM_NOT_UPRIGHT'
def metrics(t, subset=None):
 pp=P if subset is None else [x for x in P if meta[x['item_id']]['group_id'] in subset]
 st={}
 for x in pp:st.setdefault(x['item_id'],[]).append(cls(x['f'],t))
 ground=[r for r in M if r['taxonomy'] in lying and r['item_id'] in st]; floor=[r for r in M if r['taxonomy']=='floor_sitting' and r['item_id'] in st]; pilot_ids={r['item_id'] for r in csv.DictReader(open(B/'manifests/pilot156.csv'))}
 gu=sum(all(s=='GEOM_UPRIGHT' for s in st[r['item_id']]) for r in ground); pu=sum(all(s=='GEOM_UPRIGHT' for s in st[r['item_id']]) for r in ground if r['item_id'] in pilot_ids); fu=sum(all(s=='GEOM_UPRIGHT' for s in st[r['item_id']]) for r in floor); return {'ground_detected':len(ground),'ground_all_upright':gu,'pilot_ground_all_upright':pu,'floor_all_upright':fu,'states':st}
grid=list(itertools.product([35,40,45,50],[.28,.30,.32,.34],[.3,.5])); feasible=[]
for t in grid:
 m=metrics(t)
 if m['ground_all_upright']<=2 and m['pilot_ground_all_upright']==0:feasible.append((m['floor_all_upright'],t,m))
feasible.sort(key=lambda z:(z[0],z[1][0],z[1][1],z[1][2]),reverse=True)
sel=feasible[0] if feasible else None
# LOGO: per held-out group choose on training and report test group
logo=[]; groups=sorted({r['group_id'] for r in M})
for g in groups:
 train=set(groups)-{g}; cand=[]
 for t in grid:
  mm=metrics(t,train)
  if mm['ground_all_upright']<=2 and mm['pilot_ground_all_upright']==0:cand.append((mm['floor_all_upright'],t))
 cand.sort(reverse=True); tt=cand[0][1] if cand else None
 logo.append({'held_out_group':g,'selected':tt,'held_out':metrics(tt,{g}) if tt else None})
report={'global_candidates':len(feasible),'selected_thresholds':sel[1] if sel else None,'selected_metrics':{k:v for k,v in (sel[2] if sel else {}).items() if k!='states'},'logo':logo}
json.dump(report,open(B/'reports/a2/logo.json','w'),indent=2)
if sel:
 t=sel[1]; json.dump({'tau_ang':t[0],'tau_dy':t[1],'tau_kp':t[2],'logo':logo},open(B/'geometry/a2/thresholds.json','w'),indent=2)
 # full outputs
 out=[]
 for x in kept:
  f=features(x);x=dict(x);x['features_a2']=json.dumps(f,separators=(',',':'));x['geom_state_a2']=cls(f,t) if float(x['area_ratio'])>=.01 else 'BACKGROUND_'+cls(f,t);out.append(x)
 with open(B/'geometry/a2/person_geometry.csv','w',newline='') as f: w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
print(json.dumps({k:v for k,v in report.items() if k!='logo'},indent=2))
