"""Offline scoped lineage audit. Never requests models or reads VAL/Holdout resources."""
import csv, json, hashlib, importlib.util
from pathlib import Path
from collections import Counter
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
V5=ROOT.parents[1]; BASE=V5.parent
D=BASE/'13_person_fallen_v4_pose_attributes'; S=BASE/'14_person_fallen_v4_operational_freeze'
BINDINGS={}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p, expected=None):
 p=Path(p).resolve(); h=sha(p)
 if expected is not None and h!=expected: raise ValueError(f'SHA mismatch: {p}')
 BINDINGS[str(p)]=h; return h
def js(p): bind(p); return json.loads(Path(p).read_text())
def rows(p):
 bind(p)
 with open(p,newline='') as f: return list(csv.DictReader(f))
def unique(rr):
 out={r['item_id']:r for r in rr}
 if len(out)!=len(rr): raise ValueError('Duplicate item_id')
 return out
def module(name,p):
 bind(p);spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def audit():
 inv=js(V5/'reports/preparation_inventory.json')
 for p,h in inv['files'].items():bind(V5/p,h)
 policy=module('historical_policy',S/'policy/deterministic_policy.py')
 prep=module('preparation',V5/'tools/prepare_v5_dev.py')
 plan=js(D/'protocol/v4_full_dev_execution_plan.json'); sp=js(S/'protocol/final_operational_plan.json')
 diag=js(D/'protocol/v4_diagnostic_config.json'); sf=js(S/'freeze/CANDIDATE_FREEZE.json')
 bind(S/'protocol/final_operational_plan.json',sf['plan_sha256'])
 assert plan['model']==sp['model']==diag['model']
 for p in [plan,sp,diag]:
  assert p['model']['name']=='qwen3.5:4b' and p['model']['digest']=='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd'
  assert p['model']['endpoint']=='http://192.168.20.62:11434' and p['model']['ollama_version']=='0.23.2'
  assert (p['preprocess']['width'],p['preprocess']['height'],p['preprocess']['jpeg_quality'])==(448,336,70)
 for k in ['prompt','policy','temporal_policy']:
  bind(D/plan['frozen_components'][k],plan['frozen_components'][k+'_sha256'])
  bind(S/sp[k]['path'],sp[k]['sha256'])
  assert plan['frozen_components'][k+'_sha256']==sp[k]['sha256']
 bind(S/sp['definition']['path'],sp['definition']['sha256'])
 bind(S/'assets/person_detector/yolo11n.pt',sp['detector']['weight_sha256'])
 for key,spec in sp['execution_tools'].items():bind(S/spec['path'],spec['sha256'])
 for p in [D/'tools/run_v4_full_dev.py',D/'tools/run_v4_diagnostic.py']:bind(p)
 devrun=D/'eval/runs/dev_V4-A0-FULL-CROP-436'; screenrun=S/'eval/runs/screen_V4-A0-FULL-CROP'; dr=D/'eval/runs/dev_V4-A0-FULL-CROP-110'
 pr=plan['prerequisite_diagnostic']
 for f,k in [('summary.json','summary_sha256'),('COMPLETION_LOCK.json','completion_lock_sha256'),('predictions.csv','predictions_sha256')]:bind(dr/f,pr[k])
 dc=D/'manifests/v4_crop_manifest.csv'; bind(dc,pr['crop_manifest_sha256']); oldc=unique(rows(dc)); oldp=unique(rows(dr/'predictions.csv'))
 diagnostic_rows=rows(dc); diag_index={r['item_id']:i for i,r in enumerate(diagnostic_rows,1)}
 ds=js(dr/'summary.json'); assert ds['config_sha256']==bind(D/'protocol/v4_diagnostic_config.json')
 rt=js(dr/'runtime_preflight.json');assert rt['selected_model']['digest']==plan['model']['digest'] and rt['version']['version']=='0.23.2'
 assert rt['crop_manifest_sha256']==sha(dc) and rt['prompt_sha256']==sp['prompt']['sha256']
 manifests={'dev':V5/'manifests/v5_dev_manifest.csv','regression':S/'manifests/person_fallen_v4_operational_screen_crop.csv'}
 crops={'dev':D/'manifests/v4_full_dev_crop_manifest.csv','regression':manifests['regression']}
 runs={'dev':devrun,'regression':screenrun}; outputs={}; summaries={}
 for phase in ['dev','regression']:
  rr=rows(manifests[phase]); cm=unique(rows(crops[phase])); pp=rows(runs[phase]/'predictions.csv'); pm=unique(pp); sm=unique(rr)
  source_path=D/'manifests/v4_full_dev_436.csv' if phase=='dev' else S/'manifests/person_fallen_v4_operational_screen.csv'
  source_rows=unique(rows(source_path))
  assert set(source_rows)==set(sm)
  for item,sr in source_rows.items():
   for k,v in sr.items():assert sm[item][k]==v,(item,k,'source manifest binding')
  assert set(sm)==set(cm)==set(pm)
  summary=js(runs[phase]/'summary.json'); lock=js(runs[phase]/'COMPLETION_LOCK.json'); rt=js(runs[phase]/'runtime_preflight.json')
  bind(runs[phase]/'summary.json',lock['summary_sha256']); assert lock['status']==summary['status']=='COMPLETE'
  assert summary['crop_manifest_sha256']==rt['crop_manifest_sha256']==sha(crops[phase])
  assert summary['prompt_sha256']==rt['prompt_sha256']==sp['prompt']['sha256']
  assert summary['policy_sha256']==rt['policy_sha256']==sp['policy']['sha256']
  ppplan=D/'protocol/v4_full_dev_execution_plan.json' if phase=='dev' else S/'protocol/final_operational_plan.json'
  assert summary['plan_sha256']==rt['plan_sha256']==sha(ppplan)
  assert rt['selected_model']['digest']==plan['model']['digest'] and rt['version']['version']=='0.23.2'
  det=js(D/'detector/detector_full_dev_summary.json' if phase=='dev' else S/'detector/screen_detector_summary.json')
  assert det['crop_manifest_sha256']==sha(crops[phase]) and det['weight_sha256']==sp['detector']['weight_sha256']
  events=Path(runs[phase]/'request_events.jsonl');bind(events);ee=[json.loads(l) for l in events.read_text().splitlines()]
  claims={e['request_id']:e for e in ee if e['state']=='claimed'};completed={e['request_id']:e for e in ee if e['state']=='completed'}
  assert len(claims)*2==len(ee) and set(claims)==set(completed)
  out=[]
  for i,r in enumerate(rr,1):
   c=cm[r['item_id']];p=pm[r['item_id']]
   for k,v in c.items():assert r[k]==v,(r['item_id'],k)
   assert r['v3_split']==('V3_DEV' if phase=='dev' else 'V3_SCREEN')
   assert 'HOLDOUT' not in r['source_split'].upper()
   for pk,hk in [('image_path','image_sha256'),('prompt_path','prompt_sha256'),('full_view_path','full_view_sha256'),('crop_view_path','crop_view_sha256')]:bind(r[pk],r[hk])
   with Image.open(r['full_view_path']) as im:assert im.size==(448,336) and im.format=='JPEG'
   assert p['http_status']=='200' and p['strict_json_ok'].lower()=='true' and not p['parse_error']
   for k in ['taxonomy','ground_truth','metric_stratum']:
    if k in p:assert p[k]==r[k],(r['item_id'],k)
   assert p['person_detected'].lower()==r['person_detected'] and p['view_count']==r['view_count']
   attrs=policy.validate_attributes({k:p[k] for k in policy.EXPECTED_KEYS})
   dec=policy.map_attributes(attrs,detector_person_found=r['person_detected']=='true')
   assert dec['frame_decision']==p['frame_decision'] and dec['reason_code']==p['reason_code']
   if phase=='dev' and p['inference_source']=='CACHE_REUSE_IDENTICAL_INPUT':
    oc=oldc[r['item_id']];op=oldp[r['item_id']]
    for k in ['image_sha256','full_view_sha256','crop_view_sha256','person_detected','view_count']:assert oc[k]==r[k]
    for k in policy.EXPECTED_KEYS:assert op[k]==p[k]
    rawpath=dr/'responses'/f'dev_V4-A0-FULL-CROP-110_{diag_index[r["item_id"]]:04d}.json'
   else:
    assert p['request_id'] in completed
    rawpath=runs[phase]/'responses'/f'{p["request_id"]}.json'
   raw=js(rawpath);assert raw['done'] is True and raw['model']==plan['model']['name']
   assert policy.validate_attributes(json.loads(raw['response']))==attrs
   stratum=prep.classify(r) if phase=='dev' else r['operational_class']
   if phase=='dev':assert r['v5_stratum']==stratum
   if r['taxonomy']=='floor_sitting':assert stratum=='normal_negative'
   out.append({**r,'v5_stratum':stratum,'operational_id':r.get('operational_id',r.get('diagnostic_id')),'primary_decision':p['frame_decision'],'primary_cache_source':str(runs[phase]/'predictions.csv'),'primary_cache_sha256':sha(runs[phase]/'predictions.csv'),'primary_response_source':str(rawpath),'primary_response_sha256':sha(rawpath),'primary_cache_binding_ok':True,'secondary_required':p['frame_decision']!=policy.decision('ALERT_GROUND_LYING','')['frame_decision'],'request_id':f'V5_A0_{phase.upper()}_{i:04d}' if p['frame_decision']!='ALERT_GROUND_LYING' else ''})
  counts=Counter(r['v5_stratum'] for r in out);n=sum(r['secondary_required'] for r in out)
  assert counts==({'ground_lying':145,'normal_negative':230,'auxiliary_attention':41,'visual_uncertain':20} if phase=='dev' else {'ground_lying':25,'normal_negative':51})
  assert n==(288 if phase=='dev' else 52)
  assert sum(r['taxonomy']=='floor_sitting' for r in out)==(55 if phase=='dev' else 25)
  outputs[phase]=out;summaries[phase]={'rows':len(out),'strata':dict(counts),'secondary_requests_planned':n,'primary_alert_rows':len(out)-n,'primary_cache_binding_success':1.0}
 for key in ['item_id','group_id','image_sha256']:
  assert not ({r[key] for r in outputs['dev']}&{r[key] for r in outputs['regression']}),f'Split overlap {key}'
 return outputs,{'status':'PASS','phases':summaries,'model':plan['model'],'primary_preprocess':{'dev':plan['preprocess'],'regression':sp['preprocess']},'primary_detector':sp['detector'],'bindings':BINDINGS,'GT_TYPE':'PROMPT_DERIVED_SYNTHETIC_GT','HUMAN_SEMANTIC_REVIEW_REQUIRED_FOR_SYNTHETIC_DEVELOPMENT':False,'MODEL_PREDICTION_USED_AS_GT':False,'pixel_semantic_validation_claimed':False,'VAL_RESOURCES_READ':0,'HOLDOUT_RESOURCES_READ':0}

if __name__=='__main__':
 out,report=audit()
 for phase,rr in out.items():
  with (ROOT/f'manifests/{phase}.json').open('x') as f:json.dump(rr,f,ensure_ascii=False,indent=2)
  with (ROOT/f'manifests/{phase}_requests.csv').open('x',newline='') as f:
   selected=[r for r in rr if r['secondary_required']];w=csv.DictWriter(f,fieldnames=selected[0]);w.writeheader();w.writerows(selected)
 with (ROOT/'reports/cache_preflight.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
 print(json.dumps(report['phases'],indent=2))
