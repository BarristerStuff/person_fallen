"""Pure contracts; no network, GT mutation or free-text routing."""
import csv,hashlib,json,math,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
ALERT='ALERT_GROUND_LYING'; RECHECK='RECHECK_VISUAL_UNCERTAIN'
PHASES={'dev':(436,288),'regression':(76,52)}
STATES={'candidate_present','candidate_absent','uncertain'}
def utc():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def unique_pairs(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('Duplicate JSON key')
  d[k]=v
 return d
def loads(s):return json.loads(s,object_pairs_hook=unique_pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Non-finite JSON')))
def parse_response(raw):
 outer=loads(raw)
 if not isinstance(outer,dict) or outer.get('done') is not True or outer.get('done_reason')!='stop':raise ValueError('Incomplete response/done_reason')
 if outer.get('model')!='qwen3.5:4b':raise ValueError('Response model mismatch')
 if not isinstance(outer.get('response'),str):raise ValueError('Missing response string')
 obj=loads(outer['response'])
 if not isinstance(obj,dict) or set(obj)!={'scene_review','evidence'}:raise ValueError('Strict key mismatch')
 if not isinstance(obj['scene_review'],str) or obj['scene_review'] not in STATES:raise ValueError('Illegal scene_review')
 if not isinstance(obj['evidence'],str) or not obj['evidence'].strip():raise ValueError('Empty evidence')
 return outer,obj

def write_bytes(path,data):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def write_json(p,obj):write_bytes(p,(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def write_csv(p,rr):
 if not rr:raise ValueError('Empty output forbidden')
 import io
 f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr);write_bytes(p,f.getvalue().encode())
def append_jsonl(path,obj):
 with Path(path).open('a') as f:f.write(json.dumps(obj,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
def by_id(rr):
 d={r['item_id']:r for r in rr}
 if len(d)!=len(rr):raise ValueError('Duplicate item_id')
 return d
def verify_sha(path,expected):
 if sha(path)!=expected:raise ValueError(f'SHA mismatch: {path}')
def validate_manifest(phase,rr):
 if phase not in PHASES:raise ValueError('Only DEV and consumed SCREEN development regression allowed')
 by_id(rr); n,q=PHASES[phase]
 if len(rr)!=n or sum(r['primary_decision']!=ALERT for r in rr)!=q:raise ValueError('Row count or quota mismatch')
 ids=[r['request_id'] for r in rr if r['primary_decision']!=ALERT]
 if len(set(ids))!=q or any(not x.startswith(f'V5_A0_{phase.upper()}_') for x in ids):raise ValueError('Request identity mismatch')
 if any(r['secondary_required']!=(r['primary_decision']!=ALERT) for r in rr):raise ValueError('ALERT routing request mismatch')
 if any(r['v3_split']!=('V3_DEV' if phase=='dev' else 'V3_SCREEN') for r in rr):raise ValueError('Split forbidden')
 return rr

def claim_request(phase,row,run_dir,existing_claims):
 if phase not in PHASES:raise ValueError('Illegal phase')
 if row['primary_decision']==ALERT or not row['secondary_required']:raise ValueError('Primary ALERT must not request secondary')
 request_id=row['request_id']
 if request_id in existing_claims:raise ValueError('Already claimed; no resend')
 if len(existing_claims)>=PHASES[phase][1]:raise ValueError('Phase quota exceeded')
 if not request_id.startswith(f'V5_A0_{phase.upper()}_'):raise ValueError('Request ID phase mismatch')
 p=Path(run_dir)/'requests'/request_id
 p.mkdir(parents=True,exist_ok=False)
 return p

def start_stage(run_dir):
 p=Path(run_dir)
 if p.exists():raise ValueError('Existing execution: no overwrite/retry/resume')
 p.mkdir(parents=True,exist_ok=False)
 write_json(p/'STARTED.lock',{'started':utc(),'automatic_resume':False})

def percentile(vals,q):
 if not vals:return None
 ss=sorted(vals);idx=(len(ss)-1)*q;a=math.floor(idx);b=math.ceil(idx)
 return ss[a]+(ss[b]-ss[a])*(idx-a)
