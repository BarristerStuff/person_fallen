from __future__ import annotations
import base64,csv,hashlib,json,os,statistics,sys,time,urllib.request
from pathlib import Path
from PIL import Image

D=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(D/'policy'))
from person_association import match
from v7_b0_policy import person_p1,p2_match,aggregate
END='http://192.168.20.62:11434'; MODEL='qwen3.5:4b'; DIGEST='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd'
P1=(D/'prompt/v7_b0_p1.txt').read_text(); P2=(D/'prompt/v7_b0_p2.txt').read_text()
S1=json.loads((D/'schema/v7_person_attributes.json').read_text()); S2=json.loads((D/'schema/v7_scene_attributes.json').read_text())
BUDGET={'pilot':{'P1_primary':220,'P1_background':220,'P2_scene':160},'regression':{'P1_primary':8,'P1_background':8,'P2_scene':1},'full_remaining':{'P1_primary':700,'P1_background':700,'P2_scene':280}}
ALLOWED_PHASES={'pilot','regression','full_remaining'}

def hbytes(b): return hashlib.sha256(b).hexdigest()
def hfile(p): return hbytes(Path(p).read_bytes())
def append_jsonl(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('a') as f: f.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n'); f.flush(); os.fsync(f.fileno())

def validate_schema(obj,schema,path='$'):
 typ=schema.get('type')
 if typ=='object':
  if not isinstance(obj,dict): raise ValueError(f'{path}: expected object')
  req=set(schema.get('required',[])); missing=req-set(obj)
  if missing: raise ValueError(f'{path}: missing {sorted(missing)}')
  props=schema.get('properties',{})
  if schema.get('additionalProperties') is False:
   extra=set(obj)-set(props)
   if extra: raise ValueError(f'{path}: extra {sorted(extra)}')
  for k,v in obj.items():
   if k in props: validate_schema(v,props[k],f'{path}.{k}')
 elif typ=='array':
  if not isinstance(obj,list): raise ValueError(f'{path}: expected array')
  if len(obj)<schema.get('minItems',0) or len(obj)>schema.get('maxItems',10**9): raise ValueError(f'{path}: bad length')
  for i,v in enumerate(obj): validate_schema(v,schema.get('items',{}),f'{path}[{i}]')
 elif typ=='string':
  if not isinstance(obj,str): raise ValueError(f'{path}: expected string')
 elif typ=='number':
  if not isinstance(obj,(int,float)) or isinstance(obj,bool): raise ValueError(f'{path}: expected number')
  if obj<schema.get('minimum',float('-inf')) or obj>schema.get('maximum',float('inf')): raise ValueError(f'{path}: range')
 if 'enum' in schema and obj not in schema['enum']: raise ValueError(f'{path}: enum')

def validate_obj(obj,schema):
 validate_schema(obj,schema)
 if schema is S2:
  for i,p in enumerate(obj['people']):
   x1,y1,x2,y2=p['bbox_1000']
   if not (x1<x2 and y1<y2): raise ValueError(f'$.people[{i}].bbox_1000 ordering')

def build_payload(prompt,image_bytes,schema,num_predict):
 body={'model':MODEL,'prompt':prompt,'images':[base64.b64encode(image_bytes).decode()],
       'think':False,'stream':False,'format':schema,
       'options':{'temperature':0,'num_ctx':8192,'num_predict':num_predict}}
 return json.dumps(body,separators=(',',':'),ensure_ascii=False).encode()

def existing_ids(root):
 ids=set(); p=root/'ledger.jsonl'
 if p.exists():
  for line in p.read_text().splitlines():
   if line.strip():
    rec=json.loads(line)
    if rec.get('request_id'): ids.add(rec['request_id'])
 return ids

def call(data,rid,route,root,source_binding):
 if not rid.startswith('V7_B0R1C_'): raise RuntimeError('PROTOCOL_REQUEST_ID_PREFIX')
 if rid in existing_ids(root): raise RuntimeError('DUPLICATE_REQUEST_ID')
 payload_sha=hbytes(data); claimed=time.time()
 append_jsonl(root/'ledger.jsonl',{'request_id':rid,'state':'CLAIMED','route':route,'claimed_timestamp':claimed,'payload_sha256':payload_sha,**source_binding})
 req=urllib.request.Request(END+'/api/generate',data=data,headers={'Content-Type':'application/json'})
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPRedirectHandler())
 t=time.monotonic()
 try:
  with opener.open(req,timeout=180) as r:
   if r.status!=200: raise RuntimeError('HTTP_'+str(r.status))
   raw=r.read(); received=time.time()
 except Exception as e:
  append_jsonl(root/'ledger.jsonl',{'request_id':rid,'state':'COMPLETION_UNKNOWN','route':route,'error':repr(e),'failed_timestamp':time.time()})
  raise
 raw_dir=root/'raw';raw_dir.mkdir(parents=True,exist_ok=True);rp=raw_dir/(rid+'.json');rp.write_bytes(raw)
 raw_sha=hbytes(raw); append_jsonl(root/'ledger.jsonl',{'request_id':rid,'state':'RAW_SAVED','route':route,'raw_path':str(rp),'raw_sha256':raw_sha,'received_timestamp':received})
 env=json.loads(raw)
 if env.get('done') is not True: raise RuntimeError('PROTOCOL_NOT_DONE')
 if env.get('done_reason')=='length': raise RuntimeError('PROTOCOL_LENGTH_TRUNCATION')
 obj=json.loads(env.get('response','')); schema=S2 if route=='P2_scene' else S1; validate_obj(obj,schema)
 latency=time.monotonic()-t
 append_jsonl(root/'ledger.jsonl',{'request_id':rid,'state':'COMPLETED','route':route,'raw_path':str(rp),'raw_sha256':raw_sha,'latency_seconds':latency,'completed_timestamp':time.time(),'strict_json_ok':True,'source_binding_ok':True,'done':env.get('done'),'done_reason':env.get('done_reason'),'eval_count':env.get('eval_count')})
 return obj,latency,payload_sha,str(rp),raw_sha,env

