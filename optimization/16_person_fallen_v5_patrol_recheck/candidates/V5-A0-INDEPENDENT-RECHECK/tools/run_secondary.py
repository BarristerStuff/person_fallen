"""Single-candidate single-flight runner. No retry, resume, warmup, primary or detector calls."""
import argparse,base64,subprocess,sys,time
from urllib import request,error
from contracts import *
from metrics import metrics
sys.path.insert(0,str(ROOT/'policy'))
from routing_contract import route_first_frame

ENDPOINT='http://192.168.20.62:11434'
MODEL='qwen3.5:4b'
DIGEST='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd'
VERSION='0.23.2'
# Disable environment proxies and redirects; direct service only. No retries.
class NoRedirect(request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):return None

def runtime_check():
 captured={'timestamp':utc(),'endpoint':ENDPOINT}
 for suffix in ['tags','version','ps']:
  result=subprocess.run(['curl','--noproxy','*','-fsS','--max-time','10',ENDPOINT+'/api/'+suffix],capture_output=True,check=True)
  captured[suffix+'_raw']=result.stdout.decode();captured[suffix]=loads(result.stdout)
 selected=[x for x in captured['tags']['models'] if x.get('name')==MODEL]
 if len(selected)!=1 or selected[0].get('digest')!=DIGEST:raise ValueError('Model name/digest mismatch')
 if captured['version'].get('version')!=VERSION:raise ValueError('Ollama version mismatch')
 return captured

def verify_freeze():
 path=ROOT/'freeze/EXECUTION_FREEZE.json'
 verify_sha(path,(ROOT/'freeze/EXECUTION_FREEZE.sha256').read_text().strip())
 freeze=loads(path.read_bytes())
 if freeze['candidate']!='V5-A0-INDEPENDENT-RECHECK' or freeze['request_budget']!={'total':340,'dev':288,'regression':52,'primary':0,'val':0,'holdout':0,'detector':0}:raise ValueError('Freeze identity/budget mismatch')
 for p,h in freeze['bindings'].items():verify_sha(p,h)
 return freeze

