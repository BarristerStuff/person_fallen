"""Pure strict contract, persistence and request identity helpers. No inference."""
import hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE='V5-B0-TARGET-ATTRIBUTES'
MODEL='qwen3.5:4b'
PHASES={'pilot':{'rows':115,'budget':115,'manifest':'pilot115.json','prefix':'V5_B0_PILOT_'},'regression':{'rows':1,'budget':1,'manifest':'regression1.json','prefix':'V5_B0_REGRESSION_'}}
ENUMS={
 'person_visible':['yes','no','uncertain'],
 'pose':['standing','walking','chair_sitting','floor_sitting','kneeling','squat_crouch','bending','crawling','pushup_plank','supine','side_lying','prone','curled_lying','other_near_ground','unknown'],
 'torso_orientation':['upright','inclined','horizontal','unknown'],
 'torso_ground_contact':['none','partial','broad','unknown'],
 'head_shoulders_above_hips':['yes','no','unknown'],
 'support_surface':['floor','chair','bed_sofa','unknown'],
 'explicit_work_evidence':['yes','no','unknown'],
 'visual_quality':['clear','insufficient']}
PERSON_KEYS=set(ENUMS)|{'person_id','bbox_1000','evidence'}
def utc():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def duplicate_check(pairs):
 result={}
 for k,v in pairs:
  if k in result:raise ValueError('Duplicate JSON key: '+k)
  result[k]=v
 return result
def loads(raw):
 return json.loads(raw,object_pairs_hook=duplicate_check,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Non-finite JSON')))
def validate_attributes(value):
 if not isinstance(value,dict) or set(value)!={'scene_coverage','people'}:raise ValueError('Top-level exact-key contract')
 if value['scene_coverage'] not in ('complete','incomplete','unknown'):raise ValueError('scene_coverage enum')
 if not isinstance(value['people'],list) or len(value['people'])>3:raise ValueError('people array max 3')
 ids=set()
 for p in value['people']:
  if not isinstance(p,dict) or set(p)!=PERSON_KEYS:raise ValueError('Person exact 11-key contract')
  if type(p['person_id']) is not int or not 1<=p['person_id']<=3 or p['person_id'] in ids:raise ValueError('Unique integer person_id 1..3 required')
  ids.add(p['person_id']);box=p['bbox_1000']
  if box is not None:
   if not isinstance(box,list) or len(box)!=4 or any(type(v) is not int or not 0<=v<=1000 for v in box):raise ValueError('Invalid bbox integer coordinates')
   if box[0]>=box[2] or box[1]>=box[3]:raise ValueError('Invalid bbox extent')
  for k,allowed in ENUMS.items():
   if not isinstance(p[k],str) or p[k] not in allowed:raise ValueError('Invalid enum '+k)
  if not isinstance(p['evidence'],str) or not p['evidence'].strip():raise ValueError('Evidence nonempty required')
 return value

def parse_response(raw):
 outer=loads(raw)
 if not isinstance(outer,dict) or outer.get('done') is not True or outer.get('done_reason')!='stop':raise ValueError('Incomplete/truncated model completion')
 if outer.get('model')!=MODEL:raise ValueError('Response model identity mismatch')
 if not isinstance(outer.get('response'),str):raise ValueError('Response string missing')
 return outer,validate_attributes(loads(outer['response']))

def write_bytes(path,data):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def write_json(p,obj):write_bytes(p,(json.dumps(obj,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode())
def append_jsonl(p,obj):
 with Path(p).open('a') as f:f.write(json.dumps(obj,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
def verify_sha(p,h):
 if sha(p)!=h:raise ValueError(f'Frozen/input SHA mismatch: {p}')
def validate_manifest(phase,rows):
 if phase not in PHASES:raise ValueError('Unauthorized phase')
 if len(rows)!=PHASES[phase]['rows'] or len({r['item_id'] for r in rows})!=len(rows):raise ValueError('Incomplete/duplicate manifest')
 ids=[r['request_id'] for r in rows]
 if len(set(ids))!=len(rows) or any(not x.startswith(PHASES[phase]['prefix']) for x in ids):raise ValueError('Request identity binding failure')
 if any(r['phase']!=phase or r['v3_split']!=('V3_DEV' if phase=='pilot' else 'V3_SCREEN') for r in rows):raise ValueError('Unauthorized split/phase')
 for r in rows:
  if r['person_detected'] not in ('true','false'):raise ValueError('Reliable crop flag must be original explicit boolean string')
 return rows

def start_stage(directory):
 p=Path(directory)
 if p.exists():raise ValueError('Existing execution: no overwrite/retry/resume')
 p.mkdir(parents=True,exist_ok=False);write_json(p/'STARTED.lock',{'timestamp':utc(),'resend_forbidden':True})
def claim_directory(directory,phase,row,claimed,total_claims):
 if phase not in PHASES:raise ValueError('Unauthorized phase')
 rid=row['request_id']
 if rid in claimed or not rid.startswith(PHASES[phase]['prefix']):raise ValueError('Duplicate/wrong request ID')
 if len(claimed)>=PHASES[phase]['budget'] or total_claims>=116:raise ValueError('Request budget exhausted')
 p=Path(directory)/'requests'/rid;p.mkdir(parents=True,exist_ok=False);return p
