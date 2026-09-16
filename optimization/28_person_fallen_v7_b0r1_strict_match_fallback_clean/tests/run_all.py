from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path
D=Path(__file__).resolve().parents[1];sys.path.insert(0,str(D/'policy'));sys.path.insert(0,str(D/'tools'))
from v7_b0_policy import person_p1,p2_match,aggregate
from person_association import match
import run_v7_b0r1 as runner
base={'support_surface':'floor','torso_orientation':'horizontal','torso_ground_contact':'broad','body_support_configuration':'torso_ground_supported','explicit_work_evidence':'no','visual_quality':'clear'}
def obj(pose,**kw): return dict(base,pose=pose,**kw)
# hard veto and P2 role
assert person_p1(obj('supine'),'GEOM_UPRIGHT')=='NO_ALERT_NORMAL_POSE'
assert p2_match(obj('supine'),'GEOM_UPRIGHT')=='NO_EFFECT'
assert p2_match(obj('pushup_plank'),'GEOM_UPRIGHT')=='NO_EFFECT'
for p in ('floor_sitting','pushup_plank','crawling','kneeling','squat','bending','standing','walking','other_near_ground'):
 assert p2_match(obj(p),'GEOM_NOT_UPRIGHT')=='NO_EFFECT',p
for p in ('supine','side_lying','curled_lying'):
 assert p2_match(obj(p),'GEOM_NOT_UPRIGHT')=='ALERT_GROUND_LYING',p
assert p2_match(obj('prone'),'GEOM_NOT_UPRIGHT')=='RECHECK_VISUAL_UNCERTAIN'
assert person_p1(obj('prone'),'GEOM_NOT_UPRIGHT')=='PROVISIONAL_PRONE'
assert p2_match(obj('prone'),'GEOM_NOT_UPRIGHT','PROVISIONAL_PRONE')=='ALERT_GROUND_LYING'
assert p2_match(obj('pushup_plank'),'GEOM_NOT_UPRIGHT','PROVISIONAL_PRONE')=='NO_EFFECT'
assert 'ATTENTION_NEAR_GROUND' not in {p2_match(obj(p),'GEOM_NOT_UPRIGHT') for p in runner.S1['properties']['pose']['enum']}
# aggregate
assert aggregate(['NO_ALERT_NORMAL_POSE','ALERT_GROUND_LYING'])=='ALERT_GROUND_LYING'
assert aggregate([],False)=='RECHECK_VISUAL_UNCERTAIN'
# deterministic one-to-one
m=match([[0,0,100,100],[200,0,300,100]],[[5,5,95,95],[205,5,295,95]])
assert [(x['detector_index'],x['p2_index']) for x in m]==[(0,0),(1,1)]
# strict schema, enum, evidence absent, bbox order
s1=runner.S1;s2=runner.S2
assert s1['additionalProperties'] is False and 'evidence' not in s1['properties']
assert s2['additionalProperties'] is False and s2['properties']['people']['items']['additionalProperties'] is False
runner.validate_obj(obj('supine'),s1)
for bad in [dict(obj('supine'),evidence='x'),dict(obj('supine'),pose='plank')]:
 try:runner.validate_obj(bad,s1);raise AssertionError('invalid accepted')
 except ValueError:pass
try:runner.validate_obj({'people':[dict(obj('supine'),bbox_1000=[5,5,4,10])]},s2);raise AssertionError('bbox order')
except ValueError:pass
# route options and protocol invariants
assert json.loads(runner.build_payload(runner.P1,b'x',s1,384))['options']['num_predict']==384
assert json.loads(runner.build_payload(runner.P2,b'x',s2,1024))['options']['num_predict']==1024
src=(D/'tools/run_v7_b0r1.py').read_text()
assert "env.get('done_reason')=='length'" in src
assert src.index("rp.write_bytes(raw)") < src.index("env=json.loads(raw)")
assert "if rid in existing_ids(root)" in src
assert "if phase not in ALLOWED_PHASES" in src
assert "CLEAN_EXECUTION_REQUIRED_NONEMPTY_PHASE" in src
assert "V7_B0R1_" in src
assert "ProxyHandler({})" in src
# no retry loop
assert 'for attempt' not in src and 'retry' not in src.lower()
print('ALL_UNIT_TESTS_PASS')
