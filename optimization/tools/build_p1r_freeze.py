#!/usr/bin/env python3
"""Build P1R preflight artifacts solely from currently observed files and server data."""
from __future__ import annotations
import csv,hashlib,json,os,sys,urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization'); P1A=ROOT/'03_p1a_think_false_protocol'; P1R=ROOT/'04_p1r_freeze_binding_recovery'; DATA=ROOT/'01_data'; DS=Path('/home/yanbo/net_vlm_xunjian_dataset')
EXPECTED={'prompt':'b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4','splits':'16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a','formal':'771380b70099e2e2e641330a7d4f04860e2284725722bde3cd2da8988abfb2c6','p1a_config':'db933a7420a4ca0f50785c487c1f0703830af9804e4cac1f0a962f18d4500557','p1a_runner':'6ebc633b3a89ab9aaa4ea5653fd8fec126f283e8c5d70ce657c46b5e8e926f93','dev_predictions':'5d67e80d753ed71ae33cf9c222a8793b829c60a0bc1ff5ee09085518bf9d359b'}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def atomic_json(p,data):
 tmp=p.with_suffix(p.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def atomic_csv(p,rs,fields):
 tmp=p.with_suffix(p.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rs);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def http_json(url):
 with urllib.request.urlopen(url,timeout=10) as r:return json.loads(r.read().decode())
def main():
 for d in [P1R/'config',P1R/'preflight',P1R/'freeze',P1R/'val']:d.mkdir(parents=True,exist_ok=True)
 paths={'prompt':ROOT/'00_definition/p0_prompt.txt','splits':DATA/'frozen_splits.csv','formal':DATA/'frozen_manifest.csv','p1a_config':P1A/'config/p1a_think_false_config.json','p1a_runner':ROOT/'tools/run_p1a_think_false.py','p1r_runner':ROOT/'tools/run_p1r_recovery_val.py','dev_manifest':P1A/'dev/dev_manifest.csv','dev_predictions':P1A/'dev/predictions.csv','dev_raw_responses':P1A/'dev/raw_responses.jsonl','dev_request_log':P1A/'dev/request_log.jsonl','original_freeze':P1A/'freeze/p1a_dev_freeze.json','binding_audit':P1A/'freeze/p1a_dev_freeze_binding_audit.json'}
 hashes={k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()}
 for key,expected in EXPECTED.items():
  if hashes[key]['sha256']!=expected:raise SystemExit(f'BLOCKED_EXPECTED_HASH_MISMATCH:{key}')
 p1a_cfg=json.loads(paths['p1a_config'].read_text())
 expected_sem={'model':'qwen3.5:4b','endpoint':'http://192.168.20.62:11434','stream':False,'format':'json','think':False,'concurrency':1,'preprocess_mode':'letterbox','target_size':'448x336','jpeg_quality':70}
 if any(p1a_cfg.get(k)!=v for k,v in expected_sem.items()) or p1a_cfg.get('options')!={'temperature':0,'num_ctx':8192,'num_predict':256}:raise SystemExit('BLOCKED_P1A_CONFIG_SEMANTICS_MISMATCH')
 # P1R config contains the identical request semantics plus only durable-governance parameters.
 p1r_cfg={**expected_sem,'options':p1a_cfg['options'],'parser_source':'response_only','thinking_fallback':False,'attempts_per_media':1,'automatic_retry':False,'ledger':'sqlite_wal_synchronous_full','request_semantics_source':'P1A config '+hashes['p1a_config']['sha256'],'prompt_changed':False,'preprocess_changed':False}
 atomic_json(P1R/'config/p1r_config.json',p1r_cfg);hashes['p1r_config']={'path':str(P1R/'config/p1r_config.json'),'sha256':sha(P1R/'config/p1r_config.json')}
 # capability evidence is captured before freeze and bound by hash.
 version=http_json('http://192.168.20.62:11434/api/version');tags=http_json('http://192.168.20.62:11434/api/tags');atomic_json(P1R/'config/ollama_version.json',version);atomic_json(P1R/'config/ollama_tags.json',tags)
 model=next((x for x in tags.get('models',[]) if x.get('name')=='qwen3.5:4b'),None)
 if not model:raise SystemExit('BLOCKED_MODEL_MISSING')
 if model.get('digest')!='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd':raise SystemExit('BLOCKED_MODEL_DIGEST_CHANGED')
 hashes['ollama_version']={'path':str(P1R/'config/ollama_version.json'),'sha256':sha(P1R/'config/ollama_version.json')};hashes['ollama_tags']={'path':str(P1R/'config/ollama_tags.json'),'sha256':sha(P1R/'config/ollama_tags.json')}
 # Independently audit P1A DEV entity and protocol evidence.
 dm,dp=rows(paths['dev_manifest']),rows(paths['dev_predictions']);dl=[json.loads(x) for x in paths['dev_request_log'].read_text().splitlines() if x.strip()]
 sets=[{x['media_id'] for x in xset} for xset in [dm,dp,dl]]
 dev_audit={'manifest_rows':len(dm),'manifest_unique_media':len(sets[0]),'predictions_rows':len(dp),'predictions_unique_media':len(sets[1]),'request_log_rows':len(dl),'request_log_unique_media':len(sets[2]),'entity_sets_equal':sets[0]==sets[1]==sets[2],'holdout_rows':sum(x.get('split')=='HOLDOUT' for x in dm),'http_ok':sum(x.get('http_ok')=='true' for x in dp),'json_ok':sum(x.get('json_ok')=='true' for x in dp),'schema_ok':sum(x.get('schema_ok')=='true' for x in dp),'canonical_ok':sum(x.get('canonical_ok')=='true' for x in dp),'thinking_present':sum(x.get('thinking_present')=='true' for x in dp)}
 if not(dev_audit['manifest_rows']==dev_audit['manifest_unique_media']==dev_audit['predictions_rows']==dev_audit['predictions_unique_media']==dev_audit['request_log_rows']==dev_audit['request_log_unique_media']==310 and dev_audit['entity_sets_equal'] and dev_audit['holdout_rows']==0 and all(dev_audit[k]==310 for k in ['http_ok','json_ok','schema_ok','canonical_ok']) and dev_audit['thinking_present']==0):raise SystemExit('BLOCKED_P1A_DEV_AUDIT_FAILURE')
 original=json.loads(paths['original_freeze'].read_text());declared=original.get('dev_manifest_sha256');actual=hashes['dev_manifest']['sha256'];history={'original_freeze_declared_dev_manifest_sha256':declared,'actual_dev_manifest_sha256':actual,'original_freeze_binding_match':declared==actual,'original_freeze_binding_mismatch':declared!=actual,'p1a_val_prior_confirmed_exposure':10,'p1a_val_prior_possible_additional_exposure':1,'p1a_val_prior_exposure_lower_bound':10,'p1a_val_prior_exposure_upper_bound':11,'dev_entity_audit':dev_audit}
 if history['original_freeze_binding_match']:raise SystemExit('BLOCKED_HISTORY_MISMATCH_NOT_REPRODUCED')
 atomic_json(P1R/'preflight/p1a_history_audit.json',history)
 # VAL manifest must match both frozen assets and contain deterministic GT only.
 formal={x['media_id']:x for x in rows(DATA/'frozen_manifest.csv')};split={x['media_candidate_id'] or x['image_filename']:x for x in rows(DATA/'frozen_splits.csv')}
 val=[x for x in formal.values() if x['split']=='VAL']
 if len(val)!=100 or len({x['media_id'] for x in val})!=100 or any(x['event_label'] not in {'0','1'} for x in val) or any(x['split']!='VAL' for x in val):raise SystemExit('BLOCKED_RECOVERY_VAL_MANIFEST_INVALID')
 fields=['media_id','image_path','image_sha256','event_label','sample_role','scenario_id','group_id','split','source_type','event_definition_version','formal_relative_path']
 rv=[{'media_id':x['media_id'],'image_path':str(DS/x['formal_relative_path']),'image_sha256':x['image_sha256'],'event_label':x['event_label'],'sample_role':x['sample_role'],'scenario_id':x['scenario_id'],'group_id':x['group_id'],'split':x['split'],'source_type':x['source_type'],'event_definition_version':x['event_definition_version'],'formal_relative_path':x['formal_relative_path']} for x in sorted(val,key=lambda x:x['media_id'])]
 atomic_csv(P1R/'preflight/recovery_val_manifest.csv',rv,fields);hashes['recovery_val_manifest']={'path':str(P1R/'preflight/recovery_val_manifest.csv'),'sha256':sha(P1R/'preflight/recovery_val_manifest.csv')}
 inventory={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'hashes':hashes,'original_freeze_binding':history,'recovery_val_manifest_rows':len(rv),'recovery_val_manifest_unique_media':len({x['media_id'] for x in rv}),'recovery_val_holdout_rows':0,'recovery_val_uncertain_gt_count':0}
 atomic_json(P1R/'preflight/actual_hash_inventory.json',inventory)
 candidate={'stage':'P1R_FREEZE_BINDING_RECOVERY','event_name':'person_fallen','event_definition_version':'v2.0','file_hashes':hashes,'prompt_sha256':hashes['prompt']['sha256'],'frozen_splits_sha256':hashes['splits']['sha256'],'frozen_formal_manifest_sha256':hashes['formal']['sha256'],'p1a_config_sha256':hashes['p1a_config']['sha256'],'p1a_dev_manifest_actual_sha256':hashes['dev_manifest']['sha256'],'p1a_dev_predictions_sha256':hashes['dev_predictions']['sha256'],'recovery_val_manifest_sha256':hashes['recovery_val_manifest']['sha256'],'model':'qwen3.5:4b','model_digest':model['digest'],'ollama_version':version.get('version','unknown'),'endpoint':expected_sem['endpoint'],'think':False,'format':'json','temperature':0,'num_ctx':8192,'num_predict':256,'preprocess':'letterbox','target_size':'448x336','jpeg_quality':70,'parser_source':'response_only','historical_p1a_freeze_binding_error':True,'prior_val_confirmed_exposure':10,'prior_val_possible_additional_exposure':1,'holdout_requests_before_p1r':0,'generated_at_utc':datetime.now(timezone.utc).isoformat()}
 atomic_json(P1R/'preflight/recovery_freeze_candidate.json',candidate)
 print(json.dumps({'P1R_PREFLIGHT':'PASS','history_binding_mismatch':True,'dev_entity_audit':dev_audit,'recovery_val_rows':len(rv),'recovery_val_sha256':hashes['recovery_val_manifest']['sha256'],'p1r_config_sha256':hashes['p1r_config']['sha256'],'model_digest':model['digest']},ensure_ascii=False))
if __name__=='__main__':main()
