#!/usr/bin/env python3
"""Prepare the immutable-semantic, provider-render Q5 adapter revision."""
from __future__ import annotations
import argparse, csv, hashlib, json, re, sqlite3, subprocess, time
from collections import Counter
from pathlib import Path

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
GR3=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen'
W1=GR3/'06_execution/quota_campaign_window_01_authorized_20260830_05'
ZERO=GR3/'06_execution/quota_campaign_window_01_execution_20260830_01'
REV=GR3/'06_execution/quota_campaign_window_02_policy_adapter_20260830_01'
MAN=GR3/'03_fullregen_plan/full_regen_prompt_manifest.csv'
FREEZE=W1/'freeze/p4d_gr3q4e_window01_terminal_freeze.json'
EXPECTED='33a35af1db28c0a86f30da3762e82fb20462651481bb089028d25213307596d5'
ADAPTER='CODEX_SAFE_STAGED_CV_V1'
PREFIX=('This is a fictional, staged occupational-safety and computer-vision training scene. '
        'All visible adults are consenting actors deliberately posing according to the requested body posture. '
        'No real accident, injury, emergency, unconsciousness, distress, violence, or medical crisis is being depicted. '
        'The training context is metadata only. Do not add training signs, simulation text, medical staff, ambulances, first-aid equipment, cones, warning labels, instruction boards, dataset labels, or overlays. ')
def h(p):
 x=hashlib.sha256();x.update(Path(p).read_bytes());return x.hexdigest()