def payload(prompt,schema,image):
 return {'model':MODEL,'prompt':prompt,'images':[base64.b64encode(image).decode('ascii')],'think':False,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':384}}

def call_once(data):
 started=time.monotonic();raw=b'';status=None;err=None;unknown=False
 req=request.Request(ENDPOINT+'/api/generate',data=data,headers={'Content-Type':'application/json'},method='POST')
 try:
  opener=request.build_opener(request.ProxyHandler({}),NoRedirect())
  with opener.open(req,timeout=120) as response:
   status=response.status;raw=response.read()
 except error.HTTPError as exc:
  status=exc.code
  try:raw=exc.read()
  except Exception as read_error:err=repr(read_error)
  err=err or repr(exc)
 except Exception as exc:
  raw=getattr(exc,'partial',b'');unknown=True;err=repr(exc)
 return {'http_status':status,'raw':raw,'latency_seconds':time.monotonic()-started,'completion_unknown':unknown,'error':err}

def run_stage(phase):
 if phase not in PHASES:raise ValueError('Forbidden phase')
 run_dir=ROOT/'eval'/phase
 if run_dir.exists():raise ValueError('V5_EXISTING_EXECUTION_BLOCKED')
 freeze=verify_freeze()
 if phase=='regression':
  dev=ROOT/'eval/dev';lock=loads((dev/'COMPLETION_LOCK.json').read_bytes());verify_sha(dev/'summary.json',lock['summary_sha256'])
  if loads((dev/'summary.json').read_bytes())['gate']!='PASS':raise ValueError('DEV gate failed; regression forbidden')
 source=validate_manifest(phase,loads((ROOT/f'manifests/{phase}.json').read_bytes()))
 # All inputs are immutable explicit manifest references; no dataset traversal.
 runtime=runtime_check()
 start_stage(run_dir);write_json(run_dir/'runtime_preflight.json',runtime)
 prompt=(ROOT/'prompt/scene_review.txt').read_text();schema=loads((ROOT/'schema/secondary.json').read_bytes())
 plan=loads((ROOT/'protocol/execution_plan.json').read_bytes())
 model_binding=plan['secondary_model'];claimed=set();output=[];records=[]
 try:
  for row in source:
   secondary=None;rec=None
   if row['secondary_required']:
    verify_sha(row['full_view_path'],row['full_view_sha256']);verify_sha(row['image_path'],row['image_sha256']);verify_sha(row['primary_cache_source'],row['primary_cache_sha256'])
    data=json.dumps(payload(prompt,schema,Path(row['full_view_path']).read_bytes()),ensure_ascii=False,allow_nan=False).encode()
    rqdir=claim_request(phase,row,run_dir,claimed)
    total_before=sum(1 for p in (ROOT/'eval').glob('*/requests/*/claimed.json'))
    if total_before>=340:raise ValueError('Total budget exhausted')
    claim={'state':'claimed','request_id':row['request_id'],'phase':phase,'item_id':row['item_id'],'operational_id':row['operational_id'],'source_image_sha256':row['image_sha256'],'full_view_sha256':row['full_view_sha256'],'primary_cache_source':row['primary_cache_source'],'primary_cache_sha256':row['primary_cache_sha256'],'primary_decision':row['primary_decision'],'prompt_sha256':sha(ROOT/'prompt/scene_review.txt'),'schema_sha256':sha(ROOT/'schema/secondary.json'),'model_binding':model_binding,'freeze_sha256':sha(ROOT/'freeze/EXECUTION_FREEZE.json'),'payload_sha256':hashlib.sha256(data).hexdigest(),'claimed_timestamp':utc()}
    write_json(rqdir/'claimed.json',claim);append_jsonl(run_dir/'request_events.jsonl',claim);claimed.add(row['request_id'])
    result=call_once(data)
    # Raw wire response saved before parsing. Any subsequent error is terminal.
    write_bytes(rqdir/'response.raw',result.pop('raw'))
    rec={**claim,**result,'received_timestamp':utc(),'raw_response_sha256':sha(rqdir/'response.raw'),'strict_json_ok':False,'done':None,'done_reason':None,'scene_review':None,'evidence':None,'final_decision':route_first_frame(row['primary_decision'],None),'routing_reason':'UNAVAILABLE_SECONDARY_SAFE_RECHECK_PROTOCOL_FAILURE'}
    write_json(rqdir/'transport.json',rec)
    try:
     if result['completion_unknown']:raise ValueError('COMPLETION_UNKNOWN_NO_RESEND')
     if result['http_status']!=200:raise ValueError('HTTP_FAILURE_NO_RETRY')
     outer,parsed=parse_response((rqdir/'response.raw').read_bytes())
    except Exception as exc:
     rec.update(state='protocol_failure',parse_error=str(exc),completed_timestamp=utc())
     write_json(rqdir/'failure.json',rec);append_jsonl(run_dir/'request_events.jsonl',rec)
     raise
    secondary=parsed['scene_review'];final=route_first_frame(row['primary_decision'],secondary)
    reason='PRIMARY_RECHECK_PRESERVED' if row['primary_decision']==RECHECK else ('SECONDARY_ABSENT_KEEP_PRIMARY' if secondary=='candidate_absent' else 'SECONDARY_REQUIRES_RECHECK')
    rec.update(state='completed',strict_json_ok=True,done=outer['done'],done_reason=outer['done_reason'],**parsed,final_decision=final,routing_reason=reason,completed_timestamp=utc())
    write_json(rqdir/'completed.json',rec);append_jsonl(run_dir/'request_events.jsonl',rec);records.append(rec)
    print(f'{phase} {len(claimed)}/{PHASES[phase][1]} {row["request_id"]} {secondary} -> {final}',flush=True)
   else:final=route_first_frame(row['primary_decision']);reason='PRIMARY_ALERT_PRESERVED_SECONDARY_NOT_RUN'
   out={'item_id':row['item_id'],'operational_id':row['operational_id'],'taxonomy':row['taxonomy'],'v5_stratum':row['v5_stratum'],'source_split':row['source_split'],'group_id':row['group_id'],'source_image_sha256':row['image_sha256'],'full_view_sha256':row['full_view_sha256'],'primary_decision':row['primary_decision'],'primary_cache_binding_ok':row['primary_cache_binding_ok'],'PRIMARY_INFERENCE_SOURCE':'FROZEN_V4_CACHE','EVALUATION_MODE':'CACHED_PRIMARY_PLUS_NEW_SECONDARY','request_id':row['request_id'],'secondary_status':'COMPLETED' if rec else 'NOT_RUN_PRIMARY_ALERT','scene_review':secondary,'final_decision':final,'routing_reason':reason}
   output.append(out);append_jsonl(run_dir/'output.jsonl',out)
  # Re-read actual persisted records, not an in-memory promise of completion.
  persisted=[loads(l) for l in (run_dir/'output.jsonl').read_text().splitlines()]
  actual=[loads(p.read_bytes()) for p in sorted((run_dir/'requests').glob('*/completed.json'))]
  for rec in actual:
   raw=run_dir/'requests'/rec['request_id']/'response.raw';verify_sha(raw,rec['raw_response_sha256']);_,parsed=parse_response(raw.read_bytes());assert parsed['scene_review']==rec['scene_review']
  assert len(list((run_dir/'requests').glob('*/claimed.json')))==len(actual)
  verify_freeze()
  summary=metrics(source,persisted,actual,phase)
  write_csv(run_dir/'predictions.csv',persisted);write_json(run_dir/'summary.json',summary)
  write_json(run_dir/'COMPLETION_LOCK.json',{'status':'COMPLETE','gate':summary['gate'],'summary_sha256':sha(run_dir/'summary.json'),'predictions_sha256':sha(run_dir/'predictions.csv'),'completed_timestamp':utc(),'secondary_requests':len(actual)})
  print(json.dumps(summary,ensure_ascii=False),flush=True)
  return summary
 except BaseException as exc:
  failure={'status':'V5_PROTOCOL_INCOMPLETE_NO_RETRY','phase':phase,'error':repr(exc),'claimed_requests':len(claimed),'completed_requests':len(records),'output_rows':len(output),'gate':'NOT_EVALUATED_PROTOCOL_INCOMPLETE','safe_fallback_is_not_valid_model_response':True,'timestamp':utc()}
  if not (run_dir/'PROTOCOL_INCOMPLETE.json').exists():write_json(run_dir/'PROTOCOL_INCOMPLETE.json',failure)
  raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=list(PHASES));a=parser.parse_args()
 try:run_stage(a.phase)
 except Exception as exc:print(json.dumps({'error':repr(exc),'automatic_retry':False}),file=sys.stderr);sys.exit(2)
