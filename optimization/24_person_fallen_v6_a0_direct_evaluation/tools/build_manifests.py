import csv,json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent;V20=BASE/'20_person_fallen_v6_target_support_config';V13=BASE/'13_person_fallen_v4_pose_attributes'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def csvr(p):
 with open(p,newline='') as f:return list(csv.DictReader(f))
def write(name,rows):
 (ROOT/'manifests'/f'{name}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 with (ROOT/'manifests'/f'{name}.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 pilot=json.load(open(V20/'manifests/pilot156.json'));reg=json.load(open(V20/'manifests/regression1.json'));full=csvr(V13/'manifests/v4_full_dev_436.csv');crop={r['item_id']:r for r in csvr(V13/'manifests/v4_full_dev_crop_manifest.csv')};ids={r['item_id'] for r in pilot};assert len(ids)==156
 rem=[]
 for r in full:
  if r['item_id'] in ids:continue
  c=crop[r['item_id']];x=dict(r);x.update({k:c[k] for k in ['person_detected','full_view_path','full_view_sha256','crop_view_path','crop_view_sha256','view_count']});x['operational_id']=x['diagnostic_id'];x['evaluation_stratum']={'ALERT_GROUND_LYING':'ground_lying','NO_ALERT_NORMAL_POSE':'normal_negative','RECHECK_VISUAL_UNCERTAIN':'visual_uncertain'}[x['expected_v4_outcome']];x['phase']='full_remaining';x['result_source']='NEW_INFERENCE';rem.append(x)
 order=['normal_negative','ground_lying','visual_uncertain'];rem.sort(key=lambda r:(order.index(r['evaluation_stratum']),int(r['diagnostic_id'].split('_')[-1])))
 assert Counter(r['evaluation_stratum'] for r in rem)==Counter({'normal_negative':175,'ground_lying':85,'visual_uncertain':20}) and len(rem)==280
 for i,r in enumerate(rem,1):r['request_id']=f'V6_R2_FULL_{i:04d}'
 combined=[]
 for r in pilot:
  x=dict(r);x['result_source']='REUSE_V6_PILOT';x['phase']='pilot';combined.append(x)
 combined+=rem;assert len({r['item_id'] for r in combined})==436
 write('pilot156',pilot);write('regression1',reg);write('full_remaining280',rem);write('full_combined436',combined)
 bind={}
 for rows in [pilot,reg,rem]:
  for r in rows:
   for k in ['image_path','prompt_path','full_view_path','crop_view_path']:bind[str(Path(r[k]).resolve())]=sha(r[k])
 audit={'status':'PASS','pilot':156,'regression':1,'remaining':280,'combined':436,'remaining_strata':dict(Counter(r['evaluation_stratum'] for r in rem)),'pilot_sha':sha(V20/'manifests/pilot156.json'),'regression_sha':sha(V20/'manifests/regression1.json'),'full_source_sha':sha(V13/'manifests/v4_full_dev_436.csv'),'crop_source_sha':sha(V13/'manifests/v4_full_dev_crop_manifest.csv'),'resource_bindings':bind,'VAL_READ':0,'HOLDOUT_READ':0,'source_fields_changed':False}
 (ROOT/'reports/source_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(audit)
if __name__=='__main__':main()
