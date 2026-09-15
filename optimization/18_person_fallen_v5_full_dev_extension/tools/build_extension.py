import csv,json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT.parent; V17=BASE/'17_person_fallen_v5_target_attributes'; V13=BASE/'13_person_fallen_v4_pose_attributes'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
 with open(p,newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
 with open(p,'x',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
full=read(V13/'manifests/v4_full_dev_436.csv'); crop={r['item_id']:r for r in read(V13/'manifests/v4_full_dev_crop_manifest.csv')}; pilot=read(V17/'manifests/pilot115.csv'); pids={r['item_id'] for r in pilot}; assert len(pids)==115
rows=[]
for r in full:
 if r['item_id'] in pids:continue
 out=dict(r); c=crop[r['item_id']]; out.update({k:c[k] for k in ['person_detected','full_view_path','full_view_sha256','crop_view_path','crop_view_sha256','view_count']})
 out['experiment_stratum']={'ALERT_GROUND_LYING':'ground_lying','NO_ALERT_NORMAL_POSE':'normal_negative','ATTENTION_NEAR_GROUND':'auxiliary_attention','RECHECK_VISUAL_UNCERTAIN':'visual_uncertain'}[out['expected_v4_outcome']];out['experiment_role']='FULL_DEV_EXTENSION_NEW_INFERENCE';out['phase']='extension';rows.append(out)
order=['normal_negative','ground_lying','auxiliary_attention','visual_uncertain'];rows=sorted(rows,key=lambda r:(order.index(r['experiment_stratum']),int(r['diagnostic_id'].split('_')[-1])))
for i,r in enumerate(rows,1):r['request_id']=f'V5_B0_FULLDEV_EXTENSION_{i:04d}'
assert len(rows)==321 and Counter(r['experiment_stratum'] for r in rows)==Counter({'normal_negative':175,'ground_lying':85,'auxiliary_attention':41,'visual_uncertain':20})
write(ROOT/'manifests/remaining321.csv',rows)
fullmap={r['item_id']:r for r in [*pilot,*rows]}; fullout=[fullmap[r['item_id']] for r in full]; write(ROOT/'manifests/full_dev436.csv',fullout)
bindings={str(p):sha(p) for p in [V17/'freeze/EXECUTION_FREEZE.json',V17/'freeze/EXECUTION_FREEZE.sha256',V17/'protocol/execution_plan.json',V17/'prompt/target_attributes.txt',V17/'schema/target_attributes.json',V17/'policy/target_policy.py',V17/'eval/pilot/output.jsonl',V17/'eval/pilot/predictions.csv',V17/'eval/pilot/COMPLETION_LOCK.json',V13/'manifests/v4_full_dev_436.csv',V13/'manifests/v4_full_dev_crop_manifest.csv']}
for r in rows:
 for k in ['image_path','prompt_path','full_view_path','crop_view_path']:bindings[r[k]]=sha(r[k])
audit = {
 'status':'PASS',
 'counts': {'full_dev':436,'v5_reused':115,'new_remaining':321,'new_by_stratum':dict(Counter(r['experiment_stratum'] for r in rows)),'expected_strata':{'ground_lying':145,'normal_negative':230,'auxiliary_attention':41,'visual_uncertain':20},'floor_sitting':55},
 'request_order':order,'bindings':bindings,
 'scope': {'VAL_images_read':0,'VAL_predictions_read':0,'HOLDOUT_read':0,'source_fields_changed':False,'V5_B0_result_reuse_only_for_115':True,'known_regression_reused_not_in_dev':True,'pixel_semantics_verified':False,'OBJECT_LOCALIZATION_ACCURACY':'UNVERIFIED'},
 'output_sha256': {'remaining321.csv':sha(ROOT/'manifests/remaining321.csv'),'full_dev436.csv':sha(ROOT/'manifests/full_dev436.csv') }
}
(ROOT/'reports/source_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'remaining':len(rows),'by_stratum':Counter(r['experiment_stratum'] for r in rows)},ensure_ascii=False))
