import copy,sys,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'policy'))
import contracts as c
from target_policy import person_decision,evaluate,ALERT,NORMAL,ATTENTION,RECHECK

def person(**kw):
 p={'person_id':1,'bbox_1000':[100,200,400,900],'person_visible':'yes','pose':'floor_sitting','torso_orientation':'upright','torso_ground_contact':'none','head_shoulders_above_hips':'yes','support_surface':'floor','explicit_work_evidence':'no','visual_quality':'clear','evidence':'Visible seated person with torso above pelvis.'};p.update(kw);return p
def lying(**kw):
 p=person(pose='supine',torso_orientation='horizontal',torso_ground_contact='broad',head_shoulders_above_hips='no');p.update(kw);return p
def obj(*people,coverage='complete'):return {'scene_coverage':coverage,'people':list(people)}
def raw(value,**kw):
 o={'model':'qwen3.5:4b','done':True,'done_reason':'stop','response':json.dumps(value)};o.update(kw);return json.dumps(o).encode()
class TargetContract(unittest.TestCase):
 def test_schema_matches_validator(self):
  schema=json.loads((ROOT/'schema/target_attributes.json').read_text())
  self.assertEqual(set(schema['required']),{'scene_coverage','people'})
  item=schema['properties']['people']['items'];self.assertEqual(set(item['required']),c.PERSON_KEYS)
  for k,allowed in c.ENUMS.items():self.assertEqual(item['properties'][k]['enum'],allowed)
  self.assertEqual(c.parse_response(raw(obj(person())))[1],obj(person()))
 def test_schema_rejections(self):
  invalid=[]
  p=person();p['extra']=1;invalid.append(obj(p))
  v=obj(person());v['extra']=1;invalid.append(v)
  invalid += [obj(person(pose='lying')),obj(person(evidence=' ')),obj(person(person_id=True)),obj(person(person_id=4)),obj(person(),person()),obj(person(bbox_1000=[0,0,1001,900])),obj(person(bbox_1000=[200,0,100,900])),obj(person(bbox_1000=[0,100,900,100])),obj(person(bbox_1000=[False,0,900,900])),obj(person(bbox_1000=[0.,0,900,900])),obj(person(bbox_1000='none')),obj(person(person_id=1),person(person_id=2),person(person_id=3),person(person_id=4))]
  for v in invalid:
   with self.subTest(v=v),self.assertRaises(ValueError):c.parse_response(raw(v))
 def test_duplicate_json_incomplete_wrong_model(self):
  duplicate='{"scene_coverage":"complete","scene_coverage":"incomplete","people":[]}'
  for r in [b'{',raw(obj(person()),response=duplicate),raw(obj(person()),done=False),raw(obj(person()),done_reason='length'),raw(obj(person()),model='wrong'),b'{"done":true,"done":true}',raw(obj(person()),response='[]')]:
   with self.assertRaises(ValueError):c.parse_response(r)
 def test_null_empty_and_coverage(self):
  self.assertEqual(evaluate(c.validate_attributes(obj(person(bbox_1000=None))))['image_decision'],RECHECK)
  self.assertEqual(evaluate(obj())['image_decision'],RECHECK)
  for coverage in ['incomplete','unknown']:self.assertEqual(evaluate(obj(person(),coverage=coverage))['image_decision'],RECHECK)
 def test_target_evidence_gate(self):
  for update in [{'person_visible':'no'},{'person_visible':'uncertain'},{'visual_quality':'insufficient'},{'bbox_1000':None}]:
   self.assertEqual(person_decision(lying(**update))['decision'],RECHECK)
 def test_floor_sitting_complete_truth_conjunction(self):
  for ori in ['upright','inclined']:
   for contact in ['none','partial']:self.assertEqual(person_decision(person(torso_orientation=ori,torso_ground_contact=contact))['decision'],NORMAL)
  for kw in [{'head_shoulders_above_hips':'unknown'},{'head_shoulders_above_hips':'no'},{'torso_orientation':'horizontal'},{'torso_orientation':'unknown'},{'torso_ground_contact':'broad'},{'torso_ground_contact':'unknown'},{'support_surface':'unknown'},{'support_surface':'chair'}]:
   self.assertEqual(person_decision(person(**kw))['decision'],RECHECK)
 def test_lying_requires_support_and_contact(self):
  for pose in ['supine','side_lying','prone','curled_lying','other_near_ground']:
   self.assertEqual(person_decision(lying(pose=pose))['decision'],ALERT)
   for kw in [{'support_surface':'unknown'},{'torso_orientation':'inclined'},{'torso_orientation':'upright'},{'torso_ground_contact':'partial'},{'torso_ground_contact':'none'},{'torso_ground_contact':'unknown'}]:
    self.assertEqual(person_decision(lying(pose=pose,**kw))['decision'],RECHECK)
  self.assertEqual(person_decision(lying(head_shoulders_above_hips='yes'))['decision'],ALERT)
 def test_all_conflict_rows_precede_work(self):
  conflicts=[lying(support_surface='bed_sofa'),person(pose='chair_sitting'),person(support_surface='chair'),person(torso_ground_contact='broad'),person(head_shoulders_above_hips='no'),person(pose='kneeling',torso_orientation='horizontal'),lying(torso_orientation='upright'),lying(torso_ground_contact='none'),lying(pose='crawling')]
  for p in conflicts:
   p['explicit_work_evidence']='yes';self.assertEqual(person_decision(p)['decision'],RECHECK)
 def test_context_only_applies_to_target(self):
  worker=person(pose='kneeling',explicit_work_evidence='yes')
  rest=lying(support_surface='bed_sofa',torso_ground_contact='none')
  for normal in [worker,rest,person()]:
   self.assertEqual(person_decision(normal)['decision'],NORMAL)
   self.assertEqual(evaluate(obj(normal,lying(person_id=2)))['image_decision'],ALERT)
  self.assertEqual(person_decision(lying(explicit_work_evidence='yes'))['decision'],NORMAL)
 def test_auxiliary_not_lying(self):
  for pose in ['crawling','pushup_plank']:
   p=person(pose=pose,torso_orientation='horizontal');self.assertEqual(person_decision(p)['decision'],ATTENTION)
   self.assertEqual(evaluate(obj(p,person(person_id=2)))['image_decision'],ATTENTION)
   p['torso_ground_contact']='broad';self.assertEqual(person_decision(p)['decision'],RECHECK)
 def test_scene_priority(self):
  self.assertEqual(evaluate(obj(person(),lying(person_id=2),person(person_id=3,bbox_1000=None),coverage='unknown'))['image_decision'],ALERT)
  self.assertEqual(evaluate(obj(person(),person(person_id=2,bbox_1000=None)))['image_decision'],RECHECK)
  self.assertEqual(evaluate(obj(person(),person(person_id=2)))['image_decision'],NORMAL)
 def test_evidence_and_box_geometry_not_policy(self):
  for p in [person(),lying(),person(pose='unknown')]:
   before=person_decision(p)
   for text in ['another person is lying','standing normally','tools nearby','supine floor broad','No alert']:
    q={**p,'evidence':text,'bbox_1000':[0,0,999,1]};self.assertEqual(before,person_decision(q))
 def test_unknown_is_not_silent_normal(self):
  self.assertEqual(person_decision(person(pose='unknown'))['decision'],RECHECK)
  self.assertEqual(person_decision(lying(explicit_work_evidence='unknown'))['decision'],ALERT)
 def test_request_lock_and_budget(self):
  row={'request_id':'V5_B0_PILOT_0001'}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   p=Path(tmp)/'pilot';c.start_stage(p)
   with self.assertRaises(ValueError):c.start_stage(p)
   q=c.claim_directory(p,'pilot',row,set(),0);c.write_json(q/'completed.json',{'test_only':True})
   with self.assertRaises(FileExistsError):c.claim_directory(p,'pilot',row,set(),0)
   with self.assertRaises(ValueError):c.claim_directory(p,'pilot',row,{row['request_id']},1)
   with self.assertRaises(ValueError):c.claim_directory(p,'pilot',row,set(),116)
   with self.assertRaises(ValueError):c.claim_directory(p,'pilot',row,{str(i) for i in range(115)},115)
   with self.assertRaises(ValueError):c.claim_directory(p,'regression',row,set(),0)
if __name__=='__main__':unittest.main()
