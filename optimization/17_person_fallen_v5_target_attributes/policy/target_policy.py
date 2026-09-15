"""Frozen per-person physical evidence rules; bbox geometry and evidence text never classify."""
ALERT='ALERT_GROUND_LYING'
NORMAL='NO_ALERT_NORMAL_POSE'
ATTENTION='ATTENTION_NEAR_GROUND'
RECHECK='RECHECK_VISUAL_UNCERTAIN'
LYING={'supine','side_lying','prone','curled_lying'}
NORMAL_GROUND={'standing','walking','kneeling','squat_crouch','bending'}
AUXILIARY={'crawling','pushup_plank'}

def person_decision(p):
 def result(d,r):return {'person_id':p['person_id'],'decision':d,'reason':r}
 # These records are NEW target attributes, not claimed YOLO instance detections.
 if p['person_visible']!='yes' or p['visual_quality']!='clear' or p['bbox_1000'] is None:
  return result(RECHECK,'TARGET_EVIDENCE_UNRELIABLE')
 pose=p['pose'];surface=p['support_surface'];orientation=p['torso_orientation'];contact=p['torso_ground_contact'];head=p['head_shoulders_above_hips']
 # Mechanical conflicts precede work/rest exceptions. Work/rest never veto another target.
 if surface!='floor' and contact=='broad':return result(RECHECK,'NONFLOOR_SUPPORT_VS_BROAD_GROUND_CONTACT')
 if pose=='chair_sitting' and surface=='floor':return result(RECHECK,'CHAIR_POSE_VS_FLOOR_SUPPORT')
 if surface=='chair' and pose in LYING|AUXILIARY|{'floor_sitting','kneeling','squat_crouch','other_near_ground'}:
  return result(RECHECK,'GROUND_POSE_VS_CHAIR_SUPPORT')
 if pose in NORMAL_GROUND|{'floor_sitting','chair_sitting'} and contact=='broad':
  return result(RECHECK,'NORMAL_POSE_VS_BROAD_TORSO_CONTACT')
 if pose=='floor_sitting' and (head=='no' or orientation=='horizontal'):
  return result(RECHECK,'FLOOR_SITTING_HEAD_OR_AXIS_CONFLICT')
 if pose in (NORMAL_GROUND-{'bending'})|{'chair_sitting'} and orientation=='horizontal':
  return result(RECHECK,'NORMAL_POSE_VS_HORIZONTAL_TORSO')
 if pose in LYING and orientation=='upright':return result(RECHECK,'LYING_POSE_VS_UPRIGHT_TORSO')
 if pose in LYING and surface=='floor' and contact=='none':return result(RECHECK,'LYING_POSE_WITHOUT_TORSO_GROUND_CONTACT')
 if pose in AUXILIARY and contact=='broad':return result(RECHECK,'AUXILIARY_POSE_VS_BROAD_TORSO_CONTACT')
 if surface=='unknown':return result(RECHECK,'SUPPORT_SURFACE_UNRESOLVED')
 if surface=='bed_sofa':return result(NORMAL,'TARGET_NORMAL_REST_SUPPORT')
 if p['explicit_work_evidence']=='yes':return result(NORMAL,'TARGET_EXPLICIT_WORK_CONTEXT')
 if pose=='floor_sitting':
  if surface=='floor' and head=='yes' and orientation in {'upright','inclined'} and contact in {'none','partial'}:
   return result(NORMAL,'CONSISTENT_FLOOR_SITTING')
  return result(RECHECK,'FLOOR_SITTING_ATTRIBUTES_UNRESOLVED_OR_CONFLICTING')
 if pose=='chair_sitting':
  if surface=='chair' and orientation in {'upright','inclined'} and contact in {'none','partial'}:
   return result(NORMAL,'CONSISTENT_CHAIR_SITTING')
  return result(RECHECK,'CHAIR_SITTING_ATTRIBUTES_UNRESOLVED_OR_CONFLICTING')
 if pose in NORMAL_GROUND:
  allowed={'upright','inclined','horizontal'} if pose=='bending' else {'upright','inclined'}
  if surface=='floor' and orientation in allowed and contact in {'none','partial'}:
   return result(NORMAL,'CONSISTENT_NORMAL_GROUND_POSE:'+pose)
  return result(RECHECK,'NORMAL_GROUND_ATTRIBUTES_UNRESOLVED_OR_CONFLICTING')
 if pose in AUXILIARY:
  if surface=='floor' and orientation in {'inclined','horizontal'} and contact in {'none','partial'}:
   return result(ATTENTION,'CONSISTENT_AUXILIARY_POSE:'+pose)
  return result(RECHECK,'AUXILIARY_ATTRIBUTES_UNRESOLVED_OR_CONFLICTING')
 if pose in LYING|{'other_near_ground'}:
  if surface=='floor' and orientation=='horizontal' and contact=='broad':
   return result(ALERT,'HORIZONTAL_GROUND_SUPPORTED_TARGET:'+pose)
  return result(RECHECK,'GROUND_LYING_EVIDENCE_UNRESOLVED_OR_CONFLICTING')
 return result(RECHECK,'UNRESOLVED_TARGET_POSE')

def evaluate(parsed):
 people=[person_decision(p) for p in parsed['people']]
 decisions={p['decision'] for p in people}
 if ALERT in decisions:decision,reason=ALERT,'AT_LEAST_ONE_RELIABLE_GROUND_LYING_PERSON'
 elif not people or RECHECK in decisions or parsed['scene_coverage']!='complete':decision,reason=RECHECK,'EMPTY_UNRESOLVED_TARGET_OR_INCOMPLETE_COVERAGE'
 elif ATTENTION in decisions:decision,reason=ATTENTION,'AUXILIARY_WITHOUT_ALERT_OR_UNRESOLVED_TARGET'
 else:decision,reason=NORMAL,'ALL_ENUMERATED_PEOPLE_CLEAR_NORMAL'
 return {'person_decisions':people,'image_decision':decision,'image_reason':reason}
