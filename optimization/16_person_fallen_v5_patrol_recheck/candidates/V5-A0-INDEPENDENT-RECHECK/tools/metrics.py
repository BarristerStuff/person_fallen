"""Correct V4 operational strata, complete output only; RECHECK is not ALERT."""
from collections import Counter
from contracts import *
def metrics(source,output,request_records,phase):
 validate_manifest(phase,source)
 src=by_id(source);pred=by_id(output)
 if set(src)!=set(pred):raise ValueError('Missing/extra prediction')
 expected={r['request_id'] for r in source if r['secondary_required']}
 req={r['request_id']:r for r in request_records}
 if len(req)!=len(request_records) or set(req)!=expected:raise ValueError('Missing/duplicate request output')
 for r in source:
  o=pred[r['item_id']]
  if o['primary_decision']!=r['primary_decision']:raise ValueError('Primary mutation')
  if o['v5_stratum']!=r['v5_stratum'] or o['taxonomy']!=r['taxonomy']:raise ValueError('GT mutation')
  if not o['primary_cache_binding_ok']:raise ValueError('Invalid primary cache')
  if r['secondary_required']:
   rec=req[r['request_id']]
   if not rec['strict_json_ok'] or rec['state']!='completed' or rec['http_status']!=200:raise ValueError('Protocol incomplete; no metric gate')
   if o['request_id']!=rec['request_id'] or o['final_decision']!=rec['final_decision']:raise ValueError('Request/output mismatch')
 primary_alert={r['item_id'] for r in source if r['primary_decision']==ALERT}
 final_alert={r['item_id'] for r in output if r['final_decision']==ALERT}
 sub={}
 for name in ['ground_lying','normal_negative','auxiliary_attention','visual_uncertain','floor_sitting']:
  rr=[pred[k] for k,v in src.items() if (v['taxonomy']=='floor_sitting' if name=='floor_sitting' else v['v5_stratum']==name)]
  c=Counter(r['final_decision'] for r in rr);n=len(rr)
  sub[name]={'count':n,'decision_distribution':dict(c),'alert_count':c[ALERT],'recheck_count':c[RECHECK], 'alert_rate':c[ALERT]/n if n else None,'recheck_rate':c[RECHECK]/n if n else None,'alert_recheck_coverage':(c[ALERT]+c[RECHECK])/n if n else None}
 g,n,f=(sub[k] for k in ['ground_lying','normal_negative','floor_sitting'])
 if f['count']!=(55 if phase=='dev' else 25):raise ValueError('Floor-sitting denominator invalid')
 checks={'ground_lying_immediate_alert_recall':g['alert_rate']>=.95,'ground_lying_alert_recheck_coverage':g['alert_recheck_coverage']==1.,'floor_sitting_alert_fpr':f['alert_rate']==0.,'determinate_negative_alert_fpr':n['alert_rate']==0.,'determinate_negative_total_recheck_rate':n['recheck_rate']<=.10,'secondary_strict_json_success':len(req)==len(expected),'primary_cache_binding_success':True,'alert_set_unchanged':primary_alert==final_alert}
 target=None
 if phase=='regression':
  target=next(o for o in output if o['operational_id']=='PFV4_SCREEN_0066')
  checks['PFV4_SCREEN_0066_final_recheck']=target['final_decision']==RECHECK
 latency=[r['latency_seconds'] for r in request_records]
 return {'status':'COMPLETE','phase':phase,'EVALUATION_MODE':'CACHED_PRIMARY_PLUS_NEW_SECONDARY','PRIMARY_SOURCE':'FROZEN_V4_CACHE','SECONDARY_CANDIDATE':'V5-A0-INDEPENDENT-RECHECK','rows':len(output),'primary_cached_rows':len(output),'secondary_requests':len(req),'secondary_valid_responses':len(req),'ground_lying_count':g['count'],'immediate_ALERT_count':g['alert_count'],'immediate_ALERT_recall':g['alert_rate'],'ALERT_RECHECK_coverage':g['alert_recheck_coverage'],'floor_sitting_count':f['count'],'floor_sitting_ALERT_FPR':f['alert_rate'],'floor_sitting_RECHECK_rate':f['recheck_rate'],'determinate_negative_count':n['count'],'determinate_negative_ALERT_FPR':n['alert_rate'],'determinate_negative_total_RECHECK_count':n['recheck_count'],'determinate_negative_total_RECHECK_rate':n['recheck_rate'],'secondary_strict_JSON_success':len(req)/len(expected),'primary_cache_binding_success':1.,'final_ALERT_set_equals_primary_ALERT_set':primary_alert==final_alert,'scene_review_distribution':dict(Counter(r['scene_review'] for r in request_records)),'auxiliary_decision_distribution':sub['auxiliary_attention']['decision_distribution'],'uncertain_decision_distribution':sub['visual_uncertain']['decision_distribution'],'secondary_latency_p50':percentile(latency,.5),'secondary_latency_p95':percentile(latency,.95),'strata':sub,'PFV4_SCREEN_0066':target,'gate_checks':checks,'gate':'PASS' if all(checks.values()) else 'FAIL','screen_role':'CONSUMED_SCREEN_DEVELOPMENT_REGRESSION' if phase=='regression' else 'DEVELOPMENT','ROBOT_REOBSERVATION_VALIDATED':False}
