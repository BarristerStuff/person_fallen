#!/usr/bin/env python3
"""One independently-authorized Q7 network-stability generation window.

This runner is deliberately separate from Q6.  It has one provider-call site,
uses the Q7 structured classifier, persists STARTED before every provider call,
and treats a transport ambiguity as COMPLETION_UNKNOWN before considering any
quota/retry guard.
"""
from __future__ import annotations

import argparse, csv, fcntl, hashlib, importlib.util, json, os, re, shutil
import sqlite3, subprocess, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from PIL import Image

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
GR3=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen'
PREP=GR3/'06_execution/quota_campaign_window_04_gr3q7_20260831_01'
Q6=GR3/'06_execution/quota_campaign_window_03_gr3q6_authorized_20260831_01'
Q5=GR3/'06_execution/quota_campaign_window_02_policy_adapter_20260830_01'
EXEC=GR3/'06_execution/quota_campaign_window_04_gr3q7_authorized_20260831_01'
PLAN=PREP/'02_plan/q7_network_stability_balanced_20_plan.csv'
MANIFEST=GR3/'03_fullregen_plan/full_regen_prompt_manifest.csv'
ADAPTER=Q5/'01_adapter/render_prompt_manifest_v1.csv'
CLASSIFIER=PREP/'provider_failure_classifier_v2.py'
PARSER=GR3/'06_execution/quota_campaign_window_03_gr3q6_20260831_02/retry_event_parser_v2.py'
CLI=Path('/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs')
VALIDATOR=Path('/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py')
ANN=Path('/home/yanbo/net_vlm_xunjian_dataset/01_annotations')
LOCK=GR3/'06_execution/.p4d_gr3q7_active_runner.lock'
DB=EXEC/'03_ledger/gr3q7_execution.sqlite3'; RAW=EXEC/'04_raw_responses'; RIMG=EXEC/'07_generated_raw'; FINAL=EXEC/'08_final'; QA=EXEC/'06_partial_qa'; CHECK=EXEC/'05_checkpoints'; PRE=EXEC/'00_preflight'
MODEL='gpt-5.4'; PROVIDER='codex'; BACKEND='image_generation'; ADAPTER_VERSION='CODEX_SAFE_STAGED_CV_V1'; NATIVE='1536x1024'; QUALITY='medium'; FINAL_SIZE=(1920,1080)
MAX_LOGICAL=20; MAX_PHYSICAL=24; MAX_RETRIES=3; MAX_REFUSALS=3
E_PREP='9ac34d6335c48883845e1bcb8d254596623a13f9625d93a406570d80461cc8c5'; E_SUPP='5df11b38536a05afb0fec14b89cb6f61a31bafb5dc6f8fef1cc686b371f6d859'; E_Q6='95df937db097e23f2e3939fbd132f3e9a24a20bff3d0d91eb174285a082d8d52'; E_Q6E='4719e6fa842ada2346596bb3316661926082e5a741c7217740d6143c3a13010b'; E_PLAN='4b6b44597f6d91a0b754f70a3e460cb8bba45fcf8f03f1cab288e7fec6f7149f'; E_CLASS='fbd773b5d5d131f06abd334e041377fc5e0c7b9c0e5e6179164979c2abb624c0'

