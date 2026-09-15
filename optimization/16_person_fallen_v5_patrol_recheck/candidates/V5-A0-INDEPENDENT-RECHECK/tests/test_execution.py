import sys,unittest,tempfile,json,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'policy'))
import contracts as c
import run_secondary as runner
from metrics import metrics
from routing_contract import route_first_frame,DECISIONS

DEV=c.loads((ROOT/'manifests/dev.json').read_bytes());REG=c.loads((ROOT/'manifests/regression.json').read_bytes())
def outer(inner=None,**changes):
 d={'model':'qwen3.5:4b','done':True,'done_reason':'stop','response':json.dumps(inner or {'scene_review':'candidate_absent','evidence':'visible seated person'})};d.update(changes);return json.dumps(d).encode()
def simulated(rr):
 out=[];req=[]
 for r in rr:
  final=route_first_frame(r['primary_decision'],'candidate_absent')
  o={**r,'final_decision':final,'primary_cache_binding_ok':True,'scene_review':'candidate_absent' if r['secondary_required'] else None};out.append(o)
  if r['secondary_required']:req.append({'request_id':r['request_id'],'strict_json_ok':True,'state':'completed','http_status':200,'scene_review':'candidate_absent','final_decision':final,'latency_seconds':1.0})
 return out,req