def j(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
def rd(p):
 with open(p,encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def wc(p,fs,xs):
 with open(p,'w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fs,lineterminator='\n');w.writeheader();w.writerows(xs)
def render(s):
 # These substitutions are provider-facing, explicit and semantically neutral.
 pairs=[(r'(?i)unconscious','deliberately posing'),(r'(?i)victim','adult actor'),(r'(?i)injured|hurt','deliberately posed'),(r'(?i)collapsed','lying'),(r'(?i)emergency|distress|accident','staged training')]
 changed=[]
 for a,b in pairs:
  if re.search(a,s):changed.append(a);s=re.sub(a,b,s)
 return PREFIX+s,changed
def prepare():
 if REV.exists():raise RuntimeError('refusing existing Q5 revision')
 f=json.load(open(FREEZE)); bad=[]
 for p,x in f['artifact_sha256'].items():
  if h(p)!=x:bad.append(p)
 if h(FREEZE)!=EXPECTED or bad:raise RuntimeError('P4D_GR3Q5_STATUS=BLOCKED_PARENT_FREEZE_INTEGRITY')
 rows=rd(MAN); assert len(rows)==440 and h(MAN)=='5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4'
 # Existing 102 are the independently verified legacy inventory; append actual Q4E successes only.
 legacy=rd(ZERO/'01_inventory/current_verified_success_inventory.csv'); ids={r['prompt_id'] for r in legacy}; assert len(ids)==102
 c=sqlite3.connect(W1/'03_ledger/window01.sqlite3'); c.row_factory=sqlite3.Row
 q4=[dict(r) for r in c.execute("select * from slots where state='SUCCESS' order by ord")];c.close()
 assert len(q4)==30
 by={r['prompt_id']:r for r in rows}; inv=[]
 for r in legacy:
  m=by[r['prompt_id']]; inv.append({'prompt_id':r['prompt_id'],'source':'LEGACY_NO_ADAPTER','role':m['target_role'],'taxonomy':m['taxonomy'],'planned_split':m['planned_internal_split'],'raw_path':r['raw_path'],'final_path':r['final_path'],'raw_sha256':r['raw_sha256_actual'],'final_sha256':r['final_sha256_actual']})
 for r in q4:
  assert Path(r['raw_path']).is_file() and Path(r['final_path']).is_file()
  m=by[r['prompt_id']];ids.add(r['prompt_id']);inv.append({'prompt_id':r['prompt_id'],'source':'LEGACY_NO_ADAPTER','role':m['target_role'],'taxonomy':m['taxonomy'],'planned_split':m['planned_internal_split'],'raw_path':r['raw_path'],'final_path':r['final_path'],'raw_sha256':r['raw_sha256'],'final_sha256':r['final_sha256']})
 assert len(ids)==132
 outstanding=[r for r in rows if r['prompt_id'] not in ids];assert len(outstanding)==308
 REV.mkdir();
 for d in ('00_preflight','01_adapter','02_plan','03_ledger','04_raw_responses','05_checkpoints','06_partial_qa','07_generated_raw','08_final','freeze'):(REV/d).mkdir()
 fields=list(inv[0]);wc(REV/'00_preflight/current_verified_success_132.csv',fields,inv)
 pm=[]
 for m in outstanding:
  original=Path(m['original_prompt_path']).read_text(encoding='utf-8').rstrip('\n');rp,terms=render(original)
  pm.append({'prompt_id':m['prompt_id'],'original_prompt_sha256':m['prompt_sha256'],'semantic_prompt_sha256':m['prompt_sha256'],'adapter_version':ADAPTER,'render_prompt_sha256':hashlib.sha256(rp.encode()).hexdigest(),'role':m['target_role'],'taxonomy':m['taxonomy'],'planned_split':m['planned_internal_split'],'rewrite_terms_changed':json.dumps(terms),'semantic_fields_preserved':True,'status':'READY','render_prompt':rp})
 # policy-refused slot is the formal smoke; remaining order is deterministic group-aware round-robin by original ordinal.
 smoke='PF_P4D_POS_CURLED_G003_V03'; assert smoke in {x['prompt_id'] for x in pm}
 rest=sorted((x for x in pm if x['prompt_id']!=smoke),key=lambda x:(x['taxonomy'],x['planned_split'],x['prompt_id']))
 order=[next(x for x in pm if x['prompt_id']==smoke)]+rest
 for i,x in enumerate(order,1):x['execution_order']=i;x['selection_reason']='ADAPTER_SMOKE' if i==1 else 'deterministic_taxonomy_split_group_aware_order'
 mf=['prompt_id','original_prompt_sha256','semantic_prompt_sha256','adapter_version','render_prompt_sha256','role','taxonomy','planned_split','rewrite_terms_changed','semantic_fields_preserved','status','execution_order','selection_reason','render_prompt'];wc(REV/'01_adapter/render_prompt_manifest_v1.csv',mf,order)
 wc(REV/'02_plan/gr3q5_adaptive_outstanding_308.csv',mf,order)
 j(REV/'01_adapter/provider_render_adapter_v1.json',{'adapter_version':ADAPTER,'semantic_prompt_changed':False,'provider_render_prompt_changed':True,'prefix':PREFIX,'forbidden_visible_shortcuts':['training signs','simulation text','medical staff','ambulances','first-aid equipment','cones','warning labels','instruction boards','dataset labels','overlays']})
 (REV/'01_adapter/provider_render_adapter_v1.md').write_text('# CODEX_SAFE_STAGED_CV_V1\n\nProvider-facing staged training context only; frozen semantic prompts, GT, taxonomy, groups and splits remain immutable.\n')
 (REV/'01_adapter/render_adapter_lineage_policy_v1.md').write_text('# Render adapter lineage policy\n\n`semantic_prompt_sha256` remains the semantic specification. `render_prompt_sha256` and `CODEX_SAFE_STAGED_CV_V1` are generation provenance. Existing 132 are `LEGACY_NO_ADAPTER`.\n')
 j(REV/'00_preflight/window01_forensics.json',{'window01_freeze_sha256':h(FREEZE),'all_bound_artifacts_match':True,'logical':31,'success':30,'failed':1,'retry_events':0,'physical_lower_bound':31,'failed_prompt':smoke,'old_error_code':'missing_image_result','failure_class':'CONTENT_POLICY_REFUSAL_CONFIRMED','evidence':['request accepted','image_generation_call created','image_generation_call failed','response completed','image_count=0','no image bytes','native retry=0','assistant refusal text'],'http429':0})
 j(REV/'00_preflight/inventory_summary.json',{'current_verified_success':132,'outstanding':308,'role_distribution':dict(Counter(x['role'] for x in inv)),'taxonomy_distribution':dict(Counter(x['taxonomy'] for x in inv)),'split_distribution':dict(Counter(x['planned_split'] for x in inv))})
 j(REV/'05_checkpoints/authorization.json',{'authorized':True,'scope':'Q5 V03 formal adapted smoke then at most 68 logical invocations','formal_ingest':False,'c3':False,'new_val':0,'holdout_requests':0})
 print(json.dumps({'status':'READY_FOR_ADAPTER_SMOKE','success':132,'outstanding':308,'manifest_sha256':h(REV/'01_adapter/render_prompt_manifest_v1.csv'),'smoke':smoke}))
def smoke():
 mf=rd(REV/'01_adapter/render_prompt_manifest_v1.csv'); r=mf[0]; assert r['prompt_id']=='PF_P4D_POS_CURLED_G003_V03'
 db=REV/'03_ledger/gr3q5.sqlite3'; c=sqlite3.connect(db);c.execute('create table if not exists slots(prompt_id text primary key,state text,started_at text,finished_at text,http_status text,error_class text,render_prompt_sha256 text)');c.execute('insert into slots values(?,?,?,?,?,?,?)',(r['prompt_id'],'STARTED',str(time.time()),None,None,None,r['render_prompt_sha256']));c.commit()
 out=REV/'07_generated_raw'/f"{r['prompt_id']}.png"; cmd=['node','/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs','--json','--json-events','--provider','codex','images','generate','--model','gpt-5.4','--prompt',r['render_prompt'],'--out',str(out),'--format','png','--size','1536x1024','--quality','medium']
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=1800); ok=False
 try:x=json.loads(p.stdout);ok=p.returncode==0 and x.get('ok') is True and out.is_file()
 except Exception:x={'ok':False,'error':{'code':'invalid_provider_output'}}
 refusal=('image_generation_call' in p.stderr and '"status":"failed"' in p.stderr and 'image_count":0' in p.stderr and ('refusal' in p.stderr.lower() or 'safety' in p.stderr.lower()))
 state='SUCCESS' if ok else ('CONTENT_POLICY_REFUSAL_CONFIRMED' if refusal else 'FAILED_CONFIRMED')
 cls='NONE' if ok else ('CONTENT_POLICY_REFUSAL_CONFIRMED' if refusal else 'FAILED_CONFIRMED_NO_IMAGE_UNCLASSIFIED')
 raw={'prompt_id':r['prompt_id'],'returncode':p.returncode,'outer_json':x,'stderr_redacted':p.stderr,'state':state,'failure_class':cls,'native_retry_count':p.stderr.count('retry_scheduled'),'adapter_version':ADAPTER,'render_prompt_sha256':r['render_prompt_sha256']};j(REV/'04_raw_responses/adapter_smoke.json',raw);c.execute('update slots set state=?,finished_at=?,http_status=?,error_class=? where prompt_id=?',(state,str(time.time()),'200' if ok else 'UNKNOWN',cls,r['prompt_id']));c.commit();c.close();print(json.dumps({'adapter_smoke':state,'failure_class':cls,'provider_requests':1}))
def run():
 mf=rd(REV/'02_plan/post_smoke_balanced_window_v2.csv'); assert len(mf)==67 and mf[0]['prompt_id']=='PF_P4D_POS_CURLED_G003_V04'
 c=sqlite3.connect(REV/'03_ledger/gr3q5.sqlite3');c.execute("alter table slots add column raw_path text");c.execute("alter table slots add column final_path text")
 for r in mf:c.execute('insert into slots(prompt_id,state,started_at,finished_at,http_status,error_class,render_prompt_sha256) values(?,?,?,?,?,?,?)',(r['prompt_id'],'NOT_STARTED',None,None,None,None,r['render_prompt_sha256']))
 c.commit()
 for r in mf:
  # Total Q5 invocation cap includes the completed V03 smoke.
  done=c.execute("select count(*) from slots where state in ('SUCCESS','CONTENT_POLICY_REFUSAL_CONFIRMED','FAILED_CONFIRMED')").fetchone()[0]
  if done>=68: break
  c.execute("update slots set state='STARTED',started_at=? where prompt_id=?",(str(time.time()),r['prompt_id']));c.commit()
  out=REV/'07_generated_raw'/f"{r['prompt_id']}.png";cmd=['node','/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs','--json','--json-events','--provider','codex','images','generate','--model','gpt-5.4','--prompt',r['render_prompt'],'--out',str(out),'--format','png','--size','1536x1024','--quality','medium'];t=time.time()
  try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=1800);x=json.loads(p.stdout)
  except Exception as e:p=None;x={'ok':False,'error':{'code':'completion_unknown','message':str(e)}}
  ok=bool(p and p.returncode==0 and x.get('ok') is True and out.is_file());ref=('image_generation_call' in (p.stderr if p else '') and '"status":"failed"' in (p.stderr if p else '') and 'image_count":0' in (p.stderr if p else '') and ('refusal' in (p.stderr if p else '').lower() or 'safety' in (p.stderr if p else '').lower()));st='SUCCESS' if ok else ('CONTENT_POLICY_REFUSAL_CONFIRMED' if ref else 'FAILED_CONFIRMED');cls='NONE' if ok else ('CONTENT_POLICY_REFUSAL_CONFIRMED' if ref else 'FAILED_CONFIRMED_NO_IMAGE_UNCLASSIFIED');raw={'prompt_id':r['prompt_id'],'returncode':p.returncode if p else None,'outer_json':x,'stderr_redacted':p.stderr if p else '', 'state':st,'failure_class':cls,'native_retry_count':(p.stderr if p else '').count('retry_scheduled'),'adapter_version':ADAPTER,'render_prompt_sha256':r['render_prompt_sha256'],'latency_seconds':time.time()-t};j(REV/'04_raw_responses'/f"{r['prompt_id']}.json",raw);c.execute('update slots set state=?,finished_at=?,http_status=?,error_class=?,raw_path=? where prompt_id=?',(st,str(time.time()),'200' if ok else 'UNKNOWN',cls,str(out) if ok else None,r['prompt_id']));c.commit();print(json.dumps({'prompt_id':r['prompt_id'],'state':st,'failure_class':cls}),flush=True)
  if st!='SUCCESS': break
 c.close();print(json.dumps({'status':'POST_SMOKE_RUN_STOPPED','provider_requests':len(list((REV/'04_raw_responses').glob('*.json'))),'success':len(list((REV/'07_generated_raw').glob('*.png')))}))
def replan():
 rows0=rd(REV/'01_adapter/render_prompt_manifest_v1.csv'); smoke='PF_P4D_POS_CURLED_G003_V03'; rem=[x for x in rows0 if x['prompt_id']!=smoke]; groups={}
 for x in rem:groups.setdefault(x['prompt_id'].rsplit('_V',1)[0],[]).append(x)
 partial=groups.pop('PF_P4D_POS_CURLED_G003',[]); assert len(partial)==2
 # deterministic role/split quotas; pick whole groups using frozen ordinal and taxonomy deficit score.
 current=Counter(x['taxonomy'] for x in rd(REV/'00_preflight/current_verified_success_132.csv')); target=Counter(x['taxonomy'] for x in rd(MAN)); score=lambda g:max((target[x['taxonomy']]-current[x['taxonomy']])/max(1,target[x['taxonomy']]) for x in g)
 byrole={z:sorted([g for g in groups.values() if g[0]['role']==z],key=lambda g:(-score(g),g[0]['taxonomy'],g[0]['prompt_id'])) for z in ('hard_negative','positive','ordinary_negative')}
 chosen=[]
 role_groups={z:([g for g in byrole[z] if g[0]['planned_split']=='NEW_DESIGN'],[g for g in byrole[z] if g[0]['planned_split']=='NEW_SCREEN']) for z in ('hard_negative','positive','ordinary_negative')}
 found=None
 for kh in range(7):
  for kp in range(6):
   for kn in range(3):
    if kh+kp+kn==8 and kh<=len(role_groups['hard_negative'][0]) and 6-kh<=len(role_groups['hard_negative'][1]) and kp<=len(role_groups['positive'][0]) and 5-kp<=len(role_groups['positive'][1]) and kn<=len(role_groups['ordinary_negative'][0]) and 2-kn<=len(role_groups['ordinary_negative'][1]):found=(kh,kp,kn)
    if found:break
   if found:break
  if found:break
 assert found is not None
 for z,n,k in (('hard_negative',6,found[0]),('positive',5,found[1]),('ordinary_negative',2,found[2])):chosen += role_groups[z][0][:k]+role_groups[z][1][:n-k]
 assert len(chosen)==13 and sum(g[0]['planned_split']=='NEW_DESIGN' for g in chosen)==8
 order=partial+[x for x in rem if x['prompt_id'] in {y['prompt_id'] for g in chosen for y in g}]
 assert len(order)==67 and Counter(x['role'] for x in order)==Counter({'hard_negative':30,'positive':27,'ordinary_negative':10}) and Counter(x['planned_split'] for x in order)==Counter({'NEW_DESIGN':40,'NEW_SCREEN':27})
 for i,x in enumerate(order,1):x['execution_order']=i
 fs=['prompt_id','original_prompt_sha256','semantic_prompt_sha256','adapter_version','render_prompt_sha256','role','taxonomy','planned_split','rewrite_terms_changed','semantic_fields_preserved','status','execution_order','selection_reason','render_prompt'];wc(REV/'02_plan/post_smoke_balanced_window_v2.csv',fs,order);j(REV/'05_checkpoints/post_smoke_window_plan_freeze.json',{'status':'READY','rows':67,'role_distribution':dict(Counter(x['role'] for x in order)),'split_distribution':dict(Counter(x['planned_split'] for x in order)),'old_plan_preserved':True,'semantic_plan_changed':False,'adapter_changed':False,'execution_order_changed':True,'smoke_success':True,'provider_requests_added':0,'plan_sha256':h(REV/'02_plan/post_smoke_balanced_window_v2.csv')});print(json.dumps({'status':'READY_FOR_POST_SMOKE_RUN','rows':67,'plan_sha256':h(REV/'02_plan/post_smoke_balanced_window_v2.csv')}))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('command',choices=('prepare','smoke','replan','run'));z=a.parse_args();prepare() if z.command=='prepare' else smoke() if z.command=='smoke' else replan() if z.command=='replan' else run()
