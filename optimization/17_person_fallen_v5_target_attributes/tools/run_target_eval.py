"""Main-agent-only direct serial Ollama runner; NEW_TARGET_ATTRIBUTES_ONLY, no retries."""
import argparse,base64,subprocess,sys,time
from urllib import request,error
from contracts import *
from metrics import summarize
sys.path.insert(0,str(ROOT/'policy'))
from target_policy import evaluate
ENDPOINT='http://192.168.20.62:11434'
DIGEST='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd'
VERSION='0.23.2'
class NoRedirect(request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):return None

def runtime_check():
 result={'timestamp':utc(),'endpoint':ENDPOINT}
 for suffix in ['tags','version','ps']:
  cmd=['curl','--noproxy','*','-fsS','--max-time','10',ENDPOINT+'/api/'+suffix]
  raw=subprocess.run(cmd,capture_output=True,check=True).stdout
  result[suffix+'_raw']=raw.decode();result[suffix]=loads(raw)
 selected=[m for m in result['tags']['models'] if m.get('name')==MODEL]
 if len(selected)!=1 or selected[0].get('digest')!=DIGEST:raise ValueError('Ollama model name/digest mismatch')
 if result['version'].get('version')!=VERSION:raise ValueError('Ollama version mismatch')
 return result

def verify_freeze():
 p=ROOT/'freeze/EXECUTION_FREEZE.json';verify_sha(p,(ROOT/'freeze/EXECUTION_FREEZE.sha256').read_text().strip());f=loads(p.read_bytes())
 if f['candidate']!=CANDIDATE or f['budget']!={'pilot':115,'regression':1,'total':116}:raise ValueError('Freeze identity/budget mismatch')
 for path,h in f['bindings'].items():verify_sha(path,h)
 return f

