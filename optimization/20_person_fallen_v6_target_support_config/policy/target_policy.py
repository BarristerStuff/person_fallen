"""V6 per-person support policy. Never reads evidence text or bbox geometry."""
ALERT='ALERT_GROUND_LYING';NORMAL='NO_ALERT_NORMAL_POSE';ATTENTION='ATTENTION_NEAR_GROUND';RECHECK='RECHECK_VISUAL_UNCERTAIN'
LYING={'supine','side_lying','prone','curled_lying','other_near_ground'};AUX_POSES={'crawling','pushup_plank'};NORMAL_POSES={'standing','walking','chair_sitting','floor_sitting','kneeling','squat_crouch','bending'}
AUX_SUPPORT={'forearms_feet_supported','hands_feet_supported','hands_knees_supported'}
def person_decision(p):
 def r(d,x):return {'person_id':p['person_id'],'decision':d,'reason':x}
 if p['person_visible']!='yes' or p['visual_quality']!='clear' or p['bbox_1000'] is None:return r(RECHECK,'TARGET_EVIDENCE_UNRELIABLE')
 pose=p['pose'];surf=p['support_surface'];sup=p['body_support_configuration'];ori=p['torso_orientation'];contact=p['torso_ground_contact'];head=p['head_shoulders_above_hips']
 if surf=='unknown' or sup in {'unknown','mixed_or_occluded'}:return r(RECHECK,'SUPPORT_CONFIGURATION_UNRESOLVED')
 # Explicit rest support is local to this person and must be internally consistent.
 if surf=='bed_sofa' or sup=='chair_or_bed_supported':
  if surf in {'bed_sofa','chair'} and sup=='chair_or_bed_supported':return r(NORMAL,'NORMAL_REST_OR_CHAIR_SUPPORT')
  return r(RECHECK,'REST_SUPPORT_CONFLICT')
 # Limb-supported horizontal bodies are auxiliary or unresolved, never ALERT.
 if sup in AUX_SUPPORT:
  if contact=='broad':return r(RECHECK,'LIMB_SUPPORT_VS_BROAD_TORSO_CONTACT')
  if surf!='floor':return r(RECHECK,'LIMB_SUPPORT_SURFACE_CONFLICT')
  if pose=='kneeling' and sup=='hands_knees_supported':return r(NORMAL,'CONSISTENT_KNEELING_SUPPORT')
  if pose in AUX_POSES or (pose in LYING and ori=='horizontal'):
   return r(ATTENTION,'CLEAR_LIMB_SUPPORTED_NEAR_GROUND:'+sup)
  return r(RECHECK,'LIMB_SUPPORT_POSE_CONFLICT')
 if pose=='floor_sitting':
  if surf=='floor' and sup=='pelvis_supported' and head=='yes' and ori in {'upright','inclined'} and contact in {'none','partial'}:return r(NORMAL,'CONSISTENT_FLOOR_SITTING')
  return r(RECHECK,'FLOOR_SITTING_SUPPORT_CONFLICT')
 if pose=='chair_sitting':return r(RECHECK,'CHAIR_SITTING_SUPPORT_CONFLICT')
 # Work context applies to this person only. It cannot veto another person's alert.
 if p['explicit_work_evidence']=='yes' and pose not in LYING:return r(NORMAL,'EXPLICIT_WORK_CONTEXT')
 # ALERT requires the complete five-field conjunction.
 if pose in LYING:
  if surf=='floor' and ori=='horizontal' and contact=='broad' and sup=='torso_ground_supported':return r(ALERT,'CLEAR_TORSO_GROUND_SUPPORTED_LYING')
  return r(RECHECK,'LYING_SUPPORT_CONFIGURATION_CONFLICT')
 if pose in AUX_POSES:return r(RECHECK,'AUXILIARY_SUPPORT_CONFIGURATION_CONFLICT')
 if pose in {'standing','walking','squat_crouch','bending'}:
  if surf=='floor' and contact in {'none','partial'} and ori in ({'upright','inclined','horizontal'} if pose=='bending' else {'upright','inclined'}) and sup!='torso_ground_supported':return r(NORMAL,'CONSISTENT_NORMAL_POSE:'+pose)
  return r(RECHECK,'NORMAL_POSE_SUPPORT_CONFLICT')
 if pose=='kneeling':return r(RECHECK,'KNEELING_SUPPORT_CONFIGURATION_CONFLICT')
 return r(RECHECK,'UNRESOLVED_TARGET_ATTRIBUTES')
def evaluate(parsed):
 ds=[person_decision(p) for p in parsed['people']];vals={d['decision'] for d in ds}
 if ALERT in vals:return {'person_decisions':ds,'image_decision':ALERT,'image_reason':'AT_LEAST_ONE_TORSO_GROUND_SUPPORTED_PERSON'}
 if not ds or RECHECK in vals or parsed['scene_coverage']!='complete':return {'person_decisions':ds,'image_decision':RECHECK,'image_reason':'EMPTY_UNRESOLVED_OR_INCOMPLETE_COVERAGE'}
 if ATTENTION in vals:return {'person_decisions':ds,'image_decision':ATTENTION,'image_reason':'AUXILIARY_ONLY'}
 return {'person_decisions':ds,'image_decision':NORMAL,'image_reason':'ALL_PEOPLE_NORMAL'}
