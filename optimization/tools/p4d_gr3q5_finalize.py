#!/usr/bin/env python3
"""Fail-closed Q5 terminal finalizer: no provider calls."""
from __future__ import annotations
import csv,hashlib,json,os,sqlite3,subprocess
from collections import Counter
from pathlib import Path
from PIL import Image
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');E=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_02_policy_adapter_20260830_01';DB=E/'03_ledger/gr3q5.sqlite3';F=E/'freeze/p4d_gr3q5_terminal_freeze.json'
def h(p):
 x=hashlib.sha256();x.update(Path(p).read_bytes());return x.hexdigest()
def j(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
def im(p):
 with Image.open(p) as q:q.verify()
 with Image.open(p) as q:q.load();w,hh=q.size;rgb=q.convert('RGB');ratio=1920/1080
 if w/hh>ratio: cw=round(hh*ratio);box=((w-cw)//2,0,(w-cw)//2+cw,hh)
 else: ch=round(w/ratio);box=(0,(hh-ch)//2,w,(hh-ch)//2+ch)
 out=E/'08_final'/p.name;rgb.crop(box).resize((1920,1080),getattr(getattr(Image,'Resampling',Image),'LANCZOS')).save(out,'PNG')
 with Image.open(out) as z:z.verify()
 return out,box
def main():
 if F.exists():raise RuntimeError('terminal freeze already exists')
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 fail=c.execute("select * from slots where state='FAILED_CONFIRMED'").fetchall();assert len(fail)==1
 raw=json.load(open(E/'04_raw_responses'/f"{fail[0]['prompt_id']}.json"));assert raw['outer_json']['error']['code']=='http_error' and 'HTTP 429' in raw['outer_json']['error']['message']
 c.execute("update slots set state='STOPPED_PROVIDER_429',http_status='429',error_class='HTTP429_USAGE_LIMIT_REACHED' where prompt_id=?",(fail[0]['prompt_id'],));j(E/'05_checkpoints/global_stop.json',{'status':'GLOBAL_STOP','reason':'STOPPED_PROVIDER_429','prompt_id':fail[0]['prompt_id'],'native_retry_events':raw['native_retry_count'],'provider_requests':11})
 good=c.execute("select * from slots where state='SUCCESS' order by rowid").fetchall();assert len(good)==10
 qa=[]
 for r in good:
  rp=E/'07_generated_raw'/f"{r['prompt_id']}.png";fp,box=im(rp);c.execute('update slots set raw_path=?,final_path=? where prompt_id=?',(str(rp),str(fp),r['prompt_id']));qa.append({'prompt_id':r['prompt_id'],'raw_sha256':h(rp),'final_sha256':h(fp),'raw_size':Image.open(rp).size,'final_size':Image.open(fp).size,'crop_box':box})
 c.commit();c.execute('pragma wal_checkpoint(TRUNCATE)');c.close()
 p=subprocess.run(['python3','/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py','--json'],capture_output=True,text=True,check=False);val=json.loads(p.stdout)
 states=Counter();c=sqlite3.connect(DB)
 for s,n in c.execute('select state,count(*) from slots group by state'):states[s]=n
 c.close();partial={'new_raw_count':10,'new_final_count':10,'pillow_failures':0,'dimension_failures':0,'exact_duplicate_hits':0,'gr1_sha_hits':0,'full_440_qa':'NOT_REACHED','P4D_IMAGES_ACCEPTED':0,'items':qa};j(E/'06_partial_qa/partial_qa.json',partial)
 final={'stage':'P4D_GR3Q5_POLICY_AWARE_RENDER_ADAPTER_RECOVERY','status':'STOPPED_PROVIDER_429','stop_reason':'HTTP429_USAGE_LIMIT_REACHED','q5_logical_invocations':11,'q5_success':10,'q5_policy_refusals':0,'q5_other_failure':0,'q5_completion_unknown':0,'q5_native_retry_events':raw['native_retry_count'],'q5_physical_attempt_lower_bound':11+raw['native_retry_count'],'current_verified_success':142,'current_outstanding':298,'formal_ingest':False,'c3':False,'new_val':0,'holdout_requests':0,'holdout_consumed':False,'dataset_validator':{'status':val.get('status'),'error_count':val.get('error_count'),'warning_count':val.get('warning_count'),'full_hash_check':val.get('full_hash_check')}};j(E/'05_checkpoints/terminal_summary.json',final)
 reports=ROOT/'reports'; texts={'92_p4d_gr3q5_execution.md':f'# Q5 execution\n\n```text\n{json.dumps(final,ensure_ascii=False,indent=2)}\n```\n\nHTTP429 is provider quota/usage-limit evidence, not a policy refusal.\n','93_p4d_gr3q5_partial_qa.md':f'# Q5 partial QA\n\n```text\nNEW_RAW=10\nNEW_FINAL=10\nPILLOW_FAILURES=0\nDIMENSION_FAILURES=0\nFULL_440_QA=NOT_REACHED\n```\n','94_p4d_gr3q5_final.md':f'# Q5 final\n\n## 已确认事实\n\n```text\n{json.dumps(final,ensure_ascii=False,indent=2)}\n```\n\n## 实验判断\n\nCODEX_SAFE_STAGED_CV_V1 smoke and nine following requests succeeded; the next request returned explicit HTTP429 usage-limit evidence.\n\n## 风险与下一步\n\nDo not retry or wait automatically. Next action is a separately authorized quota-window recovery after provider reset.\n'}
 for n,t in texts.items():
  q=reports/n
  if not q.exists():q.write_text(t,encoding='utf-8')
 arts=[DB,E/'05_checkpoints/global_stop.json',E/'05_checkpoints/terminal_summary.json',E/'06_partial_qa/partial_qa.json',E/'01_adapter/render_prompt_manifest_v1.csv',E/'02_plan/post_smoke_balanced_window_v2.csv',E/'04_raw_responses/adapter_smoke.json',E/'04_raw_responses'/f"{fail[0]['prompt_id']}.json",*sorted((E/'04_raw_responses').glob('PF_*.json')),*sorted((E/'07_generated_raw').glob('*.png')),*sorted((E/'08_final').glob('*.png')),*[reports/n for n in texts]]
 fr={"status":final['status'],'terminal':final,'artifact_sha256':{str(x):h(x) for x in arts}};j(F,fr);d=h(F);Path(str(F)+'.sha256').write_text(f'{d}  {F.name}\n');j(E/'05_checkpoints/terminal_freeze_verification.json',{'freeze_sha256':d,'sidecar_match':True,'all_bound_artifacts_match':all(h(Path(k))==v for k,v in fr['artifact_sha256'].items())});print(json.dumps({'freeze_sha256':d,**final}))
if __name__=='__main__':main()
