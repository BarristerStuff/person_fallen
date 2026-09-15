#!/usr/bin/env python3
"""Durable, no-retry P2 inference runner for canary, SCREEN, and VAL."""
from __future__ import annotations
import argparse,base64,csv,hashlib,json,os,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path
from urllib import error,request
from PIL import Image

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization'
CFG=P2/'03_candidates/p2_request_config.json';CANDIDATE_FREEZE=P2/'03_candidates/candidate_freeze.json';CANDIDATE_ATTEST=P2/'03_candidates/candidate_freeze_attestation.json';WINNER_FREEZE=P2/'05_winner_freeze/p2_winner_freeze.json';WINNER_ATTEST=P2/'05_winner_freeze/p2_winner_freeze_attestation.json'
RESAMPLE=getattr(getattr(Image,'Resampling',Image),'LANCZOS')

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def load_rows(path):
 with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def atomic_json(path,obj):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def fsync_event(handle,obj):
 handle.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n');handle.flush();os.fsync(handle.fileno())
def prompt_path(candidate):return P2/'03_candidates'/('C0_BASELINE' if candidate=='C0' else candidate)/(candidate+'_prompt.txt')
def paths(phase,candidate):
 if phase=='canary':return P2/'03_candidates'/candidate/'canary',P2/'03_candidates/protocol_canary_manifest.csv'
 if phase=='screen':return P2/'04_screening'/candidate,P2/'01_internal_split/p2_screen_manifest.csv'
 if phase=='val':return P2/'06_val',ROOT/'04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv'
 raise ValueError(phase)
