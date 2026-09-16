import csv,json,base64,hashlib,time,urllib.request,urllib.error,sys,io
from pathlib import Path
from PIL import Image
D=Path(__file__).resolve().parents[1]; END='http://192.168.20.62:11434'; MODEL='qwen3.5:4b'
P1=(D/'prompt/v7_b0_p1.txt').read_text(); P2=(D/'prompt/v7_b0_p2.txt').read_text(); S1=json.loads((D/'schema/v7_person_attributes.json').read_text()); S2=json.loads((D/'schema/v7_scene_attributes.json').read_text())
from importlib.util import spec_from_file_location,module_from_spec
sp=spec_from_file_location('pol',D/'policy/v7_b0_policy.py'); pol=module_from_spec(sp); sp.loader.exec_module(pol)
geo={}
for x in csv.DictReader((D/'geometry/person_geometry.csv').open()): geo.setdefault(x['item_id'],[]).append(x)
def payload(prompt,images,schema):
 return json.dumps({'model':MODEL,'prompt':prompt,'images':[base64.b64encode(x).decode() for x in images],'think':False,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':512}},separators=(',',':')).encode()
def call(data, rid, root):
 ps=hashlib.sha256(data).hexdigest(); c={'request_id':rid,'claimed_at':time.time(),'payload_sha256':ps,'state':'CLAIMED'}
 with (root/'ledger.jsonl').open('a') as f:f.write(json.dumps(c)+'\n');f.flush()
 t=time.monotonic(); req=urllib.request.Request(END+'/api/generate',data=data,headers={'Content-Type':'application/json'})
 try:
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPRedirectHandler())
  with opener.open(req,timeout=120) as r:
   if r.status!=200: raise RuntimeError('HTTP_'+str(r.status))
   raw=r.read()
 except Exception as e:
  with (root/'ledger.jsonl').open('a') as f:f.write(json.dumps({'request_id':rid,'state':'UNKNOWN','error':repr(e)})+'\n');f.flush()
  raise
 (root/'raw').mkdir(exist_ok=True); rp=root/'raw'/(rid+'.json'); rp.write_bytes(raw)
 env=json.loads(raw); text=env.get('response'); obj=json.loads(text); lat=time.monotonic()-t
 with (root/'ledger.jsonl').open('a') as f:f.write(json.dumps({'request_id':rid,'state':'COMPLETED','raw_path':str(rp),'raw_sha256':hashlib.sha256(raw).hexdigest(),'latency':lat})+'\n');f.flush()
 return obj,lat,ps,str(rp)
def crop(row,g):
 with Image.open(row['full_view_path']) as src:
  src.load(); W,H=src.size;x1,y1,x2,y2=map(float,[g['x1'],g['y1'],g['x2'],g['y2']]);w=x2-x1;h=y2-y1
  im=src.convert('RGB').crop((max(0,int(x1-.4*w)),max(0,int(y1-.4*h)),min(W,int(x2+.4*w)),min(H,int(y2+.4*h)))); im.thumbnail((448,448)); out=Image.new('RGB',(448,448),'gray');out.paste(im,((448-im.width)//2,(448-im.height)//2));b=io.BytesIO();out.save(b,'JPEG',quality=70);return b.getvalue()
def run(phase,manifest):
 root=D/'eval'/phase;root.mkdir(parents=True,exist_ok=True); (root/'raw').mkdir(exist_ok=True)
 out=(root/'output.jsonl').open('a'); rows=list(csv.DictReader(open(manifest))); results=[]; route={"P1_primary":0,"P1_background":0,"P2_scene":0}
 for idx,row in enumerate(rows,1):
  gs=geo.get(row['item_id'],[]); targets=[('P1_primary',x) for x in gs if x['level']=='primary' and x['geom_state_a2']!='GEOM_UPRIGHT']+[('P1_background',x) for x in gs if x['level']=='background' and x['geom_state_a2']!='GEOM_UPRIGHT']; ds=[]; provisional=[]
  for rt,g in targets:
   rid=f'V7_B0_{phase}_{idx:04d}_{rt}_{g["person_idx"]}'; obj,lat,ps,rp=call(payload(P1,[crop(row,g)],S1),rid,root); d=pol.person_p1(obj,g['geom_state_a2']); ds.append(d); provisional.append({'route':rt,'person_idx':g['person_idx'],'geom':g['geom_state_a2'],'decision':d,'vlm':obj,'latency':lat,'payload_sha256':ps,'raw_path':rp});route[rt]+=1
  need_p2=(not ds) or ('ALERT_GROUND_LYING' not in ds) or ('PROVISIONAL_PRONE' in ds)
  p2=None
  if need_p2:
   rid=f'V7_B0_{phase}_{idx:04d}_P2_scene'; obj,lat,ps,rp=call(payload(P2,[open(row['full_view_path'],'rb').read()],S2),rid,root); route['P2_scene']+=1; p2={'vlm':obj,'latency':lat,'payload_sha256':ps,'raw_path':rp}
   with Image.open(row['full_view_path']) as _im: W,H=_im.size
   def iou(a,b):
    ax1,ay1,ax2,ay2=a; bx1,by1,bx2,by2=b; ix1=max(ax1,bx1);iy1=max(ay1,by1);ix2=min(ax2,bx2);iy2=min(ay2,by2); iw=max(0,ix2-ix1);ih=max(0,iy2-iy1); inter=iw*ih
    return inter/(max(1,(ax2-ax1)*(ay2-ay1)+(bx2-bx1)*(by2-by1)-inter))
   p2ds=[]; used=set()
   for j,person in enumerate(obj.get('people',[])):
    bb=person.get('bbox_1000'); best=None; bestv=0
    if isinstance(bb,list) and len(bb)==4:
     for k,g in enumerate(gs):
      v=iou([float(g['x1'])/W*1000,float(g['y1'])/H*1000,float(g['x2'])/W*1000,float(g['y2'])/H*1000],list(map(float,bb)))
      if v>=.3 and v>bestv: best,bestv=k,v
    if best is not None: used.add(best); geom=gs[best]['geom_state_a2']; p1state=next((x['decision'] for x in provisional if int(x['person_idx'])==int(gs[best]['person_idx'])),None)
    else: geom='GEOM_NOT_UPRIGHT'; p1state=None
    d=pol.p2_match(person,geom,p1state)
    if best is None and person.get('pose') in pol.DIRECT_LYING and pol._five(person): d='ALERT_GROUND_LYING'
    elif best is None and person.get('pose')=='prone': d='RECHECK_VISUAL_UNCERTAIN'
    p2ds.append(d)
   ds += p2ds
  image=pol.aggregate(ds,detected=bool(gs))
  rec={'item_id':row['item_id'],'request_id':row.get('request_id'),'taxonomy':row['taxonomy'],'image_decision':image,'p1':provisional,'p2':p2};out.write(json.dumps(rec,ensure_ascii=False)+'\n');out.flush();results.append(rec)
 json.dump({'phase':phase,'rows':len(rows),'route_counts':route,'results':results},(root/'summary.json').open('w'),indent=2,ensure_ascii=False); return route
if __name__=='__main__':
 phase=sys.argv[1]; manifest=D/'manifests'/(('pilot156.csv' if phase=='pilot' else 'regression1.csv' if phase=='regression' else 'full_remaining.csv')); print(run(phase,manifest))
