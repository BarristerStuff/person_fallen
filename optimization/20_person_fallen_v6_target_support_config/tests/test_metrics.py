import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import metrics
def person(pid=1,support='pelvis_supported'):
 return {'person_id':pid,'bbox_1000':[1,1,900,999],'person_visible':'yes','pose':'floor_sitting','torso_orientation':'upright','torso_ground_contact':'partial','head_shoulders_above_hips':'yes','support_surface':'floor','body_support_configuration':support,'explicit_work_evidence':'no','visual_quality':'clear','evidence':'synthetic'}
def output(row,decision=metrics.NO_ALERT,people=None):
 people=people or [person()];ds=[{'person_id':p['person_id'],'decision':decision,'reason':'fixture'} for p in people]
 return {'item_id':row['item_id'],'operational_id':row.get('operational_id'),'request_id':row['request_id'],'taxonomy':row['taxonomy'],'group_id':row.get('group_id','g'),'evaluation_stratum':row.get('evaluation_stratum'),'parsed':{'scene_coverage':'complete','people':people},'person_decisions':ds,'image_decision':decision,'strict_json_ok':True,'source_binding_ok':True,'http_status':200,'latency_seconds':.1,'eval_count':10}
def request(o):return {**o,'state':'completed','completion_unknown':False,'done':True,'done_reason':'stop'}
class MetricsTests(unittest.TestCase):
 def test_missing_duplicate_failed_never_pass(self):
  m=[{'item_id':'a','request_id':'r1','taxonomy':'floor_sitting','evaluation_stratum':'normal_negative'}];o=output(m[0]);
  self.assertEqual(metrics.summarize('pilot',m,[],[])['gate'],'FAIL')
  self.assertEqual(metrics.summarize('pilot',m,[o,o],[request(o)])['gate'],'FAIL')
  bad=request(o);bad['state']='failed';self.assertEqual(metrics.summarize('pilot',m,[o],[bad])['gate'],'FAIL')
 def test_recheck_not_alert_and_latency(self):
  m=[{'item_id':'a','request_id':'r1','taxonomy':'floor_sitting','evaluation_stratum':'normal_negative'}];o=output(m[0],metrics.RECHECK);g=metrics.summarize('pilot',m,[o],[request(o)]);self.assertEqual(g['floor_sitting_decisions'][metrics.ALERT],0);self.assertEqual(g['floor_sitting_decisions'][metrics.RECHECK],1);self.assertEqual(g['latency']['p50'],.1)
 def test_schema_bbox_and_duplicate_people(self):
  m=[{'item_id':'a','request_id':'r1','taxonomy':'floor_sitting','evaluation_stratum':'normal_negative'}];o=output(m[0]);o['parsed']['people'][0].pop('pose');self.assertTrue(metrics.summarize('pilot',m,[o],[request(o)])['protocol_errors'])
  o=output(m[0]);o['parsed']['people'][0]['bbox_1000']=[9,1,1,2];self.assertTrue(metrics.summarize('pilot',m,[o],[request(o)])['protocol_errors'])
  o=output(m[0],people=[person(1),person(1)]);self.assertTrue(metrics.summarize('pilot',m,[o],[request(o)])['protocol_errors'])
 def test_regression_contract(self):
  m=[{'item_id':'P4D_PLAN::PF_P4D_POS_CURLED_G003_V05','operational_id':'PFV4_SCREEN_0066','request_id':'reg','taxonomy':'curled_or_partially_occluded_lying','group_id':'g','evaluation_stratum':'ground_lying'}]
  ps=[person(1),person(2,'torso_ground_supported')];o=output(m[0],metrics.ALERT,ps);self.assertEqual(metrics.summarize('regression',m,[o],[request(o)])['gate'],'PASS')
 def test_phase(self):
  with self.assertRaises(ValueError):metrics.summarize('val',[],[],[])
if __name__=='__main__':unittest.main()
