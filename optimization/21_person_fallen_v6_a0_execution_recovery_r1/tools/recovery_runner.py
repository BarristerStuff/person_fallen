"""V6-A0 recovery runner for pilot, regression, and remaining full DEV.
Uses the frozen V6 semantic files from stage 20 via absolute paths."""
import argparse,base64,hashlib,json,subprocess,sys,time
from pathlib import Path
from urllib import request,error
ROOT=Path(__file__).resolve().parents[1];V20=ROOT.parent/'20_person_fallen_v6_target_support_config';ENDPOINT='http://192.168.20.62:11434';MODEL='qwen3.5:4b';DIGEST='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd';VERSION='0.23.2'
import importlib.util
def load(n,p):
 sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
VC=load('v6_original_contracts',V20/'tools/contracts.py');VP=load('v6_original_policy',V20/'policy/target_policy.py')
sys.path.insert(0,str(ROOT/'adapters'))
from contracts import write_json,write_bytes,append_jsonl,sha,verify
parse=VC.parse; evaluate=VP.evaluate
MET=load('v6_original_metrics',V20/'tools/metrics.py')
summarize=MET.summarize

def freeze():
 p=ROOT/'freeze/RECOVERY_FREEZE.json';verify(p,(ROOT/'freeze/RECOVERY_FREEZE.sha256').read_text().strip());f=json.loads(p.read_text())
 expected={'pilot':156,'regression':1,'full_dev_remaining':280,'total':437,'val':0,'holdout':0,'detector':0}
 if f.get('candidate')!='V6-A0-TARGET-SUPPORT-CONFIG' or f.get('budget')!=expected:raise ValueError('freeze identity/budget mismatch')
 for q,h in f['bindings'].items():verify(q,h)
 return f

def preflight():
 d={}
 for s in ['tags','version','ps']:
  raw=subprocess.run(['curl','--noproxy','*','-fsS','--max-time','10',ENDPOINT+'/api/'+s],capture_output=True,check=True).stdout;d[s]=json.loads(raw);d[s+'_raw']=raw.decode()
 ms=[m for m in d['tags'].get('models',[]) if m.get('name')==MODEL]
 if len(ms)!=1 or ms[0].get('digest')!=DIGEST or d['version'].get('version')!=VERSION:raise ValueError('Ollama preflight mismatch')
 return d