def now(): return datetime.now(timezone.utc).isoformat(timespec='milliseconds')
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def jwrite(p:Path,x:Any):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+'.tmp')
 with t.open('w',encoding='utf-8') as f: json.dump(x,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p); fd=os.open(str(p.parent),os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def jappend(p:Path,x:Any):
 with p.open('a',encoding='utf-8') as f:f.write(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
def rows(p:Path):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def parse(s:str):
 try:
  x=json.loads(s);return x if isinstance(x,dict) else {'ok':False,'error':{'code':'invalid_provider_output'}}
 except Exception:return {'ok':False,'error':{'code':'invalid_provider_output','message':'stdout is not JSON'}}
def scrub(s:str): return re.sub(r'(?i)(authorization\s*:\s*bearer\s+)[^\s"\']+',r'\1<REDACTED>',s)
def text(x:Any)->str:
 if isinstance(x,dict):return ' '.join(text(v) for v in x.values())
 if isinstance(x,list):return ' '.join(text(v) for v in x)
 return str(x)
def status(payload:dict,rc:int|None):
 m=re.search(r'\bHTTP\s*(\d{3})\b',text(payload),re.I) or re.search(r'\b(429|401|403|5\d\d)\b',text(payload))
 return int(m.group(1)) if m else (200 if rc==0 and payload.get('ok') is True else None)
def loadmod(name:str,p:Path):
 spec=importlib.util.spec_from_file_location(name,p)
 if not spec or not spec.loader:raise RuntimeError(f'cannot import {p}')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def verify(f:Path,expect:str,all_artifacts:bool=True):
 actual=sha(f); side=f.with_name(f.name+'.sha256'); sideok=side.is_file() and side.read_text().split()[0]==actual
 x=json.loads(f.read_text()); checks={p:Path(p).is_file() and sha(Path(p))==h for p,h in x.get('artifact_sha256',{}).items()}
 result={'path':str(f),'expected_sha256':expect,'actual_sha256':actual,'sidecar_match':sideok,'bound_artifact_count':len(checks),'all_bound_artifacts_match':all(checks.values()),'mismatched_artifacts':[p for p,v in checks.items() if not v]}
 if actual!=expect or not sideok or (all_artifacts and not all(checks.values())):raise RuntimeError('freeze integrity failure '+json.dumps(result,ensure_ascii=False))
 return result
def validator(label:str):
 proc=subprocess.run(['python3',str(VALIDATOR),'--json'],capture_output=True,text=True,timeout=240); x=parse(proc.stdout); hits={}
 for n in ('media.csv','labels.csv','batches.csv','splits.csv'):
  p=ANN/n; hits[n]=sum('p4d' in q.lower() or 'person-fallen-v2-p4d' in q.lower() for q in p.read_text(encoding='utf-8').splitlines()[1:])
 out={'captured_at':now(),'returncode':proc.returncode,'validator':x,'p4d_active_reference_hits':hits,'p4d_active_reference_total':sum(hits.values())};jwrite(PRE/f'dataset_{label}.json',out)
 if proc.returncode or x.get('status')!='valid' or x.get('error_count')!=0 or not x.get('full_hash_check') or out['p4d_active_reference_total']!=0:raise RuntimeError('dataset gate failed')
 return out
def convert(raw:Path,final:Path):
 with Image.open(raw) as im:im.verify()
 with Image.open(raw) as im:
  im.load();w,h=im.size;im=im.convert('RGB');target=16/9;r=w/h
  if r>target: cw=round(h*target);box=((w-cw)//2,0,(w-cw)//2+cw,h)
  elif r<target:ch=round(w/target);box=(0,(h-ch)//2,w,(h-ch)//2+ch)
  else:box=(0,0,w,h)
  rs=getattr(getattr(Image,'Resampling',Image),'LANCZOS'); o=im.crop(box).resize(FINAL_SIZE,rs);t=final.with_name(final.name+'.tmp');o.save(t,'PNG')
 with Image.open(t) as im:im.verify()
 with Image.open(t) as im:im.load();fw,fh=im.size
 if (fw,fh)!=FINAL_SIZE:raise RuntimeError('final dimension mismatch')
 os.replace(t,final);return {'native_width':w,'native_height':h,'final_width':fw,'final_height':fh,'crop_box':list(box),'resize_method':'Pillow_LANCZOS'}
def event(db,pid,typ,x):db.execute('INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)',(pid,typ,json.dumps(x,ensure_ascii=False,sort_keys=True),now()))

def init():
 if EXEC.exists():raise RuntimeError(f'execution revision exists: {EXEC}')
 # Q6 erratum's only mutable artifact is the append-only overview.  Its seal,
 # sidecar and all immutable Q6 evidence remain exact; Q7 supplement freezes
 # the current overview.  Record this exception rather than rewriting history.
 prep=verify(PREP/'freeze/p4d_gr3q7_preparation_freeze.json',E_PREP);supp=verify(PREP/'freeze/p4d_gr3q7_preparation_supplement_freeze.json',E_SUPP);q6=verify(Q6/'freeze/p4d_gr3q6_execution_terminal_freeze.json',E_Q6);q6e=verify(Q6/'freeze/p4d_gr3q6_execution_post_freeze_erratum.json',E_Q6E,False)
 if q6e['mismatched_artifacts'] != [str(ROOT/'PERSON_FALLEN_V2.md')]:raise RuntimeError('unexpected Q6 erratum bound-artifact drift')
 if sha(PLAN)!=E_PLAN or sha(CLASSIFIER)!=E_CLASS:raise RuntimeError('plan/classifier hash mismatch')
 plan=rows(PLAN); universe=rows(MANIFEST); succ=rows(PREP/'01_inventory/verified_success.csv'); unknown=rows(PREP/'01_inventory/completion_unknown_quarantine.csv'); safe=rows(PREP/'01_inventory/safe_executable_outstanding.csv')
 if len(plan)!=20 or len({x['prompt_id'] for x in plan})!=20 or Counter(x['role'] for x in plan)!=Counter({'positive':15,'hard_negative':5}) or Counter(x['planned_split'] for x in plan)!=Counter({'NEW_DESIGN':10,'NEW_SCREEN':10}):raise RuntimeError('Q7 plan rows/role/split mismatch')
 groups=['PF_P4D_POS_INTENTIONAL_G001','PF_P4D_POS_MULTI_G001','PF_P4D_POS_CORRIDOR_G001','PF_P4D_HN_SQUAT_G006']
 if [x['group_id'] for x in plan[::5]]!=groups or any('MAINT_G006' in x['prompt_id'] for x in plan):raise RuntimeError('Q7 group/order/isolation mismatch')
 a={x['prompt_id'] for x in succ};b={x['prompt_id'] for x in unknown};c={x['prompt_id'] for x in safe};u={x['prompt_id'] for x in universe}
 if (len(a),len(b),len(c))!=(151,1,288) or a&b or a&c or b&c or a|b|c!=u or any(x['prompt_id'] not in c for x in plan):raise RuntimeError('authoritative Q7 partition mismatch')
 if b!={'PF_P4D_HN_MAINT_G006_V02'}:raise RuntimeError('Q6 unknown identity mismatch')
 regress=json.loads((PREP/'00_preflight/classifier_regression.json').read_text())
 if regress.get('pass_count')!=3 or regress.get('total')!=3 or regress.get('classifier_sha256')!=E_CLASS:raise RuntimeError('classifier regression mismatch')
 EXEC.mkdir()
 for d in ('00_preflight','01_authorization','02_runner','03_ledger','04_raw_responses','05_checkpoints','06_partial_qa','07_generated_raw','08_final','freeze'):(EXEC/d).mkdir()
 runtime_proc=subprocess.run(['node',str(CLI),'--json','--provider','codex','doctor'],capture_output=True,text=True,timeout=90);runtime={'returncode':runtime_proc.returncode,'payload':parse(runtime_proc.stdout),'provider_requests':0}
 if runtime_proc.returncode or runtime['payload'].get('ok') is not True or runtime['payload'].get('provider_selection',{}).get('resolved')!='codex':raise RuntimeError('provider readiness failed')
 before=validator('before')
 jwrite(PRE/'parent_freeze_verification.json',{'q7_preparation':prep,'q7_supplement':supp,'q6_original':q6,'q6_erratum_seal':q6e,'q6_erratum_overview_append_only_exception':True})
 jwrite(PRE/'provider_runtime.json',runtime)
 jwrite(EXEC/'01_authorization/authorization.json',{'authorized':True,'stage':'P4D_GR3Q7_NETWORK_STABILITY_RECOVERY','max_logical_invocations':20,'concurrency':1,'outer_retry':False,'native_max_retries':3,'max_physical_attempt_lower_bound':24,'max_unique_native_retry_events':3,'max_confirmed_policy_refusals':3,'formal_ingest':False,'c3':False,'new_val':0,'val':0,'holdout_requests':0})
 for src,dst in [(PLAN,'q7_network_stability_balanced_20_plan.csv'),(CLASSIFIER,'provider_failure_classifier_v2.py'),(PARSER,'retry_event_parser_v2.py'),(Path(__file__),Path(__file__).name)]:shutil.copy2(src,EXEC/'02_runner'/dst)
 config={'provider':PROVIDER,'request_model':MODEL,'generation_backend':BACKEND,'runtime_expected':'0.7.3','adapter_version':ADAPTER_VERSION,'native_size':NATIVE,'quality':QUALITY,'format':'png','final_size':list(FINAL_SIZE),'concurrency':1,'outer_retry':False,'native_max_retries':3,'semantic_frozen_prompt_changed':False,'provider_render_prompt_changed':True,'q7_plan_sha256':sha(PLAN),'classifier_v2_sha256':sha(CLASSIFIER),'runner_sha256':sha(Path(__file__))};jwrite(EXEC/'02_runner/run_config.json',config)
 db=sqlite3.connect(DB)
 try:
  db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL');db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('CREATE TABLE slots(ord INTEGER PRIMARY KEY,prompt_id TEXT UNIQUE,group_id TEXT,variant_id TEXT,role TEXT,taxonomy TEXT,planned_split TEXT,render_prompt_sha256 TEXT,state TEXT,started_at TEXT,finished_at TEXT,http_status INTEGER,error_class TEXT,error_reason TEXT,raw_path TEXT,final_path TEXT,raw_sha256 TEXT,final_sha256 TEXT,native_width INTEGER,native_height INTEGER,final_width INTEGER,final_height INTEGER,crop_box TEXT,latency_seconds REAL,native_retry_events INTEGER DEFAULT 0,request_started_events INTEGER DEFAULT 0,physical_attempt_lower_bound INTEGER DEFAULT 0)');db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,prompt_id TEXT,event_type TEXT,payload_json TEXT,captured_at TEXT)')
  db.executemany('INSERT INTO slots(ord,prompt_id,group_id,variant_id,role,taxonomy,planned_split,render_prompt_sha256,state) VALUES(?,?,?,?,?,?,?,?,?)',[(int(r['q7_order']),r['prompt_id'],r['group_id'],r['variant_id'],r['role'],r['taxonomy'],r['planned_split'],r['render_prompt_sha256'],'NOT_STARTED') for r in plan]);db.executemany('INSERT INTO meta VALUES(?,?)',[('stage','P4D_GR3Q7_NETWORK_STABILITY_RECOVERY'),('authorization','true'),('provider_requests','0')]);db.commit();db.execute('PRAGMA wal_checkpoint(FULL)')
 finally:db.close()
 jwrite(CHECK/'ready.json',{'status':'READY_FOR_AUTHORIZED_EXECUTION','provider_requests':0,'starting_verified_success':151,'starting_completion_unknown':1,'starting_safe_executable_outstanding':288,'dataset_before':before});print(json.dumps({'status':'READY_FOR_AUTHORIZED_EXECUTION','execution_revision':str(EXEC),'plan_sha256':sha(PLAN)}))

def terminal(stop:str,simultaneous:str|None):
 db=sqlite3.connect(DB);db.row_factory=sqlite3.Row
 try:
  slots=[dict(x) for x in db.execute('SELECT * FROM slots ORDER BY ord')];db.commit();db.execute('PRAGMA wal_checkpoint(FULL)')
 finally:db.close()
 base_s=rows(PREP/'01_inventory/verified_success.csv');base_u=rows(PREP/'01_inventory/completion_unknown_quarantine.csv');manifest={x['prompt_id']:x for x in rows(MANIFEST)}
 good=[x for x in slots if x['state']=='SUCCESS'];newu=[x for x in slots if x['state']=='COMPLETION_UNKNOWN'];successful={x['prompt_id'] for x in base_s}|{x['prompt_id'] for x in good};unknown={x['prompt_id'] for x in base_u}|{x['prompt_id'] for x in newu};allids=set(manifest);safe=allids-successful-unknown
 if successful&unknown or successful|unknown|safe!=allids:raise RuntimeError('final partition failure')
 def rec(pid,source):
  m=manifest[pid];s=next((x for x in good if x['prompt_id']==pid),None);return {'prompt_id':pid,'role':m.get('role',m.get('target_role')),'taxonomy':m['taxonomy'],'planned_split':m.get('planned_split',m.get('planned_internal_split')),'source':source,'raw_path':s['raw_path'] if s else '', 'final_path':s['final_path'] if s else '', 'raw_sha256':s['raw_sha256'] if s else '', 'final_sha256':s['final_sha256'] if s else '', 'adapter_version':ADAPTER_VERSION}
 def outcsv(p,rs):
  keys=['prompt_id','role','taxonomy','planned_split','source','raw_path','final_path','raw_sha256','final_sha256','adapter_version'];
  with p.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rs)
 outcsv(QA/'verified_success.csv',[rec(x['prompt_id'],x.get('source','PRE_Q7_VERIFIED')) for x in base_s]+[rec(x['prompt_id'],'Q7_EXECUTION') for x in good])
 outcsv(QA/'completion_unknown_quarantine.csv',[rec(x['prompt_id'],x.get('source','PRE_Q7_UNKNOWN')) for x in base_u]+[rec(x['prompt_id'],'Q7_EXECUTION_UNKNOWN') for x in newu])
 outcsv(QA/'safe_executable_outstanding.csv',[rec(pid,'SAFE_EXECUTABLE_OUTSTANDING') for pid in sorted(safe)])
 oldhash=set();gr1hash=set();
 for p in GR3.rglob('*.png'):
  if EXEC not in p.parents:
   try:oldhash.add(sha(p))
   except OSError:pass
 gr1=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr1_generation_resume'
 if gr1.exists():
  for p in gr1.rglob('*.png'):
   try:gr1hash.add(sha(p))
   except OSError:pass
 dup=sum(x['raw_sha256'] in oldhash or x['final_sha256'] in oldhash for x in good);g1=sum(x['raw_sha256'] in gr1hash or x['final_sha256'] in gr1hash for x in good)
 allgood=[rec(x['prompt_id'],x.get('source','PRE_Q7_VERIFIED')) for x in base_s]+[rec(x['prompt_id'],'Q7_EXECUTION') for x in good]
 qa={'partial_mechanical_qa':'PASS' if not any(x['state']=='MECHANICAL_QA_FAILED' for x in slots) else 'FAIL','new_raw_count':len(good),'new_final_count':len(good),'pillow_failures':sum(x['state']=='MECHANICAL_QA_FAILED' for x in slots),'dimension_failures':0,'exact_duplicate_hits':dup,'gr1_sha_hits':g1,'adapter_provenance':'PASS','profile_provenance':'RECORDED','full_440_qa':'NOT_REACHED' if len(successful)<440 else 'REACHED','P4D_IMAGES_ACCEPTED':0,'current_verified_success':len(successful),'current_completion_unknown':len(unknown),'current_safe_executable_outstanding':len(safe),'role_distribution':dict(Counter(x['role'] for x in allgood)),'split_distribution':dict(Counter(x['planned_split'] for x in allgood)),'taxonomy_distribution':dict(Counter(x['taxonomy'] for x in allgood))};jwrite(QA/'partial_qa.json',qa)
 after=validator('after');cnt=Counter(x['state'] for x in slots);http=Counter(str(x['http_status']) for x in slots if x['http_status'] is not None)
 summary={'stage':'P4D_GR3Q7_NETWORK_STABILITY_RECOVERY','status':stop,'stop_reason': 'NETWORK_ERROR_COMPLETION_AMBIGUITY' if stop=='STOPPED_COMPLETION_UNKNOWN' else stop,'simultaneous_guard_reached':simultaneous,'starting_verified_success':151,'starting_completion_unknown':1,'starting_safe_executable_outstanding':288,'q7_plan_sha256':sha(PLAN),'q7_plan_rows':20,'q7_groups':['PF_P4D_POS_INTENTIONAL_G001','PF_P4D_POS_MULTI_G001','PF_P4D_POS_CORRIDOR_G001','PF_P4D_HN_SQUAT_G006'],'provider':PROVIDER,'request_model':MODEL,'generation_backend':BACKEND,'runtime_version':'0.7.3','adapter_version':ADAPTER_VERSION,'logical_invocations':sum(x['state']!='NOT_STARTED' for x in slots),'success':cnt['SUCCESS'],'content_policy_refusals':cnt['CONTENT_POLICY_REFUSAL_CONFIRMED'],'other_confirmed_failures':cnt['FAILED_CONFIRMED']+cnt['MECHANICAL_QA_FAILED'],'new_completion_unknown':cnt['COMPLETION_UNKNOWN'],'unique_native_retry_events':sum(x['native_retry_events'] for x in slots),'observed_physical_attempt_lower_bound':sum(x['physical_attempt_lower_bound'] for x in slots),'http200':http['200'],'http429':http['429'],'http401':http['401'],'http403':http['403'],'http5xx':sum(v for k,v in http.items() if k.startswith('5')),'network_errors':cnt['COMPLETION_UNKNOWN'],'timeouts':0,'current_verified_success':len(successful),'current_completion_unknown':len(unknown),'current_safe_executable_outstanding':len(safe),'qa':qa,'formal_ingest':False,'media_added':0,'labels_added':0,'c3':False,'new_val':0,'val':0,'holdout_requests':0,'holdout_consumed':False,'dataset_after':after};jwrite(CHECK/'terminal_summary.json',summary)
 artifacts=[DB,EXEC/'01_authorization/authorization.json',EXEC/'02_runner/q7_network_stability_balanced_20_plan.csv',EXEC/'02_runner/provider_failure_classifier_v2.py',EXEC/'02_runner/retry_event_parser_v2.py',EXEC/'02_runner'/Path(__file__).name,EXEC/'02_runner/run_config.json',PRE/'parent_freeze_verification.json',PRE/'provider_runtime.json',PRE/'dataset_before.json',PRE/'dataset_after.json',CHECK/'ready.json',CHECK/'global_stop.json',CHECK/'terminal_summary.json',QA/'partial_qa.json',QA/'verified_success.csv',QA/'completion_unknown_quarantine.csv',QA/'safe_executable_outstanding.csv',*sorted(RAW.glob('*.json')),*sorted(RIMG.glob('*.png')),*sorted(FINAL.glob('*.png'))]
 f=EXEC/'freeze/p4d_gr3q7_execution_terminal_freeze.json';jwrite(f,{'stage':summary['stage'],'terminal':summary,'artifact_sha256':{str(p):sha(p) for p in artifacts}});d=sha(f);f.with_name(f.name+'.sha256').write_text(f'{d}  {f.name}\n',encoding='utf-8');v={'freeze_sha256':d,'sidecar_match':f.with_name(f.name+'.sha256').read_text().split()[0]==d,'bound_artifact_count':len(artifacts),'all_bound_artifacts_match':all(sha(Path(p))==h for p,h in json.loads(f.read_text())['artifact_sha256'].items())};jwrite(CHECK/'terminal_freeze_verification.json',v);return summary|{'sqlite_canonical_sha256':sha(DB),'execution_terminal_freeze_sha256':d,'terminal_freeze_verification':v}

def run():
 if not EXEC.exists() or (EXEC/'freeze/p4d_gr3q7_execution_terminal_freeze.json').exists():raise RuntimeError('missing init or terminal sealed')
 fp=LOCK.open('w')
 try:
  try:fcntl.flock(fp.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise RuntimeError('BLOCKED_CONCURRENT_RUNNER')
  external=[]
  for line in subprocess.run(['ps','-eo','pid=,args='],capture_output=True,text=True,check=True).stdout.splitlines():
   xs=line.strip().split(None,1)
   if len(xs)==2 and Path(__file__).name in xs[1] and int(xs[0]) not in {os.getpid(),os.getppid()}:external.append(line)
  if external:raise RuntimeError('BLOCKED_CONCURRENT_RUNNER '+str(external))
  parser=loadmod('q7parser',EXEC/'02_runner/retry_event_parser_v2.py');classifier=loadmod('q7classifier',EXEC/'02_runner/provider_failure_classifier_v2.py');render={x['prompt_id']:x for x in rows(ADAPTER)};plan=rows(EXEC/'02_runner/q7_network_stability_balanced_20_plan.csv');db=sqlite3.connect(DB);db.row_factory=sqlite3.Row;stop=None;sim=None
  try:
   for r in plan:
    slot=dict(db.execute('SELECT * FROM slots WHERE prompt_id=?',(r['prompt_id'],)).fetchone())
    if slot['state']!='NOT_STARTED':raise RuntimeError('non-pristine slot')
    db.execute("UPDATE slots SET state='STARTED',started_at=? WHERE prompt_id=?",(now(),r['prompt_id']));event(db,r['prompt_id'],'STARTED',{'q7_order':r['q7_order']});db.commit()
    request={'model':MODEL,'provider':PROVIDER,'generation_backend':BACKEND,'size':NATIVE,'quality':QUALITY,'format':'png','adapter_version':ADAPTER_VERSION,'render_prompt_sha256':r['render_prompt_sha256'],'outer_retry':False,'native_max_retries':3};jappend(EXEC/'request_log.jsonl',{'timestamp':now(),'prompt_id':r['prompt_id'],'split':r['planned_split'],'request':request})
    rawp=RIMG/(r['prompt_id']+'.png');fin=FINAL/(r['prompt_id']+'.png');cmd=['node',str(CLI),'--json','--json-events','--provider','codex','images','generate','--model',MODEL,'--prompt',render[r['prompt_id']]['render_prompt'],'--out',str(rawp),'--format','png','--size',NATIVE,'--quality',QUALITY]
    t=time.monotonic();proc=None;timed=False
    try:proc=subprocess.run(cmd,capture_output=True,text=True,timeout=1800)
    except subprocess.TimeoutExpired as e:timed=True;stdout=e.stdout or '';stderr=e.stderr or ''
    else:stdout=proc.stdout;stderr=proc.stderr
    if isinstance(stdout,bytes):stdout=stdout.decode('utf-8','replace')
    if isinstance(stderr,bytes):stderr=stderr.decode('utf-8','replace')
    outer=parse(stdout);tele=parser.telemetry_from_events(parser.parse_json_events(stderr));hs=status(outer,proc.returncode if proc else None);lat=time.monotonic()-t;details={};classification=None
    ok=bool(proc and proc.returncode==0 and outer.get('ok') is True and rawp.is_file() and rawp.stat().st_size>0)
    if timed:state='COMPLETION_UNKNOWN';reason='TIMEOUT_COMPLETION_AMBIGUITY';err='subprocess timeout'
    elif ok:
     try:details=convert(rawp,fin);state='SUCCESS';reason='NONE';err=''
     except Exception as e:state='MECHANICAL_QA_FAILED';reason='MECHANICAL_QA_FAILED';err=str(e)
    else:
     classification=classifier.classify({'outer_json':outer,'stderr_redacted':scrub(stderr)});state=classification['state'];reason=classification['reason'];err=text(outer)[:800]
    raw={'prompt_id':r['prompt_id'],'command_config':request,'returncode':proc.returncode if proc else None,'http_status':hs,'outer_json':outer,'stderr_redacted':scrub(stderr),'state':state,'failure_classification':classification,'failure_reason':reason,'latency_seconds':lat,'telemetry':tele,'timeout':timed,'adapter_version':ADAPTER_VERSION,'render_prompt_sha256':r['render_prompt_sha256']};jwrite(RAW/(r['prompt_id']+'.json'),raw);jappend(EXEC/'raw_responses.jsonl',raw)
    db.execute('UPDATE slots SET state=?,finished_at=?,http_status=?,error_class=?,error_reason=?,raw_path=?,final_path=?,raw_sha256=?,final_sha256=?,native_width=?,native_height=?,final_width=?,final_height=?,crop_box=?,latency_seconds=?,native_retry_events=?,request_started_events=?,physical_attempt_lower_bound=? WHERE prompt_id=?',(state,now(),hs,state,reason,str(rawp) if rawp.exists() else None,str(fin) if fin.exists() else None,sha(rawp) if rawp.exists() else None,sha(fin) if fin.exists() else None,details.get('native_width'),details.get('native_height'),details.get('final_width'),details.get('final_height'),json.dumps(details.get('crop_box')) if details else None,lat,tele['unique_native_retry_events'],tele['request_started_events'],tele['physical_attempt_lower_bound'],r['prompt_id']));event(db,r['prompt_id'],'FINAL',{'state':state,'reason':reason,'http_status':hs,'telemetry':tele});db.commit()
    c=dict(db.execute("SELECT COALESCE(SUM(native_retry_events),0) retries,COALESCE(SUM(physical_attempt_lower_bound),0) physical,COALESCE(SUM(state='CONTENT_POLICY_REFUSAL_CONFIRMED'),0) refusals,COALESCE(SUM(state!='NOT_STARTED'),0) logical FROM slots").fetchone());print(json.dumps({'prompt_id':r['prompt_id'],'state':state,'reason':reason,'http_status':hs,**c},sort_keys=True),flush=True)
    if state=='COMPLETION_UNKNOWN':stop='STOPPED_COMPLETION_UNKNOWN';sim='NATIVE_RETRY_GUARD' if c['retries']>=MAX_RETRIES else None
    elif hs==429:stop='STOPPED_PROVIDER_429'
    elif hs in (401,403) or (hs and 500<=hs<=599):stop=f'STOPPED_PROVIDER_HTTP{hs}'
    elif state in ('FAILED_CONFIRMED','MECHANICAL_QA_FAILED'):stop='STOPPED_UNCLASSIFIED_PROVIDER_FAILURE' if state=='FAILED_CONFIRMED' else 'STOPPED_MECHANICAL_QA_FAILURE'
    elif c['retries']>=MAX_RETRIES:stop='NATIVE_RETRY_GUARD'
    elif c['physical']>=MAX_PHYSICAL:stop='PHYSICAL_ATTEMPT_GUARD'
    elif c['refusals']>=MAX_REFUSALS:stop='POLICY_REFUSAL_PRESSURE_GUARD'
    elif c['logical']>=MAX_LOGICAL:stop='WINDOW_CAP_REACHED_SUCCESS'
    if stop:break
   if not stop:stop='STOPPED_UNEXPECTED_SCHEDULER_STATE'
   jwrite(CHECK/'global_stop.json',{'global_stop':True,'stop_reason':stop,'simultaneous_guard_reached':sim,'stopped_at':now()})
  finally:db.close()
  print(json.dumps(terminal(stop,sim),sort_keys=True),flush=True)
 finally:fp.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['init','run']);a=p.parse_args();init() if a.command=='init' else run()
