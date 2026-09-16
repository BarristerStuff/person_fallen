import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'policy'))
from v7_b0_policy import *
from person_association import match
b={'support_surface':'floor','torso_orientation':'horizontal','torso_ground_contact':'broad','body_support_configuration':'torso_ground_supported','visual_quality':'clear'}
assert p1(dict(b,pose='supine'),'GEOM_UPRIGHT')=='NO_ALERT_NORMAL_POSE'
assert p2(dict(b,pose='supine'),'GEOM_UPRIGHT')=='NO_EFFECT'
assert p2(dict(b,pose='pushup_plank'),'GEOM_NOT_UPRIGHT')=='NO_EFFECT'
assert p2(dict(b,pose='crawling'),'GEOM_NOT_UPRIGHT')=='NO_EFFECT'
assert p2(dict(b,pose='supine'),'GEOM_NOT_UPRIGHT')=='ALERT_GROUND_LYING'
assert p2(dict(b,pose='prone'),'GEOM_NOT_UPRIGHT')=='RECHECK_VISUAL_UNCERTAIN'
assert p1(dict(b,pose='prone'),'GEOM_NOT_UPRIGHT')=='PROVISIONAL_PRONE'
assert p2(dict(b,pose='prone'),'GEOM_NOT_UPRIGHT',p1_state='PROVISIONAL_PRONE')=='ALERT_GROUND_LYING'
assert match([[0,0,100,100]],[[10,10,90,90]])[0]['detector_index']==0
schema=json.load(open(Path(__file__).resolve().parents[1]/'schema/v7_person_attributes.json'))
assert 'evidence' not in schema['properties'] and 'evidence' not in schema['required']
print('B0R1_POLICY_ASSOCIATION_SCHEMA_PASS')
