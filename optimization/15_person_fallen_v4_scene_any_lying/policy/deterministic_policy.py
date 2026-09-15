from typing import Any
POSES={"standing","walking","chair_sitting","floor_sitting","kneeling","squat_crouch","bending","crawling","pushup_plank","supine","side_lying","prone","curled_lying","other_near_ground","unknown"}
ENUMS={"any_person_ground_lying_on_nonrest_surface":{"yes","no","unknown"},"person_visible":{"yes","no","uncertain"},"pose":POSES,"torso_orientation":{"upright","inclined","horizontal","unknown"},"torso_ground_contact":{"none","partial","broad","unknown"},"head_shoulders_above_hips":{"yes","no","unknown"},"support_surface":{"floor","chair","bed_sofa","unknown"},"explicit_work_evidence":{"yes","no","unknown"},"visual_quality":{"clear","insufficient"}}
EXPECTED_KEYS=set(ENUMS)|{"evidence"}
class AttributeContractError(ValueError): pass
def validate_attributes(v:Any)->dict[str,str]:
 if not isinstance(v,dict) or set(v)!=EXPECTED_KEYS: raise AttributeContractError('strict attribute keys mismatch')
 out={}
 for k,a in ENUMS.items():
  x=v.get(k)
  if not isinstance(x,str) or x not in a: raise AttributeContractError(f'invalid {k}: {x!r}')
  out[k]=x
 if not isinstance(v.get('evidence'),str) or not v['evidence'].strip(): raise AttributeContractError('evidence must be non-empty')
 out['evidence']=v['evidence'].strip(); return out
def map_attributes(raw:Any, detector_person_found=True):
 try:v=validate_attributes(raw)
 except AttributeContractError as e:return {'frame_decision':'RECHECK_VISUAL_UNCERTAIN','reason_code':f'ATTRIBUTE_CONTRACT_ERROR:{e}'}
 if v['any_person_ground_lying_on_nonrest_surface']=='yes': return {'frame_decision':'ALERT_GROUND_LYING','reason_code':'SCENE_ANY_PERSON_GROUND_LYING'}
 if v['any_person_ground_lying_on_nonrest_surface']=='unknown':
  if v['person_visible']!='yes' or v['visual_quality']!='clear': return {'frame_decision':'RECHECK_VISUAL_UNCERTAIN','reason_code':'SCENE_UNKNOWN_AND_CROP_UNRELIABLE'}
 if not detector_person_found:return {'frame_decision':'RECHECK_VISUAL_UNCERTAIN','reason_code':'NO_RELIABLE_PERSON_CROP'}
 if v['person_visible']!='yes' or v['visual_quality']!='clear':return {'frame_decision':'RECHECK_VISUAL_UNCERTAIN','reason_code':'VISIBILITY_OR_QUALITY_INSUFFICIENT'}
 if v['support_surface']=='bed_sofa':return {'frame_decision':'NO_ALERT_NORMAL_POSE','reason_code':'NORMAL_REST_SUPPORT'}
 if v['explicit_work_evidence']=='yes':return {'frame_decision':'NO_ALERT_NORMAL_POSE','reason_code':'EXPLICIT_WORK_CONTEXT'}
 pose=v['pose']; ori=v['torso_orientation']; contact=v['torso_ground_contact']; head=v['head_shoulders_above_hips']
 if pose=='floor_sitting':
  if head=='yes' and ori in {'upright','inclined'} and contact in {'none','partial'}:return {'frame_decision':'NO_ALERT_NORMAL_POSE','reason_code':'CLEAR_FLOOR_SITTING'}
  return {'frame_decision':'RECHECK_VISUAL_UNCERTAIN','reason_code':'FLOOR_SITTING_ATTRIBUTE_CONFLICT'}
 if pose in {'standing','walking','chair_sitting','kneeling','squat_crouch','bending'}:
  if ori=='horizontal' and contact=='broad':return {'frame_decision':'RECHECK_VISUAL_UNCERTAIN','reason_code':'NORMAL_POSE_ATTRIBUTE_CONFLICT'}
  return {'frame_decision':'NO_ALERT_NORMAL_POSE','reason_code':f'CLEAR_NORMAL_POSE:{pose}'}
 if pose in {'supine','side_lying','prone','curled_lying'} and v['support_surface']=='floor':return {'frame_decision':'ALERT_GROUND_LYING','reason_code':f'CLEAR_LYING_POSE:{pose}'}
 if pose in {'crawling','pushup_plank','other_near_ground'}:return {'frame_decision':'ATTENTION_NEAR_GROUND','reason_code':f'CLEAR_NEAR_GROUND_POSE:{pose}'}
 if ori=='horizontal' and contact=='broad' and v['support_surface']=='floor':return {'frame_decision':'ALERT_GROUND_LYING','reason_code':'HORIZONTAL_BROAD_TORSO_CONTACT'}
 return {'frame_decision':'RECHECK_VISUAL_UNCERTAIN','reason_code':'UNRESOLVED_ATTRIBUTES'}
