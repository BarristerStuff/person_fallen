#!/usr/bin/env python3
"""Independently authorized Q8 25-slot balanced generation window."""
from __future__ import annotations
import argparse,csv,fcntl,hashlib,importlib.util,json,os,re,shutil,sqlite3,subprocess,time
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from PIL import Image

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization'); GR3=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen'
Q7=GR3/'06_execution/quota_campaign_window_04_gr3q7_authorized_20260831_01'; Q5=GR3/'06_execution/quota_campaign_window_02_policy_adapter_20260830_01'
Q7PREP=GR3/'06_execution/quota_campaign_window_04_gr3q7_20260831_01'
EXEC=GR3/'06_execution/quota_campaign_window_05_gr3q8_authorized_20260831_01'; MANIFEST=GR3/'03_fullregen_plan/full_regen_prompt_manifest.csv'; ADAPTER=Q5/'01_adapter/render_prompt_manifest_v1.csv'; CLASSIFIER=Q7/'02_runner/provider_failure_classifier_v2.py'; PARSER=Q7/'02_runner/retry_event_parser_v2.py'; CLI=Path('/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs'); VALIDATOR=Path('/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py'); ANN=Path('/home/yanbo/net_vlm_xunjian_dataset/01_annotations'); OVERVIEW=ROOT/'PERSON_FALLEN_V2.md'
DB=EXEC/'03_ledger/gr3q8_execution.sqlite3';PLAN=EXEC/'02_plan/q8_balanced_stable_25_plan.csv';RAW=EXEC/'04_raw_responses';RIMG=EXEC/'07_generated_raw';FINAL=EXEC/'08_final';QA=EXEC/'06_partial_qa';CHECK=EXEC/'05_checkpoints';PRE=EXEC/'00_preflight';LOCK=GR3/'06_execution/.p4d_gr3q8_active_runner.lock'
MODEL='gpt-5.4';PROVIDER='codex';BACKEND='image_generation';ADAPTER_VERSION='CODEX_SAFE_STAGED_CV_V1';NATIVE='1536x1024';QUALITY='medium';FINAL_SIZE=(1920,1080);MAX_LOGICAL=25;MAX_PHYSICAL=30;MAX_RETRIES=4;MAX_REFUSALS=3
E_Q7='9adc539e0b55a9207111b025bebdefcc4951760616b83f9680f91df28ef5aaf9';E_CLASS='fbd773b5d5d131f06abd334e041377fc5e0c7b9c0e5e6179164979c2abb624c0'
GROUPS=['PF_P4D_POS_SUPINE_G001','PF_P4D_POS_PRONE_G001','PF_P4D_POS_SIDE_G003','PF_P4D_HN_PLANK_G001','PF_P4D_HN_MIX_G003']

