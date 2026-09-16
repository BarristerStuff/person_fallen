from __future__ import annotations
import base64,csv,hashlib,io,json,shutil
from collections import defaultdict
from pathlib import Path
from PIL import Image, ImageStat

D=Path(__file__).resolve().parents[1]
PARENT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/28_person_fallen_v7_b0r1_strict_match_fallback_clean')
PARENT_FREEZE='b4591557c0ce7b1580fe1f5500ee636318a18d72fec88c2def9df2a4c8ebca44'
MODEL='qwen3.5:4b'; DIGEST='2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd'

def hb(b): return hashlib.sha256(b).hexdigest()
def hf(p): return hb(Path(p).read_bytes())
def dump(p,o): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
def rows(p): return list(csv.DictReader(Path(p).open()))

def semantic_equivalence():
    rels=['geometry/thresholds.json','geometry/person_geometry.csv','geometry/persons_full_dev.csv','geometry/yolo11n-pose.pt',
          'policy/person_association.py','policy/v7_b0_policy.py','policy/v7_policy_base.py','prompt/v7_b0_p1.txt','prompt/v7_b0_p2.txt',
          'schema/v7_person_attributes.json','schema/v7_scene_attributes.json','manifests/pilot156.csv','manifests/regression1.csv',
          'manifests/full_remaining.csv','manifests/full_combined436.csv']
    checks=[]
    for rel in rels:
        a,b=PARENT/rel,D/rel
        checks.append({'path':rel,'parent_sha256':hf(a),'successor_sha256':hf(b),'equal':hf(a)==hf(b)})
    out={'candidate':'V7-B0R1C-CROP-COMPLETE-RECOVERY','parent_candidate':'V7-B0R1-STRICT-MATCH-FALLBACK',
         'parent_freeze_sha':PARENT_FREEZE,'checks':checks,'SEMANTIC_EQUIVALENCE_TO_PARENT':'PASS' if all(x['equal'] for x in checks) else 'FAIL'}
    dump(D/'reports/semantic_equivalence.json',out)
    if out['SEMANTIC_EQUIVALENCE_TO_PARENT']!='PASS': raise SystemExit('B0R1C_SEMANTIC_DRIFT_BLOCKED')

