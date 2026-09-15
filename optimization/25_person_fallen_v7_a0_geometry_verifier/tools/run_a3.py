import csv,json,base64,hashlib,time,urllib.request,urllib.error,sys,io,os
from pathlib import Path
from PIL import Image
B=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/25_person_fallen_v7_a0_geometry_verifier'); GEO=list(csv.DictReader(open(B/'geometry/a2/person_geometry.csv'))); gb={}
for x in GEO:gb.setdefault(x['item_id'],[]).append(x)
P1=json.loads(open(B/'schema/v7_person_attributes.json').read()); P2={'type':'object','additionalProperties':False,'required':['people'],'properties':{'people':{'type':'array','maxItems':8,'items':{'type':'object','required':['pose','torso_orientation','torso_ground_contact','support_surface','body_support_configuration','explicit_work_evidence','visual_quality','evidence','bbox_1000'],'additionalProperties':False,'properties':{'pose':{'type':'string'},'torso_orientation':{'type':'string'},'torso_ground_contact':{'type':'string'},'support_surface':{'type':'string'},'body_support_configuration':{'type':'string'},'explicit_work_evidence':{'type':'string'},'visual_quality':{'type':'string'},'evidence':{'type':'string'},'bbox_1000':{'type':'array','minItems':4,'maxItems':4,'items':{'type':'number'}}}}}}}; prompt1=open(B/'prompt/v7_person_verifier.txt').read(); END='http://192.168.20.62:11434'; MODEL='qwen3.5:4b'
LY={'supine','side_lying','prone','curled_lying','other_near_ground'}; AUX={'forearms_feet_supported','hands_feet_supported','hands_knees_supported'}
def five(x):return x.get('pose') in LY and x.get('support_surface')=='floor' and x.get('torso_orientation')=='horizontal' and x.get('torso_ground_contact')=='broad' and x.get('body_support_configuration')=='torso_ground_supported'
def decision(x,geom):
 import re
 if geom=='GEOM_UPRIGHT':return 'NO_ALERT_NORMAL_POSE'
 if x.get('visual_quality')=='insufficient':return 'RECHECK_VISUAL_UNCERTAIN'
 if re.search(r'forearm|hands and feet|hands and knees|on (his|her|their) knees|plank|push-up|crawl',x.get('evidence',''),re.I) and x.get('body_support_configuration')=='torso_ground_supported':return 'RECHECK_VISUAL_UNCERTAIN'
 if five(x):return 'ALERT_GROUND_LYING'
 if x.get('pose') in LY:return 'RECHECK_VISUAL_UNCERTAIN'
 if x.get('body_support_configuration') in AUX or x.get('pose') in {'crawling','plank','push_up'}:return 'ATTENTION_NEAR_GROUND'
 return 'NO_ALERT_NORMAL_POSE'
def call(prompt,im,schema):
 data=json.dumps({'model':MODEL,'prompt':prompt,'images':[base64.b64encode(im).decode()],'think':False,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':512}}).encode();t=time.monotonic();req=urllib.request.Request(END+'/api/generate',data=data,headers={'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPRedirectHandler()).open(req,timeout=120) as r: raw=r.read(); status=r.status
 lat=time.monotonic()-t; env=json.loads(raw); txt=env.get('response',''); obj=json.loads(txt);return obj,raw,lat,hashlib.sha256(data).hexdigest()
def crop(row,g):
 im=Image.open(row['full_view_path']).convert('RGB'); W,H=im.size;x1,y1,x2,y2=map(float,[g['x1'],g['y1'],g['x2'],g['y2']]);w=x2-x1;h=y2-y1;x1=max(0,x1-.4*w);y1=max(0,y1-.4*h);x2=min(W,x2+.4*w);y2=min(H,y2+.4*h);im=im.crop((int(x1),int(y1),int(x2),int(y2)));im.thumbnail((448,448));out=Image.new('RGB',(448,448),'gray');out.paste(im,((448-im.width)//2,(448-im.height)//2));b=io.BytesIO();out.save(b,'JPEG',quality=70);return b.getvalue()
def run(phase,manifest_path):
 outroot=B/('eval/a3_'+phase);outroot.mkdir(parents=True,exist_ok=True); f=open(outroot/'output.jsonl','w'); reqcount={'P1_primary':0,'P1_background':0,'P2_scene':0}; results=[]
 rows=list(csv.DictReader(open(manifest_path))); schema1=P1
 for row in rows:
  gs=[g for g in gb.get(row['item_id'],[])]; primary=[g for g in gs if g['level']=='primary' and g['geom_state_a2']!='GEOM_UPRIGHT']; bg=[g for g in gs if g['level']=='background' and g['geom_state_a2']!='GEOM_UPRIGHT']; decisions=[]
  for route,arr in [('P1_primary',primary),('P1_background',bg)]:
   for g in arr:
    rid=f'A3_{phase}_{row.get("request_id")}_{route}_{g["person_idx"]}'; im=crop(row,g);obj,raw,lat,ps=call(prompt1,im,schema1);reqcount[route]+=1;d=decision(obj,g['geom_state_a2']);decisions.append(d)
    with open(outroot/'requests.jsonl','a') as q:q.write(json.dumps({'request_id':rid,'item_id':row['item_id'],'route':route,'geom_state':g['geom_state_a2'],'parsed':obj,'decision':d,'latency':lat,'payload_sha256':ps,'raw_sha256':hashlib.sha256(raw).hexdigest()})+'\n')
  if not any(x=='ALERT_GROUND_LYING' for x in decisions):
   reqcount['P2_scene']+=1
   im=open(row['full_view_path'],'rb').read(); scene_prompt=prompt1+'\nReturn all people in this full scene with bbox_1000.'; obj2,raw2,lat2,ps2=call(scene_prompt,im,P2)
   p2ds=[]
   for personx in obj2.get('people',[]):
    if five(personx): p2ds.append('ALERT_GROUND_LYING')
    elif personx.get('pose') in LY:p2ds.append('RECHECK_VISUAL_UNCERTAIN')
   img2='ALERT_GROUND_LYING' if 'ALERT_GROUND_LYING' in p2ds else ('RECHECK_VISUAL_UNCERTAIN' if 'RECHECK_VISUAL_UNCERTAIN' in p2ds else ('ATTENTION_NEAR_GROUND' if any(x=='ATTENTION_NEAR_GROUND' for x in decisions) else 'NO_ALERT_NORMAL_POSE'))
   results.append({'item_id':row['item_id'],'request_id':row.get('request_id'),'taxonomy':row['taxonomy'],'image_decision':img2,'p1_decisions':decisions,'p2':obj2,'p2_latency':lat2})
  else: results.append({'item_id':row['item_id'],'request_id':row.get('request_id'),'taxonomy':row['taxonomy'],'image_decision':'ALERT_GROUND_LYING','p1_decisions':decisions})
  f.write(json.dumps(results[-1])+'\n');f.flush()
 json.dump({'phase':phase,'rows':len(rows),'route_counts':reqcount,'results':results},open(outroot/'summary.json','w'),indent=2);return reqcount,results
if __name__=='__main__':
 phase=sys.argv[1]; path=B/'manifests/pilot156.csv' if phase=='pilot' else B/'manifests/regression1.csv';print(run(phase,path)[0])
