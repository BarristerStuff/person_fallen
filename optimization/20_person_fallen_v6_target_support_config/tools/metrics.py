"""Pure fail-closed V6 pilot/regression metrics; no I/O or inference."""
from collections import Counter
from statistics import mean
import math
ALERT='ALERT_GROUND_LYING';RECHECK='RECHECK_VISUAL_UNCERTAIN';NO_ALERT='NO_ALERT_NORMAL_POSE';ATTENTION='ATTENTION_NEAR_GROUND';DECISIONS={ALERT,RECHECK,NO_ALERT,ATTENTION}
PERSON_FIELDS={'person_id','bbox_1000','person_visible','pose','torso_orientation','torso_ground_contact','head_shoulders_above_hips','support_surface','body_support_configuration','explicit_work_evidence','visual_quality','evidence'}
def _pct(v,q):
 if not v:return None
 v=sorted(v);x=(len(v)-1)*q;a=math.floor(x);b=math.ceil(x);return v[a]+(v[b]-v[a])*(x-a)
def _index(rows,key,label,errors):
 d={}
 for i,r in enumerate(rows):
  if not isinstance(r,dict) or not r.get(key):errors.append(f'{label}[{i}] missing {key}');continue
  if r[key] in d:errors.append(f'{label} duplicate {key}:{r[key]}')
  d[r[key]]=r
 return d
def _valid_output(o):
 e=[];p=o.get('parsed')
 if not isinstance(p,dict) or set(p)!={'scene_coverage','people'}:return ['parsed exact keys']
 if p['scene_coverage'] not in {'complete','incomplete','unknown'}:e.append('coverage enum')
 if not isinstance(p['people'],list) or len(p['people'])>3:return e+['people array']
 ids=[]
 for i,x in enumerate(p['people']):
  if not isinstance(x,dict) or set(x)!=PERSON_FIELDS:e.append(f'person{i} keys');continue
  pid=x['person_id'];ids.append(pid)
  if type(pid) is not int or not 1<=pid<=3:e.append(f'person{i} id')
  b=x['bbox_1000']
  if b is not None and (not isinstance(b,list) or len(b)!=4 or any(type(z) is not int or not 0<=z<=1000 for z in b) or b[0]>=b[2] or b[1]>=b[3]):e.append(f'person{i} bbox')
  if not isinstance(x['evidence'],str) or not x['evidence'].strip():e.append(f'person{i} evidence')
 if len(ids)!=len(set(ids)):e.append('duplicate person_id')
 ds=o.get('person_decisions')
 if not isinstance(ds,list) or any(not isinstance(d,dict) or set(d)!={'person_id','decision','reason'} or d['decision'] not in DECISIONS for d in ds):e.append('person decisions')
 elif set(d['person_id'] for d in ds)!=set(ids):e.append('person decision coverage')
 if o.get('image_decision') not in DECISIONS:e.append('image decision')
 elif isinstance(ds,list) and any(isinstance(d,dict) and d.get('decision')==ALERT for d in ds)!=(o['image_decision']==ALERT):e.append('alert aggregation')
 for k in ['strict_json_ok','source_binding_ok']:
  if o.get(k) is not True:e.append(k)
 if o.get('http_status')!=200:e.append('http status')
 if type(o.get('latency_seconds')) not in (int,float) or o['latency_seconds']<0:e.append('latency')
 return e