def preprocess(src,dst,cfg):
 with Image.open(src) as im:im.verify()
 with Image.open(src) as im:
  im=im.convert('RGB');im.thumbnail((cfg['target_width'],cfg['target_height']),RESAMPLE);canvas=Image.new('RGB',(cfg['target_width'],cfg['target_height']),tuple(cfg['letterbox_rgb']));canvas.paste(im,((cfg['target_width']-im.width)//2,(cfg['target_height']-im.height)//2));canvas.save(dst,'JPEG',quality=cfg['jpeg_quality'],optimize=cfg['jpeg_optimize'])
def verify_common(cfg,manifest,rows):
 if cfg!={
  'stage':'P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION','model':'qwen3.5:4b','model_digest':'2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd','ollama_version':'0.23.2','endpoint':'http://192.168.20.62:11434','stream':False,'format':'json','think':False,'options':{'temperature':0,'num_ctx':8192,'num_predict':256},'concurrency':1,'timeout_seconds':120,'attempts_per_media':1,'automatic_retry':False,'preprocess':'letterbox','target_width':448,'target_height':336,'jpeg_quality':70,'jpeg_optimize':True,'letterbox_rgb':[128,128,128],'parser_source':'response_only','thinking_fallback':False}:raise SystemExit('P2_RUN_BLOCKED_CONFIG_SEMANTICS')
 if not rows or len({r['media_id'] for r in rows})!=len(rows):raise SystemExit('P2_RUN_BLOCKED_MANIFEST_SHAPE')
 for row in rows:
  split=row.get('split') or row.get('original_split')
  if split=='HOLDOUT':raise SystemExit('P2_STATUS=INVALID_HOLDOUT_CONTAMINATION')
  image=Path(row['image_path'])
  if not image.is_file() or sha(image)!=row['image_sha256']:raise SystemExit('P2_RUN_BLOCKED_IMAGE_HASH_MISMATCH')
def verify_phase(phase,candidate,manifest):
 if phase=='canary':
  if candidate not in {'C1','C2','C3'}:raise SystemExit('P2_CANARY_CANDIDATE_INVALID')
  return
 if phase=='screen':
  freeze=json.loads(CANDIDATE_FREEZE.read_text());att=json.loads(CANDIDATE_ATTEST.read_text())
  if att.get('verification_result')!='PASS' or att.get('freeze_sha256')!=sha(CANDIDATE_FREEZE):raise SystemExit('P2_SCREEN_BLOCKED_CANDIDATE_FREEZE')
  if sha(manifest)!=freeze['screen_manifest_sha256'] or sha(CFG)!=freeze['request_config_sha256'] or sha(Path(__file__))!=freeze['runner_sha256'] or sha(prompt_path(candidate))!=freeze['candidates'][candidate]['prompt_sha256']:raise SystemExit('P2_SCREEN_BLOCKED_HASH_MISMATCH')
  return
 if phase=='val':
  freeze=json.loads(WINNER_FREEZE.read_text());att=json.loads(WINNER_ATTEST.read_text())
  if att.get('verification_result')!='PASS' or att.get('freeze_sha256')!=sha(WINNER_FREEZE) or freeze.get('winner_candidate_id')!=candidate:raise SystemExit('P2_VAL_BLOCKED_WINNER_FREEZE')
  if sha(manifest)!=freeze['val_manifest_sha256'] or sha(CFG)!=freeze['config_sha256'] or sha(Path(__file__))!=freeze['runner_sha256'] or sha(prompt_path(candidate))!=freeze['prompt_sha256']:raise SystemExit('P2_VAL_BLOCKED_HASH_MISMATCH')
def init_db(run_dir,rows,manifest,candidate,phase):
 db=run_dir/'request_ledger.sqlite3';new=not db.exists();conn=sqlite3.connect(db);conn.execute('PRAGMA journal_mode=WAL');conn.execute('PRAGMA synchronous=FULL');conn.execute('CREATE TABLE IF NOT EXISTS metadata (k TEXT PRIMARY KEY,v TEXT NOT NULL)');conn.execute('CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY,media_id TEXT UNIQUE NOT NULL,state TEXT NOT NULL,started_at TEXT,completed_at TEXT,attempt INTEGER NOT NULL,image_sha256 TEXT NOT NULL,config_sha256 TEXT NOT NULL,prompt_sha256 TEXT NOT NULL,http_status INTEGER,latency_seconds REAL,response_sha256 TEXT,error_type TEXT)')
 run_id=f'P2_{phase.upper()}_{candidate}_'+datetime.now().strftime('%Y%m%d_%H%M%S')
 if new:
  metadata={'run_id':run_id,'phase':phase,'candidate':candidate,'manifest_sha256':sha(manifest),'config_sha256':sha(CFG),'prompt_sha256':sha(prompt_path(candidate)),'runner_sha256':sha(Path(__file__)),'planned_requests':str(len(rows)),'automatic_retry':'false'}
  conn.executemany('INSERT INTO metadata(k,v) VALUES (?,?)',metadata.items())
  for idx,row in enumerate(rows,1):conn.execute('INSERT INTO requests(request_id,media_id,state,attempt,image_sha256,config_sha256,prompt_sha256) VALUES (?,?,?,?,?,?,?)',(f'{run_id}_{idx:03d}',row['media_id'],'NOT_STARTED',1,row['image_sha256'],sha(CFG),sha(prompt_path(candidate))))
  conn.commit()
 else:
  metadata=dict(conn.execute('SELECT k,v FROM metadata'))
  if metadata.get('manifest_sha256')!=sha(manifest) or metadata.get('config_sha256')!=sha(CFG) or metadata.get('prompt_sha256')!=sha(prompt_path(candidate)):raise SystemExit('P2_RUN_BLOCKED_EXISTING_LEDGER_BINDING')
 return conn
def main():
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['canary','screen','val']);ap.add_argument('candidate',choices=['C0','C1','C2','C3']);args=ap.parse_args();cfg=json.loads(CFG.read_text());run_dir,manifest=paths(args.phase,args.candidate);run_dir.mkdir(parents=True,exist_ok=True);rows=load_rows(manifest);verify_common(cfg,manifest,rows)
 if args.phase=='canary' and any(r['p2_internal_role']!='P2_DESIGN' for r in rows):raise SystemExit('P2_CANARY_NOT_DESIGN_ONLY')
 if args.phase=='screen' and (len(rows)!=120 or any(r['p2_internal_role']!='P2_SCREEN' for r in rows)):raise SystemExit('P2_SCREEN_MANIFEST_INVALID')
 if args.phase=='val' and (len(rows)!=100 or any(r.get('split')!='VAL' for r in rows)):raise SystemExit('P2_VAL_MANIFEST_INVALID')
 verify_phase(args.phase,args.candidate,manifest);(run_dir/'responses').mkdir(exist_ok=True);(run_dir/'processed_448x336').mkdir(exist_ok=True);conn=init_db(run_dir,rows,manifest,args.candidate,args.phase)
 if conn.execute("SELECT count(*) FROM requests WHERE state='STARTED'").fetchone()[0]:raise SystemExit('P2_RUN_INCOMPLETE_INDETERMINATE_REQUEST')
 by_id={r['media_id']:r for r in rows};pending=conn.execute("SELECT request_id,media_id FROM requests WHERE state='NOT_STARTED' ORDER BY request_id").fetchall();events=(run_dir/'request_events.jsonl').open('a',encoding='utf-8');prompt=prompt_path(args.candidate).read_text(encoding='utf-8')
 for index,(request_id,media_id) in enumerate(pending,1):
  row=by_id[media_id];started=utc();conn.execute("UPDATE requests SET state='STARTED',started_at=? WHERE request_id=? AND state='NOT_STARTED'",(started,request_id));conn.commit();fsync_event(events,{'event':'REQUEST_STARTED','request_id':request_id,'media_id':media_id,'timestamp_utc':started,'attempt':1,'image_sha256':row['image_sha256'],'config_sha256':sha(CFG),'prompt_sha256':sha(prompt_path(args.candidate))})
  processed=run_dir/'processed_448x336'/(media_id+'.jpg');preprocess(Path(row['image_path']),processed,cfg);payload={'model':cfg['model'],'prompt':prompt,'images':[base64.b64encode(processed.read_bytes()).decode()],'stream':False,'format':'json','think':False,'options':cfg['options']};started_clock=time.time()
  try:
   req=request.Request(cfg['endpoint']+'/api/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
   with request.urlopen(req,timeout=cfg['timeout_seconds']) as response:raw=response.read().decode();code=response.status
   try:outer=json.loads(raw);outer_error=''
   except Exception as exc:outer={};outer_error=type(exc).__name__+': '+str(exc)
   wrapper={'request_id':request_id,'media_id':media_id,'http_status':code,'outer_raw':raw,'outer_json':outer,'outer_json_error':outer_error,'request_payload_without_image':{k:v for k,v in payload.items() if k!='images'},'image_sha256':row['image_sha256'],'timestamp_start_utc':started,'timestamp_end_utc':utc()};response_path=run_dir/'responses'/(request_id+'.json');atomic_json(response_path,wrapper);latency=time.time()-started_clock;conn.execute("UPDATE requests SET state='COMPLETED',completed_at=?,http_status=?,latency_seconds=?,response_sha256=?,error_type='' WHERE request_id=?",(utc(),code,latency,sha(response_path),request_id));conn.commit();fsync_event(events,{'event':'REQUEST_COMPLETED','request_id':request_id,'media_id':media_id,'timestamp_utc':utc(),'http_status':code,'latency_seconds':latency,'response_sha256':sha(response_path)})
  except error.HTTPError as exc:
   latency=time.time()-started_clock;conn.execute("UPDATE requests SET state='FAILED_CONFIRMED',completed_at=?,http_status=?,latency_seconds=?,error_type=? WHERE request_id=?",(utc(),exc.code,latency,'HTTPError: '+str(exc),request_id));conn.commit();fsync_event(events,{'event':'REQUEST_FAILED_CONFIRMED','request_id':request_id,'media_id':media_id,'timestamp_utc':utc(),'http_status':exc.code,'latency_seconds':latency,'error_type':'HTTPError: '+str(exc)})
  except (error.URLError,TimeoutError,KeyboardInterrupt) as exc:
   fsync_event(events,{'event':'REQUEST_INTERRUPTED_OR_UNKNOWN','request_id':request_id,'media_id':media_id,'timestamp_utc':utc(),'error_type':type(exc).__name__+': '+str(exc)});events.close();conn.close();raise SystemExit('P2_RUN_INCOMPLETE_INDETERMINATE_REQUEST')
  if index%10==0 or index==len(pending):print(f'P2_{args.phase.upper()}_{args.candidate}_PROGRESS={index}/{len(pending)}',flush=True)
 events.close();states=dict(conn.execute('SELECT state,count(*) FROM requests GROUP BY state'));conn.close();print(json.dumps({'phase':args.phase,'candidate':args.candidate,'ledger_states':states,'new_requests':len(pending),'holdout_requests':0},sort_keys=True))
if __name__=='__main__':main()
