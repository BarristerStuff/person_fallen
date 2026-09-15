import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'policy'))
from contracts import parse,validate
from target_policy import *
def p(**kw):
 x={'person_id':1,'bbox_1000':[10,10,500,900],'person_visible':'yes','pose':'floor_sitting','torso_orientation':'upright','torso_ground_contact':'partial','head_shoulders_above_hips':'yes','support_surface':'floor','body_support_configuration':'pelvis_supported','explicit_work_evidence':'no','visual_quality':'clear','evidence':'visible facts'};x.update(kw);return x
def obj(*ps,coverage='complete'):return {'scene_coverage':coverage,'people':list(ps)}
class PolicyContract(unittest.TestCase):
 def test_alert_exact_five_field_conjunction(self):
  base=p(pose='prone',torso_orientation='horizontal',torso_ground_contact='broad',support_surface='floor',body_support_configuration='torso_ground_supported',head_shoulders_above_hips='no')
  self.assertEqual(person_decision(base)['decision'],ALERT)
  for k,v in [('pose','pushup_plank'),('torso_orientation','inclined'),('torso_ground_contact','partial'),('support_surface','chair'),('body_support_configuration','forearms_feet_supported')]:
   q={**base,k:v};self.assertNotEqual(person_decision(q)['decision'],ALERT)
 def test_limb_support_never_alert(self):
  for sup in AUX_SUPPORT:
   q=p(pose='prone',torso_orientation='horizontal',torso_ground_contact='partial',body_support_configuration=sup,head_shoulders_above_hips='no')
   self.assertEqual(person_decision(q)['decision'],ATTENTION)
   q['torso_ground_contact']='broad';self.assertEqual(person_decision(q)['decision'],RECHECK)
 def test_floor_crawl_rest(self):
  self.assertEqual(person_decision(p())['decision'],NORMAL)
  self.assertEqual(person_decision(p(pose='crawling',body_support_configuration='hands_knees_supported',torso_orientation='inclined',head_shoulders_above_hips='no'))['decision'],ATTENTION)
  self.assertEqual(person_decision(p(pose='supine',support_surface='bed_sofa',body_support_configuration='chair_or_bed_supported',torso_orientation='horizontal',torso_ground_contact='none'))['decision'],NORMAL)
 def test_scene_priority_and_evidence_invariance(self):
  normal=p();lying=p(person_id=2,pose='side_lying',torso_orientation='horizontal',torso_ground_contact='broad',head_shoulders_above_hips='no',body_support_configuration='torso_ground_supported')
  self.assertEqual(evaluate(obj(normal,lying,coverage='incomplete'))['image_decision'],ALERT)
  for text in ['push up','lying person','normal']:self.assertEqual(person_decision({**lying,'evidence':text})['decision'],ALERT)
  self.assertEqual(evaluate(obj())['image_decision'],RECHECK);self.assertEqual(evaluate(obj(normal,coverage='incomplete'))['image_decision'],RECHECK)
 def test_duplicate_id_and_json_contract(self):
  with self.assertRaises(ValueError):validate(obj(p(),p()))
  raw=json.dumps({'model':'qwen3.5:4b','done':True,'done_reason':'stop','response':'{"scene_coverage":"complete","scene_coverage":"unknown","people":[]}'})
  with self.assertRaises(ValueError):parse(raw)
if __name__=='__main__':unittest.main()
