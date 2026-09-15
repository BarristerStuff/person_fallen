"""Prepare, execute, and summarize the V5-B0 remaining-47 diagnostic."""
from __future__ import annotations
import argparse, base64, csv, hashlib, importlib.util, json, math, os, statistics, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT.parent
V13=BASE/'13_person_fallen_v4_pose_attributes'; V17=BASE/'17_person_fallen_v5_target_attributes'; V19=BASE/'19_person_fallen_v5_b0_full_dev_recovery_r1'
sys.path.insert(0,str(ROOT/'protocol')); from spec import REQUEST_BUDGET,EXPECTED_REUSED,EXPECTED_FULL,ALLOWED_PHASE,REQUEST_PREFIX,MODEL
FULL_CSV=V13/'manifests/v4_full_dev_crop_manifest.csv'; OLD_OUTPUT=V19/'eval/full_dev/output.jsonl'
PROMPT=V17/'prompt/target_attributes.txt'; SCHEMA=V17/'schema/target_attributes.json'; POLICY=V17/'policy/target_policy.py'; CONTRACTS=V17/'tools/contracts.py'
MANIFEST=ROOT/'manifests/remaining47.json'; REUSE=ROOT/'manifests/reused389.json'; FREEZE=ROOT/'freeze/EXECUTION_FREEZE.json'; RUN=ROOT/'eval/remaining47'; PREFLIGHT=ROOT/'reports/ollama_preflight.json'
DECISIONS=('ALERT_GROUND_LYING','RECHECK_VISUAL_UNCERTAIN','NO_ALERT_NORMAL_POSE','ATTENTION_NEAR_GROUND')