def load_context(manifest):
 geo={}
 with (D/'geometry/person_geometry.csv').open() as f:
  for x in csv.DictReader(f): geo.setdefault(x['item_id'],[]).append(x)
 crop={}
 qa=json.loads((D/'reports/crop_qa_complete.json').read_text())
 for q in qa['qa']: crop[(q['item_id'],str(q['person_idx']))]=q
 rows=list(csv.DictReader(Path(manifest).open()))
 return geo,crop,rows

def route_budget_check(phase,counts,route):
 if counts[route]>=BUDGET[phase][route]: raise RuntimeError('BUDGET_EXCEEDED_'+route)

def source_size(row):
 with Image.open(row['image_path']) as im: return im.size

def should_stop_pilot(results,total_by_taxonomy=None):
 # Irreversible false positives plus mathematically impossible positive gates.
 c={}
 for r in results:
  c.setdefault(r['taxonomy'],{}).setdefault(r['image_decision'],0); c[r['taxonomy']][r['image_decision']]+=1
 floor=c.get('floor_sitting',{})
 if floor.get('ALERT_GROUND_LYING',0)>0 or floor.get('ATTENTION_NEAR_GROUND',0)>0: return 'FLOOR_IRREVERSIBLE_FP'
 if c.get('pushup_plank',{}).get('ALERT_GROUND_LYING',0)>0:return 'PUSHUP_PLANK_IRREVERSIBLE_FP'
 crawling_tax={'crawling_without_explicit_maintenance','crawling_quadruped_support'}
 if any(c.get(t,{}).get('ALERT_GROUND_LYING',0)>0 for t in crawling_tax): return 'CRAWLING_IRREVERSIBLE_FP'
 if total_by_taxonomy:
  done_by_taxonomy={}
  for r in results: done_by_taxonomy[r['taxonomy']]=done_by_taxonomy.get(r['taxonomy'],0)+1
  ground_tax={'supine_ground_lying','prone_ground_lying','side_lying'}
  ground_good=sum(c.get(t,{}).get('ALERT_GROUND_LYING',0)+c.get(t,{}).get('RECHECK_VISUAL_UNCERTAIN',0) for t in ground_tax)
  ground_remaining=sum(total_by_taxonomy.get(t,0)-done_by_taxonomy.get(t,0) for t in ground_tax)
  if ground_good+ground_remaining<60: return 'GROUND_GATE_MATHEMATICALLY_IMPOSSIBLE'
  multi=c.get('multi_person_one_lying',{}); multi_alert=multi.get('ALERT_GROUND_LYING',0)
  multi_remaining=total_by_taxonomy.get('multi_person_one_lying',0)-done_by_taxonomy.get('multi_person_one_lying',0)
  if multi_alert+multi_remaining<5: return 'MULTI_GATE_MATHEMATICALLY_IMPOSSIBLE'
 return None


