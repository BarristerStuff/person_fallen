import csv,json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent;V20=BASE/'20_person_fallen_v6_target_support_config';V13=BASE/'13_person_fallen_v4_pose_attributes'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def csvr(p):
 with open(p,newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
 with open(p,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
full=csvr(V13/'manifests/v4_full_dev_436.csv');crop={r['item_id']:r for r in csvr(V13/'manifests/v4_full_dev_crop_manifest.csv')};pilot=json.load(open(V20/'manifests/pilot156.json'));pids={r['item_id'] for r in pilot}
rows=[]
for r in full:
 if r['item_id'] in pids:continue
 c=crop[r['item_id']];x=dict(r);x.update({k:c[k] for k in ['person_detected','full_view_path','full_view_sha256','crop_view_path','crop_view_sha256','view_count']});x['operational_id']=x['diagnostic_id'];x['phase']='full_dev_remaining';x['result_source']='NEW_INFERENCE';x['evaluation_stratum']={'ALERT_GROUND_LYING':'ground_lying','NO_ALERT_NORMAL_POSE':'normal_negative','RECHECK_VISUAL_UNCERTAIN':'visual_uncertain','ATTENTION_NEAR_GROUND':'auxiliary_attention'}[x['expected_v4_outcome']];rows.append(x)
order=['normal_negative','ground_lying','visual_uncertain'];rows=sorted(rows,key=lambda x:(order.index(x['evaluation_stratum']),int(x['diagnostic_id'].split('_')[-1])))
assert len(rows)==280 and Counter(x['evaluation_stratum'] for x in rows)==Counter({'normal_negative':175,'ground_lying':85,'visual_uncertain':20})
for i,x in enumerate(rows,1):x['request_id']=f'V6_A0_FULLDEV_{i:04d}'
write(ROOT/'manifests/full_dev_remaining.csv',rows);json.dump(rows,open(ROOT/'manifests/full_dev_remaining.json','w'),ensure_ascii=False,indent=2)
# compact full combined metadata for metrics
combined=[]
for r in pilot:
 x=dict(r);x['phase']='pilot_reused';x['result_source']='REUSE_V6_PILOT';combined.append(x)
combined.extend(rows);json.dump(combined,open(ROOT/'manifests/full_dev_combined.json','w'),ensure_ascii=False,indent=2)
audit={'status':'PASS','counts':{'pilot':156,'regression':1,'remaining':280,'full':436,'remaining_by_stratum':dict(Counter(x['evaluation_stratum'] for x in rows))},'pilot_manifest_sha256':sha(V20/'manifests/pilot156.json'),'full_source_manifest_sha256':sha(V13/'manifests/v4_full_dev_436.csv'),'full_crop_manifest_sha256':sha(V13/'manifests/v4_full_dev_crop_manifest.csv'),'source_fields_unchanged':True,'VAL_READ':0,'HOLDOUT_READ':0,'localization':'UNVERIFIED'}
json.dump(audit,open(ROOT/'reports/source_audit.json','w'),ensure_ascii=False,indent=2)
print(audit)
