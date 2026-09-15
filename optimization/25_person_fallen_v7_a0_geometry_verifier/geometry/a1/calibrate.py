import csv,json,math,itertools
from pathlib import Path
B=Path(__file__).parents[2];M={r['item_id']:r for r in csv.DictReader(open(B/'manifests/full_combined436.csv'))};R=list(csv.DictReader(open(B/'geometry/person_geometry.csv')))
lying={'prone_ground_lying','side_lying','supine_ground_lying','partially_occluded_lying','small_target_ground_lying','irregular_sprawled_lying','curled_or_sprawled_lying','intentional_ground_lying','multi_person_one_lying'}
def f(x):
 z=json.loads(x['features']) if x['features'] else {}; z=z or {}; kp=json.loads(x['kp_json']);
 def mid(a,b):
  q=[kp[i] for i in (a,b) if i<len(kp) and kp[i][2]>=.2]; return sum(qi[1] for qi in q)/len(q) if q else None
 h=mid(11,12); k=[]
 for i in (13,14,15,16):
  if i<len(kp) and kp[i][2]>=.2:k.append(kp[i][1])
 z['hip_vs_knee_ankle']=((h-sum(k)/len(k))/max(float(x['y2'])-float(x['y1']),1)) if h is not None and k else 0
 z['shoulder_conf']=[kp[i][2] for i in (5,6) if i<len(kp)];z['hip_conf']=[kp[i][2] for i in (11,12) if i<len(kp)];z['visible_points']=z.get('visible',0);return z
P=[x for x in R if x['level']=='primary']; feats={x['item_id']:f(x) for x in P}; groups={x['item_id']:M[x['item_id']]['group_id'] for x in P}
def pred(z,t):
 kp=z['shoulder_conf']+z['hip_conf']
 if not kp or min(kp)<t[0] or z['visible_points']<8:return 'U'
 if z['shoulder_hip_dy']>=t[1] and z['torso_angle']>=t[2] and z['hip_vs_knee_ankle']<=-t[3]:return 'R'
 if z['torso_angle']<=t[4] and z['y_band_ratio']<=t[5]:return 'L'
 return 'U'
cands=[]
for t in itertools.product([.3,.4,.5,.6],[.08,.12,.16,.2],[15,25,35,45],[0,.03,.08,.15],[15,25,35],[.5,.7,.9,1.1]):
 st={}
 for iid,z in feats.items():st.setdefault(iid,[]).append(pred(z,t))
 def state(iid):
  ss=st[iid];return 'R' if all(s=='R' for s in ss) else ('L' if any(s=='L' for s in ss) else 'U')
 gs=[i for i in st if M[i]['taxonomy'] in lying]; fs=[i for i in st if M[i]['taxonomy']=='floor_sitting']
 g1=sum(state(i)!='R' for i in gs); fu=sum(state(i)=='R' for i in fs); f_unc=sum(state(i)=='U' for i in fs); aux=[i for i in st if M[i]['taxonomy'] in {'pushup_plank','crawling_without_explicit_maintenance','crawling_quadruped_support'}]
 if g1==145 and f_unc<=5:cands.append((fu,-f_unc,t))
print('candidates',len(cands)); cands.sort(reverse=True);print(cands[:5])
if cands:
 t=cands[0][2];json.dump({'tau_kp':t[0],'tau_dy':t[1],'tau_ang':t[2],'tau_hip':t[3],'tau_flat':t[4],'tau_band':t[5],'logo_note':'grid search over DEV; selected max floor upright subject G1/G3'},open(B/'geometry/a1/thresholds.json','w'),indent=2)