def verify_inherited_prefix(rows):
 inherited=json.loads((D/'protocol/INHERITED_PILOT_PREFIX.json').read_text())
 if inherited.get('INHERITANCE_TYPE')!='EXACT_PAYLOAD_EQUIVALENCE' or inherited.get('INHERITED_PARENT_ROWS')!=4: raise RuntimeError('INHERITED_PREFIX_INVALID')
 xs=inherited.get('rows',[])
 if len(xs)!=4 or [x.get('row_index') for x in xs]!=[1,2,3,4]: raise RuntimeError('INHERITED_PREFIX_INVALID_ROWS')
 report=json.loads((D/'reports/inherited_prefix_equivalence.json').read_text())
 if report.get('gate')!='PASS' or report.get('payload_equivalent')!=4 or report.get('raw_verified')!=4: raise RuntimeError('INHERITED_PREFIX_EQUIVALENCE_REPORT_INVALID')
 for x,row in zip(xs,rows[:4]):
  if not x.get('equivalence_verified'): raise RuntimeError('INHERITED_PREFIX_NOT_VERIFIED')
  if x.get('item_id')!=row.get('item_id') or x.get('source_image_sha256')!=row.get('image_sha256') or x.get('view_sha256')!=row.get('full_view_sha256'): raise RuntimeError('INHERITED_PREFIX_BINDING_MISMATCH')
  fb=Path(row['full_view_path']).read_bytes()
  if hbytes(fb)!=x['view_sha256']: raise RuntimeError('INHERITED_PREFIX_VIEW_SHA_MISMATCH')
  if hbytes(build_payload(P2,fb,S2,1024))!=x['payload_sha256']: raise RuntimeError('INHERITED_PREFIX_PAYLOAD_MISMATCH')
  raw_path=Path(x['parent_output_record']['p2']['raw_path'])
  if not raw_path.exists() or hfile(raw_path)!=x['raw_sha256']: raise RuntimeError('INHERITED_PREFIX_RAW_MISMATCH')
  if x['parent_output_record'].get('item_id')!=x['item_id'] or x['parent_output_record'].get('image_decision')!=x['image_decision']: raise RuntimeError('INHERITED_PREFIX_OUTPUT_MISMATCH')
 return xs