def utc():return datetime.now(timezone.utc).isoformat(timespec='milliseconds')
def sha(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p:Path,x:Any):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.tmp')
 with t.open('w',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p);fd=os.open(str(p.parent),os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def append(p:Path,x:Any):
 with p.open('a',encoding='utf-8') as f:f.write(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
def rows(p:Path):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def parse(s):
 try:x=json.loads(s);return x if isinstance(x,dict) else {'ok':False,'error':{'code':'invalid_provider_output'}}
 except Exception:return {'ok':False,'error':{'code':'invalid_provider_output','message':'stdout is not JSON'}}
def scrub(s):return re.sub(r'(?i)(authorization\s*:\s*bearer\s+)[^\s"\']+',r'\1<REDACTED>',s)
def walktext(x):
 if isinstance(x,dict):return ' '.join(walktext(v) for v in x.values())
 if isinstance(x,list):return ' '.join(walktext(v) for v in x)
 return str(x)
def http(payload,rc):
 m=re.search(r'\bHTTP\s*(\d{3})\b',walktext(payload),re.I) or re.search(r'\b(429|401|403|5\d\d)\b',walktext(payload));return int(m.group(1)) if m else (200 if rc==0 and payload.get('ok') is True else None)
def mod(n,p):
 s=importlib.util.spec_from_file_location(n,p)
 if not s or not s.loader:raise RuntimeError('module load failure')
 x=importlib.util.module_from_spec(s);s.loader.exec_module(x);return x
def verify_q7():
 f=Q7/'freeze/p4d_gr3q7_execution_terminal_freeze.json';x=json.loads(f.read_text());checks={p:Path(p).is_file() and sha(Path(p))==h for p,h in x['artifact_sha256'].items()};out={'expected_sha256':E_Q7,'actual_sha256':sha(f),'sidecar_match':f.with_name(f.name+'.sha256').read_text().split()[0]==sha(f),'bound_artifact_count':len(checks),'all_bound_artifacts_match':all(checks.values())}
 if out['actual_sha256']!=E_Q7 or not out['sidecar_match'] or not out['all_bound_artifacts_match'] or len(checks)!=78:raise RuntimeError('Q7 terminal integrity failure')
 return out
def validator(label):
 p=subprocess.run(['python3',str(VALIDATOR),'--json'],capture_output=True,text=True,timeout=240);x=parse(p.stdout);hits={}
 for n in ('media.csv','labels.csv','batches.csv','splits.csv'):hits[n]=sum('p4d' in z.lower() or 'person-fallen-v2-p4d' in z.lower() for z in (ANN/n).read_text(encoding='utf-8').splitlines()[1:])
 o={'captured_at':utc(),'returncode':p.returncode,'validator':x,'p4d_active_reference_hits':hits,'p4d_active_reference_total':sum(hits.values())};write(PRE/f'dataset_{label}.json',o)
 if p.returncode or x.get('status')!='valid' or x.get('error_count')!=0 or not x.get('full_hash_check') or o['p4d_active_reference_total']!=0:raise RuntimeError('dataset validator gate')
 return o
def crop(raw,final):
 with Image.open(raw) as im:im.verify()
 with Image.open(raw) as im:
  im.load();w,h=im.size;im=im.convert('RGB');r=w/h;t=16/9
  if r>t:cw=round(h*t);box=((w-cw)//2,0,(w-cw)//2+cw,h)
  elif r<t:ch=round(w/t);box=(0,(h-ch)//2,w,(h-ch)//2+ch)
  else:box=(0,0,w,h)
  rs=getattr(getattr(Image,'Resampling',Image),'LANCZOS');tmp=final.with_name(final.name+'.tmp');im.crop(box).resize(FINAL_SIZE,rs).save(tmp,'PNG')
 with Image.open(tmp) as im:im.verify()
 with Image.open(tmp) as im:im.load();fw,fh=im.size
 if (fw,fh)!=FINAL_SIZE:raise RuntimeError('final dimension mismatch')
 os.replace(tmp,final);return {'observed_native_width':w,'observed_native_height':h,'final_width':fw,'final_height':fh,'crop_box':list(box),'resize_method':'Pillow_LANCZOS'}
def ev(db,pid,typ,x):db.execute('INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)',(pid,typ,json.dumps(x,ensure_ascii=False,sort_keys=True),utc()))
def plan_rows(manifest,safe):
 m={x['prompt_id']:x for x in manifest};safeids={x['prompt_id'] for x in safe};out=[];order=1
 reasons={'PF_P4D_POS_SUPINE_G001':'positive DESIGN; lowest original ordinal among tied low-coverage available positive taxonomies','PF_P4D_POS_PRONE_G001':'positive DESIGN; next lowest original ordinal among distinct tied low-coverage available positive taxonomies','PF_P4D_POS_SIDE_G003':'positive SCREEN; distinct tied low-coverage available positive taxonomy with lowest eligible original ordinal','PF_P4D_HN_PLANK_G001':'hard-negative DESIGN; maximum deficit (zero verified) with stable original-group-ordinal tie-break','PF_P4D_HN_MIX_G003':'hard-negative SCREEN; maximum deficit (zero verified), distinct taxonomy, and stable eligible tie-break'}
 for gid in GROUPS:
  group=sorted([x for x in manifest if x['group_id']==gid],key=lambda x:x['variant_id'])
  if len(group)!=5 or any(x['prompt_id'] not in safeids for x in group):raise RuntimeError('Q8 selected group not complete safe outstanding '+gid)
  for x in group:
   out.append({'q8_order':str(order),'prompt_id':x['prompt_id'],'group_id':gid,'variant_id':x['variant_id'],'role':x['target_role'],'taxonomy':x['taxonomy'],'planned_split':x['planned_internal_split'],'parent_state':'SAFE_EXECUTABLE_OUTSTANDING','adapter_version':ADAPTER_VERSION,'render_prompt_sha256':'','selection_reason':reasons[gid]});order+=1
 return out
def init():
 if EXEC.exists():raise RuntimeError('Q8 execution revision already exists')
 q7=verify_q7();manifest=rows(MANIFEST);success=rows(Q7/'06_partial_qa/verified_success.csv');unknown=rows(Q7/'06_partial_qa/completion_unknown_quarantine.csv');safe=rows(Q7/'06_partial_qa/safe_executable_outstanding.csv');a={x['prompt_id'] for x in success};b={x['prompt_id'] for x in unknown};c={x['prompt_id'] for x in safe};u={x['prompt_id'] for x in manifest}
 if (len(a),len(b),len(c))!=(171,1,268) or a&b or a&c or b&c or a|b|c!=u or b!={'PF_P4D_HN_MAINT_G006_V02'}:raise RuntimeError('Q8 authoritative partition integrity failure')
 if sha(CLASSIFIER)!=E_CLASS:raise RuntimeError('classifier sha mismatch')
 reg=json.loads((Q7PREP/'00_preflight/classifier_regression.json').read_text())
 if (reg.get('pass_count'),reg.get('total'),reg.get('classifier_sha256'))!=(3,3,E_CLASS):raise RuntimeError('classifier regression mismatch')
 adapter={x['prompt_id']:x for x in rows(ADAPTER)};plan=plan_rows(manifest,safe)
 for r in plan:
  if r['prompt_id'] not in adapter or adapter[r['prompt_id']]['adapter_version']!=ADAPTER_VERSION:raise RuntimeError('adapter binding mismatch')
  r['render_prompt_sha256']=adapter[r['prompt_id']]['render_prompt_sha256']
 role=Counter(x['role'] for x in plan);split=Counter(x['planned_split'] for x in plan)
 if len(plan)!=25 or len({x['prompt_id'] for x in plan})!=25 or role!=Counter({'positive':15,'hard_negative':10}) or split!=Counter({'NEW_DESIGN':15,'NEW_SCREEN':10}) or any('MAINT_G006' in x['prompt_id'] for x in plan):raise RuntimeError('BLOCKED_Q8_PLAN_INTEGRITY')
 EXEC.mkdir()
 for d in ('00_preflight','01_authorization','02_plan','03_ledger','04_raw_responses','05_checkpoints','06_partial_qa','07_generated_raw','08_final','freeze'):(EXEC/d).mkdir()
 with PLAN.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(plan[0]));w.writeheader();w.writerows(plan)
 p=subprocess.run(['node',str(CLI),'--json','--provider','codex','doctor'],capture_output=True,text=True,timeout=90);runtime={'returncode':p.returncode,'payload':parse(p.stdout),'provider_requests':0}
 if p.returncode or runtime['payload'].get('ok') is not True or runtime['payload'].get('provider_selection',{}).get('resolved')!='codex':raise RuntimeError('provider readiness gate')
 before=validator('before');write(PRE/'q7_terminal_freeze_verification.json',q7);write(PRE/'provider_runtime.json',runtime);write(PRE/'partition_rebuild.json',{'verified_success':171,'completion_unknown':1,'safe_outstanding':268,'disjoint':True,'union_frozen440':True,'foreign_event_assets_used':0});write(EXEC/'01_authorization/authorization.json',{'authorized':True,'stage':'P4D_GR3Q8_BALANCED_STABLE_WINDOW','max_logical_invocations':25,'concurrency':1,'outer_retry':False,'native_max_retries':3,'max_physical_attempt_lower_bound':30,'max_unique_native_retry_events':4,'max_confirmed_policy_refusals':3,'formal_ingest':False,'c3':False,'val':0,'holdout_requests':0})
 for s,d in [(CLASSIFIER,'provider_failure_classifier_v2.py'),(PARSER,'retry_event_parser_v2.py'),(Path(__file__),Path(__file__).name)]:shutil.copy2(s,EXEC/'02_plan'/d)
 cfg={'provider':PROVIDER,'request_model':MODEL,'generation_backend':BACKEND,'runtime_expected':'0.7.3','adapter_version':ADAPTER_VERSION,'requested_native_size':NATIVE,'native_size_contract_enforced':False,'final_output_dimension_contract':'1920x1080','quality':QUALITY,'format':'png','concurrency':1,'outer_retry':False,'native_max_retries':3,'semantic_frozen_prompt_changed':False,'provider_render_prompt_changed':True,'q8_plan_sha256':sha(PLAN),'classifier_v2_sha256':sha(CLASSIFIER),'runner_sha256':sha(Path(__file__))};write(EXEC/'02_plan/run_config.json',cfg)
 db=sqlite3.connect(DB)
 try:
  db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL');db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('CREATE TABLE slots(ord INTEGER PRIMARY KEY,prompt_id TEXT UNIQUE,group_id TEXT,variant_id TEXT,role TEXT,taxonomy TEXT,planned_split TEXT,render_prompt_sha256 TEXT,state TEXT,started_at TEXT,finished_at TEXT,http_status INTEGER,error_class TEXT,error_reason TEXT,raw_path TEXT,final_path TEXT,raw_sha256 TEXT,final_sha256 TEXT,observed_native_width INTEGER,observed_native_height INTEGER,final_width INTEGER,final_height INTEGER,crop_box TEXT,latency_seconds REAL,native_retry_events INTEGER DEFAULT 0,request_started_events INTEGER DEFAULT 0,physical_attempt_lower_bound INTEGER DEFAULT 0)');db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,prompt_id TEXT,event_type TEXT,payload_json TEXT,captured_at TEXT)');db.executemany('INSERT INTO slots(ord,prompt_id,group_id,variant_id,role,taxonomy,planned_split,render_prompt_sha256,state) VALUES(?,?,?,?,?,?,?,?,?)',[(int(x['q8_order']),x['prompt_id'],x['group_id'],x['variant_id'],x['role'],x['taxonomy'],x['planned_split'],x['render_prompt_sha256'],'NOT_STARTED') for x in plan]);db.executemany('INSERT INTO meta VALUES(?,?)',[('stage','P4D_GR3Q8_BALANCED_STABLE_WINDOW'),('authorization','true')]);db.commit();db.execute('PRAGMA wal_checkpoint(FULL)')
 finally:db.close()
 write(CHECK/'ready.json',{'status':'READY_FOR_AUTHORIZED_EXECUTION','provider_requests':0,'q8_plan_sha256':sha(PLAN),'starting_verified_success':171,'starting_completion_unknown':1,'starting_safe_outstanding':268,'dataset_before':before});print(json.dumps({'status':'READY_FOR_AUTHORIZED_EXECUTION','execution_revision':str(EXEC),'q8_plan_sha256':sha(PLAN)}))
def csvout(p,rs):
 keys=['prompt_id','role','taxonomy','planned_split','source','raw_path','final_path','raw_sha256','final_sha256','adapter_version']
 with p.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rs)
def terminal(stop,sim):
 db=sqlite3.connect(DB);db.row_factory=sqlite3.Row
 try:slots=[dict(x) for x in db.execute('SELECT * FROM slots ORDER BY ord')];db.commit();db.execute('PRAGMA wal_checkpoint(FULL)')
 finally:db.close()
 manifest={x['prompt_id']:x for x in rows(MANIFEST)};prior=rows(Q7/'06_partial_qa/verified_success.csv');old_unknown=rows(Q7/'06_partial_qa/completion_unknown_quarantine.csv');good=[x for x in slots if x['state']=='SUCCESS'];newunk=[x for x in slots if x['state']=='COMPLETION_UNKNOWN'];s={x['prompt_id'] for x in prior}|{x['prompt_id'] for x in good};u={x['prompt_id'] for x in old_unknown}|{x['prompt_id'] for x in newunk};safe=set(manifest)-s-u
 if s&u or s|u|safe!=set(manifest):raise RuntimeError('Q8 final partition failure')
 by={x['prompt_id']:x for x in good}
 def record(pid,source):
  m=manifest[pid];z=by.get(pid);return {'prompt_id':pid,'role':m['target_role'],'taxonomy':m['taxonomy'],'planned_split':m['planned_internal_split'],'source':source,'raw_path':z['raw_path'] if z else '','final_path':z['final_path'] if z else '','raw_sha256':z['raw_sha256'] if z else '','final_sha256':z['final_sha256'] if z else '','adapter_version':ADAPTER_VERSION}
 csvout(QA/'verified_success.csv',prior+[record(x['prompt_id'],'Q8_EXECUTION') for x in good]);csvout(QA/'completion_unknown_quarantine.csv',old_unknown+[record(x['prompt_id'],'Q8_EXECUTION_UNKNOWN') for x in newunk]);csvout(QA/'safe_executable_outstanding.csv',[record(x,'SAFE_EXECUTABLE_OUTSTANDING') for x in sorted(safe)])
 old=set();gr1=set()
 for p in GR3.rglob('*.png'):
  if EXEC not in p.parents:
   try:old.add(sha(p))
   except OSError:pass
 g=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr1_generation_resume'
 if g.exists():
  for p in g.rglob('*.png'):
   try:gr1.add(sha(p))
   except OSError:pass
 dup=sum(x['raw_sha256'] in old or x['final_sha256'] in old for x in good);gh=sum(x['raw_sha256'] in gr1 or x['final_sha256'] in gr1 for x in good);allrec=prior+[record(x['prompt_id'],'Q8_EXECUTION') for x in good];sizes=Counter(f'{x["observed_native_width"]}x{x["observed_native_height"]}' for x in good)
 qa={'partial_mechanical_qa':'PASS' if not any(x['state']=='MECHANICAL_QA_FAILED' for x in slots) else 'FAIL','new_raw_count':len(good),'new_final_count':len(good),'pillow_failures':sum(x['state']=='MECHANICAL_QA_FAILED' for x in slots),'dimension_failures':0,'exact_duplicate_hits':dup,'gr1_sha_hits':gh,'adapter_provenance':'PASS','profile_provenance':'RECORDED','requested_native_size':NATIVE,'observed_native_size_distribution':dict(sizes),'native_size_contract_enforced':False,'final_output_dimension_contract':'1920x1080','foreign_event_assets_used':0,'full_440_qa':'NOT_REACHED' if len(s)<440 else 'REACHED','P4D_IMAGES_ACCEPTED':0,'current_verified_success':len(s),'current_completion_unknown':len(u),'current_safe_executable_outstanding':len(safe),'role_distribution':dict(Counter(x['role'] for x in allrec)),'split_distribution':dict(Counter(x['planned_split'] for x in allrec)),'taxonomy_distribution':dict(Counter(x['taxonomy'] for x in allrec))};write(QA/'partial_qa.json',qa)
 after=validator('after');cnt=Counter(x['state'] for x in slots);hs=Counter(str(x['http_status']) for x in slots if x['http_status'] is not None);summary={'stage':'P4D_GR3Q8_BALANCED_STABLE_WINDOW','status':stop,'stop_reason':'NETWORK_ERROR_COMPLETION_AMBIGUITY' if stop=='STOPPED_COMPLETION_UNKNOWN' else stop,'simultaneous_guard_reached':sim,'starting_verified_success':171,'starting_completion_unknown':1,'starting_safe_executable_outstanding':268,'q8_plan_sha256':sha(PLAN),'q8_plan_rows':25,'q8_groups':GROUPS,'q8_role_distribution':dict(Counter(x['role'] for x in rows(PLAN))),'q8_split_distribution':dict(Counter(x['planned_split'] for x in rows(PLAN))),'q8_taxonomies':sorted(set(x['taxonomy'] for x in rows(PLAN))),'classifier_v2_sha256':sha(CLASSIFIER),'classifier_regression':'3/3_PASS','provider':PROVIDER,'request_model':MODEL,'generation_backend':BACKEND,'runtime_version':'0.7.3','adapter_version':ADAPTER_VERSION,'logical_invocations':sum(x['state']!='NOT_STARTED' for x in slots),'success':cnt['SUCCESS'],'content_policy_refusals':cnt['CONTENT_POLICY_REFUSAL_CONFIRMED'],'other_confirmed_failures':cnt['FAILED_CONFIRMED']+cnt['MECHANICAL_QA_FAILED'],'new_completion_unknown':cnt['COMPLETION_UNKNOWN'],'unique_native_retry_events':sum(x['native_retry_events'] for x in slots),'observed_physical_attempt_lower_bound':sum(x['physical_attempt_lower_bound'] for x in slots),'http200':hs['200'],'http429':hs['429'],'http401':hs['401'],'http403':hs['403'],'http5xx':sum(v for k,v in hs.items() if k.startswith('5')),'network_errors':cnt['COMPLETION_UNKNOWN'],'timeouts':0,'current_verified_success':len(s),'current_completion_unknown':len(u),'current_safe_executable_outstanding':len(safe),'qa':qa,'formal_ingest':False,'media_added':0,'labels_added':0,'c3':False,'new_val':0,'val':0,'holdout_requests':0,'holdout_consumed':False,'dataset_after':after};write(CHECK/'terminal_summary.json',summary)
 shutil.copy2(OVERVIEW,EXEC/'freeze/overview_snapshot_at_freeze.md');arts=[DB,EXEC/'01_authorization/authorization.json',PLAN,EXEC/'02_plan/run_config.json',EXEC/'02_plan/provider_failure_classifier_v2.py',EXEC/'02_plan/retry_event_parser_v2.py',EXEC/'02_plan'/Path(__file__).name,PRE/'q7_terminal_freeze_verification.json',PRE/'provider_runtime.json',PRE/'partition_rebuild.json',PRE/'dataset_before.json',PRE/'dataset_after.json',CHECK/'ready.json',CHECK/'global_stop.json',CHECK/'terminal_summary.json',QA/'partial_qa.json',QA/'verified_success.csv',QA/'completion_unknown_quarantine.csv',QA/'safe_executable_outstanding.csv',EXEC/'freeze/overview_snapshot_at_freeze.md',*sorted(RAW.glob('*.json')),*sorted(RIMG.glob('*.png')),*sorted(FINAL.glob('*.png'))];freeze=EXEC/'freeze/p4d_gr3q8_execution_terminal_freeze.json';write(freeze,{'stage':summary['stage'],'terminal':summary,'live_overview_bound_to_immutable_freeze':False,'overview_snapshot_sha256':sha(EXEC/'freeze/overview_snapshot_at_freeze.md'),'artifact_sha256':{str(x):sha(x) for x in arts}});d=sha(freeze);freeze.with_name(freeze.name+'.sha256').write_text(f'{d}  {freeze.name}\n',encoding='utf-8');v={'freeze_sha256':d,'sidecar_match':freeze.with_name(freeze.name+'.sha256').read_text().split()[0]==d,'bound_artifact_count':len(arts),'all_bound_artifacts_match':all(sha(Path(p))==h for p,h in json.loads(freeze.read_text())['artifact_sha256'].items())};write(CHECK/'terminal_freeze_verification.json',v);return summary|{'sqlite_canonical_sha256':sha(DB),'execution_terminal_freeze_sha256':d,'overview_snapshot_sha256':sha(EXEC/'freeze/overview_snapshot_at_freeze.md'),'terminal_freeze_verification':v}
def run():
 if not EXEC.exists() or (EXEC/'freeze/p4d_gr3q8_execution_terminal_freeze.json').exists():raise RuntimeError('missing init or already sealed')
 f=LOCK.open('w')
 try:
  try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise RuntimeError('BLOCKED_CONCURRENT_RUNNER')
  ext=[]
  for z in subprocess.run(['ps','-eo','pid=,args='],capture_output=True,text=True,check=True).stdout.splitlines():
   x=z.strip().split(None,1)
   if len(x)==2 and Path(__file__).name in x[1] and int(x[0]) not in {os.getpid(),os.getppid()}:ext.append(z)
  if ext:raise RuntimeError('BLOCKED_CONCURRENT_RUNNER '+str(ext))
  parser=mod('q8parser',EXEC/'02_plan/retry_event_parser_v2.py');classifier=mod('q8classifier',EXEC/'02_plan/provider_failure_classifier_v2.py');render={x['prompt_id']:x for x in rows(ADAPTER)};db=sqlite3.connect(DB);db.row_factory=sqlite3.Row;stop=None;sim=None
  try:
   for r in rows(PLAN):
    old=dict(db.execute('SELECT * FROM slots WHERE prompt_id=?',(r['prompt_id'],)).fetchone())
    if old['state']!='NOT_STARTED':raise RuntimeError('non-pristine slot')
    db.execute("UPDATE slots SET state='STARTED',started_at=? WHERE prompt_id=?",(utc(),r['prompt_id']));ev(db,r['prompt_id'],'STARTED',{'q8_order':r['q8_order']});db.commit();req={'model':MODEL,'provider':PROVIDER,'generation_backend':BACKEND,'size':NATIVE,'quality':QUALITY,'format':'png','adapter_version':ADAPTER_VERSION,'render_prompt_sha256':r['render_prompt_sha256'],'outer_retry':False,'native_max_retries':3};append(EXEC/'request_log.jsonl',{'timestamp':utc(),'prompt_id':r['prompt_id'],'split':r['planned_split'],'request':req});rawp=RIMG/(r['prompt_id']+'.png');fin=FINAL/(r['prompt_id']+'.png');cmd=['node',str(CLI),'--json','--json-events','--provider','codex','images','generate','--model',MODEL,'--prompt',render[r['prompt_id']]['render_prompt'],'--out',str(rawp),'--format','png','--size',NATIVE,'--quality',QUALITY];start=time.monotonic();p=None;timed=False
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=1800)
    except subprocess.TimeoutExpired as e:timed=True;out=e.stdout or '';err=e.stderr or ''
    else:out=p.stdout;err=p.stderr
    if isinstance(out,bytes):out=out.decode('utf-8','replace')
    if isinstance(err,bytes):err=err.decode('utf-8','replace')
    outer=parse(out);tele=parser.telemetry_from_events(parser.parse_json_events(err));h=http(outer,p.returncode if p else None);lat=time.monotonic()-start;details={};cl=None;ok=bool(p and p.returncode==0 and outer.get('ok') is True and rawp.is_file() and rawp.stat().st_size>0)
    if timed:state='COMPLETION_UNKNOWN';reason='TIMEOUT_COMPLETION_AMBIGUITY';msg='subprocess timeout'
    elif ok:
     try:details=crop(rawp,fin);state='SUCCESS';reason='NONE';msg=''
     except Exception as e:state='MECHANICAL_QA_FAILED';reason='MECHANICAL_QA_FAILED';msg=str(e)
    else:cl=classifier.classify({'outer_json':outer,'stderr_redacted':scrub(err)});state=cl['state'];reason=cl['reason'];msg=walktext(outer)[:800]
    raw={'prompt_id':r['prompt_id'],'command_config':req,'returncode':p.returncode if p else None,'http_status':h,'outer_json':outer,'stderr_redacted':scrub(err),'state':state,'failure_classification':cl,'failure_reason':reason,'latency_seconds':lat,'telemetry':tele,'timeout':timed,'adapter_version':ADAPTER_VERSION,'render_prompt_sha256':r['render_prompt_sha256']};write(RAW/(r['prompt_id']+'.json'),raw);append(EXEC/'raw_responses.jsonl',raw);db.execute('UPDATE slots SET state=?,finished_at=?,http_status=?,error_class=?,error_reason=?,raw_path=?,final_path=?,raw_sha256=?,final_sha256=?,observed_native_width=?,observed_native_height=?,final_width=?,final_height=?,crop_box=?,latency_seconds=?,native_retry_events=?,request_started_events=?,physical_attempt_lower_bound=? WHERE prompt_id=?',(state,utc(),h,state,reason,str(rawp) if rawp.exists() else None,str(fin) if fin.exists() else None,sha(rawp) if rawp.exists() else None,sha(fin) if fin.exists() else None,details.get('observed_native_width'),details.get('observed_native_height'),details.get('final_width'),details.get('final_height'),json.dumps(details.get('crop_box')) if details else None,lat,tele['unique_native_retry_events'],tele['request_started_events'],tele['physical_attempt_lower_bound'],r['prompt_id']));ev(db,r['prompt_id'],'FINAL',{'state':state,'reason':reason,'http_status':h,'telemetry':tele});db.commit();c=dict(db.execute("SELECT COALESCE(SUM(native_retry_events),0) retries,COALESCE(SUM(physical_attempt_lower_bound),0) physical,COALESCE(SUM(state='CONTENT_POLICY_REFUSAL_CONFIRMED'),0) refusals,COALESCE(SUM(state!='NOT_STARTED'),0) logical FROM slots").fetchone());print(json.dumps({'prompt_id':r['prompt_id'],'state':state,'reason':reason,'http_status':h,**c},sort_keys=True),flush=True)
    if state=='COMPLETION_UNKNOWN':stop='STOPPED_COMPLETION_UNKNOWN';sim='NATIVE_RETRY_GUARD' if c['retries']>=MAX_RETRIES else None
    elif h==429:stop='STOPPED_PROVIDER_429'
    elif h in (401,403) or (h and 500<=h<=599):stop=f'STOPPED_PROVIDER_HTTP{h}'
    elif state in ('FAILED_CONFIRMED','MECHANICAL_QA_FAILED'):stop='STOPPED_UNCLASSIFIED_PROVIDER_FAILURE' if state=='FAILED_CONFIRMED' else 'STOPPED_MECHANICAL_QA_FAILURE'
    elif c['retries']>=MAX_RETRIES:stop='NATIVE_RETRY_GUARD'
    elif c['physical']>=MAX_PHYSICAL:stop='PHYSICAL_ATTEMPT_GUARD'
    elif c['refusals']>=MAX_REFUSALS:stop='POLICY_REFUSAL_PRESSURE_GUARD'
    elif c['logical']>=MAX_LOGICAL:stop='WINDOW_CAP_REACHED_SUCCESS'
    if stop:break
   if not stop:stop='STOPPED_UNEXPECTED_SCHEDULER_STATE'
   write(CHECK/'global_stop.json',{'global_stop':True,'stop_reason':stop,'simultaneous_guard_reached':sim,'stopped_at':utc()})
  finally:db.close()
  print(json.dumps(terminal(stop,sim),sort_keys=True),flush=True)
 finally:f.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['init','run']);a=p.parse_args();init() if a.command=='init' else run()
