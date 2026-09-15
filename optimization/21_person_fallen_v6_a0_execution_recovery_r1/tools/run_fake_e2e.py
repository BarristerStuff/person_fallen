import json,tempfile,contextlib,io
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));import recovery_runner as rr

def fake(payload,row):
 import base64
 from importlib.util import spec_from_file_location,module_from_spec
 sp=spec_from_file_location('p',ROOT.parent/'20_person_fallen_v6_target_support_config/policy/target_policy.py');m=module_from_spec(sp);sp.loader.exec_module(m)
 def p(pid,kind):
  x={'person_id':pid,'bbox_1000':[1,1,800,900],'person_visible':'yes','pose':'floor_sitting','torso_orientation':'upright','torso_ground_contact':'partial','head_shoulders_above_hips':'yes','support_surface':'floor','body_support_configuration':'pelvis_supported','explicit_work_evidence':'no','visual_quality':'clear','evidence':'x'}
  if kind=='ground':x.update(pose='prone',torso_orientation='horizontal',torso_ground_contact='broad',head_shoulders_above_hips='no',body_support_configuration='torso_ground_supported')
  if kind=='push':x.update(pose='pushup_plank',torso_orientation='horizontal',torso_ground_contact='partial',head_shoulders_above_hips='no',body_support_configuration='hands_feet_supported')
  return x
 if row.get('taxonomy')=='multi_person_one_lying' or row.get('operational_id')=='PFV4_SCREEN_0066':people=[p(1,'normal'),p(2,'ground')]
 elif row.get('evaluation_stratum')=='ground_lying':people=[p(1,'ground')]
 elif row.get('taxonomy')=='pushup_plank':people=[p(1,'push')]
 else:people=[p(1,'normal')]
 parsed={'scene_coverage':'complete','people':people};outer={'model':'qwen3.5:4b','done':True,'done_reason':'stop','eval_count':100,'response':json.dumps(parsed)}
 return {'http_status':200,'raw':json.dumps(outer).encode(),'latency_seconds':.001,'completion_unknown':False,'transport_error':None}
def main():
 import tempfile
 f={'candidate':'V6-A0-TARGET-SUPPORT-CONFIG','budget':{'pilot':156,'regression':1,'full_dev_remaining':280,'total':437,'val':0,'holdout':0,'detector':0}}
 with tempfile.TemporaryDirectory() as td:
  from pathlib import Path
  with contextlib.redirect_stdout(io.StringIO()):
   a=rr.run_phase('pilot',fake,Path(td)/'pilot',f)
   b=rr.run_phase('regression',fake,Path(td)/'regression',f)
  assert a['gate']=='PASS' and b['gate']=='PASS';print(json.dumps({'status':'PASS_FAKE_E2E','pilot':a['gate'],'regression':b['gate'],'requests':157}))
if __name__=='__main__':main()
