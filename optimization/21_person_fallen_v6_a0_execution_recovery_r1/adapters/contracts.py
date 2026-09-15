import json,hashlib,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
MODEL='qwen3.5:4b'
ENUMS={'person_visible':{'yes','no','uncertain'},'pose':{'standing','walking','chair_sitting','floor_sitting','kneeling','squat_crouch','bending','crawling','pushup_plank','supine','side_lying','prone','curled_lying','other_near_ground','unknown'},'torso_orientation':{'upright','inclined','horizontal','unknown'},'torso_ground_contact':{'none','partial','broad','unknown'},'head_shoulders_above_hips':{'yes','no','unknown'},'support_surface':{'floor','chair','bed_sofa','unknown'},'body_support_configuration':{'torso_ground_supported','forearms_feet_supported','hands_feet_supported','hands_knees_supported','pelvis_supported','chair_or_bed_supported','mixed_or_occluded','unknown'},'explicit_work_evidence':{'yes','no','unknown'},'visual_quality':{'clear','insufficient'}}
PERSON_KEYS=set(ENUMS)|{'person_id','bbox_1000','evidence'}
def utc():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pairs(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('duplicate JSON key')
  d[k]=v
 return d
def loads(raw):return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def validate(v):
 if not isinstance(v,dict) or set(v)!={'scene_coverage','people'}:raise ValueError('top-level keys')
 if v['scene_coverage'] not in {'complete','incomplete','unknown'}:raise ValueError('coverage enum')
 if not isinstance(v['people'],list) or len(v['people'])>3:raise ValueError('people array')
 ids=set()
 for p in v['people']:
  if not isinstance(p,dict) or set(p)!=PERSON_KEYS:raise ValueError('person keys')
  if type(p['person_id']) is not int or not 1<=p['person_id']<=3 or p['person_id'] in ids:raise ValueError('person id')
  ids.add(p['person_id'])
  b=p['bbox_1000']
  if b is not None and (not isinstance(b,list) or len(b)!=4 or any(type(x) is not int or not 0<=x<=1000 for x in b) or b[0]>=b[2] or b[1]>=b[3]):raise ValueError('bbox')
  for k,a in ENUMS.items():
   if p[k] not in a:raise ValueError(k)
  if not isinstance(p['evidence'],str) or not p['evidence'].strip():raise ValueError('evidence')
 return v
def parse(raw):
 o=loads(raw)
 if not isinstance(o,dict) or o.get('done') is not True or o.get('done_reason')!='stop':raise ValueError('incomplete')
 if o.get('model')!=MODEL or not isinstance(o.get('response'),str):raise ValueError('model/response')
 return o,validate(loads(o['response']))
def write_bytes(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
def write_json(p,o):write_bytes(p,(json.dumps(o,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode())
def append_jsonl(p,o):
 with Path(p).open('a') as f:f.write(json.dumps(o,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
def verify(p,h):
 if sha(p)!=h:raise ValueError(f'sha mismatch {p}')
