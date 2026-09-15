#!/usr/bin/env python3
"""Run the frozen V2 P0 image protocol on DEV and VAL only."""
from __future__ import annotations

import base64, csv, hashlib, json, math, shutil, statistics, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from PIL import Image

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
DATA=ROOT/'01_data'; FORMAL=Path('/home/yanbo/net_vlm_xunjian_dataset')
CONFIG=json.loads((ROOT/'02_p0_image_baseline/config/p0_image_baseline_v2.json').read_text())
PROMPT=(ROOT/'00_definition/p0_prompt.txt').read_text()
PROMPT_SHA=hashlib.sha256(PROMPT.encode()).hexdigest()
IMAGE_RESAMPLING=getattr(getattr(Image,'Resampling',Image),'LANCZOS')

def hash_file(p:Path)->str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def write_csv(p:Path,rows,fields):
 with p.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def pctl(xs,q):
 if not xs:return None
 xs=sorted(xs); k=(len(xs)-1)*q; lo=math.floor(k); hi=math.ceil(k)
 return xs[lo] if lo==hi else xs[lo]+(xs[hi]-xs[lo])*(k-lo)
def finite(v):return round(v,6) if isinstance(v,float) else v

def process(src:Path,dst:Path):
 with Image.open(src) as im:
  im.verify()
 with Image.open(src) as im:
  im=im.convert('RGB'); im.thumbnail((448,336),IMAGE_RESAMPLING)
  canvas=Image.new('RGB',(448,336),(128,128,128)); x=(448-im.width)//2; y=(336-im.height)//2;canvas.paste(im,(x,y));canvas.save(dst,'JPEG',quality=70,optimize=True)

def one_request(image:Path):
 payload={'model':CONFIG['model'],'prompt':PROMPT,'images':[base64.b64encode(image.read_bytes()).decode('ascii')],'stream':False,'format':'json','options':{'temperature':0,'num_ctx':8192,'num_predict':256}}
 data=json.dumps(payload).encode(); start=time.time(); first=True
 for attempt in range(1,CONFIG['max_transport_retries']+2):
  try:
   req=request.Request(CONFIG['endpoint']+'/api/generate',data=data,headers={'Content-Type':'application/json'},method='POST')
   with request.urlopen(req,timeout=CONFIG['timeout_seconds']) as resp: raw=resp.read().decode('utf-8'); status=resp.status
   return {'http_ok':True,'status_code':status,'raw':raw,'attempt_count':attempt,'first_attempt_success':attempt==1,'latency_seconds':time.time()-start,'error_type':''}
  except (error.URLError,error.HTTPError,TimeoutError) as exc:
   last={'http_ok':False,'status_code':getattr(exc,'code',None),'raw':'','attempt_count':attempt,'first_attempt_success':False,'latency_seconds':time.time()-start,'error_type':type(exc).__name__+': '+str(exc)}
   if attempt<=CONFIG['max_transport_retries']:continue
   return last

def parse(result):
 if not result['http_ok']:return 'protocol_failure','',False,False,result['error_type']
 try: outer=json.loads(result['raw']); text=outer.get('response',''); obj=json.loads(text)
 except Exception as exc:return 'protocol_failure','',False,False,'json_parse_failure: '+str(exc)
 if not isinstance(obj,dict) or set(obj)!={'person_fallen','evidence'} or obj.get('person_fallen') not in {'positive','negative','uncertain'} or not isinstance(obj.get('evidence'),str) or not obj['evidence'].strip(): return 'protocol_failure','',True,False,'schema_failure'
 return obj['person_fallen'],obj['evidence'].strip(),True,True,''