def run(phase,manifest):
 if phase not in ALLOWED_PHASES: raise RuntimeError('PHASE_REJECTED')
 freeze=D/'freeze/CANDIDATE_FREEZE.json'
 if not freeze.exists(): raise RuntimeError('FREEZE_REQUIRED')
 root=D/'eval'/phase
 if root.exists() and any(root.iterdir()): raise RuntimeError('CLEAN_EXECUTION_REQUIRED_NONEMPTY_PHASE')
 root.mkdir(parents=True,exist_ok=True)
 geo,crop_map,rows=load_context(manifest); results=[]; counts={'P1_primary':0,'P1_background':0,'P2_scene':0}; latencies={k:[] for k in counts}
 total_by_taxonomy={}
 for row in rows: total_by_taxonomy[row['taxonomy']]=total_by_taxonomy.get(row['taxonomy'],0)+1
 output=root/'output.jsonl'; start_index=1; inherited_count=0
 if phase=='pilot':
  inherited_rows=verify_inherited_prefix(rows)
  for x in inherited_rows:
   rec=x['parent_output_record']; append_jsonl(output,rec); results.append(rec)
   append_jsonl(root/'ledger.jsonl',{'state':'INHERITED_PARENT','parent_request_id':x['parent_request_id'],'row_index':x['row_index'],'item_id':x['item_id'],'payload_sha256':x['payload_sha256'],'raw_sha256':x['raw_sha256'],'equivalence_verified':True})
  start_index=5; inherited_count=4
 for idx,row in enumerate(rows,1):
  if idx<start_index: continue
  if hfile(row['image_path'])!=row['image_sha256']: raise RuntimeError('SOURCE_SHA_MISMATCH_'+row['item_id'])
  if hfile(row['full_view_path'])!=row['full_view_sha256']: raise RuntimeError('FULL_VIEW_SHA_MISMATCH_'+row['item_id'])
  gs=geo.get(row['item_id'],[]); targets=[]
  for g in gs:
   if g['geom_state_a2']!='GEOM_UPRIGHT': targets.append(('P1_primary' if g['level']=='primary' else 'P1_background',g))
  p1recs=[]; decisions=[]
  for route,g in targets:
   route_budget_check(phase,counts,route); q=crop_map.get((row['item_id'],str(g['person_idx'])))
   if not q or not q.get('valid'): raise RuntimeError('MISSING_VALID_PREPARED_CROP')
   cp=Path(q['crop_path']); cb=cp.read_bytes()
   if hbytes(cb)!=q['crop_sha256']: raise RuntimeError('CROP_SHA_MISMATCH')
   rid=f'V7_B0R1C_{phase}_{idx:04d}_{route}_{g["person_idx"]}'
   bind={'item_id':row['item_id'],'source_image_sha256':row['image_sha256'],'view_sha256':q['crop_sha256'],'person_idx':g['person_idx'],'geom_state':g['geom_state_a2']}
   obj,lat,ps,rp,rs,env=call(build_payload(P1,cb,S1,384),rid,route,root,bind); counts[route]+=1;latencies[route].append(lat)
   dec=person_p1(obj,g['geom_state_a2']); decisions.append(dec);p1recs.append({'request_id':rid,'route':route,'person_idx':g['person_idx'],'geom_state':g['geom_state_a2'],'decision':dec,'vlm':obj,'latency_seconds':lat,'payload_sha256':ps,'raw_path':rp,'raw_sha256':rs})
  need_p2=(not decisions) or ('ALERT_GROUND_LYING' not in decisions) or ('PROVISIONAL_PRONE' in decisions)
  p2rec=None
  if need_p2:
   route='P2_scene';route_budget_check(phase,counts,route);fb=Path(row['full_view_path']).read_bytes();rid=f'V7_B0R1C_{phase}_{idx:04d}_P2_scene'
   bind={'item_id':row['item_id'],'source_image_sha256':row['image_sha256'],'view_sha256':row['full_view_sha256']}
   obj,lat,ps,rp,rs,env=call(build_payload(P2,fb,S2,1024),rid,route,root,bind);counts[route]+=1;latencies[route].append(lat)
   W,H=source_size(row);det_boxes=[[float(g['x1'])/W*1000,float(g['y1'])/H*1000,float(g['x2'])/W*1000,float(g['y2'])/H*1000] for g in gs]
   people=obj.get('people',[]); associations=match(det_boxes,[p['bbox_1000'] for p in people]);by_p={a['p2_index']:a for a in associations};p2dec=[]
   for j,person in enumerate(people):
    a=by_p.get(j)
    if a:
     g=gs[a['detector_index']]; prior=next((x['decision'] for x in p1recs if str(x['person_idx'])==str(g['person_idx'])),None)
     dec=p2_match(person,g['geom_state_a2'],prior)
    else: dec=p2_match(person,'GEOM_NOT_UPRIGHT',None)
    p2dec.append({'p2_index':j,'matched_detector_index':a['detector_index'] if a else None,'decision':dec,'vlm':person})
    if dec!='NO_EFFECT': decisions.append(dec)
   p2rec={'request_id':rid,'route':route,'vlm':obj,'associations':associations,'person_decisions':p2dec,'latency_seconds':lat,'payload_sha256':ps,'raw_path':rp,'raw_sha256':rs}
  image=aggregate(decisions,detected=bool(gs))
  rec={'state':'completed','phase':phase,'row_index':idx,'item_id':row['item_id'],'operational_id':row.get('operational_id'),'taxonomy':row['taxonomy'],'source_image_sha256':row['image_sha256'],'strict_json_ok':True,'source_binding_ok':True,'p1':p1recs,'p2':p2rec,'image_decision':image}
  append_jsonl(output,rec);results.append(rec)
  if phase=='pilot':
   why=should_stop_pilot(results,total_by_taxonomy)
   if why:
    summary={'phase':phase,'status':'EARLY_STOP','reason':why,'rows':len(results),'inherited_rows':inherited_count,'new_rows':len(results)-inherited_count,'route_counts':counts,'results':results};(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');raise RuntimeError('PILOT_EARLY_STOP_'+why)
 summary={'phase':phase,'status':'COMPLETE','rows':len(results),'inherited_rows':inherited_count,'new_rows':len(results)-inherited_count,'route_counts':counts,'latency':{k:{'p50':statistics.median(v) if v else None,'p95':sorted(v)[max(0,int(len(v)*.95)-1)] if v else None} for k,v in latencies.items()},'results':results}
 (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 return summary

if __name__=='__main__':
 if len(sys.argv)!=2: raise SystemExit('usage: run_v7_b0r1c.py pilot|regression|full_remaining')
 phase=sys.argv[1]; names={'pilot':'pilot156.csv','regression':'regression1.csv','full_remaining':'full_remaining.csv'}
 print(json.dumps(run(phase,D/'manifests'/names[phase]),ensure_ascii=False))
