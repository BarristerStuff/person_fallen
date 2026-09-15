import argparse,base64,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from urllib import request,error
ROOT=Path(__file__).resolve().parents[1];V17=ROOT.parent/'17_person_fallen_v5_target_attributes';sys.path.insert(0,str(V17/'tools'));sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'tools'))
# unique import aliases: source is frozen V5-B0; do not import any older revision
import importlib.util
cs=importlib.util.spec_from_file_location('v5b_contracts',V17/'tools/contracts.py');contracts=importlib.util.module_from_spec(cs);cs.loader.exec_module(contracts)
ts=importlib.util.spec_from_file_location('v5b_policy',V17/'policy/target_policy.py');policy=importlib.util.module_from_spec(ts);ts.loader.exec_module(policy)
from full_dev_metrics import summarize,early_stop
ENDPOINT='http://192.168.20.62:11434';MODEL='qwen3.5:4b';DIGEST='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd';VERSION='0.23.2';ALERT='ALERT_GROUND_LYING'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def utc():return __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
def load(p):return json.loads(Path(p).read_text())
def write(p,x):contracts.write_bytes(p,(json.dumps(x,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode())
def append(p,x):
 with open(p,'a') as f:f.write(json.dumps(x,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
def check_runtime():
 d={}
 for s in ['tags','version','ps']:
  raw=subprocess.run(['curl','--noproxy','*','-fsS','--max-time','10',ENDPOINT+'/api/'+s],capture_output=True,check=True).stdout;d[s]=json.loads(raw);d[s+'_raw']=raw.decode()
 ms=[m for m in d['tags'].get('models',[]) if m.get('name')==MODEL]
 if len(ms)!=1 or ms[0].get('digest')!=DIGEST or d['version'].get('version')!=VERSION:raise RuntimeError('OLLAMA_PREFLIGHT_BLOCKED_MODEL_BINDING')
 return d
def call(data):
 t=time.monotonic();req=request.Request(ENDPOINT+'/api/generate',data=data,headers={'Content-Type':'application/json'},method='POST');raw=b''
 try:
  with request.build_opener(request.ProxyHandler({})).open(req,timeout=120) as r:return {'http_status':r.status,'raw':r.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':None}
 except error.HTTPError as e:return {'http_status':e.code,'raw':e.read(),'latency_seconds':time.monotonic()-t,'completion_unknown':False,'transport_error':repr(e)}
 except Exception as e:return {'http_status':None,'raw':raw,'latency_seconds':time.monotonic()-t,'completion_unknown':True,'transport_error':repr(e)}
def main():
 rt=check_runtime();
 preflight_path=ROOT/'reports/ollama_extension_preflight.json'
 if not preflight_path.exists(): write(preflight_path,rt)
 else:
  old=load(preflight_path); assert old['tags']['models']==rt['tags']['models'] and old['version']==rt['version'] and old['ps']==rt['ps']
 freeze=load(ROOT/'freeze/EXTENSION_FREEZE.json');assert sha(ROOT/'freeze/EXTENSION_FREEZE.json')==Path(ROOT/'freeze/EXTENSION_FREEZE.sha256').read_text().strip()
 for p,h in freeze['bindings'].items():contracts.verify_sha(p,h)
 rows=list(__import__('csv').DictReader(open(ROOT/'manifests/remaining321.csv')));assert len(rows)==321
 pilot=[json.loads(x) for x in (V17/'eval/pilot/output.jsonl').read_text().splitlines()];pman=list(__import__('csv').DictReader(open(V17/'manifests/pilot115.csv')));pmap={x['item_id']:x for x in pman};
 full=list(__import__('csv').DictReader(open(ROOT/'manifests/full_dev436.csv'))); frows=[]
 for r in full:
  x=dict(r);x['phase']='full_dev';frows.append(x)
 cached={x['item_id']:{**x,'inference_source':'V5_B0_REUSED_RESULT','request_id':next(r['request_id'] for r in frows if r['item_id']==x['item_id']),'source_binding_ok':True,'strict_json_ok':True} for x in pilot}
 out=list(cached.values());requests=[];run=ROOT/'eval/full_dev';
 if run.exists():raise RuntimeError('V5_B0_FULL_DEV_EXISTING_EXECUTION_BLOCKED')
 run.mkdir(parents=True);write(run/'STARTED.lock',{'timestamp':utc(),'resend_forbidden':True});prompt=(V17/'prompt/target_attributes.txt').read_text();schema=load(V17/'schema/target_attributes.json')
 for i,row in enumerate(rows,1):
  if row['experiment_stratum'] not in {'normal_negative','ground_lying','auxiliary_attention','visual_uncertain'}:raise RuntimeError('bad stratum')
  for k in ['image_path','prompt_path','full_view_path','crop_view_path']:contracts.verify_sha(row[k],row[k.replace('_path','_sha256')] if k!='prompt_path' else row['prompt_sha256'])
  rid=row['request_id'];q=run/'requests'/rid;q.mkdir(parents=False);claim={'state':'claimed','phase':'full_dev_extension','request_id':rid,'item_id':row['item_id'],'operational_id':row['diagnostic_id'],'source_image_sha256':row['image_sha256'],'full_view_sha256':row['full_view_sha256'],'crop_view_sha256':row['crop_view_sha256'],'prompt_sha256':sha(V17/'prompt/target_attributes.txt'),'schema_sha256':sha(V17/'schema/target_attributes.json'),'policy_sha256':sha(V17/'policy/target_policy.py'),'model':freeze['model'],'claimed_timestamp':utc()};write(q/'claimed.json',claim);append(run/'request_events.jsonl',claim)
  imgs=[Path(row['full_view_path']).read_bytes()]+([Path(row['crop_view_path']).read_bytes()] if row['person_detected']=='true' else []);payload={'model':MODEL,'prompt':prompt,'images':[base64.b64encode(x).decode() for x in imgs],'think':False,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':768}};res=call(json.dumps(payload,ensure_ascii=False,allow_nan=False).encode());contracts.write_bytes(q/'response.raw',res['raw']);rec={**claim,**{k:v for k,v in res.items() if k!='raw'},'raw_response_sha256':sha(q/'response.raw'),'raw_response_path':str(q/'response.raw'),'received_timestamp':utc()}
  if res['completion_unknown'] or res['http_status']!=200:write(q/'failure.json',{**rec,'state':'protocol_failure'});raise RuntimeError('V5_B0_FULL_DEV_PROTOCOL_INCOMPLETE_NO_RETRY')
  try:outer,parsed=contracts.parse_response(res['raw'])
  except Exception as e:write(q/'failure.json',{**rec,'state':'protocol_failure','parse_error':str(e)});raise RuntimeError('V5_B0_FULL_DEV_PROTOCOL_INCOMPLETE_NO_RETRY')
  dec=policy.evaluate(parsed);rec.update({'state':'completed','strict_json_ok':True,'source_binding_ok':True,'done':outer['done'],'done_reason':outer['done_reason'],'eval_count':outer.get('eval_count'),'parsed':parsed,**dec,'completed_timestamp':utc(),'inference_source':'NEW_MODEL_REQUEST','EVALUATION_MODE':'SAME_V5_B0_EXACT_RESULT_REUSE_PLUS_NEW_INFERENCE','LEGACY_V4_CACHE_USED_FOR_DECISION':False});write(q/'completed.json',rec);append(run/'request_events.jsonl',rec);requests.append(rec);out.append(rec)
  # progressive exact full-dev stop evaluation, with cached 115 already included
  temp=summarize(frows,out,requests,complete=False);reason=None; n=temp['normal_negative'];g=temp['ground_lying']
  if n['ALERT']>0:reason='A_DETERMINATE_NEGATIVE_ALERT'
  elif n['RECHECK']>=24:reason='B_NORMAL_NEGATIVE_RECHECK_REACHED_24'
  elif g['NO_ALERT']+g['ATTENTION']>0:reason='C_GROUND_NO_ALERT_OR_ATTENTION'
  elif 145-g['ALERT']>=8:reason='D_GROUND_NON_ALERT_REACHED_8'
  if reason:write(run/'EARLY_STOP.json',{'status':'V5_B0_FULL_DEV_EARLY_GATE_FAIL','trigger':reason,'claimed':len(requests),'completed':len(requests),'not_started':321-len(requests),'partial_observed_summary':temp});raise RuntimeError('V5_B0_FULL_DEV_EARLY_GATE_FAIL:'+reason)
 # complete merge output with normalized fields
 write(run/'output.jsonl',out);summary=summarize(frows,out,requests,complete=True);write(run/'summary.json',summary);write(run/'COMPLETION_LOCK.json',{'status':'COMPLETE','summary_sha256':sha(run/'summary.json'),'requests':len(requests),'timestamp':utc()});print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'status':'FAILED','error':str(e)}),file=sys.stderr);sys.exit(2)