def metrics(rows):
 determ=[r for r in rows if r['ground_truth'] in {'0','1'} and r['canonical_prediction_success']=='true']
 tp=fp=tn=fn=0
 for r in determ:
  gt=r['ground_truth']; alert=r['predicted_binary_alert']=='true'
  if gt=='1' and alert:tp+=1
  elif gt=='1':fn+=1
  elif alert:fp+=1
  else:tn+=1
 d=tp+tn+fp+fn
 ratio=lambda n,d:None if not d else n/d
 hard=[r for r in determ if r['sample_role']=='hard_negative']; ordinary=[r for r in determ if r['sample_role']=='negative']
 return {'evaluated_determinate_count':d,'TP':tp,'FP':fp,'TN':tn,'FN':fn,'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),'accuracy':ratio(tp+tn,d),'fpr':ratio(fp,fp+tn),'specificity':ratio(tn,tn+fp),'positive_recall':ratio(tp,tp+fn),'hard_negative_count':len(hard),'hard_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in hard),len(hard)),'ordinary_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in ordinary),len(ordinary)),'model_uncertain_rate':ratio(sum(r['predicted_status']=='uncertain' for r in determ),len(determ)),'protocol_failure_count':sum(r['canonical_prediction_success']!='true' for r in rows)}

def main():
 manifest=list(csv.DictReader((DATA/'frozen_manifest.csv').open()))
 selected=[r for r in manifest if r['split'] in {'DEV','VAL'}]
 holdout=[r for r in manifest if r['split']=='HOLDOUT']
 if any(r['split']=='HOLDOUT' for r in selected) or len(selected)+len(holdout)!=len(manifest):raise SystemExit('holdout isolation invariant failed')
 stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); run=ROOT/'02_p0_image_baseline/runs'/f'P0_{stamp}'; proc=run/'processed_448x336';proc.mkdir(parents=True)
 shutil.copy2(ROOT/'02_p0_image_baseline/config/p0_image_baseline_v2.json',run/'run_config.json');(run/'prompt.txt').write_text(PROMPT);(run/'prompt.sha256').write_text(PROMPT_SHA+'  prompt.txt\n')
 fields=['media_id','image_sha256','split','scenario_id','group_id','ground_truth','sample_role','predicted_status','predicted_binary_alert','evidence','http_ok','json_ok','schema_ok','canonical_prediction_success','attempt_count','latency_seconds','is_correct','error_type']
 preds=[]; logs=[]; raws=[]; errors=[]
 for n,row in enumerate(selected,1):
  src=FORMAL/row['formal_relative_path']; dst=proc/(row['media_id']+'.jpg')
  try:process(src,dst); result=one_request(dst); pred,evidence,jsonok,schemaok,etype=parse(result)
  except Exception as exc: result={'http_ok':False,'attempt_count':0,'latency_seconds':0.0,'first_attempt_success':False,'raw':'','status_code':None};pred='protocol_failure';evidence='';jsonok=False;schemaok=False;etype='preprocess_failure: '+str(exc)
  canonical=pred in {'positive','negative','uncertain'}; alert=pred=='positive'; gt=row['event_label']; correct=(canonical and ((gt=='1' and alert) or (gt=='0' and not alert))) if gt in {'0','1'} else ''
  out={'media_id':row['media_id'],'image_sha256':row['image_sha256'],'split':row['split'],'scenario_id':row['scenario_id'],'group_id':row['group_id'],'ground_truth':gt,'sample_role':row['sample_role'],'predicted_status':pred,'predicted_binary_alert':str(alert).lower() if canonical else '','evidence':evidence,'http_ok':str(result['http_ok']).lower(),'json_ok':str(jsonok).lower(),'schema_ok':str(schemaok).lower(),'canonical_prediction_success':str(canonical).lower(),'attempt_count':result['attempt_count'],'latency_seconds':f"{result['latency_seconds']:.6f}",'is_correct':str(correct).lower() if correct!='' else '','error_type':etype};preds.append(out)
  logs.append({'media_id':row['media_id'],'split':row['split'],'request_start_utc':'','request_end_utc':'','latency_seconds':result['latency_seconds'],'attempt_count':result['attempt_count'],'first_attempt_success':result['first_attempt_success'],'http_ok':result['http_ok'],'status_code':result.get('status_code'),'error_type':etype})
  raws.append({'media_id':row['media_id'],'response':result.get('raw','')})
  if not canonical:errors.append(out)
  if n%10==0:print(f'P0_PROGRESS={n}/{len(selected)}',flush=True)
 write_csv(run/'run_manifest.csv',selected,list(selected[0]));write_csv(run/'predictions.csv',preds,fields);write_csv(run/'request_log.csv',logs,list(logs[0]));write_csv(run/'protocol_errors.csv',errors,fields)
 with (run/'raw_responses.jsonl').open('w') as f:
  for x in raws:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 with (run/'request_log.jsonl').open('w') as f:
  for x in logs:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 for name,subset in [('false_negatives.csv',[r for r in preds if r['ground_truth']=='1' and r['canonical_prediction_success']=='true' and r['predicted_binary_alert']!='true']),('false_positives.csv',[r for r in preds if r['ground_truth']=='0' and r['canonical_prediction_success']=='true' and r['predicted_binary_alert']=='true']),('model_uncertain.csv',[r for r in preds if r['predicted_status']=='uncertain']),('protocol_failures.csv',errors)]:write_csv(run/name,subset,fields)
 bysplit={s:metrics([r for r in preds if r['split']==s]) for s in ['DEV','VAL']};bysplit['DEV+VAL']=metrics(preds)
 success=[r for r in preds if r['canonical_prediction_success']=='true']; lats=[float(r['latency_seconds']) for r in success]; warm=lats[1:]
 protocol={'request_count':len(preds),'holdout_requests':0,'holdout_consumed':False,'http_success_rate':sum(r['http_ok']=='true' for r in preds)/len(preds),'json_parse_success_rate':sum(r['json_ok']=='true' for r in preds)/len(preds),'schema_success_rate':sum(r['schema_ok']=='true' for r in preds)/len(preds),'canonical_prediction_success_rate':len(success)/len(preds),'first_attempt_success_rate':sum(x['first_attempt_success'] for x in logs)/len(logs),'prediction_distribution':dict(Counter(r['predicted_status'] for r in preds)),'latency_seconds':{'cold_start':lats[0] if lats else None,'warm_mean':statistics.mean(warm) if warm else None,'p50':pctl(warm,.5),'p95':pctl(warm,.95),'max':max(warm) if warm else None}}
 summary={'P0_NAME':'P0_IMAGE_BASELINE_V2','run_dir':str(run),'model':CONFIG['model'],'endpoint':CONFIG['endpoint'],'prompt_sha256':PROMPT_SHA,'frozen_manifest_sha256':hash_file(DATA/'frozen_manifest.csv'),'frozen_splits_sha256':hash_file(DATA/'frozen_splits.csv'),'planned_dev_requests':sum(r['split']=='DEV' for r in selected),'planned_val_requests':sum(r['split']=='VAL' for r in selected),'planned_holdout_requests':0,'metrics':bysplit,'protocol':protocol,'source_type':'ai_generated','preprocess':{'mode':'letterbox','target_size':'448x336','jpeg_quality':70}}
 (run/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=finite)+'\n')
 lines=['# P0_IMAGE_BASELINE_V2','',f"- Model: `{CONFIG['model']}`",f"- Endpoint: `{CONFIG['endpoint']}`",f"- Requests: DEV={summary['planned_dev_requests']}, VAL={summary['planned_val_requests']}, HOLDOUT=0",f"- HOLDOUT_CONSUMED=false",'', '## Metrics']
 for k,v in bysplit.items():lines += [f'### {k}',*['- '+a+': '+str(finite(b)) for a,b in v.items()]]
 lines += ['', '## Protocol and latency', *['- '+a+': '+str(finite(b)) for a,b in protocol.items()]]
 (run/'summary.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({'P0_STATUS':'COMPLETE','run_dir':str(run),'requests':len(preds),'holdout_requests':0,'summary':summary},ensure_ascii=False,default=finite))
if __name__=='__main__':main()