class Contracts(unittest.TestCase):
 def test_strata(self):
  from collections import Counter
  self.assertEqual(Counter(r['v5_stratum'] for r in DEV),{'ground_lying':145,'normal_negative':230,'auxiliary_attention':41,'visual_uncertain':20})
  self.assertEqual(sum(r['taxonomy']=='floor_sitting' and r['v5_stratum']=='normal_negative' for r in DEV),55)
 def test_binding_all_preparation_and_inputs(self):
  audit=c.loads((ROOT/'reports/cache_preflight.json').read_bytes())
  for p,h in audit['bindings'].items():c.verify_sha(p,h)
 def test_metrics_correct_denominators(self):
  out,req=simulated(DEV);m=metrics(DEV,out,req,'dev')
  self.assertEqual((m['ground_lying_count'],m['determinate_negative_count'],m['floor_sitting_count']),(145,230,55))
  self.assertEqual(m['immediate_ALERT_count'],141);self.assertEqual(m['floor_sitting_ALERT_FPR'],0.)
  self.assertEqual(m['secondary_requests'],288);self.assertTrue(m['gate_checks']['alert_set_unchanged'])
 def test_floor_fpr_not_na(self):
  out,req=simulated(DEV);o=next(r for r in out if r['taxonomy']=='floor_sitting');o['final_decision']=c.ALERT
  next(r for r in req if r['request_id']==o['request_id'])['final_decision']=c.ALERT
  m=metrics(DEV,out,req,'dev');self.assertEqual(m['floor_sitting_ALERT_FPR'],1/55);self.assertEqual(m['determinate_negative_ALERT_FPR'],1/230);self.assertEqual(m['gate'],'FAIL')
 def test_total_recheck_budget_23_24(self):
  for count in [23,24]:
   out,req=simulated(DEV);normal=[r for r in out if r['v5_stratum']=='normal_negative'];already=[r for r in normal if r['final_decision']==c.RECHECK];chosen=already+[r for r in normal if r not in already][:count-len(already)]
   for o in chosen:
    o['final_decision']=c.RECHECK;next(r for r in req if r['request_id']==o['request_id'])['final_decision']=c.RECHECK
   m=metrics(DEV,out,req,'dev');self.assertEqual(m['determinate_negative_total_RECHECK_count'],count);self.assertEqual(m['gate_checks']['determinate_negative_total_recheck_rate'],count==23)
 def test_routing_exhaustive(self):
  for p in DECISIONS:
   for s in [None,*c.STATES]:
    f=route_first_frame(p,s)
    self.assertEqual(f==c.ALERT,p==c.ALERT)
    if p==c.RECHECK or (p!=c.ALERT and s in [None,'uncertain','candidate_present']):self.assertEqual(f,c.RECHECK)
 def test_strict_valid(self):self.assertEqual(c.parse_response(outer())[1]['scene_review'],'candidate_absent')
 def test_strict_rejections(self):
  invalid=[outer({'scene_review':'no','evidence':'x'}),outer({'scene_review':'uncertain','evidence':' '}),outer({'scene_review':'uncertain','evidence':'x','extra':1}),outer(done=False),outer(done_reason='length'),outer(model='other'),outer(response='{"scene_review":"uncertain","scene_review":"candidate_absent","evidence":"x"}'),b'{"done":true,"done":false}',b'{',outer(response='[]'),outer({'scene_review':None,'evidence':'x'})]
  for raw in invalid:
   with self.subTest(raw=raw),self.assertRaises((ValueError,TypeError)):c.parse_response(raw)
 def test_duplicate_and_missing_predictions_block(self):
  out,req=simulated(DEV)
  for bad in [out[:-1],out+[out[0]]]:
   with self.assertRaises(ValueError):metrics(DEV,bad,req,'dev')
  with self.assertRaises(ValueError):c.validate_manifest('dev',DEV[:-1]+[DEV[0]])
 def test_missing_secondary_or_protocol_failure_not_success(self):
  out,req=simulated(DEV)
  with self.assertRaises(ValueError):metrics(DEV,out,req[:-1],'dev')
  req[0]['strict_json_ok']=False
  with self.assertRaises(ValueError):metrics(DEV,out,req,'dev')
 def test_sha_mismatch(self):
  with self.assertRaises(ValueError):c.verify_sha(DEV[0]['full_view_path'],'0'*64)
 def test_request_identity_and_quota(self):
  r=next(x for x in DEV if x['secondary_required'])
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   c.claim_request('dev',r,tmp,set())
   with self.assertRaises(FileExistsError):c.claim_request('dev',r,tmp,set())
   with self.assertRaises(ValueError):c.claim_request('dev',r,tmp,{r['request_id']})
   with self.assertRaises(ValueError):c.claim_request('dev',r,tmp,{str(x) for x in range(288)})
   with self.assertRaises(ValueError):c.claim_request('regression',r,tmp,set())
 def test_alert_never_sends(self):
  r=next(x for x in DEV if not x['secondary_required'])
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,self.assertRaises(ValueError):c.claim_request('dev',r,tmp,set())
 def test_existing_start_completion_lock_blocks(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   p=Path(tmp)/'stage';c.start_stage(p);c.write_json(p/'COMPLETION_LOCK.json',{'status':'COMPLETE'})
   with self.assertRaises(ValueError):c.start_stage(p)
 def test_forbidden_phases(self):
  for phase in ['val','holdout','screen','VAL','HOLDOUT']:
   with self.assertRaises(ValueError):runner.run_stage(phase)
 def test_payload_no_lineage(self):
  pp=runner.payload('fixed prompt',{'type':'object'},b'jpeg')
  self.assertEqual(set(pp),{'model','prompt','images','think','stream','format','options'})
  self.assertEqual(pp['images'],['anBlZw==']);self.assertFalse(pp['think']);self.assertEqual(pp['options'],{'temperature':0,'num_ctx':8192,'num_predict':384})
 def test_transport_failure_stops_without_retry(self):
  # Temporary fixture only. No real eval artifact and no network call.
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp)
   for d in ['manifests','prompt','schema','protocol','freeze']:(root/d).mkdir()
   c.write_json(root/'manifests/dev.json',DEV)
   for p in ['prompt/scene_review.txt','schema/secondary.json','protocol/execution_plan.json']:(root/p).write_bytes((ROOT/p).read_bytes())
   (root/'freeze/EXECUTION_FREEZE.json').write_text('{}')
   failed={'http_status':None,'raw':b'','latency_seconds':.1,'completion_unknown':True,'error':'offline test timeout'}
   with patch.object(runner,'ROOT',root),patch.object(runner,'verify_freeze',return_value={}),patch.object(runner,'runtime_check',return_value={'offline_test':True}),patch.object(runner,'call_once',return_value=failed) as call:
    with self.assertRaises(ValueError):runner.run_stage('dev')
    self.assertEqual(call.call_count,1)
    self.assertTrue((root/'eval/dev/PROTOCOL_INCOMPLETE.json').exists());self.assertFalse((root/'eval/dev/summary.json').exists())
    with self.assertRaises(ValueError):runner.run_stage('dev')
    self.assertEqual(call.call_count,1)
 def test_regression_baseline_target_fails_before_secondary(self):
  out,req=simulated(REG);m=metrics(REG,out,req,'regression');self.assertFalse(m['gate_checks']['PFV4_SCREEN_0066_final_recheck']);self.assertEqual(m['immediate_ALERT_recall'],24/25)

if __name__=='__main__':unittest.main()
