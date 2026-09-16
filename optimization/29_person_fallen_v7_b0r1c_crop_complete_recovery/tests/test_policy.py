import sys
sys.path.insert(0,'policy')
from v7_b0_policy import *
base={'support_surface':'floor','torso_orientation':'horizontal','torso_ground_contact':'broad','body_support_configuration':'torso_ground_supported','visual_quality':'clear'}
def t(pose,geom='GEOM_NOT_UPRIGHT',**kw): return person_p1(dict(base,pose=pose,**kw),geom)
def test_hard_veto(): assert t('supine','GEOM_UPRIGHT')=='NO_ALERT_NORMAL_POSE'
def test_direct(): assert t('supine')=='ALERT_GROUND_LYING'
def test_prone_provisional(): assert t('prone')=='PROVISIONAL_PRONE'
def test_prone_consensus(): assert p2_match(dict(base,pose='prone'),'GEOM_NOT_UPRIGHT','PROVISIONAL_PRONE')=='ALERT_GROUND_LYING'
def test_aux(): assert t('pushup_plank')=='ATTENTION_NEAR_GROUND'; assert t('prone',body_support_configuration='hands_feet_supported')=='ATTENTION_NEAR_GROUND'
def test_other(): assert t('other_near_ground')=='RECHECK_VISUAL_UNCERTAIN'
def test_agg_unmatched(): assert aggregate(['NO_ALERT_NORMAL_POSE','ALERT_GROUND_LYING'])=='ALERT_GROUND_LYING'
def test_evidence_irrelevant():
 a=dict(base,pose='supine',evidence='push-up'); b=dict(a,evidence='normal'); assert person_p1(a,'GEOM_NOT_UPRIGHT')==person_p1(b,'GEOM_NOT_UPRIGHT')
