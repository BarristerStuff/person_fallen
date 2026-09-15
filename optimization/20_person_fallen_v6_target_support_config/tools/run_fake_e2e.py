import json,sys,tempfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'policy'))
from contracts import parse,write_json,write_bytes,append_jsonl,sha
from target_policy import evaluate
from metrics import summarize
def person(pid,kind):
 p={'person_id':pid,'bbox_1000':[100*pid,100,100*pid+300,900],'person_visible':'yes','pose':'floor_sitting','torso_orientation':'upright','torso_ground_contact':'partial','head_shoulders_above_hips':'yes','support_surface':'floor','body_support_configuration':'pelvis_supported','explicit_work_evidence':'no','visual_quality':'clear','evidence':'fake visible facts'}
 if kind=='ground':p.update(pose='prone',torso_orientation='horizontal',torso_ground_contact='broad',head_shoulders_above_hips='no',body_support_configuration='torso_ground_supported')
 elif kind=='push':p.update(pose='pushup_plank',torso_orientation='horizontal',torso_ground_contact='partial',head_shoulders_above_hips='no',body_support_configuration='hands_feet_supported')
 elif kind=='crawl':p.update(pose='crawling',torso_orientation='inclined',torso_ground_contact='partial',head_shoulders_above_hips='no',body_support_configuration='hands_knees_supported')
 return p
def fake_for(row):
 t=row['taxonomy']; people=[person(1,'normal')]
 if t=='pushup_plank':people=[person(1,'push')]
 elif t.startswith('crawling'):people=[person(1,'crawl')]
 elif t=='multi_person_one_lying' or row.get('operational_id')=='PFV4_SCREEN_0066':people=[person(1,'normal'),person(2,'ground')]
 elif row['evaluation_stratum']=='ground_lying':people=[person(1,'ground')]
 return {'scene_coverage':'complete','people':people}
def run(phase,manifest,run):
 (run/'requests').mkdir(parents=True);outputs=[];requests=[]
 for row in manifest:
  q=run/'requests'/row['request_id'];q.mkdir();claim={'state':'claimed','request_id':row['request_id'],'item_id':row['item_id']};write_json(q/'claimed.json',claim);append_jsonl(run/'request_events.jsonl',claim)
  parsed=fake_for(row);raw=json.dumps({'model':'qwen3.5:4b','done':True,'done_reason':'stop','eval_count':100,'response':json.dumps(parsed)}).encode();write_bytes(q/'response.raw',raw);outer,p=parse(raw);dec=evaluate(p)
  o={'item_id':row['item_id'],'operational_id':row.get('operational_id'),'request_id':row['request_id'],'taxonomy':row['taxonomy'],'group_id':row['group_id'],'evaluation_stratum':row['evaluation_stratum'],'parsed':p,**dec,'strict_json_ok':True,'source_binding_ok':True,'http_status':200,'latency_seconds':.001,'eval_count':100};rec={**o,'state':'completed','completion_unknown':False,'raw_response_sha256':sha(q/'response.raw')};write_json(q/'completed.json',rec);append_jsonl(run/'request_events.jsonl',rec);append_jsonl(run/'output.jsonl',o);outputs.append(o);requests.append(rec)
 s=summarize(phase,manifest,outputs,requests);write_json(run/'summary.json',s);write_json(run/'COMPLETION_LOCK.json',{'status':'COMPLETE','gate':s['gate'],'summary_sha256':sha(run/'summary.json'),'requests':len(requests)});return s
def main():
 with tempfile.TemporaryDirectory(prefix='v6_fake_') as td:
  p=json.loads((ROOT/'manifests/pilot156.json').read_text());r=json.loads((ROOT/'manifests/regression1.json').read_text());base=Path(td);a=run('pilot',p,base/'pilot');b=run('regression',r,base/'regression');assert a['gate']==b['gate']=='PASS';assert len((base/'pilot/output.jsonl').read_text().splitlines())==156;assert len((base/'pilot/request_events.jsonl').read_text().splitlines())==312;print(json.dumps({'status':'PASS_FAKE_E2E','pilot_gate':'PASS','regression_gate':'PASS','rows':157,'claimed_raw_completed':157,'jsonl_valid':True,'network':0}))
if __name__=='__main__':main()
