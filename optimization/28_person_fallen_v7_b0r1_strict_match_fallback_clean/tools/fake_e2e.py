from __future__ import annotations
import sys
from pathlib import Path
D=Path(__file__).resolve().parents[1];sys.path.insert(0,str(D/'policy'))
from v7_b0_policy import person_p1,p2_match,aggregate
from person_association import match
base={'support_surface':'floor','torso_orientation':'horizontal','torso_ground_contact':'broad','body_support_configuration':'torso_ground_supported','explicit_work_evidence':'no','visual_quality':'clear'}
def p(pose,box):return dict(base,pose=pose,bbox_1000=box)
# Multi-person: upright detector matches normal P2; missed supine remains unmatched and alerts.
det=[[590,220,710,690]]; people=[p('supine',[258,536,544,656]),p('standing',[592,226,708,683])]
a=match(det,[x['bbox_1000'] for x in people]);by={x['p2_index']:x for x in a}
assert by[1]['detector_index']==0 and 0 not in by
decs=[]
for i,x in enumerate(people):
 decs.append(p2_match(x,'GEOM_UPRIGHT' if i in by else 'GEOM_NOT_UPRIGHT'))
assert decs==['ALERT_GROUND_LYING','NO_EFFECT'] and aggregate(decs)=='ALERT_GROUND_LYING'
# Floor: matched upright stays no effect and image remains normal.
people=[p('floor_sitting',[400,300,650,800])];a=match([[390,290,660,810]],[people[0]['bbox_1000']]);assert len(a)==1
assert aggregate([p2_match(people[0],'GEOM_UPRIGHT')])=='NO_ALERT_NORMAL_POSE'
# Prone cross-view.
p1=person_p1(dict(base,pose='prone'),'GEOM_NOT_UPRIGHT');assert p1=='PROVISIONAL_PRONE'
p2=p2_match(dict(base,pose='prone'),'GEOM_NOT_UPRIGHT',p1);assert aggregate([p1,p2])=='ALERT_GROUND_LYING'
print('FAKE_E2E_PASS')
