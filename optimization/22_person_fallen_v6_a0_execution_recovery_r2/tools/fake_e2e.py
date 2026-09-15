import json,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));from engine import *
def fake(data,row):
 def p(pid,kind):
  x={'person_id':pid,'bbox_1000':[1,1,900,900],'person_visible':'yes','pose':'floor_sitting','torso_orientation':'upright','torso_ground_contact':'partial','head_shoulders_above_hips':'yes','support_surface':'floor','body_support_configuration':'pelvis_supported','explicit_work_evidence':'no','visual_quality':'clear','evidence':'fake'}
  if kind=='ground':x.update(pose='prone',torso_orientation='horizontal',torso_ground_contact='broad',head_shoulders_above_hips='no',body_support_configuration='torso_ground_supported')
  elif kind=='push':x.update(pose='pushup_plank',torso_orientation='horizontal',torso_ground_contact='partial',head_shoulders_above_hips='no',body_support_configuration='hands_feet_supported')
  elif kind=='crawl':x.update(pose='crawling',torso_orientation='inclined',torso_ground_contact='partial',head_shoulders_above_hips='no',body_support_configuration='hands_knees_supported')
  return x
 t=row.get('taxonomy');people=[p(1,'normal')]
 if row.get('operational_id')=='PFV4_SCREEN_0066' or t=='multi_person_one_lying':people=[p(1,'normal'),p(2,'ground')]
 elif row.get('evaluation_stratum')=='ground_lying':people=[p(1,'ground')]
 elif t=='pushup_plank':people=[p(1,'push')]
 elif str(t).startswith('crawling'):people=[p(1,'crawl')]
 parsed={'scene_coverage':'complete','people':people};o={'model':'qwen3.5:4b','done':True,'done_reason':'stop','eval_count':100,'response':json.dumps(parsed)}
 return {'http_status':200,'raw':json.dumps(o).encode(),'latency_seconds':.001,'completion_unknown':False,'transport_error':None}
def main():
 f={'candidate':'V6-A0-TARGET-SUPPORT-CONFIG','model':MODEL,'budget':EXPECTED_BUDGET}
 validate_freeze(f);calls=[]
 def tx(data,row):calls.append(row['request_id']);return fake(data,row)
 with tempfile.TemporaryDirectory() as td:
  rr=Path(td)/'runs';snap={'status':'PASS'}
  a=run_stage('pilot',rr,f,tx,snap);assert a['gate']=='PASS'
  b=run_stage('regression',rr,f,tx,snap);assert b['gate']=='PASS'
  c=run_stage('full_remaining',rr,f,tx,snap);assert c['gate']=='PASS'
  d=aggregate_full(rr);assert d['gate']=='PASS'
  assert len(calls)==437 and len(set(calls))==437
  assert (rr/'full_dev_combined/FULL_DEV_COMPLETION_LOCK.json').exists()
 print(json.dumps({'status':'PASS_FAKE_E2E_437','pilot':a['gate'],'regression':b['gate'],'full_remaining':c['gate'],'full_dev':d['gate'],'transport_calls':len(calls),'network':0}))
if __name__=='__main__':main()
