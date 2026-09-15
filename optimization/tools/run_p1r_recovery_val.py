#!/usr/bin/env python3
"""P1R one-shot recovery VAL runner with durable request-level evidence."""
from __future__ import annotations
import base64,csv,hashlib,json,os,sqlite3,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from urllib import error,request
from PIL import Image

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization'); P1R=ROOT/'04_p1r_freeze_binding_recovery'; VAL=P1R/'val'; MAN=P1R/'preflight/recovery_val_manifest.csv'; FREEZE=P1R/'freeze/p1r_recovery_freeze.json'; TOKEN=P1R/'freeze/val_unlock_token.json'; CFG=P1R/'config/p1r_config.json'; PROMPT=ROOT/'00_definition/p0_prompt.txt'; RESAMPLE=getattr(getattr(Image,'Resampling',Image),'LANCZOS')
FIELDS=['request_id','media_id','split','event_label','sample_role','scenario_id','group_id','image_sha256','predicted_status','predicted_binary_alert','evidence','response_nonempty','thinking_present','http_ok','json_ok','schema_ok','canonical_ok','attempt_count','latency_seconds','done_reason','eval_count','is_correct','error_type']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def fsync_jsonl(f,obj):
 f.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
def atomic_json(p,obj):
 t=p.with_suffix(p.suffix+'.tmp')
 with t.open('w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def load_csv(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def preprocess(src,dst):
 with Image.open(src) as im:im.verify()
 with Image.open(src) as im:
  im=im.convert('RGB');im.thumbnail((448,336),RESAMPLE);c=Image.new('RGB',(448,336),(128,128,128));c.paste(im,((448-im.width)//2,(336-im.height)//2));c.save(dst,'JPEG',quality=70,optimize=True)
def parse(outer,http_ok,transport_error=''):
 if not http_ok:return 'protocol_failure','',False,False,False,False,'',None,transport_error
 response=outer.get('response','');thinking=outer.get('thinking','');nonempty=isinstance(response,str) and bool(response.strip());think=isinstance(thinking,str) and bool(thinking.strip())
 if not nonempty:return 'protocol_failure','',False,False,False,think,outer.get('done_reason',''),outer.get('eval_count'),'response_empty'
 try:o=json.loads(response)
 except Exception as e:return 'protocol_failure','',True,False,False,think,outer.get('done_reason',''),outer.get('eval_count'),'response_json_parse_failure: '+str(e)
 if not isinstance(o,dict) or set(o)!={'person_fallen','evidence'} or o.get('person_fallen') not in {'positive','negative','uncertain'} or not isinstance(o.get('evidence'),str) or not o['evidence'].strip():return 'protocol_failure','',True,True,False,think,outer.get('done_reason',''),outer.get('eval_count'),'response_schema_failure'
 return o['person_fallen'],o['evidence'].strip(),True,True,True,think,outer.get('done_reason',''),outer.get('eval_count'),''
def verify_unlock():
 t=json.loads(TOKEN.read_text());f=json.loads(FREEZE.read_text());
 if t.get('verification_status')!='PASS' or sha(FREEZE)!=t.get('freeze_sha256') or sha(MAN)!=t.get('val_manifest_sha256') or f.get('parser_source')!='response_only' or f.get('think') is not False:raise SystemExit('VAL_RUN_BLOCKED_FREEZE_OR_TOKEN_MISMATCH')
 cfg=json.loads(CFG.read_text())
 sem={'model':'qwen3.5:4b','endpoint':'http://192.168.20.62:11434','stream':False,'format':'json','think':False,'concurrency':1,'preprocess_mode':'letterbox','target_size':'448x336','jpeg_quality':70,'parser_source':'response_only','thinking_fallback':False,'attempts_per_media':1,'automatic_retry':False}
 if any(cfg.get(k)!=v for k,v in sem.items()) or cfg.get('options')!={'temperature':0,'num_ctx':8192,'num_predict':256}:raise SystemExit('VAL_RUN_BLOCKED_CONFIG_SEMANTICS_MISMATCH')
 if sha(PROMPT)!=f.get('prompt_sha256') or sha(CFG)!=f['file_hashes']['p1r_config']['sha256'] or sha(Path(__file__))!=f['file_hashes']['p1r_runner']['sha256']:raise SystemExit('VAL_RUN_BLOCKED_CURRENT_HASH_MISMATCH')
 return cfg,f,t
def init_db(rows,cfg_sha):
 db=VAL/'request_ledger.sqlite3';new=not db.exists();c=sqlite3.connect(db);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA synchronous=FULL');c.execute('CREATE TABLE IF NOT EXISTS metadata (k TEXT PRIMARY KEY,v TEXT NOT NULL)');c.execute('CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY,media_id TEXT UNIQUE NOT NULL,state TEXT NOT NULL,started_at TEXT,completed_at TEXT,attempt INTEGER NOT NULL,image_sha256 TEXT NOT NULL,config_sha256 TEXT NOT NULL,http_status INTEGER,latency_seconds REAL,response_sha256 TEXT,error_type TEXT)')
 if new:
  runid='P1R_VAL_'+datetime.now().strftime('%Y%m%d_%H%M%S');c.execute('INSERT INTO metadata(k,v) VALUES (?,?)',('run_id',runid));c.execute('INSERT INTO metadata(k,v) VALUES (?,?)',('manifest_sha256',sha(MAN)));c.execute('INSERT INTO metadata(k,v) VALUES (?,?)',('config_sha256',cfg_sha));
  for i,r in enumerate(rows,1):c.execute('INSERT INTO requests(request_id,media_id,state,attempt,image_sha256,config_sha256) VALUES (?,?,?,?,?,?)',(f'{runid}_{i:03d}',r['media_id'],'NOT_STARTED',1,r['image_sha256'],cfg_sha))
  c.commit();atomic_json(VAL/'run_metadata.json',{'run_id':runid,'created_at_utc':utc(),'manifest_sha256':sha(MAN),'config_sha256':cfg_sha,'runner_sha256':sha(Path(__file__)),'attempts_per_media':1,'automatic_retry':False,'planned_requests':len(rows),'prior_val_confirmed_exposure':10,'prior_val_possible_additional_exposure':1})
 else:
  if c.execute('SELECT v FROM metadata WHERE k="manifest_sha256"').fetchone()[0]!=sha(MAN) or c.execute('SELECT v FROM metadata WHERE k="config_sha256"').fetchone()[0]!=cfg_sha:raise SystemExit('VAL_RUN_BLOCKED_EXISTING_LEDGER_BINDING_MISMATCH')
 return c
def main():
 cfg,freeze,token=verify_unlock();rows=load_csv(MAN)
 if len(rows)!=100 or len({r['media_id'] for r in rows})!=100 or any(r['split']!='VAL' for r in rows) or any(r['event_label'] not in {'0','1'} for r in rows):raise SystemExit('VAL_RUN_BLOCKED_MANIFEST_INVALID')
 VAL.mkdir(exist_ok=True);(VAL/'responses').mkdir(exist_ok=True);(VAL/'processed_448x336').mkdir(exist_ok=True);db=init_db(rows,sha(CFG));events=(VAL/'request_events.jsonl').open('a',encoding='utf-8')
 unknown=db.execute("SELECT count(*) FROM requests WHERE state='STARTED'").fetchone()[0]
 if unknown:raise SystemExit('P1R_VAL_EXECUTION_INCOMPLETE_INDETERMINATE_REQUEST')
 byid={r['media_id']:r for r in rows};pending=db.execute("SELECT request_id,media_id FROM requests WHERE state='NOT_STARTED' ORDER BY request_id").fetchall()
 for n,(rid,mid) in enumerate(pending,1):
  r=byid[mid];started=utc();db.execute("UPDATE requests SET state='STARTED',started_at=? WHERE request_id=? AND state='NOT_STARTED'",(started,rid));db.commit();fsync_jsonl(events,{'event':'REQUEST_STARTED','request_id':rid,'media_id':mid,'timestamp_utc':started,'attempt':1,'image_sha256':r['image_sha256'],'config_sha256':sha(CFG)})
  dst=VAL/'processed_448x336'/(mid+'.jpg');preprocess(Path(r['image_path']),dst);payload={'model':cfg['model'],'prompt':PROMPT.read_text(),'images':[base64.b64encode(dst.read_bytes()).decode()],'stream':False,'format':'json','think':False,'options':cfg['options']};t=time.time()
  try:
   req=request.Request(cfg['endpoint']+'/api/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
   with request.urlopen(req,timeout=120) as resp:raw=resp.read().decode();code=resp.status
   outer=json.loads(raw);rp=VAL/'responses'/(rid+'.json');atomic_json(rp,outer);rh=sha(rp);lat=time.time()-t;db.execute("UPDATE requests SET state='COMPLETED',completed_at=?,http_status=?,latency_seconds=?,response_sha256=?,error_type='' WHERE request_id=?",(utc(),code,lat,rh,rid));db.commit();fsync_jsonl(events,{'event':'REQUEST_COMPLETED','request_id':rid,'media_id':mid,'timestamp_utc':utc(),'http_status':code,'latency_seconds':lat,'response_sha256':rh});
  except error.HTTPError as exc:
   lat=time.time()-t;db.execute("UPDATE requests SET state='FAILED_CONFIRMED',completed_at=?,http_status=?,latency_seconds=?,error_type=? WHERE request_id=?",(utc(),exc.code,lat,'HTTPError: '+str(exc),rid));db.commit();fsync_jsonl(events,{'event':'REQUEST_FAILED_CONFIRMED','request_id':rid,'media_id':mid,'timestamp_utc':utc(),'http_status':exc.code,'latency_seconds':lat,'error_type':'HTTPError: '+str(exc)})
  except (error.URLError,TimeoutError,KeyboardInterrupt) as exc:
   # State remains STARTED; the next launch must fail closed and never resend it.
   fsync_jsonl(events,{'event':'REQUEST_INTERRUPTED_OR_UNKNOWN','request_id':rid,'media_id':mid,'timestamp_utc':utc(),'error_type':type(exc).__name__+': '+str(exc)});events.close();db.close();raise SystemExit('P1R_VAL_EXECUTION_INCOMPLETE_INDETERMINATE_REQUEST')
  if n%10==0:print(f'P1R_VAL_PROGRESS completed_or_failed={n}/{len(pending)}',flush=True)
 events.close();db.close();print('P1R_VAL_EXECUTION_DURABLE_TERMINAL_COMPLETE')
if __name__=='__main__':main()
