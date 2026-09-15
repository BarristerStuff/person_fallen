import json,tempfile,sys,unittest,contextlib,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));import engine
class EngineTests(unittest.TestCase):
 def freeze(self):return {'candidate':'V6-A0-TARGET-SUPPORT-CONFIG','model':engine.MODEL,'budget':engine.EXPECTED_BUDGET}
 def test_budget_exact_and_phase_whitelist(self):
  engine.validate_freeze(self.freeze())
  bad=self.freeze();bad['budget']=dict(bad['budget']);bad['budget']['x']=0
  with self.assertRaises(ValueError):engine.validate_freeze(bad)
  with tempfile.TemporaryDirectory() as td:
   for phase in ['val','holdout','screen','full','production']:
    with self.assertRaises(ValueError):engine.run_stage(phase,Path(td),self.freeze(),lambda d,r:{}, {'status':'PASS'})
 def test_fake_437(self):
  import fake_e2e
  with contextlib.redirect_stdout(io.StringIO()):
   with tempfile.TemporaryDirectory() as td:
    rr=Path(td)/'run';a=engine.run_stage('pilot',rr,self.freeze(),fake_e2e.fake,{'status':'PASS'});b=engine.run_stage('regression',rr,self.freeze(),fake_e2e.fake,{'status':'PASS'});c=engine.run_stage('full_remaining',rr,self.freeze(),fake_e2e.fake,{'status':'PASS'});d=engine.aggregate_full(rr)
    self.assertEqual((a['gate'],b['gate'],c['gate'],d['gate']),('PASS','PASS','PASS','PASS'))
    self.assertEqual(engine.ledger(rr),437)
    self.assertTrue((rr/'full_dev_combined/FULL_DEV_COMPLETION_LOCK.json').exists())
    self.assertEqual(len((rr/'pilot/output.jsonl').read_text().splitlines()),156)
    self.assertEqual(len((rr/'full_remaining/output.jsonl').read_text().splitlines()),280)
 def test_pilot_failed_blocks_regression(self):
  with tempfile.TemporaryDirectory() as td:
   rr=Path(td)/'run';(rr/'pilot').mkdir(parents=True);(rr/'pilot/summary.json').write_text(json.dumps({'gate':'FAIL'}));(rr/'pilot/COMPLETION_LOCK.json').write_text(json.dumps({'status':'COMPLETE','summary_sha256':engine.sha(rr/'pilot/summary.json')}))
   with self.assertRaises(ValueError):engine.run_stage('regression',rr,self.freeze(),lambda d,r:{}, {'status':'PASS'})
 def test_early_stop(self):
  full=engine.read_json(ROOT/'manifests/full_combined436.json');pilot=[]
  # 156 fake pilot neutral rows, then append 24 normal rechecks to trigger B
  for r in full:
   if r['result_source']=='REUSE_V6_PILOT':pilot.append({'item_id':r['item_id'],'evaluation_stratum':r['evaluation_stratum'],'image_decision':'RECHECK_VISUAL_UNCERTAIN' if r['taxonomy']=='floor_sitting' and len([x for x in pilot if x['evaluation_stratum']=='normal_negative'])<5 else ('ALERT_GROUND_LYING' if r['evaluation_stratum']=='ground_lying' else 'ATTENTION_NEAR_GROUND'),'strict_json_ok':True,'source_binding_ok':True})
  normal=[r for r in full if r['result_source']=='NEW_INFERENCE' and r['evaluation_stratum']=='normal_negative']
  rows=list(pilot)
  for i,r in enumerate(normal[:19],1):
   rows.append({'item_id':r['item_id'],'evaluation_stratum':'normal_negative','image_decision':'RECHECK_VISUAL_UNCERTAIN','strict_json_ok':True,'source_binding_ok':True})
   self.assertEqual(engine.early(pilot,rows[len(pilot):],full),None if i<19 else 'B_NORMAL_RECHECK_24')
if __name__=='__main__':unittest.main()
