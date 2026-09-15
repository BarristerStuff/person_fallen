import base64, importlib.util, json, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('diag',ROOT/'tools/diagnostic.py'); d=importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
def attrs(row):
 pose='pushup_plank' if row['evaluation_stratum']=='auxiliary_attention' else 'unknown'
 return {'scene_coverage':'complete','people':[{'person_id':1,'bbox_1000':[10,10,900,900],'person_visible':'yes','pose':pose,'torso_orientation':'horizontal' if pose=='pushup_plank' else 'unknown','torso_ground_contact':'partial' if pose=='pushup_plank' else 'unknown','head_shoulders_above_hips':'no' if pose=='pushup_plank' else 'unknown','support_surface':'floor' if pose=='pushup_plank' else 'unknown','explicit_work_evidence':'no','visual_quality':'clear','evidence':'visible person'}]}
class DiagnosticTests(unittest.TestCase):
 def test_identity_and_payload(self):
  rows=d.read_json(d.MANIFEST); reused=d.read_json(d.REUSE)
  self.assertEqual((len(rows),len(reused),len({x['item_id'] for x in rows}|{x['item_id'] for x in reused})),(47,389,436)); self.assertFalse({x['item_id'] for x in rows}&{x['item_id'] for x in reused})
  payload=json.loads(d.build_payload(rows[0])); text=json.dumps(payload)
  for forbidden in ('item_id','taxonomy','ground_truth','image_path','prompt_path'): self.assertNotIn(forbidden,text)
 def test_reused_raw_parser_policy_replay(self):
  evidence=d.verify_reused(); self.assertEqual(len(evidence),389); self.assertEqual(len({x['item_id'] for x in evidence}),389)
 def test_fake_full_execution(self):
  calls=[]
  def fake(payload,rid,row):
   calls.append(rid); outer={'model':d.MODEL['name'],'done':True,'done_reason':'stop','eval_count':20,'response':json.dumps(attrs(row))}; return {'http_status':200,'raw':json.dumps(outer).encode(),'latency_seconds':.01,'completion_unknown':False,'error':None}
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/'run'; result=d.execute(fake,out,False); self.assertEqual(len(calls),47); self.assertEqual(result['FULL_DEV_OBSERVED_ROWS'],436); self.assertEqual(len(d.read_jsonl(out/'output.jsonl')),47); self.assertEqual(d.read_json(out/'COMPLETION_LOCK.json')['completed'],47)
 def test_failures_do_not_complete(self):
  cases=[{'http_status':500,'raw':b'x','latency_seconds':0,'completion_unknown':False,'error':'http'},{'http_status':None,'raw':b'','latency_seconds':0,'completion_unknown':True,'error':'timeout'},{'http_status':200,'raw':b'{}','latency_seconds':0,'completion_unknown':False,'error':None}]
  for result in cases:
   with self.subTest(result=result), tempfile.TemporaryDirectory() as td:
    with self.assertRaises(Exception): d.execute(lambda *a:result,Path(td)/'run',False)
    self.assertFalse((Path(td)/'run/COMPLETION_LOCK.json').exists())
 def test_manifest_and_raw_tamper_detected(self):
  with tempfile.TemporaryDirectory() as td:
   td=Path(td); manifest=td/'manifest.json'; reuse=td/'reuse.json'; bound=td/'bound'; freeze=td/'freeze.json'
   manifest.write_bytes(d.MANIFEST.read_bytes()); reuse.write_bytes(d.REUSE.read_bytes()); bound.write_text('original')
   freeze.write_text(json.dumps({'request_budget':47,'manifest_sha256':d.sha(manifest),'reused_results_sha256':d.sha(reuse),'bindings':{str(bound):d.sha(bound)}}))
   originals=d.FREEZE,d.MANIFEST,d.REUSE
   try:
    d.FREEZE,d.MANIFEST,d.REUSE=freeze,manifest,reuse; d.verify_freeze(); manifest.write_text('[]')
    with self.assertRaises(ValueError): d.verify_freeze()
   finally: d.FREEZE,d.MANIFEST,d.REUSE=originals
 def test_duplicate_request_id_rejected_before_stage_start(self):
  rows=d.read_json(d.MANIFEST); rows[1]['request_id']=rows[0]['request_id']
  with tempfile.TemporaryDirectory() as td:
   altered=Path(td)/'manifest.json'; altered.write_text(json.dumps(rows)); old=d.MANIFEST
   try:
    d.MANIFEST=altered
    with self.assertRaises(ValueError): d.execute(lambda *a:None,Path(td)/'run',False)
   finally:d.MANIFEST=old
 def test_unauthorized_phase(self):
  row=dict(d.read_json(d.MANIFEST)[0]); row['phase']='val'
  with self.assertRaises(ValueError): d.verify_input(row)
if __name__=='__main__': unittest.main()