def summarize(phase,manifest_rows,output_rows,request_records):
 if phase not in {'pilot','regression'}:raise ValueError('phase')
 m=list(manifest_rows);o=list(output_rows);q=list(request_records);errors=[]
 mm=_index(m,'item_id','manifest',errors);oo=_index(o,'item_id','output',errors);qq=_index(q,'request_id','request',errors)
 expected={r.get('request_id') for r in m};
 if set(mm)!=set(oo):errors.append('output identity incomplete/extra')
 if set(qq)!=expected:errors.append('request identity incomplete/extra')
 if any(r.get('state')!='completed' or r.get('completion_unknown') is True for r in q):errors.append('request incomplete/failed')
 for item,x in oo.items():
  errors.extend(f'{item}:{z}' for z in _valid_output(x))
  if item in mm and x.get('request_id')!=mm[item].get('request_id'):errors.append(f'{item}:request mismatch')
 valid=[oo[r['item_id']] for r in m if r.get('item_id') in oo and not _valid_output(oo[r['item_id']])]
 def subset(pred):return [oo[r['item_id']] for r in m if pred(r) and r.get('item_id') in oo]
 def counts(rows):
  c=Counter(x['image_decision'] for x in rows);return {d:c[d] for d in [ALERT,RECHECK,NO_ALERT,ATTENTION]}
 ground=subset(lambda r:r.get('evaluation_stratum')=='ground_lying');floor=subset(lambda r:r.get('taxonomy')=='floor_sitting');push=subset(lambda r:r.get('taxonomy')=='pushup_plank');crawl=subset(lambda r:r.get('taxonomy') in {'crawling_without_explicit_maintenance','crawling_quadruped_support'});multi=subset(lambda r:r.get('taxonomy')=='multi_person_one_lying')
 cg,cf,cp,cc,cm=map(counts,[ground,floor,push,crawl,multi]);people=[p for x in valid for p in x['parsed']['people']];lat=[float(x['latency_seconds']) for x in valid];tokens=[x['eval_count'] for x in valid if type(x.get('eval_count')) is int]
 taxonomy={}
 for t in sorted({r.get('taxonomy') for r in m}):taxonomy[t]={'count':sum(r.get('taxonomy')==t for r in m),'decisions':counts(subset(lambda r,t=t:r.get('taxonomy')==t))}
 gates={'row_count':len(m)==(156 if phase=='pilot' else 1),'protocol':not errors,'valid_responses':len(valid)==len(m)}
 if phase=='pilot':gates.update({'ground_count_60':len(ground)==60,'ground_alert_min57':cg[ALERT]>=57,'ground_coverage60':cg[ALERT]+cg[RECHECK]==60,'ground_noalert0':cg[NO_ALERT]==0,'ground_attention0':cg[ATTENTION]==0,'floor_count55':len(floor)==55,'floor_alert0':cf[ALERT]==0,'floor_recheck_max5':cf[RECHECK]<=5,'floor_noalert_min50':cf[NO_ALERT]>=50,'floor_attention0':cf[ATTENTION]==0,'push_count26':len(push)==26,'push_alert0':cp[ALERT]==0,'crawl_count15':len(crawl)==15,'crawl_alert0':cc[ALERT]==0,'multi_count5':len(multi)==5,'multi_alert5':cm[ALERT]==5,'multi_group1':len({r['group_id'] for r in m if r.get('taxonomy')=='multi_person_one_lying'})==1})
 else:
  target=m[0] if len(m)==1 else {};x=oo.get(target.get('item_id'),{});ps=x.get('parsed',{}).get('people',[]) if isinstance(x,dict) else [];ds=x.get('person_decisions',[]) if isinstance(x,dict) else []
  gates.update({'target_identity':target.get('operational_id')=='PFV4_SCREEN_0066' and target.get('item_id')=='P4D_PLAN::PF_P4D_POS_CURLED_G003_V05','coverage_complete':x.get('parsed',{}).get('scene_coverage')=='complete','two_people':len(ps)>=2 and len({p['person_id'] for p in ps})==len(ps),'person_alert':any(d.get('decision')==ALERT for d in ds if isinstance(d,dict)),'image_alert':x.get('image_decision')==ALERT})
 return {'phase':phase,'rows':len(m),'new_model_requests':len(q),'valid_responses':len(valid),'strict_JSON_success':len(valid)/len(m) if m else 0,'source_binding_success':len(valid)/len(m) if m else 0,'ground_lying_count':len(ground),'ground_lying_decisions':cg,'floor_sitting_count':len(floor),'floor_sitting_decisions':cf,'pushup_plank_count':len(push),'pushup_plank_decisions':cp,'crawling_count':len(crawl),'crawling_decisions':cc,'multi_person_count':len(multi),'multi_person_group_count':len({r['group_id'] for r in m if r.get('taxonomy')=='multi_person_one_lying'}),'multi_person_decisions':cm,'body_support_configuration_distribution':dict(Counter(p['body_support_configuration'] for p in people)),'people_count_distribution':dict(Counter(len(x['parsed']['people']) for x in valid)),'scene_coverage_distribution':dict(Counter(x['parsed']['scene_coverage'] for x in valid)),'bbox_null_count':sum(p['bbox_1000'] is None for p in people),'attribute_conflict_distribution':dict(Counter(d['reason'] for x in valid for d in x['person_decisions'] if any(z in d['reason'] for z in ['CONFLICT','UNRESOLVED','UNRELIABLE']))),'taxonomy':taxonomy,'latency':{'p50':_pct(lat,.5),'p95':_pct(lat,.95),'p99':_pct(lat,.99),'count':len(lat)},'eval_count_statistics':{'count':len(tokens),'min':min(tokens) if tokens else None,'max':max(tokens) if tokens else None,'mean':mean(tokens) if tokens else None},'protocol_errors':errors,'gate_checks':gates,'gate':'PASS' if all(gates.values()) else 'FAIL','OBJECT_LOCALIZATION_ACCURACY':'UNVERIFIED'}
