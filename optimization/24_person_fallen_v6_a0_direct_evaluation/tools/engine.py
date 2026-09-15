"""Single R2 execution engine used by fake and real V6-A0 stages."""
from __future__ import annotations
import base64,csv,hashlib,json,math,os,time
from pathlib import Path
from datetime import datetime,timezone
from urllib import request,error
from collections import Counter
import sys
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent;V20=BASE/'20_person_fallen_v6_target_support_config'
sys.path.insert(0,str(ROOT/'protocol'));from budget import EXPECTED_BUDGET,ALLOWED_PHASES
sys.path.insert(0,str(ROOT/'adapters'));from v6_semantics import CONTRACTS,POLICY,PROMPT,SCHEMA,SEMANTIC_PATHS,bindings as semantic_bindings
MODEL={'endpoint':'http://192.168.20.62:11434','name':'qwen3.5:4b','digest':'2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd','ollama_version':'0.23.2','think':False,'stream':False,'temperature':0,'num_ctx':8192,'num_predict':768,'concurrency':1,'timeout_seconds':120,'automatic_retry':False,'resend_completion_unknown':False}
DEC=['ALERT_GROUND_LYING','RECHECK_VISUAL_UNCERTAIN','NO_ALERT_NORMAL_POSE','ATTENTION_NEAR_GROUND']
class ProtocolError(RuntimeError):pass
class GateFail(RuntimeError):pass
class EarlyStop(GateFail):pass
def utc():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_json(p):return json.loads(Path(p).read_text())
def write_exclusive(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def write_bytes(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
def append(p,obj):
 with Path(p).open('a') as f:f.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
def replace_json(p,obj):
 p=Path(p);tmp=p.with_name(p.name+'.tmp')
 with tmp.open('w') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def load_manifest(phase):
 paths={'pilot':ROOT/'manifests/pilot156.json','regression':ROOT/'manifests/regression1.json','full_remaining':ROOT/'manifests/full_remaining280.json'}
 if phase not in ALLOWED_PHASES:raise ValueError(f'unauthorized phase {phase}')
 return read_json(paths[phase])
def validate_budget(b):
 if b!=EXPECTED_BUDGET:raise ValueError(f'budget mismatch {b}')
def validate_freeze(f):
 validate_budget(f.get('budget')); 
 if f.get('candidate')!='V6-A0-TARGET-SUPPORT-CONFIG' or f.get('model')!=MODEL:raise ValueError('freeze identity/model')
 return f
def verify_real_freeze():
 p=ROOT/'freeze/RECOVERY_FREEZE.json';h=ROOT/'freeze/RECOVERY_FREEZE.sha256'
 if sha(p)!=h.read_text().strip():raise ValueError('freeze sha')
 f=read_json(p);validate_freeze(f)
 for path,digest in f['bindings'].items():
  if sha(path)!=digest:raise ValueError(f'freeze binding mismatch {path}')
 return f
def validate_row(r):
 if r.get('v3_split')!='V3_DEV' and r.get('operational_id')!='PFV4_SCREEN_0066':raise ValueError('split')
 for pk,hk in [('image_path','image_sha256'),('prompt_path','prompt_sha256'),('full_view_path','full_view_sha256'),('crop_view_path','crop_view_sha256')]:
  if sha(r[pk])!=r[hk]:raise ValueError(f'input sha {pk}')
 if r['person_detected'] not in {'true','false'}:raise ValueError('person_detected')
 if int(r['view_count']) != (2 if r['person_detected']=='true' else 1):raise ValueError('view_count')
def payload(images):
 return json.dumps({'model':MODEL['name'],'prompt':PROMPT.read_text(),'images':[base64.b64encode(x).decode() for x in images],'think':False,'stream':False,'format':read_json(SCHEMA),'options':{'temperature':0,'num_ctx':8192,'num_predict':768}},ensure_ascii=False).encode()
def call_real(data):
 t=time.monotonic();req=request.Request(MODEL['endpoint']+'/api/generate',data=data,headers={'Content-Type':'application/json'},method='POST')
 try:
  class NoRedirect(request.HTTPRedirectHandler):
   def redirect_request(self,*a,**k):return None
  with request.build_opener(request.ProxyHandler({}),NoRedirect()).open(req,timeout=120) as r:return {'http_status':r.status,'raw':r.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':None}
 except error.HTTPError as e:return {'http_status':e.code,'raw':e.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':repr(e)}
 except Exception as e:return {'http_status':None,'raw':b'','latency_seconds':time.monotonic()-t,'completion_unknown':True,'transport_error':repr(e)}
def stage_dir(runroot,phase):return Path(runroot)/phase
def load_lines(p):
 return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
def lock_ok(runroot,phase):
 d=stage_dir(runroot,phase);lock=read_json(d/'COMPLETION_LOCK.json');
 if lock['status']!='COMPLETE' or sha(d/'summary.json')!=lock['summary_sha256'] or read_json(d/'summary.json')['gate']!='PASS':raise ValueError(f'{phase} dependency lock')
 return lock
def ledger(runroot):
 claims=list(Path(runroot).glob('*/requests/*/claimed.json')); ids=[];items=[]
 for p in claims:
  r=read_json(p);ids.append(r['request_id']);items.append(r['item_id'])
 if len(ids)!=len(set(ids)) or len(items)!=len(set(items)):raise ValueError('cross-stage duplicate identity')
 if len(ids)>EXPECTED_BUDGET['total']:raise ValueError('budget exceeded')
 return len(ids)
def decisions(rows):
 c=Counter(r['image_decision'] for r in rows);return {d:c[d] for d in DEC}
def stage_summary(phase,manifest,outputs,requests):
 if len(outputs)!=len(manifest) or len(requests)!=len(manifest):return {'phase':phase,'gate':'FAIL','protocol_errors':['incomplete']}
 by={r['item_id']:r for r in outputs}
 if len(by)!=len(outputs):return {'phase':phase,'gate':'FAIL','protocol_errors':['duplicate output']}
 def sub(pred):return [by[r['item_id']] for r in manifest if pred(r)]
 g=sub(lambda r:r.get('evaluation_stratum')=='ground_lying');floor=sub(lambda r:r.get('taxonomy')=='floor_sitting');push=sub(lambda r:r.get('taxonomy')=='pushup_plank');crawl=sub(lambda r:r.get('taxonomy','').startswith('crawling'));multi=sub(lambda r:r.get('taxonomy')=='multi_person_one_lying')
 cg,cf,cp,cc,cm=map(decisions,[g,floor,push,crawl,multi]);checks={'rows':len(manifest)==(156 if phase=='pilot' else 1),'strict':all(r['strict_json_ok'] for r in outputs),'source':all(r['source_binding_ok'] for r in outputs)}
 if phase=='pilot':checks.update({'ground':len(g)==60 and cg['ALERT_GROUND_LYING']>=57 and cg['ALERT_GROUND_LYING']+cg['RECHECK_VISUAL_UNCERTAIN']==60 and cg['NO_ALERT_NORMAL_POSE']==cg['ATTENTION_NEAR_GROUND']==0,'floor':len(floor)==55 and cf['ALERT_GROUND_LYING']==cf['ATTENTION_NEAR_GROUND']==0 and cf['RECHECK_VISUAL_UNCERTAIN']<=5 and cf['NO_ALERT_NORMAL_POSE']>=50,'push':len(push)==26 and cp['ALERT_GROUND_LYING']==0,'crawl':len(crawl)==15 and cc['ALERT_GROUND_LYING']==0,'multi':len(multi)==5 and cm['ALERT_GROUND_LYING']==5 and len({r['group_id'] for r in manifest if r['taxonomy']=='multi_person_one_lying'})==1})
 else:
  x=outputs[0];ps=x['parsed']['people'];checks.update({'regression_target':manifest[0]['operational_id']=='PFV4_SCREEN_0066','coverage':x['parsed']['scene_coverage']=='complete','people':len(ps)>=2 and len({p['person_id'] for p in ps})==len(ps),'person_alert':any(d['decision']=='ALERT_GROUND_LYING' for d in x['person_decisions']),'image_alert':x['image_decision']=='ALERT_GROUND_LYING'})
 return {'phase':phase,'rows':len(manifest),'new_requests':len(requests),'valid_responses':len(outputs),'ground':cg,'floor':cf,'pushup':cp,'crawling':cc,'multi':cm,'gate_checks':checks,'gate':'PASS' if all(checks.values()) else 'FAIL'}
def combined_summary(pilot,remaining,manifest):
 outs=pilot+remaining;by={r['item_id']:r for r in outs}
 if len(outs)!=436 or len(by)!=436:return {'gate':'FAIL','error':'combined identity'}
 def sub(s):return [by[r['item_id']] for r in manifest if r['evaluation_stratum']==s]
 g,n,a,u=map(sub,['ground_lying','normal_negative','auxiliary_attention','visual_uncertain']);floor=[by[r['item_id']] for r in manifest if r['taxonomy']=='floor_sitting']
 cg,cn,ca,cu,cf=map(decisions,[g,n,a,u,floor]);checks={'rows':len(outs)==436,'strict':all(r['strict_json_ok'] for r in outs),'source':all(r['source_binding_ok'] for r in outs),'ground':cg['ALERT_GROUND_LYING']>=138 and cg['ALERT_GROUND_LYING']+cg['RECHECK_VISUAL_UNCERTAIN']==145 and cg['NO_ALERT_NORMAL_POSE']==cg['ATTENTION_NEAR_GROUND']==0,'normal':cn['ALERT_GROUND_LYING']==0 and cn['RECHECK_VISUAL_UNCERTAIN']<=23,'floor':cf['ALERT_GROUND_LYING']==0 and cf['RECHECK_VISUAL_UNCERTAIN']<=5 and cf['NO_ALERT_NORMAL_POSE']>=50,'aux':ca['ALERT_GROUND_LYING']==0}
 return {'rows':436,'ground':cg,'normal':cn,'floor':cf,'auxiliary':ca,'visual_uncertain':cu,'gate_checks':checks,'gate':'PASS' if all(checks.values()) else 'FAIL'}
def early(pilot,remaining,full_manifest):
 s=combined_summary(pilot,remaining,[r for r in full_manifest if r['item_id'] in {x['item_id'] for x in pilot+remaining}]) if False else None
 rows=pilot+remaining;# use observed direct
 def c(st,d):return sum(r.get('evaluation_stratum')==st and r['image_decision']==d for r in rows)
 if c('normal_negative','ALERT_GROUND_LYING')>=1:return 'A_NORMAL_ALERT'
 if c('normal_negative','RECHECK_VISUAL_UNCERTAIN')>=24:return 'B_NORMAL_RECHECK_24'
 if c('ground_lying','NO_ALERT_NORMAL_POSE')+c('ground_lying','ATTENTION_NEAR_GROUND')>=1:return 'C_GROUND_NO_ALERT_OR_ATTENTION'
 if c('ground_lying','RECHECK_VISUAL_UNCERTAIN')+c('ground_lying','NO_ALERT_NORMAL_POSE')+c('ground_lying','ATTENTION_NEAR_GROUND')>=8:return 'D_GROUND_NON_ALERT_8'
 if c('auxiliary_attention','ALERT_GROUND_LYING')>=1:return 'E_AUXILIARY_ALERT'
 return None
def run_stage(phase,runroot,freeze_spec,transport,preflight_snapshot):
 if phase not in ALLOWED_PHASES:raise ValueError(f'unauthorized phase {phase}')
 validate_freeze(freeze_spec);runroot=Path(runroot);d=stage_dir(runroot,phase)
 if d.exists():raise ValueError('existing stage')
 if phase=='regression':lock_ok(runroot,'pilot')
 if phase=='full_remaining':lock_ok(runroot,'pilot');lock_ok(runroot,'regression')
 manifest=load_manifest(phase);d.mkdir(parents=True);(d/'requests').mkdir();write_exclusive(d/'STARTED.lock',{'phase':phase,'timestamp':utc()});write_exclusive(d/'runtime_preflight.json',preflight_snapshot);outputs=[];reqs=[]
 for row in manifest:
  validate_row(row);ledger(runroot);q=d/'requests'/row['request_id'];q.mkdir();imgs=[Path(row['full_view_path']).read_bytes()]+([Path(row['crop_view_path']).read_bytes()] if row['person_detected']=='true' else []);data=payload(imgs);claim={'state':'claimed','phase':phase,'request_id':row['request_id'],'item_id':row['item_id'],'operational_id':row.get('operational_id'),'taxonomy':row['taxonomy'],'group_id':row['group_id'],'evaluation_stratum':row['evaluation_stratum'],'source_image_sha256':row['image_sha256'],'full_view_sha256':row['full_view_sha256'],'crop_view_sha256':row['crop_view_sha256'],'payload_sha256':hashlib.sha256(data).hexdigest(),'claimed_timestamp':utc()};write_exclusive(q/'claimed.json',claim);append(d/'request_events.jsonl',claim)
  res=transport(data,row) if transport else call_real(data);write_bytes(q/'response.raw',res['raw']);base={**claim,**{k:v for k,v in res.items() if k!='raw'},'raw_response_sha256':sha(q/'response.raw'),'raw_response_path':str(q/'response.raw'),'received_timestamp':utc()};write_exclusive(q/'transport.json',base)
  if res['completion_unknown'] or res['http_status']!=200:write_exclusive(q/'failure.json',{**base,'state':'protocol_failure'});raise ProtocolError('V6_A0_PROTOCOL_INCOMPLETE_NO_RETRY')
  try:o,parsed=CONTRACTS.parse(res['raw'])
  except Exception as e:write_exclusive(q/'failure.json',{**base,'state':'protocol_failure','parse_error':str(e)});raise ProtocolError('V6_A0_PROTOCOL_INCOMPLETE_NO_RETRY')
  dec=POLICY.evaluate(parsed);rec={**base,'state':'completed','strict_json_ok':True,'source_binding_ok':True,'done':o['done'],'done_reason':o['done_reason'],'eval_count':o.get('eval_count'),'parsed':parsed,**dec,'latency_seconds':res['latency_seconds'],'completed_timestamp':utc()};write_exclusive(q/'completed.json',rec);append(d/'request_events.jsonl',rec);append(d/'output.jsonl',rec);outputs.append(rec);reqs.append(rec)
  if phase=='full_remaining':
   pilot=load_lines(stage_dir(runroot,'pilot')/'output.jsonl');fullman=read_json(ROOT/'manifests/full_combined436.json');trigger=early(pilot,outputs,fullman)
   replace_json(d/'partial_metrics.json',{'phase':phase,'observed_new':len(outputs),'pending_new':280-len(outputs),'early_stop':trigger})
   if trigger:write_exclusive(d/'EARLY_STOP.json',{'status':'V6_A0_FULL_DEV_EARLY_GATE_FAIL','trigger':trigger,'new_completed':len(outputs),'new_not_started':280-len(outputs)});raise EarlyStop(trigger)
 summary=stage_summary('pilot' if phase=='pilot' else 'regression',manifest,outputs,reqs) if phase!='full_remaining' else {'phase':'full_remaining','rows':len(outputs),'gate':'PASS','new_requests':len(reqs)}
 replace_json(d/'summary.json',summary);write_exclusive(d/'COMPLETION_LOCK.json',{'status':'COMPLETE','gate':summary['gate'],'summary_sha256':sha(d/'summary.json'),'requests':len(reqs),'timestamp':utc()});return summary
def aggregate_full(runroot):
 lock_ok(runroot,'pilot');lock_ok(runroot,'regression');lock_ok(runroot,'full_remaining');pilot=load_lines(stage_dir(runroot,'pilot')/'output.jsonl');rem=load_lines(stage_dir(runroot,'full_remaining')/'output.jsonl');full=read_json(ROOT/'manifests/full_combined436.json');s=combined_summary(pilot,rem,full);d=Path(runroot)/'full_dev_combined';d.mkdir();
 for r in pilot+rem:append(d/'output.jsonl',r)
 replace_json(d/'summary.json',s)
 if s['gate']=='PASS':write_exclusive(d/'FULL_DEV_COMPLETION_LOCK.json',{'status':'COMPLETE','gate':'PASS','summary_sha256':sha(d/'summary.json'),'rows':436,'timestamp':utc()})
 return s