def crop_bytes(row,g,source_path=None,source_kind=None):
    # Exact parent preprocessing contract recovered from the parent construction evidence.
    if source_path is not None:
        src_path=Path(source_path); use_original=(source_kind=='original')
    else:
        source=Path(row['image_path']); use_original=source.exists(); src_path=source if use_original else Path(row['full_view_path'])
    with Image.open(src_path) as src:
        src.load(); src=src.convert('RGB'); W,H=src.size
        sx=1 if use_original else W/1920; sy=1 if use_original else H/1080
        x1=float(g['x1'])*sx; y1=float(g['y1'])*sy; x2=float(g['x2'])*sx; y2=float(g['y2'])*sy
        w=x2-x1; h=y2-y1
        box=(max(0,int(x1-.4*w)),max(0,int(y1-.4*h)),min(W,int(x2+.4*w)),min(H,int(y2+.4*h)))
        if box[2]<=box[0] or box[3]<=box[1]: raise ValueError(f'empty crop {row["item_id"]}/{g["person_idx"]}: {box}')
        crop=src.crop(box); scale=min(448/crop.width,448/crop.height); nw=max(1,round(crop.width*scale)); nh=max(1,round(crop.height*scale))
        resample=getattr(Image,'ANTIALIAS',Image.BICUBIC); crop=crop.resize((nw,nh),resample)
        out=Image.new('RGB',(448,448),(114,114,114)); out.paste(crop,((448-nw)//2,(448-nh)//2))
        data=io.BytesIO(); out.save(data,'JPEG',quality=70)
        return data.getvalue(),list(box),[W,H],[W,H]

def build_inventory_and_crops():
    geo=defaultdict(list)
    for g in rows(D/'geometry/person_geometry.csv'): geo[g['item_id']].append(g)
    phases={'pilot':rows(D/'manifests/pilot156.csv'),'regression':rows(D/'manifests/regression1.csv'),'full_remaining':rows(D/'manifests/full_remaining.csv')}
    manifest_by_item={r['item_id']:r for rs in phases.values() for r in rs}
    required={}; phase_keys={}
    for phase,rs in phases.items():
        ks=set()
        for r in rs:
            for g in geo.get(r['item_id'],[]):
                if g['geom_state_a2']!='GEOM_UPRIGHT':
                    key=(r['item_id'],str(g['person_idx'])); ks.add(key)
                    z=required.setdefault(key,{'phase':set(),'item_id':r['item_id'],'operational_id':r.get('operational_id'),'taxonomy':r['taxonomy'],
                      'person_idx':str(g['person_idx']),'level':g['level'],'geom_state_a2':g['geom_state_a2'],'image_path':r['image_path'],
                      'image_sha256':r['image_sha256'],'full_view_path':r['full_view_path'],'full_view_sha256':r['full_view_sha256']})
                    z['phase'].add(phase)
        phase_keys[phase]=ks
    old=json.loads((PARENT/'reports/crop_qa.json').read_text())['qa']; oldmap={(x['item_id'],str(x['person_idx'])):x for x in old}
    oldkeys=set(oldmap); reqkeys=set(required)
    missing=reqkeys-oldkeys; extra=oldkeys-reqkeys
    inv={'pilot_required_targets':len(phase_keys['pilot']),'regression_required_targets':len(phase_keys['regression']),
      'full_remaining_required_targets':len(phase_keys['full_remaining']),'union_required_targets':len(reqkeys),
      'primary_required':sum(required[k]['level']=='primary' for k in reqkeys),'background_required':sum(required[k]['level']=='background' for k in reqkeys),
      'old_crop_plan_targets':len(oldkeys),'old_plan_missing_targets':len(missing),'old_plan_extra_targets':len(extra),
      'missing_targets':[{**required[k],'phase':sorted(required[k]['phase'])} for k in sorted(missing)],
      'extra_targets':[{'item_id':k[0],'person_idx':k[1]} for k in sorted(extra)]}
    dump(D/'reports/required_p1_target_inventory.json',inv)
    # Reproduce parent crop bytes before writing any successor crop.
    repro=[]
    for key,q in sorted(oldmap.items()):
        row=manifest_by_item[key[0]]; g=next(x for x in geo[key[0]] if str(x['person_idx'])==key[1])
        b,box,view_size,source_size=crop_bytes(row,g,q['source_path'],q.get('source_kind')); actual=hb(b)
        repro.append({'item_id':key[0],'person_idx':key[1],'expected_sha256':q['crop_sha256'],'regenerated_sha256':actual,'match':actual==q['crop_sha256'],'bbox_scaled':box})
    rep={'checked':len(repro),'exact_sha_match':sum(x['match'] for x in repro),'gate':'PASS' if all(x['match'] for x in repro) else 'FAIL','rows':repro}
    dump(D/'reports/old_crop_reproducibility.json',rep)
    if rep['gate']!='PASS': raise SystemExit('B0R1C_CROP_GENERATION_NONDETERMINISTIC')
    # Generate exact required set.
    qa=[]; cropdir=D/'prepared/crops'; cropdir.mkdir(parents=True,exist_ok=True)
    for key in sorted(reqkeys):
        z=required[key]; row=manifest_by_item[key[0]]; g=next(x for x in geo[key[0]] if str(x['person_idx'])==key[1])
        if hf(row['image_path'])!=row['image_sha256'] or hf(row['full_view_path'])!=row['full_view_sha256']: raise SystemExit('SOURCE_OR_FULLVIEW_BINDING_FAIL')
        qold=oldmap.get(key); b,box,view_size,source_size=crop_bytes(row,g,qold['source_path'],qold.get('source_kind')) if qold else crop_bytes(row,g); name=f'{hb(key[0].encode())[:16]}_{key[1]}.jpg'; out=cropdir/name
        tmp=out.with_suffix('.tmp'); tmp.write_bytes(b); tmp.replace(out)
        with Image.open(out) as im:
            im.load(); stat=ImageStat.Stat(im); valid=im.size==(448,448) and im.format=='JPEG' and max(stat.var)>0
        qa.append({'item_id':key[0],'operational_id':z['operational_id'],'taxonomy':z['taxonomy'],'phase':sorted(z['phase']),
          'person_idx':key[1],'level':z['level'],'geom_state':z['geom_state_a2'],'source_path':row['full_view_path'],
          'source_image_path':row['image_path'],'source_image_sha256':row['image_sha256'],'source_sha256':row['full_view_sha256'],
          'bbox':box,'source_size':source_size,'full_view_size':view_size,'crop_path':str(out),'crop_sha256':hf(out),'width':448,'height':448,
          'jpeg_quality':70,'valid':bool(valid)})
    qkeys={(x['item_id'],x['person_idx']) for x in qa}; dup=len(qa)-len(qkeys)
    phase_cov={p:{'required':len(ks),'covered':len(ks&qkeys),'coverage_percent':100*len(ks&qkeys)/len(ks) if ks else 100} for p,ks in phase_keys.items()}
    report={'planned':len(qa),'valid':sum(x['valid'] for x in qa),'invalid':sum(not x['valid'] for x in qa),
      'required_targets':len(reqkeys),'required_without_crop':len(reqkeys-qkeys),'duplicate_crop_bindings':dup,'unexpected_crop_bindings':len(qkeys-reqkeys),
      'phase_coverage':phase_cov,'qa':qa}
    report['gate']='PASS' if report['valid']==len(reqkeys) and report['required_without_crop']==0 and dup==0 and report['unexpected_crop_bindings']==0 else 'FAIL'
    dump(D/'reports/crop_qa_complete.json',report)
    if report['gate']!='PASS': raise SystemExit('B0R1C_CROP_PLAN_COVERAGE_FAIL')

def build_payload(prompt,image_bytes,schema,num_predict):
    body={'model':MODEL,'prompt':prompt,'images':[base64.b64encode(image_bytes).decode()],'think':False,'stream':False,'format':schema,
          'options':{'temperature':0,'num_ctx':8192,'num_predict':num_predict}}
    return json.dumps(body,separators=(',',':'),ensure_ascii=False).encode()

def inherited_prefix():
    mans=rows(D/'manifests/pilot156.csv'); p2=(D/'prompt/v7_b0_p2.txt').read_text(); s2=json.loads((D/'schema/v7_scene_attributes.json').read_text())
    claims={}; completes={}
    for x in [json.loads(l) for l in (PARENT/'eval/pilot/ledger.jsonl').read_text().splitlines() if l.strip()]:
        if x['state']=='CLAIMED': claims[x['request_id']]=x
        if x['state']=='COMPLETED': completes[x['request_id']]=x
    outs=[json.loads(l) for l in (PARENT/'eval/pilot/output.jsonl').read_text().splitlines() if l.strip()]
    audit=[]; inherited=[]
    for idx in range(1,5):
        row=mans[idx-1]; rec=outs[idx-1]; rid=f'V7_B0R1_pilot_{idx:04d}_P2_scene'; rawp=PARENT/'eval/pilot/raw'/f'{rid}.json'; raw=rawp.read_bytes(); env=json.loads(raw); parsed=json.loads(env['response'])
        payload=build_payload(p2,Path(row['full_view_path']).read_bytes(),s2,1024); ps=hb(payload); claim=claims[rid]; complete=completes[rid]
        checks={'manifest_item_id':rec['item_id']==row['item_id'],'taxonomy':rec['taxonomy']==row['taxonomy'],
          'source_image_sha':rec['source_image_sha256']==row['image_sha256']==hf(row['image_path']),
          'full_view_sha':row['full_view_sha256']==hf(row['full_view_path']),'payload_sha':ps==claim['payload_sha256'],
          'raw_sha':hb(raw)==complete['raw_sha256']==rec['p2']['raw_sha256'],'parsed_json':parsed==rec['p2']['vlm'],
          'final_decision':rec['image_decision']=='NO_ALERT_NORMAL_POSE'}
        audit.append({'row_index':idx,'request_id':rid,'item_id':row['item_id'],'recomputed_payload_sha256':ps,'parent_payload_sha256':claim['payload_sha256'],'checks':checks,'equivalent':all(checks.values())})
        inherited.append({'parent_candidate':'V7-B0R1-STRICT-MATCH-FALLBACK','parent_freeze_sha':PARENT_FREEZE,'parent_request_id':rid,
          'row_index':idx,'item_id':row['item_id'],'payload_sha256':ps,'raw_sha256':hb(raw),'source_image_sha256':row['image_sha256'],
          'view_sha256':row['full_view_sha256'],'strict_json_ok':True,'source_binding_ok':True,'image_decision':rec['image_decision'],
          'parent_output_record':rec,'equivalence_verified':all(checks.values())})
    out={'rows':4,'payload_equivalent':sum(x['equivalent'] for x in audit),'raw_verified':sum(x['checks']['raw_sha'] and x['checks']['parsed_json'] for x in audit),
      'resends':0,'gate':'PASS' if all(x['equivalent'] for x in audit) else 'FAIL','audit':audit}
    dump(D/'reports/inherited_prefix_equivalence.json',out)
    if out['gate']!='PASS': raise SystemExit('B0R1C_INHERITED_PREFIX_NOT_EQUIVALENT')
    dump(D/'protocol/INHERITED_PILOT_PREFIX.json',{'candidate':'V7-B0R1C-CROP-COMPLETE-RECOVERY','INHERITED_PARENT_REQUESTS':4,
      'INHERITED_PARENT_ROWS':4,'INHERITANCE_TYPE':'EXACT_PAYLOAD_EQUIVALENCE','rows':inherited})

def main():
    if hf(PARENT/'freeze/CANDIDATE_FREEZE.json')!=PARENT_FREEZE: raise SystemExit('PARENT_FREEZE_MISMATCH')
    semantic_equivalence(); build_inventory_and_crops(); inherited_prefix()
    dump(D/'protocol/WORKSPACE_PROVENANCE.json',{'candidate':'V7-B0R1C-CROP-COMPLETE-RECOVERY','parent_candidate':'V7-B0R1-STRICT-MATCH-FALLBACK',
      'parent_freeze_sha':PARENT_FREEZE,'base_git_commit':'2ae3c17188f1b065988920e8572faab97a05850f','semantic_change':False,'protocol_change':True,
      'crop_plan_change':True,'runner_recovery_change':True,'parent_requests_before_successor_freeze':4})
    print('PASS')
if __name__=='__main__': main()