def utc(): return datetime.now(timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()
def read_json(p): return json.loads(Path(p).read_text())
def read_jsonl(p):
 out=[]
 for n,line in enumerate(Path(p).read_text().splitlines(),1):
  if not line.strip(): raise ValueError(f'blank JSONL line {p}:{n}')
  v=json.loads(line)
  if not isinstance(v,dict): raise ValueError(f'non-object JSONL {p}:{n}')
  out.append(v)
 return out
def write_x(p,data):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
 mode='xb' if isinstance(data,bytes) else 'x'
 with p.open(mode,encoding=None if isinstance(data,bytes) else 'utf-8') as f:
  f.write(data); f.flush(); os.fsync(f.fileno())
def write_json_x(p,v): write_x(p,json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
def replace_json(p,v):
 tmp=Path(str(p)+'.tmp'); tmp.write_text(json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+'\n'); os.replace(tmp,p)
def append_jsonl(p,v):
 with Path(p).open('a') as f: f.write(json.dumps(v,ensure_ascii=False,allow_nan=False)+'\n'); f.flush(); os.fsync(f.fileno())
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
CONTRACT=module('v5b_contract_diag',CONTRACTS); POLICY_MOD=module('v5b_policy_diag',POLICY)

def stratum(row):
 t=row['taxonomy']
 if t in {'pushup_plank','crawling_without_explicit_maintenance','crawling_quadruped_support'}: return 'auxiliary_attention'
 if row['expected_v4_outcome']=='RECHECK_VISUAL_UNCERTAIN': return 'visual_uncertain'
 if row['ground_truth']=='positive': return 'ground_lying'
 return 'normal_negative'

def prepare():
 if MANIFEST.exists() or REUSE.exists(): raise ValueError('prepared files already exist')
 with FULL_CSV.open(newline='') as f: full=list(csv.DictReader(f))
 old=read_jsonl(OLD_OUTPUT); old_ids=[r['item_id'] for r in old]; full_ids=[r['item_id'] for r in full]
 if len(old)!=EXPECTED_REUSED or len(set(old_ids))!=EXPECTED_REUSED: raise ValueError('reused results not 389 unique')
 if len(full)!=EXPECTED_FULL or len(set(full_ids))!=EXPECTED_FULL or not set(old_ids)<=set(full_ids): raise ValueError('full DEV identity mismatch')
 remaining=[r for r in full if r['item_id'] not in set(old_ids)]
 if len(remaining)!=REQUEST_BUDGET: raise ValueError('mechanical difference is not 47')
 for i,r in enumerate(remaining,1):
  r=dict(r); r.update({'phase':ALLOWED_PHASE,'request_id':f'{REQUEST_PREFIX}{i:04d}','evaluation_stratum':stratum(r),'result_source':'NEW_DIAGNOSTIC_INFERENCE'}); remaining[i-1]=r
 counts=Counter(r['evaluation_stratum'] for r in remaining)
 if counts!=Counter(auxiliary_attention=27,visual_uncertain=20): raise ValueError(f'remaining strata mismatch {counts}')
 # Historical request state is checked only in the bounded V5-B0 execution roots.
 hits=[]
 for root in (V17/'eval',BASE/'18_person_fallen_v5_full_dev_extension/eval',V19/'eval'):
  if not root.exists(): continue
  for p in root.rglob('*'):
   if not p.is_file() or (p.name not in {'claimed.json','completed.json','failure.json'} and p.suffix!='.jsonl'): continue
   try: vals=read_jsonl(p) if p.suffix=='.jsonl' else [read_json(p)]
   except Exception: continue
   hits.extend((str(p),v.get('item_id')) for v in vals if isinstance(v,dict) and v.get('item_id') in {x['item_id'] for x in remaining})
 if hits: raise ValueError(f'remaining items have prior request state: {hits[:3]}')
 write_json_x(REUSE,old); write_json_x(MANIFEST,remaining)
 audit={'status':'PASS','task_authorization_date':'2026-09-10','actual_preparation_time':utc(),'full_rows':436,'reused_rows':389,'remaining_rows':47,'remaining_strata':dict(counts),'reused_unique':len(set(old_ids)),'disjoint':not(set(old_ids)&{r['item_id'] for r in remaining}),'union_equals_full':set(old_ids)|{r['item_id'] for r in remaining}==set(full_ids),'prior_request_state_hits':0,'known_regression_in_dev': 'P4D_PLAN::PF_P4D_POS_CURLED_G003_V05' in set(full_ids),'hash_matching_is_not_pixel_semantic_review':True}
 write_json_x(ROOT/'reports/source_and_reuse_audit.json',audit); return audit

def verify_reused(rows=None):
 rows=rows or read_json(REUSE); seen=set(); evidence=[]
 pilot_source={(r['item_id'],r['request_id']):r for r in read_jsonl(V17/'eval/pilot/output.jsonl')}
 recovery_source={(r['item_id'],r['request_id']):r for r in read_jsonl(OLD_OUTPUT) if r.get('raw_response_path')}
 for r in rows:
  item=r.get('item_id'); rid=r.get('request_id'); source=(pilot_source if r.get('result_source')=='REUSE_V5_B0_PILOT' else recovery_source).get((item,rid),{})
  raw=Path(source.get('raw_response_path',''))
  if not item or item in seen or not raw.is_file() or sha(raw)!=source.get('raw_response_sha256'): raise ValueError(f'reuse evidence mismatch {item}')
  seen.add(item); outer,parsed=CONTRACT.parse_response(raw.read_bytes())
  if parsed!=r.get('parsed') or POLICY_MOD.evaluate(parsed)!={k:r.get(k) for k in ('person_decisions','image_decision','image_reason')}: raise ValueError(f'reuse replay mismatch {item}')
  rd=raw.parent
  for name in ('claimed.json','transport.json','completed.json'):
   if not (rd/name).is_file(): raise ValueError(f'reuse ledger missing {item} {name}')
  evidence.append({'item_id':item,'request_id':rid,'raw_path':str(raw),'raw_sha256':sha(raw),'claimed_sha256':sha(rd/'claimed.json'),'transport_sha256':sha(rd/'transport.json'),'completed_sha256':sha(rd/'completed.json')})
 if len(seen)!=389: raise ValueError('reuse replay count mismatch')
 return evidence

def create_freeze():
 if FREEZE.exists(): raise ValueError('freeze already exists')
 if read_json(PREFLIGHT).get('status')!='PASS': raise ValueError('successful Ollama GET preflight required')
 rows=read_json(MANIFEST); evidence=verify_reused(); bindings={}
 for p in (PROMPT,SCHEMA,POLICY,CONTRACTS,Path(__file__),ROOT/'protocol/spec.py',ROOT/'protocol/execution_plan.json',ROOT/'tests/test_diagnostic.py',MANIFEST,REUSE,OLD_OUTPUT,PREFLIGHT,V17/'freeze/EXECUTION_FREEZE.json',V19/'freeze/RECOVERY_FREEZE.json'):
  bindings[str(p)]=sha(p)
 for r in rows:
  for key in ('image_path','prompt_path','full_view_path','crop_view_path'): bindings[r[key]]=sha(r[key])
 for e in evidence:
  raw=Path(e['raw_path']);
  for name in ('response.raw','claimed.json','transport.json','completed.json'): bindings[str(raw.parent/name)]=sha(raw.parent/name)
 freeze={'status':'IMMUTABLE_EXECUTION_FREEZE','candidate':'V5-B0-TARGET-ATTRIBUTES','execution':'REMAINING47_DIAGNOSTIC','purpose':'COMPLETE_DEVELOPMENT_RISK_PROFILE','original_candidate_rejection_remains':True,'task_authorization_date':'2026-09-10','freeze_created_at':utc(),'request_budget':REQUEST_BUDGET,'manifest_sha256':sha(MANIFEST),'reused_results_sha256':sha(REUSE),'model':MODEL,'bindings':dict(sorted(bindings.items())),'output_contract':{'protocol_error':'stop_no_retry','business_failure':'continue_diagnostic','completion_requires':47,'full_report_requires_unique_rows':436},'val_requests':0,'holdout_requests':0,'v6_requests':0}
 write_json_x(FREEZE,freeze); write_x(ROOT/'freeze/EXECUTION_FREEZE.sha256',sha(FREEZE)+'\n')
 report={'status':'PASS','freeze_sha256':sha(FREEZE),'binding_count':len(bindings),'reused_raw_ledger_rows':len(evidence),'actual_manifest':str(MANIFEST),'actual_manifest_sha256':sha(MANIFEST),'semantic_sha256':{'prompt':sha(PROMPT),'schema':sha(SCHEMA),'policy':sha(POLICY),'contracts':sha(CONTRACTS)}}; write_json_x(ROOT/'reports/execution_freeze_inventory.json',report); return report

def preflight():
 if PREFLIGHT.exists(): raise ValueError('preflight record already exists')
 class NoRedirect(request.HTTPRedirectHandler):
  def redirect_request(self,*a,**k): raise error.HTTPError(a[0].full_url,599,'redirect forbidden',None,None)
 opener=request.build_opener(request.ProxyHandler({}),NoRedirect())
 def get(path):
  with opener.open(MODEL['endpoint']+path,timeout=10) as rsp:
   if rsp.status!=200: raise ValueError(f'GET {path} HTTP {rsp.status}')
   return json.loads(rsp.read())
 tags=get('/api/tags'); version=get('/api/version'); ps=get('/api/ps')
 matches=[m for m in tags.get('models',[]) if m.get('name')==MODEL['name'] and m.get('digest')==MODEL['digest']]
 if len(matches)!=1 or version.get('version')!=MODEL['ollama_version']: raise ValueError('Ollama model digest/version mismatch')
 report={'status':'PASS','checked_at':utc(),'endpoint':MODEL['endpoint'],'model':MODEL['name'],'digest':MODEL['digest'],'version':version,'tags_match_count':len(matches),'tags':tags,'ps_snapshot':ps,'proxy_disabled':True,'redirects_rejected':True,'generate_requests':0}
 write_json_x(PREFLIGHT,report); return report

def build_payload(row):
 images=[base64.b64encode(Path(row['full_view_path']).read_bytes()).decode()]
 if row['person_detected']=='true': images.append(base64.b64encode(Path(row['crop_view_path']).read_bytes()).decode())
 payload={'model':MODEL['name'],'prompt':PROMPT.read_text(),'images':images,'format':read_json(SCHEMA),'stream':False,'think':False,'options':{'temperature':0,'num_ctx':8192,'num_predict':768}}
 return json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
def verify_input(r):
 if r['phase']!=ALLOWED_PHASE or r['v3_split']!='V3_DEV': raise ValueError('unauthorized phase/split')
 for pk,hk in [('image_path','image_sha256'),('prompt_path','prompt_sha256'),('full_view_path','full_view_sha256'),('crop_view_path','crop_view_sha256')]:
  if sha(r[pk])!=r[hk]: raise ValueError(f'input SHA mismatch {r["item_id"]} {pk}')

def call(payload):
 class NoRedirect(request.HTTPRedirectHandler):
  def redirect_request(self,*a,**k): raise error.HTTPError(a[0].full_url,599,'redirect forbidden',None,None)
 opener=request.build_opener(request.ProxyHandler({}),NoRedirect()); req=request.Request(MODEL['endpoint']+'/api/generate',data=payload,headers={'Content-Type':'application/json'},method='POST'); start=time.monotonic()
 try:
  with opener.open(req,timeout=MODEL['timeout_seconds']) as rsp: return {'http_status':rsp.status,'raw':rsp.read(),'latency_seconds':time.monotonic()-start,'completion_unknown':False,'error':None}
 except error.HTTPError as e: return {'http_status':e.code,'raw':e.read() if e.fp else b'','latency_seconds':time.monotonic()-start,'completion_unknown':False,'error':repr(e)}
 except Exception as e: return {'http_status':None,'raw':b'','latency_seconds':time.monotonic()-start,'completion_unknown':True,'error':repr(e)}

def verify_freeze():
 f=read_json(FREEZE)
 if f['request_budget']!=REQUEST_BUDGET or f['manifest_sha256']!=sha(MANIFEST) or f['reused_results_sha256']!=sha(REUSE): raise ValueError('freeze core mismatch')
 for p,h in f['bindings'].items():
  if sha(p)!=h: raise ValueError(f'freeze binding mismatch {p}')
 return f

def execute(transport=None,run_dir=RUN,enforce_freeze=True):
 rows=read_json(MANIFEST); reused=read_json(REUSE)
 request_ids=[r.get('request_id') for r in rows]; item_ids=[r.get('item_id') for r in rows]
 if len(rows)!=47 or len(reused)!=389 or len(set(request_ids))!=47 or len(set(item_ids))!=47: raise ValueError('execution inputs incomplete or duplicate')
 if run_dir.exists() and any(run_dir.iterdir()): raise ValueError('existing execution; no resume/retry')
 run_dir.mkdir(parents=True,exist_ok=True); write_json_x(run_dir/'STARTED.lock',{'phase':ALLOWED_PHASE,'started':utc()}); (run_dir/'requests').mkdir()
 if enforce_freeze: verify_freeze()
 outputs=[]; attempts=[]; events=run_dir/'request_events.jsonl'; output=run_dir/'output.jsonl'; transport=transport or (lambda payload,rid,row:call(payload))
 try:
  for i,row in enumerate(rows,1):
   verify_input(row); payload=build_payload(row); rid=row['request_id']; rd=run_dir/'requests'/rid; rd.mkdir()
   claim={'state':'claimed','phase':ALLOWED_PHASE,'request_id':rid,'item_id':row['item_id'],'payload_sha256':hashlib.sha256(payload).hexdigest(),'full_view_sha256':row['full_view_sha256'],'crop_view_sha256':row['crop_view_sha256'],'prompt_sha256':sha(PROMPT),'schema_sha256':sha(SCHEMA),'policy_sha256':sha(POLICY),'claimed_timestamp':utc()}
   write_json_x(rd/'claimed.json',claim); append_jsonl(events,claim)
   result=transport(payload,rid,row); raw=result.get('raw',b''); raw=raw if isinstance(raw,bytes) else bytes(raw); write_x(rd/'response.raw',raw)
   received={**claim,'state':'received','http_status':result.get('http_status'),'completion_unknown':result.get('completion_unknown'),'transport_error':result.get('error'),'latency_seconds':result.get('latency_seconds'),'raw_response_sha256':sha(rd/'response.raw'),'received_timestamp':utc()}; write_json_x(rd/'transport.json',received); attempts.append(received)
   if received['completion_unknown'] or received['http_status']!=200:
    failure={**received,'state':'protocol_failure','failure_code':'COMPLETION_UNKNOWN' if received['completion_unknown'] else 'HTTP_FAILURE','failure_timestamp':utc()}; write_json_x(rd/'failure.json',failure); append_jsonl(events,failure); raise RuntimeError(failure['failure_code'])
   try: outer,parsed=CONTRACT.parse_response(raw)
   except Exception as exc:
    failure={**received,'state':'protocol_failure','failure_code':'STRICT_JSON_OR_SCHEMA_FAILURE','parse_error':str(exc),'failure_timestamp':utc()}; write_json_x(rd/'failure.json',failure); append_jsonl(events,failure); raise
   decision=POLICY_MOD.evaluate(parsed)
   done={**received,'state':'completed','strict_json_ok':True,'source_binding_ok':True,'done':outer['done'],'done_reason':outer['done_reason'],'eval_count':outer.get('eval_count'),'parsed':parsed,**decision,'taxonomy':row['taxonomy'],'group_id':row['group_id'],'source_split':row['source_split'],'v3_split':row['v3_split'],'ground_truth':row['ground_truth'],'expected_v4_outcome':row['expected_v4_outcome'],'evaluation_stratum':row['evaluation_stratum'],'result_source':'NEW_DIAGNOSTIC_INFERENCE','completed_timestamp':utc()}
   write_json_x(rd/'completed.json',done); append_jsonl(events,done); append_jsonl(output,done); outputs.append(done)
  summary=summarize(reused+outputs,outputs); replace_json(run_dir/'summary.json',summary)
  inventory=evidence_inventory(run_dir); replace_json(run_dir/'evidence_inventory.json',inventory)
  lock={'status':'COMPLETE_DIAGNOSTIC','output_sha256':sha(output),'events_sha256':sha(events),'summary_sha256':sha(run_dir/'summary.json'),'evidence_inventory_sha256':sha(run_dir/'evidence_inventory.json'),'completed':47,'created':utc()}; write_json_x(run_dir/'COMPLETION_LOCK.json',lock); return summary
 except Exception as e:
  status={'status':'V5_B0_REMAINING47_PROTOCOL_INCOMPLETE_NO_RETRY','error':repr(e),'claimed':len(attempts)+(1 if not attempts and list((run_dir/'requests').iterdir()) else 0),'completed':len(outputs),'unknown':sum(x.get('completion_unknown') is True for x in attempts),'not_started':47-len(list((run_dir/'requests').iterdir())),'timestamp':utc()}; replace_json(run_dir/'PROTOCOL_INCOMPLETE.json',status); raise

def evidence_inventory(run_dir):
 rows=[]
 for rd in sorted((run_dir/'requests').iterdir()):
  rows.append({'request_id':rd.name,**{n:sha(rd/n) for n in ('claimed.json','response.raw','transport.json','completed.json')}})
 return {'requests':rows,'count':len(rows)}
def dist(rows): return {d:sum(r['image_decision']==d for r in rows) for d in DECISIONS}
def pct(v,q):
 if not v:return None
 v=sorted(v); x=(len(v)-1)*q; a=math.floor(x); b=math.ceil(x); return v[a]+(v[b]-v[a])*(x-a)
def summarize(all_rows,new_rows):
 if len(all_rows)!=436 or len({r['item_id'] for r in all_rows})!=436: raise ValueError('cannot create complete report without 436 unique rows')
 by=lambda pred:[r for r in all_rows if pred(r)]
 groups={'GROUND_LYING_DECISIONS':by(lambda r:r['evaluation_stratum']=='ground_lying'),'NORMAL_NEGATIVE_DECISIONS':by(lambda r:r['evaluation_stratum']=='normal_negative'),'FLOOR_SITTING_DECISIONS':by(lambda r:r['taxonomy']=='floor_sitting'),'PUSHUP_PLANK_DECISIONS':by(lambda r:r['taxonomy']=='pushup_plank'),'CRAWLING_DECISIONS':by(lambda r:r['taxonomy'] in {'crawling_without_explicit_maintenance','crawling_quadruped_support'}),'VISUAL_UNCERTAIN_DECISIONS':by(lambda r:r['evaluation_stratum']=='visual_uncertain')}
 result={k:dist(v) for k,v in groups.items()}; aux=by(lambda r:r['evaluation_stratum']=='auxiliary_attention'); g=groups['GROUND_LYING_DECISIONS']; n=groups['NORMAL_NEGATIVE_DECISIONS']; f=groups['FLOOR_SITTING_DECISIONS']
 checks={'ground_alert_min':dist(g)[DECISIONS[0]]>=138,'ground_coverage':dist(g)[DECISIONS[0]]+dist(g)[DECISIONS[1]]==145,'normal_alert_zero':dist(n)[DECISIONS[0]]==0,'normal_recheck_max':dist(n)[DECISIONS[1]]<=23,'floor_alert_zero':dist(f)[DECISIONS[0]]==0,'floor_recheck_max':dist(f)[DECISIONS[1]]<=5,'floor_noalert_min':dist(f)[DECISIONS[2]]>=50,'auxiliary_alert_zero':dist(aux)[DECISIONS[0]]==0}
 lat=[r['latency_seconds'] for r in new_rows]; ev=[r['eval_count'] for r in new_rows if type(r.get('eval_count')) is int]; people=Counter(len(r['parsed']['people']) for r in all_rows); cov=Counter(r['parsed']['scene_coverage'] for r in all_rows)
 result.update({'CANDIDATE':'V5-B0-TARGET-ATTRIBUTES','EXECUTION':'REMAINING47_DIAGNOSTIC','ORIGINAL_REJECTION_REMAINS':True,'REUSED_RESULTS':389,'NEW_REQUESTS_CLAIMED':47,'NEW_REQUESTS_COMPLETED':47,'NEW_REQUESTS_UNKNOWN':0,'NEW_REQUESTS_NOT_STARTED':0,'FULL_DEV_OBSERVED_ROWS':436,'FULL_DEV_COMPLETE':True,'gate_checks':checks,'ORIGINAL_GATE_RESULT':'FAIL','new47_latency':{'p50':pct(lat,.5),'p95':pct(lat,.95),'p99':pct(lat,.99)},'new47_eval_count':{'count':len(ev),'min':min(ev) if ev else None,'max':max(ev) if ev else None,'mean':statistics.mean(ev) if ev else None},'people_count_distribution':dict(people),'scene_coverage_distribution':dict(cov),'bbox_null_count':sum(p['bbox_1000'] is None for r in all_rows for p in r['parsed']['people']),'by_taxonomy':{t:dist(by(lambda r,t=t:r['taxonomy']==t)) for t in sorted({r['taxonomy'] for r in all_rows})},'NEW_MODEL_REQUESTS_MAX':47,'VAL_REQUESTS':0,'VAL_IMAGES_READ':0,'HOLDOUT_REQUESTS':0,'HOLDOUT_CONSUMED':False,'V6_REQUESTS':0,'CODE_COMMITTED':False,'CURRENT_WINNER':'NONE','PRODUCTION_INTEGRATION_READY':False,'FINAL_STATUS':'V5_B0_FULL_DEV_DIAGNOSTIC_COMPLETE_REJECTED_CANDIDATE_RETAINED','NEXT_ACTION':'REVIEW_SINGLE_EVIDENCE_BASED_DIRECTION'})
 return result

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('action',choices=['prepare','preflight','freeze','run']); a=ap.parse_args()
 print(json.dumps(prepare() if a.action=='prepare' else preflight() if a.action=='preflight' else create_freeze() if a.action=='freeze' else execute(),ensure_ascii=False))
if __name__=='__main__': main()