def call(payload):
 t=time.monotonic();req=request.Request(ENDPOINT+'/api/generate',data=payload,headers={'Content-Type':'application/json'},method='POST')
 try:
  class NoRedirect(request.HTTPRedirectHandler):
   def redirect_request(self,*a,**k):return None
  with request.build_opener(request.ProxyHandler({}),NoRedirect()).open(req,timeout=120) as r:return {'http_status':r.status,'raw':r.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':None}
 except error.HTTPError as e:return {'http_status':e.code,'raw':e.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':repr(e)}
 except Exception as e:return {'http_status':None,'raw':b'','latency_seconds':time.monotonic()-t,'completion_unknown':True,'transport_error':repr(e)}

def load_manifest(phase):
 src=V20/'manifests'/({'pilot':'pilot156.json','regression':'regression1.json'}[phase]) if phase in {'pilot','regression'} else ROOT/'manifests/full_dev_remaining.json'
 return json.loads(src.read_text())
def phase_dir(phase):return ROOT/'eval'/phase
def build_payload(prompt,schema,images):return json.dumps({'model':MODEL,'prompt':prompt,'images':[base64.b64encode(x).decode() for x in images],'think':False,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':768}},ensure_ascii=False).encode()
def run_phase(phase,transport=None,run_root=None,freeze_override=None):
 f=freeze_override if freeze_override is not None else freeze();d=run_root if run_root is not None else phase_dir(phase)
 if d.exists():raise ValueError('existing phase execution')
 if phase=='regression' and freeze_override is None and json.loads((ROOT/'eval/pilot/summary.json').read_text())['gate']!='PASS':raise ValueError('pilot not pass')
 if phase=='full' and json.loads((ROOT/'eval/regression/summary.json').read_text())['gate']!='PASS':raise ValueError('regression not pass')
 rows=load_manifest(phase);prompt=(V20/'prompt/target_support_attributes.txt').read_text();schema=json.loads((V20/'schema/target_attributes.json').read_text());d.mkdir(parents=True);(d/'requests').mkdir();write_json(d/'STARTED.lock',{'phase':phase,'timestamp':time.time()});outputs=[];reqs=[]
 for row in rows:
  for pk,hk in [('image_path','image_sha256'),('prompt_path','prompt_sha256'),('full_view_path','full_view_sha256'),('crop_view_path','crop_view_sha256')]:verify(row[pk],row[hk])
  q=d/'requests'/row['request_id'];q.mkdir();imgs=[Path(row['full_view_path']).read_bytes()]+([Path(row['crop_view_path']).read_bytes()] if row['person_detected']=='true' else []);payload=build_payload(prompt,schema,imgs)
  claim={'state':'claimed','phase':phase,'request_id':row['request_id'],'item_id':row['item_id'],'operational_id':row.get('operational_id'),'taxonomy':row['taxonomy'],'group_id':row['group_id'],'evaluation_stratum':row['evaluation_stratum'],'source_image_sha256':row['image_sha256'],'full_view_sha256':row['full_view_sha256'],'crop_view_sha256':row['crop_view_sha256'],'payload_sha256':hashlib.sha256(payload).hexdigest(),'prompt_sha256':sha(V20/'prompt/target_support_attributes.txt'),'schema_sha256':sha(V20/'schema/target_attributes.json'),'policy_sha256':sha(V20/'policy/target_policy.py'),'freeze_sha256':sha(ROOT/'freeze/RECOVERY_FREEZE.json') if (ROOT/'freeze/RECOVERY_FREEZE.json').exists() else 'FAKE_FREEZE','claimed_timestamp':utc()};write_json(q/'claimed.json',claim);append_jsonl(d/'request_events.jsonl',claim)
  res=transport(payload,row) if transport else call(payload);write_bytes(q/'response.raw',res['raw']);tr={**claim,**{k:v for k,v in res.items() if k!='raw'},'raw_response_sha256':sha(q/'response.raw'),'raw_response_path':str(q/'response.raw'),'received_timestamp':utc()};write_json(q/'transport.json',tr)
  if res['completion_unknown'] or res['http_status']!=200:write_json(q/'failure.json',{**tr,'state':'protocol_failure'});raise RuntimeError('V6_A0_PROTOCOL_INCOMPLETE_NO_RETRY')
  try:o,p=parse(res['raw'])
  except Exception as e:write_json(q/'failure.json',{**tr,'state':'protocol_failure','parse_error':str(e)});raise RuntimeError('V6_A0_PROTOCOL_INCOMPLETE_NO_RETRY')
  dec=evaluate(p);rec={**claim,'state':'completed','strict_json_ok':True,'source_binding_ok':True,'http_status':200,'done':True,'done_reason':'stop','completion_unknown':False,'transport_error':None,'raw_response_sha256':tr['raw_response_sha256'],'raw_response_path':tr['raw_response_path'],'received_timestamp':tr['received_timestamp'],'eval_count':o.get('eval_count'),'parsed':p,**dec,'latency_seconds':res['latency_seconds'],'completed_timestamp':utc()};write_json(q/'completed.json',rec);append_jsonl(d/'request_events.jsonl',rec);outputs.append(rec);reqs.append(rec);append_jsonl(d/'output.jsonl',rec)
  # Pilot early-stop is evaluated only after complete summary; full is evaluated incrementally via combined custom downstream.
 s=summarize('pilot' if phase=='pilot' else 'regression',rows,outputs,reqs) if phase!='full' else {'phase':'full','rows':len(rows),'new_model_requests':len(reqs),'gate':'NOT_EVALUATED_PARTIAL'};write_json(d/'summary.json',s);write_json(d/'COMPLETION_LOCK.json',{'status':'COMPLETE','gate':s['gate'],'summary_sha256':sha(d/'summary.json'),'requests':len(reqs),'timestamp':utc()});return s
def utc():return __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['pilot','regression','full']);a=p.parse_args()
 try:
  pf=preflight();write_json(ROOT/'reports/ollama_recovery_preflight.json',pf);s=run_phase(a.phase);print(json.dumps(s,ensure_ascii=False))
 except Exception as e:print(json.dumps({'status':'FAILED','error':repr(e)}),file=sys.stderr);sys.exit(2)
