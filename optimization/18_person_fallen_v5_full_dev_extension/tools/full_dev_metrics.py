from collections import Counter
import statistics,math
ALERT='ALERT_GROUND_LYING'; RECHECK='RECHECK_VISUAL_UNCERTAIN'; NORMAL='NO_ALERT_NORMAL_POSE'; ATTENTION='ATTENTION_NEAR_GROUND'
def percentile(v,q):
 if not v:return None
 v=sorted(v);x=(len(v)-1)*q;a=math.floor(x);b=math.ceil(x);return v[a]+(v[b]-v[a])*(x-a)
def summarize(rows,outputs,requests,complete=True):
 src={r['item_id']:r for r in rows}; out={r['item_id']:r for r in outputs}; errs=[]
 if len(src)!=len(rows) or len(out)!=len(outputs) or set(src)!=set(out):errs.append('row identity incomplete/duplicate')
 for r in rows:
  o=out.get(r['item_id']);
  if not o:continue
  if o.get('item_id')!=r['item_id'] or o.get('source_binding_ok') is not True or o.get('strict_json_ok') is not True:errs.append('binding/protocol failure:'+r['item_id'])
  if o.get('v5_stratum')!=r['v5_stratum']:errs.append('stratum mismatch:'+r['item_id'])
 ground=[r for r in rows if r['v5_stratum']=='ground_lying'];normal=[r for r in rows if r['v5_stratum']=='normal_negative'];floor=[r for r in normal if r['taxonomy']=='floor_sitting'];aux=[r for r in rows if r['v5_stratum']=='auxiliary_attention'];unc=[r for r in rows if r['v5_stratum']=='visual_uncertain']
 def counts(rr):return Counter(out[r['item_id']]['image_decision'] for r in rr if r['item_id'] in out)
 cg,cn,cf,ca,cu=map(counts,[ground,normal,floor,aux,unc]);
 lat=[out[r['item_id']]['latency_seconds'] for r in rows if r['item_id'] in out and out[r['item_id']].get('inference_source')=='NEW_MODEL_REQUEST']
 checks={'complete_rows':complete and len(rows)==436 and len(out)==436,'protocol_complete':not errs and len(requests)==len([o for o in outputs if o.get('inference_source')=='NEW_MODEL_REQUEST']),'ground_alert_recall':cg[ALERT]/145>=.95,'ground_coverage':(cg[ALERT]+cg[RECHECK])/145==1.,'normal_alert_zero':cn[ALERT]==0,'normal_recheck_rate':cn[RECHECK]/230<=.1,'floor_alert_zero':cf[ALERT]==0,'floor_recheck_max':cf[RECHECK]<=5,'floor_no_alert_min':cf[NORMAL]>=50}
 return {'status':'COMPLETE' if complete else 'EARLY_STOP_PARTIAL','rows':len(rows),'V5_B0_REUSED_RESULTS':115,'new_requests_claimed':len(requests),'new_requests_completed':sum(1 for r in requests if r.get('state')=='completed'),'new_requests_unknown':sum(1 for r in requests if r.get('completion_unknown')),'new_requests_not_started':321-len(requests),'completed_full_dev':complete,'ground_lying':{'count':145,'ALERT':cg[ALERT],'RECHECK':cg[RECHECK],'NO_ALERT':cg[NORMAL],'ATTENTION':cg[ATTENTION],'ALERT_recall':cg[ALERT]/145,'ALERT_RECHECK_coverage':(cg[ALERT]+cg[RECHECK])/145},'normal_negative':{'count':230,'ALERT':cn[ALERT],'RECHECK':cn[RECHECK],'NO_ALERT':cn[NORMAL],'ATTENTION':cn[ATTENTION],'ALERT_FPR':cn[ALERT]/230,'total_RECHECK_rate':cn[RECHECK]/230},'floor_sitting':{'count':55,'ALERT':cf[ALERT],'RECHECK':cf[RECHECK],'NO_ALERT':cf[NORMAL],'ATTENTION':cf[ATTENTION]},'auxiliary_decision_distribution':dict(ca),'visual_uncertain_decision_distribution':dict(cu),'by_taxonomy':{t:dict(counts([r for r in rows if r['taxonomy']==t])) for t in sorted({r['taxonomy'] for r in rows})},'people_count_distribution':dict(Counter(len(out[r['item_id']]['parsed']['people']) for r in rows if r['item_id'] in out)),'scene_coverage_distribution':dict(Counter(out[r['item_id']]['parsed']['scene_coverage'] for r in rows if r['item_id'] in out)),'bbox_null_count':sum(1 for r in rows if r['item_id'] in out for p in out[r['item_id']]['parsed']['people'] if p['bbox_1000'] is None),'new_request_latency_p50':percentile(lat,.5),'new_request_latency_p95':percentile(lat,.95),'new_request_output_token_statistics':{'count':sum(1 for r in requests if r.get('eval_count') is not None),'min':min((r['eval_count'] for r in requests if r.get('eval_count') is not None),default=None),'max':max((r['eval_count'] for r in requests if r.get('eval_count') is not None),default=None),'mean':statistics.mean([r['eval_count'] for r in requests if r.get('eval_count') is not None]) if any(r.get('eval_count') is not None for r in requests) else None},'gate_checks':checks,'FULL_DEV_GATE':'PASS' if all(checks.values()) else ('NOT_EVALUATED' if not complete else 'FAIL'),'validation_errors':errs}
def early_stop(rows,outputs):
 m=summarize(rows,outputs,[],complete=False);g=m['ground_lying'];n=m['normal_negative'];
 if n['ALERT']>0:return 'A_DETERMINATE_NEGATIVE_ALERT'
 if n['RECHECK']>=24:return 'B_NORMAL_NEGATIVE_RECHECK_REACHED_24'
 if g['NO_ALERT']+g['ATTENTION']>0:return 'C_GROUND_NO_ALERT_OR_ATTENTION'
 if 145-g['ALERT']>=8:return 'D_GROUND_NON_ALERT_REACHED_8'
 return None
