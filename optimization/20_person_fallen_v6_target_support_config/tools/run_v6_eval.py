import argparse,base64,subprocess,time,json,sys
from pathlib import Path
from urllib import request,error
from contracts import *
ROOT=Path(__file__).resolve().parents[1];FREEZE=ROOT/'freeze/CANDIDATE_FREEZE.json';FREEZE_SHA=ROOT/'freeze/CANDIDATE_FREEZE.sha256';ENDPOINT='http://192.168.20.62:11434';MODEL='qwen3.5:4b';DIGEST='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd';VERSION='0.23.2'
sys.path.insert(0,str(ROOT/'policy'));from target_policy import evaluate
from metrics import summarize

def verify_freeze():
 if not FREEZE.is_file() or not FREEZE_SHA.is_file():raise ValueError('freeze missing')
 if sha(FREEZE)!=FREEZE_SHA.read_text().strip():raise ValueError('freeze hash mismatch')
 f=loads(FREEZE.read_bytes())
 if f.get('candidate')!='V6-A0-TARGET-SUPPORT-CONFIG' or f.get('budget')!={'pilot':156,'regression':1,'total':157}:raise ValueError('freeze identity/budget')
 for p,h in f.get('bindings',{}).items():verify(p,h)
 return f

def preflight():
 d={}
 for s in ['tags','version','ps']:
  raw=subprocess.run(['curl','--noproxy','*','-fsS','--max-time','10',ENDPOINT+'/api/'+s],capture_output=True,check=True).stdout;d[s]=loads(raw);d[s+'_raw']=raw.decode()
 ms=[m for m in d['tags'].get('models',[]) if m.get('name')==MODEL]
 if len(ms)!=1 or ms[0].get('digest')!=DIGEST or d['version'].get('version')!=VERSION:raise ValueError('OLLAMA_PREFLIGHT_BLOCKED')
 return d

def call(data):
 t=time.monotonic();req=request.Request(ENDPOINT+'/api/generate',data=data,headers={'Content-Type':'application/json'},method='POST')
 try:
  with request.build_opener(request.ProxyHandler({})).open(req,timeout=120) as r:return {'http_status':r.status,'raw':r.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':None}
 except error.HTTPError as e:return {'http_status':e.code,'raw':e.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':repr(e)}
 except Exception as e:return {'http_status':None,'raw':b'','latency_seconds':time.monotonic()-t,'completion_unknown':True,'transport_error':repr(e)}

def stage(phase):
 if phase not in {'pilot','regression'}:raise ValueError('unauthorized phase')
 run=ROOT/'eval'/phase
 freeze=verify_freeze()
 if run.exists():raise ValueError('existing execution')
 manifest=json.loads((ROOT/'manifests/pilot156.json' if phase=='pilot' else ROOT/'manifests/regression1.json').read_text())
 if phase=='regression':
  pilot=json.loads((ROOT/'eval/pilot/summary.json').read_text());
  if pilot['gate']!='PASS':raise ValueError('pilot gate failed')
 schema=json.loads((ROOT/'schema/target_attributes.json').read_text());prompt=(ROOT/'prompt/target_support_attributes.txt').read_text();rt=preflight();run.mkdir(parents=True);(run/'requests').mkdir();write_json(run/'runtime_preflight.json',rt);outputs=[];requests=[]
 try:
  for row in manifest:
   for pk,hk in [('image_path','image_sha256'),('prompt_path','prompt_sha256'),('full_view_path','full_view_sha256'),('crop_view_path','crop_view_sha256')]:verify(row[pk],row[hk])
   imgs=[Path(row['full_view_path']).read_bytes()]+([Path(row['crop_view_path']).read_bytes()] if row['person_detected']=='true' else [])
   payload={'model':MODEL,'prompt':prompt,'images':[base64.b64encode(x).decode() for x in imgs],'think':False,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':768}}
   q=run/'requests'/row['request_id'];q.mkdir();claim={'state':'claimed','request_id':row['request_id'],'phase':phase,'item_id':row['item_id'],'operational_id':row.get('operational_id'),'evaluation_stratum':row['evaluation_stratum'],'source_image_sha256':row['image_sha256'],'full_view_sha256':row['full_view_sha256'],'crop_view_sha256':row['crop_view_sha256'],'prompt_sha256':sha(ROOT/'prompt/target_support_attributes.txt'),'schema_sha256':sha(ROOT/'schema/target_attributes.json'),'policy_sha256':sha(ROOT/'policy/target_policy.py'),'payload_sha256':__import__('hashlib').sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest(),'claimed_timestamp':utc()};write_json(q/'claimed.json',claim);append_jsonl(run/'request_events.jsonl',claim)
   res=call(json.dumps(payload,ensure_ascii=False).encode());write_bytes(q/'response.raw',res['raw']);t={**claim,**{k:v for k,v in res.items() if k!='raw'},'raw_response_sha256':sha(q/'response.raw'),'raw_response_path':str(q/'response.raw'),'received_timestamp':utc()};write_json(q/'transport.json',t)
   if res['completion_unknown'] or res['http_status']!=200:write_json(q/'failure.json',{**t,'state':'protocol_failure'});raise RuntimeError('V6_PROTOCOL_INCOMPLETE_NO_RETRY')
   try:o,p=parse(res['raw'])
   except Exception as e:write_json(q/'failure.json',{**t,'state':'protocol_failure','parse_error':str(e)});raise RuntimeError('V6_PROTOCOL_INCOMPLETE_NO_RETRY')
   d=evaluate(p);rec={**claim,'state':'completed','strict_json_ok':True,'source_binding_ok':True,'http_status':200,'done':True,'done_reason':'stop','eval_count':o.get('eval_count'),'parsed':p,**d,'latency_seconds':res['latency_seconds'],'completed_timestamp':utc(),'taxonomy':row['taxonomy'],'group_id':row['group_id'],'evaluation_stratum':row['evaluation_stratum'],'completion_unknown':False,'transport_error':None,'raw_response_sha256':t['raw_response_sha256'],'raw_response_path':t['raw_response_path'],'received_timestamp':t['received_timestamp'],'model_binding':freeze['model'],'freeze_sha256':sha(FREEZE)};write_json(q/'completed.json',rec);append_jsonl(run/'request_events.jsonl',rec);requests.append(rec);outputs.append(rec);append_jsonl(run/'output.jsonl',rec)
  summary=summarize(phase,manifest,outputs,requests);write_json(run/'summary.json',summary);write_json(run/'COMPLETION_LOCK.json',{'status':'COMPLETE','gate':summary['gate'],'summary_sha256':sha(run/'summary.json'),'requests':len(requests),'timestamp':utc()});print(json.dumps(summary,ensure_ascii=False));return summary
 except Exception:
  if not (run/'PROTOCOL_INCOMPLETE.json').exists():write_json(run/'PROTOCOL_INCOMPLETE.json',{'status':'V6_PROTOCOL_INCOMPLETE_NO_RETRY','requests':len(requests),'outputs':len(outputs),'timestamp':utc()})
  raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['pilot','regression']);a=p.parse_args()
 try:stage(a.phase)
 except Exception as e:print(json.dumps({'status':'FAILED','error':repr(e)}),file=sys.stderr);sys.exit(2)
