import sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]/'policy'))
from v7_b0_policy import *
base={'support_surface':'floor','torso_orientation':'horizontal','torso_ground_contact':'broad','body_support_configuration':'torso_ground_supported','visual_quality':'clear'}
# hard veto; prone cross-view; unmatched direct lying; auxiliary; no detection
cases=[
 (person_p1(dict(base,pose='supine'),'GEOM_UPRIGHT'),'NO_ALERT_NORMAL_POSE'),
 (person_p1(dict(base,pose='prone'),'GEOM_NOT_UPRIGHT'),'PROVISIONAL_PRONE'),
 (p2_match(dict(base,pose='prone'),'GEOM_NOT_UPRIGHT','PROVISIONAL_PRONE'),'ALERT_GROUND_LYING'),
 (p2_match(dict(base,pose='supine'),'GEOM_UPRIGHT',None),'NO_ALERT_NORMAL_POSE'),
 (person_p1(dict(base,pose='pushup_plank'),'GEOM_NOT_UPRIGHT'),'ATTENTION_NEAR_GROUND'),
 (person_p1(dict(base,pose='other_near_ground'),'GEOM_NOT_UPRIGHT'),'RECHECK_VISUAL_UNCERTAIN'),
 (aggregate(['NO_ALERT_NORMAL_POSE','ALERT_GROUND_LYING']),'ALERT_GROUND_LYING'),
 (aggregate([],False),'RECHECK_VISUAL_UNCERTAIN')]
for got,want in cases: assert got==want,(got,want)
print('FAKE_E2E_PASS')