def payload(prompt,schema,images):
 return {'model':MODEL,'prompt':prompt,'images':[base64.b64encode(image).decode('ascii') for image in images],'think':False,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':768}}

def call_once(data):
 started=time.monotonic();raw=b'';status=None;unknown=False;failure=None
 req=request.Request(ENDPOINT+'/api/generate',data=data,headers={'Content-Type':'application/json'},method='POST')
 try:
  opener=request.build_opener(request.ProxyHandler({}),NoRedirect())
  with opener.open(req,timeout=120) as response:status=response.status;raw=response.read()
 except error.HTTPError as exc:
  status=exc.code;failure=repr(exc)
  try:raw=exc.read()
  except Exception as e:failure+=' '+repr(e)
 except Exception as exc:unknown=True;failure=repr(exc);raw=getattr(exc,'partial',b'')
 return {'http_status':status,'raw':raw,'latency_seconds':time.monotonic()-started,'completion_unknown':unknown,'transport_error':failure}

def stage(phase):
 if phase not in PHASES:raise ValueError('Unauthorized phase')
 run_dir=ROOT/'eval'/phase
 if run_dir.exists():raise ValueError('Existing execution; no overwrite/retry/resume')
 freeze=verify_freeze()
 if phase=='regression':
  p=ROOT/'eval/pilot';lock=loads((p/'COMPLETION_LOCK.json').read_bytes());verify_sha(p/'summary.json',lock['summary_sha256'])
  if loads((p/'summary.json').read_bytes())['gate']!='PASS':raise ValueError('Pilot not passed; known regression forbidden')
 rows=validate_manifest(phase,loads((ROOT/'manifests'/PHASES[phase]['manifest']).read_bytes()))
 runtime=runtime_check();start_stage(run_dir);write_json(run_dir/'runtime_preflight.json',runtime)
 prompt=(ROOT/'prompt/target_attributes.txt').read_text();schema=loads((ROOT/'schema/target_attributes.json').read_bytes())
 claims=set();records=[];output=[]
 try:
  for row in rows:
   for pk,hk in [('image_path','image_sha256'),('prompt_path','prompt_sha256'),('full_view_path','full_view_sha256'),('crop_view_path','crop_view_sha256')]:verify_sha(row[pk],row[hk])
   view_paths=[row['full_view_path']]+([row['crop_view_path']] if row['person_detected']=='true' else [])
   data=json.dumps(payload(prompt,schema,[Path(p).read_bytes() for p in view_paths]),ensure_ascii=False,allow_nan=False).encode()
   total=sum(1 for p in (ROOT/'eval').glob('*/requests/*/claimed.json'))
   rqdir=claim_directory(run_dir,phase,row,claims,total)
   claim={'state':'claimed','phase':phase,'request_id':row['request_id'],'item_id':row['item_id'],'operational_id':row.get('operational_id',''),'source_image_sha256':row['image_sha256'],'full_view_sha256':row['full_view_sha256'],'crop_view_sha256':row['crop_view_sha256'],'view_count':len(view_paths),'view_sha256':[sha(p) for p in view_paths],'prompt_sha256':sha(ROOT/'prompt/target_attributes.txt'),'schema_sha256':sha(ROOT/'schema/target_attributes.json'),'person_policy_sha256':sha(ROOT/'policy/target_policy.py'),'scene_aggregation_sha256':sha(ROOT/'policy/target_policy.py'),'model_binding':freeze['model'],'freeze_sha256':sha(ROOT/'freeze/EXECUTION_FREEZE.json'),'payload_sha256':hashlib.sha256(data).hexdigest(),'claimed_timestamp':utc()}
   write_json(rqdir/'claimed.json',claim);append_jsonl(run_dir/'request_events.jsonl',claim);claims.add(row['request_id'])
   result=call_once(data)
   write_bytes(rqdir/'response.raw',result.pop('raw'))
   rec={**claim,**result,'received_timestamp':utc(),'raw_response_sha256':sha(rqdir/'response.raw'),'raw_response_path':str(rqdir/'response.raw'),'strict_json_ok':False,'source_binding_ok':True,'done':None,'done_reason':None,'eval_count':None}
   write_json(rqdir/'transport.json',rec)
   try:
    if result['completion_unknown']:raise ValueError('COMPLETION_UNKNOWN_NO_RESEND')
    if result['http_status']!=200:raise ValueError('HTTP_FAILURE_NO_RETRY')
    outer,parsed=parse_response((rqdir/'response.raw').read_bytes())
   except Exception as exc:
    rec.update(state='protocol_failure',parse_error=str(exc),completed_timestamp=utc())
    # Preserve outer completion metadata even if the inner contract is invalid.
    try:
     o=loads((rqdir/'response.raw').read_bytes())
     if isinstance(o,dict):rec.update(done=o.get('done'),done_reason=o.get('done_reason'),eval_count=o.get('eval_count'))
    except Exception:pass
    write_json(rqdir/'failure.json',rec);append_jsonl(run_dir/'request_events.jsonl',rec);raise
   decisions=evaluate(parsed)
   rec.update(state='completed',strict_json_ok=True,done=outer['done'],done_reason=outer['done_reason'],eval_count=outer.get('eval_count'),parsed=parsed,**decisions,completed_timestamp=utc(),EVALUATION_MODE='NEW_TARGET_ATTRIBUTES_ONLY',CACHED_PRIMARY_USED_FOR_FINAL_DECISION=False)
   write_json(rqdir/'completed.json',rec);append_jsonl(run_dir/'request_events.jsonl',rec);records.append(rec)
   output.append(rec);append_jsonl(run_dir/'output.jsonl',rec)
   print(f'{phase} {len(claims)}/{len(rows)} {row["request_id"]} people={len(parsed["people"])} -> {decisions["image_decision"]}',flush=True)
  persisted=[loads(l) for l in (run_dir/'output.jsonl').read_text().splitlines()]
  actual=[loads(p.read_bytes()) for p in sorted((run_dir/'requests').glob('*/completed.json'))]
  if len(list((run_dir/'requests').glob('*/claimed.json')))!=len(actual):raise ValueError('Incomplete ledger')
  for rec in actual:
   raw=Path(rec['raw_response_path']);verify_sha(raw,rec['raw_response_sha256']);_,parsed=parse_response(raw.read_bytes())
   if parsed!=rec['parsed'] or evaluate(parsed)!={k:rec[k] for k in ['person_decisions','image_decision','image_reason']}:raise ValueError('Persisted replay mismatch')
  verify_freeze();summary=summarize(phase,rows,persisted,actual)
  if summary.get('validation_errors') or summary.get('valid_responses')!=len(rows):raise ValueError('Metric input integrity failure: '+str(summary.get('validation_errors')))
  write_json(run_dir/'summary.json',summary)
  import csv,io
  csv_rows=[{'item_id':r['item_id'],'request_id':r['request_id'],'phase':phase,'people_count':len(r['parsed']['people']),'scene_coverage':r['parsed']['scene_coverage'],'person_attributes_json':json.dumps(r['parsed']['people'],ensure_ascii=False),'person_decisions_json':json.dumps(r['person_decisions'],ensure_ascii=False),'image_decision':r['image_decision'],'image_reason':r['image_reason'],'strict_json_ok':r['strict_json_ok'],'source_binding_ok':r['source_binding_ok'],'latency_seconds':r['latency_seconds'],'eval_count':r['eval_count'],'raw_response_sha256':r['raw_response_sha256']} for r in persisted]
  f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=csv_rows[0]);w.writeheader();w.writerows(csv_rows);write_bytes(run_dir/'predictions.csv',f.getvalue().encode())
  write_json(run_dir/'COMPLETION_LOCK.json',{'status':'COMPLETE','gate':summary['gate'],'summary_sha256':sha(run_dir/'summary.json'),'predictions_sha256':sha(run_dir/'predictions.csv'),'requests':len(actual),'completed_timestamp':utc()})
  print(json.dumps(summary,ensure_ascii=False),flush=True);return summary
 except BaseException as exc:
  failure={'status':'V5_B0_PROTOCOL_INCOMPLETE_NO_RETRY','phase':phase,'error':repr(exc),'claimed_requests':len(claims),'completed_requests':len(records),'output_rows':len(output),'gate':'NOT_EVALUATED_PROTOCOL_INCOMPLETE','timestamp':utc()}
  if not (run_dir/'PROTOCOL_INCOMPLETE.json').exists():write_json(run_dir/'PROTOCOL_INCOMPLETE.json',failure)
  raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=list(PHASES));args=parser.parse_args()
 try:stage(args.phase)
 except Exception as exc:print(json.dumps({'error':repr(exc),'resend_allowed':False}),file=sys.stderr);sys.exit(2)
