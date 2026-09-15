import sys,json,tempfile,unittest,copy,contextlib,io
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'tests'))
import run_target_eval as run
import contracts as c
from test_target_contract import person,obj,raw

class Runner(unittest.TestCase):
 def test_no_forbidden_phases(self):
  for p in ['full_dev','full_dev436','screen','VAL','val','Holdout','holdout']:
   with self.assertRaises(ValueError):run.stage(p)
 def test_payload_no_source_or_history(self):
  p=run.payload('fixed prompt',{'type':'object'},[b'full',b'crop'])
  self.assertEqual(set(p),{'model','prompt','images','think','stream','format','options'})
  self.assertEqual(p['images'],['ZnVsbA==','Y3JvcA=='])
  self.assertFalse(p['think']);self.assertFalse(p['stream'])
  self.assertEqual(p['options'],{'temperature':0,'num_ctx':8192,'num_predict':768})
  serialized=json.dumps(p)
  for token in ['taxonomy','ground_truth','item_id','image_path','expected_v4_outcome','primary_decision','scene_review']:self.assertNotIn(token,serialized)
 def setup_fixture(self,tmp):
  root=Path(tmp)
  for d in ['manifests','prompt','schema','policy','freeze']:(root/d).mkdir()
  for p in ['manifests/pilot115.json','prompt/target_attributes.txt','schema/target_attributes.json','policy/target_policy.py']:(root/p).write_bytes((ROOT/p).read_bytes())
  (root/'freeze/EXECUTION_FREEZE.json').write_text('{}')
  return root
 def test_full_offline_runner_integration_no_model(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=self.setup_fixture(tmp)
   def mock_call(data):
    payload=json.loads(data);self.assertEqual(len(payload['images']),2)
    self.assertEqual(payload['prompt'],(ROOT/'prompt/target_attributes.txt').read_text())
    return {'http_status':200,'raw':raw(obj(person())),'latency_seconds':.01,'completion_unknown':False,'transport_error':None}
   with patch.object(run,'ROOT',root),patch.object(run,'verify_freeze',return_value={'model':{'offline_test':True}}),patch.object(run,'runtime_check',return_value={'offline_test':True}),patch.object(run,'call_once',side_effect=mock_call) as call,contextlib.redirect_stdout(io.StringIO()):
    result=run.stage('pilot');self.assertEqual(call.call_count,115);self.assertEqual(result['valid_responses'],115);self.assertEqual(result['validation_errors'],[])
    self.assertEqual(result['gate'],'FAIL') # all-seated fixture cannot pass lying gate
    with self.assertRaises(ValueError):run.stage('pilot')
    with self.assertRaises(ValueError):run.stage('regression')
    self.assertEqual(call.call_count,115)
    self.assertEqual(len(list((root/'eval/pilot/requests').glob('*/claimed.json'))),115)
    self.assertTrue((root/'eval/pilot/COMPLETION_LOCK.json').exists())
 def test_protocol_failures_stop_once_no_metric(self):
  examples=[{'http_status':200,'raw':raw(obj(person()),done_reason='length'),'latency_seconds':.1,'completion_unknown':False,'transport_error':None},{'http_status':None,'raw':b'','latency_seconds':.1,'completion_unknown':True,'transport_error':'offline connection loss'},{'http_status':500,'raw':b'service error','latency_seconds':.1,'completion_unknown':False,'transport_error':'offline HTTP500'}]
  for failed in examples:
   with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
    root=self.setup_fixture(tmp)
    with patch.object(run,'ROOT',root),patch.object(run,'verify_freeze',return_value={'model':{'offline_test':True}}),patch.object(run,'runtime_check',return_value={'offline_test':True}),patch.object(run,'call_once',return_value=copy.deepcopy(failed)) as call:
     with self.assertRaises(ValueError):run.stage('pilot')
     self.assertEqual(call.call_count,1);self.assertTrue((root/'eval/pilot/PROTOCOL_INCOMPLETE.json').exists());self.assertFalse((root/'eval/pilot/summary.json').exists())
     with self.assertRaises(ValueError):run.stage('pilot')
     self.assertEqual(call.call_count,1)
 def test_manifest_and_sha_fail_closed(self):
  rows=c.loads((ROOT/'manifests/pilot115.json').read_bytes())
  with self.assertRaises(ValueError):c.validate_manifest('pilot',rows[:-1])
  with self.assertRaises(ValueError):c.validate_manifest('pilot',rows[:-1]+[rows[0]])
  with self.assertRaises(ValueError):c.verify_sha(ROOT/'prompt/target_attributes.txt','0'*64)
if __name__=='__main__':unittest.main()
