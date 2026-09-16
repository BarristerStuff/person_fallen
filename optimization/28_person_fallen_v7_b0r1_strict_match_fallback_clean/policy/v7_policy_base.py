import re
LY={'supine','side_lying','prone','curled_lying','other_near_ground'}
AUX={'forearms_feet_supported','hands_feet_supported','hands_knees_supported'}
def five(x):return x.get('pose') in LY and x.get('support_surface')=='floor' and x.get('torso_orientation')=='horizontal' and x.get('torso_ground_contact')=='broad' and x.get('body_support_configuration')=='torso_ground_supported'
def person(geom,x,background=False):
 if geom=='GEOM_UPRIGHT': return 'NO_ALERT_NORMAL_POSE'
 if x.get('visual_quality')=='insufficient':return 'RECHECK_VISUAL_UNCERTAIN'
 if re.search(r'forearm|hands and feet|hands and knees|on (his|her|their) knees|plank|push-up|crawl',x.get('evidence',''),re.I) and x.get('body_support_configuration')=='torso_ground_supported':return 'RECHECK_VISUAL_UNCERTAIN'
 if five(x):return 'ALERT_GROUND_LYING'
 if x.get('pose') in LY:return 'RECHECK_VISUAL_UNCERTAIN'
 if x.get('body_support_configuration') in AUX or x.get('pose') in {'crawling','plank','push_up'}:return 'ATTENTION_NEAR_GROUND'
 return 'NO_ALERT_NORMAL_POSE'
def aggregate(ds):
 if any(x=='ALERT_GROUND_LYING' for x in ds):return 'ALERT_GROUND_LYING'
 if any(x=='RECHECK_VISUAL_UNCERTAIN' for x in ds):return 'RECHECK_VISUAL_UNCERTAIN'
 if any(x=='ATTENTION_NEAR_GROUND' for x in ds):return 'ATTENTION_NEAR_GROUND'
 return 'NO_ALERT_NORMAL_POSE'
