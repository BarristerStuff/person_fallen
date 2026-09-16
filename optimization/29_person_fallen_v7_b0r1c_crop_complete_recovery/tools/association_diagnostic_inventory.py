from __future__ import annotations
import csv, hashlib, json, sys
from pathlib import Path
from PIL import Image

D = Path(__file__).resolve().parents[1]
ROOT = Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
GIT_ROOT = Path('/home/yanbo/person_fallen_v7_b0r1_clean_git')
sys.path.insert(0, str(D / 'policy'))
from person_association import match

MULTI_OUT = ROOT / '24_person_fallen_v6_a0_direct_evaluation/eval/pilot/output.jsonl'
SCREEN_OUT = ROOT / '17_person_fallen_v5_target_attributes/eval/regression/output.jsonl'
SCREEN_DET = ROOT / '14_person_fallen_v4_operational_freeze/detector/screen_detections.csv'
MULTI_TAXONOMY = 'multi_person_one_lying'
SCREEN_ITEM = 'P4D_PLAN::PF_P4D_POS_CURLED_G003_V05'
SCREEN_OPERATIONAL = 'PFV4_SCREEN_0066'
DIRECT = {'supine', 'side_lying', 'curled_lying', 'prone'}
NORMAL = {'standing', 'walking', 'kneeling', 'floor_sitting', 'squat', 'bending', 'crawling', 'pushup_plank'}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def read_jsonl(path: Path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def source_dims(path: str):
    with Image.open(path) as im: return im.size

def normalized_det(gs, w, h):
    return [[float(g['x1'])/w*1000, float(g['y1'])/h*1000,
             float(g['x2'])/w*1000, float(g['y2'])/h*1000] for g in gs]

# Mechanical search inventory: file names are recorded only when content has a target token.
searched_roots = [str(ROOT), str(GIT_ROOT)]
searched_files = []
for root in (ROOT, GIT_ROOT):
    for p in root.rglob('*'):
        if not p.is_file() or '.git' in p.parts: continue
        try:
            if p.stat().st_size > 50_000_000: continue
            data = p.read_bytes()
        except OSError:
            continue
        if (b'multi_person_one_lying' in data or b'PFV4_SCREEN_0066' in data or
                b'P4D_PLAN::PF_P4D_POS_CURLED_G003_V05' in data):
            searched_files.append(str(p))
searched_files = sorted(set(searched_files))

geo = {}
with (D/'geometry/person_geometry.csv').open() as f:
    for g in csv.DictReader(f): geo.setdefault(g['item_id'], []).append(g)
manifests = {}
for mp in (D/'manifests/full_combined436.csv', D/'manifests/regression1.csv'):
    with mp.open() as f:
        for r in csv.DictReader(f): manifests[r['item_id']] = r

multi_candidates = []
valid_multi = []
wrong_upright_attachments = 0
multi_pass = True
for r in read_jsonl(MULTI_OUT):
    if r.get('taxonomy') != MULTI_TAXONOMY: continue
    item = r['item_id']; gs = geo.get(item, []); people = (r.get('parsed') or {}).get('people') or []
    m = manifests.get(item); raw = Path(r.get('raw_response_path', ''))
    rec = {'item_id': item, 'request_id': r.get('request_id'), 'source_path': m.get('image_path') if m else None,
           'source_sha256': r.get('source_image_sha256'), 'detector_source': str(D/'geometry/person_geometry.csv'),
           'detector_boxes_count': len(gs), 'p2_source': str(MULTI_OUT), 'p2_people_count': len(people)}
    core = bool(m and gs and people and all(isinstance(p.get('bbox_1000'), list) and len(p['bbox_1000']) == 4 for p in people))
    source_ok = bool(core and Path(m['image_path']).is_file() and sha(Path(m['image_path'])) == m['image_sha256'] == r.get('source_image_sha256'))
    raw_ok = bool(raw.is_file() and sha(raw) == r.get('raw_response_sha256'))
    rec.update({'source_binding_ok': source_ok, 'raw_response_binding_ok': raw_ok,
                'strict_json_ok': r.get('strict_json_ok'), 'model_request_binding_present': bool(r.get('payload_sha256')),
                'binding_status': 'BOUND' if core and source_ok and raw_ok and r.get('strict_json_ok') else 'INCOMPLETE'})
    multi_candidates.append(rec)
    if rec['binding_status'] != 'BOUND': continue
    w,h = source_dims(m['image_path']); det = normalized_det(gs,w,h); boxes = [p['bbox_1000'] for p in people]
    associations = match(det, boxes); by_p = {a['p2_index']: a for a in associations}
    normal_matched = [] ; missed_lying_unmatched = [] ; wrong = []
    for j,p in enumerate(people):
        pose = p.get('pose'); a = by_p.get(j)
        if pose in NORMAL and a is not None:
            normal_matched.append({'p2_index': j, 'pose': pose, 'detector_index': a['detector_index'], 'geom_state': gs[a['detector_index']]['geom_state_a2'], 'metrics': a['metrics']})
        if pose in DIRECT and a is None:
            missed_lying_unmatched.append({'p2_index': j, 'pose': pose, 'bbox_1000': p['bbox_1000']})
        if pose in DIRECT and a is not None and gs[a['detector_index']]['geom_state_a2'] == 'GEOM_UPRIGHT':
            wrong.append({'p2_index':j,'detector_index':a['detector_index'],'pose':pose})
    wrong_upright_attachments += len(wrong)
    sample_pass = bool(normal_matched and missed_lying_unmatched and not wrong)
    if sample_pass:
        valid_multi.append({**rec, 'association_diagnostic_valid': True, 'normal_matches': normal_matched,
                            'detector_missed_lying_unmatched': missed_lying_unmatched,
                            'wrong_attachment_to_GEOM_UPRIGHT': wrong, 'all_associations': associations})

multi_pass = bool(valid_multi) and wrong_upright_attachments == 0

# PFV4_SCREEN_0066: measurable only if both historical detector and structured P2 bbox exist.
screen_candidates = []
screen_row = next((x for x in read_jsonl(SCREEN_OUT) if x.get('item_id') == SCREEN_ITEM or x.get('operational_id') == SCREEN_OPERATIONAL), None)
det_row = None
if SCREEN_DET.exists():
    with SCREEN_DET.open() as f: det_row = next((x for x in csv.DictReader(f) if x.get('operational_id') == SCREEN_OPERATIONAL), None)
has_det = bool(det_row and det_row.get('crop_box'))
people = ((screen_row or {}).get('parsed') or {}).get('people') or []
has_p2 = bool(people and all(isinstance(p.get('bbox_1000'), list) and len(p['bbox_1000']) == 4 for p in people))
measurable = bool(screen_row and has_det and has_p2)
screen_result = 'NOT_MEASURABLE_FROM_EXISTING_ARTIFACTS'
if screen_row:
    screen_candidates.append({'item_id': SCREEN_ITEM, 'request_id': screen_row.get('request_id'),
      'source_path': manifests.get(SCREEN_ITEM,{}).get('image_path'), 'source_sha256': screen_row.get('source_image_sha256'),
      'detector_source': str(SCREEN_DET), 'detector_boxes_count': 1 if has_det else 0,
      'p2_source': str(SCREEN_OUT), 'p2_people_count': len(people),
      'binding_status': 'BOUND' if measurable and screen_row.get('strict_json_ok') and screen_row.get('source_binding_ok') else 'INCOMPLETE'})
if measurable:
    vals = [float(x) for x in det_row['crop_box'].strip('"').split(',')]
    W=float(det_row['source_width']); H=float(det_row['source_height'])
    det = [[vals[0]/W*1000,vals[1]/H*1000,vals[2]/W*1000,vals[3]/H*1000]]
    associations = match(det,[p['bbox_1000'] for p in people]); by_p={a['p2_index']:a for a in associations}
    normal = [j for j,p in enumerate(people) if p.get('pose') in NORMAL]
    lying = [j for j,p in enumerate(people) if p.get('pose') in DIRECT]
    screen_pass = bool(normal and all(j in by_p for j in normal) and lying and all(j not in by_p for j in lying))
    screen_result = 'PASS' if screen_pass else 'FAIL'
    screen_candidates[-1].update({'associations': associations, 'normal_person_indices': normal,
                                  'lying_person_indices': lying, 'normal_all_matched': all(j in by_p for j in normal),
                                  'lying_all_unmatched': all(j not in by_p for j in lying)})

report = {
 'searched_roots': searched_roots, 'searched_files': searched_files,
 'multi_person_candidates_found': len(multi_candidates), 'valid_multi_person_diagnostics': valid_multi,
 'multi_person_candidates': multi_candidates, 'MULTI_PERSON_ASSOCIATION_PREFLIGHT': 'PASS' if multi_pass else 'FAIL',
 'wrong_attachment_of_lying_to_GEOM_UPRIGHT': wrong_upright_attachments,
 'PFV4_SCREEN_0066_candidates_found': len(screen_candidates),
 'PFV4_SCREEN_0066_has_detector_boxes': has_det,
 'PFV4_SCREEN_0066_has_P2_structured_bbox': has_p2,
 'PFV4_SCREEN_0066_measurable': measurable,
 'PFV4_SCREEN_0066_OFFLINE_ASSOCIATION': screen_result,
 'PFV4_SCREEN_0066_candidates': screen_candidates,
}
(D/'reports/association_diagnostic_inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
preflight = {'gate': 'PASS' if multi_pass and screen_result in {'PASS','NOT_MEASURABLE_FROM_EXISTING_ARTIFACTS'} else 'FAIL',
             'multi_person': report['MULTI_PERSON_ASSOCIATION_PREFLIGHT'],
             'screen0066': screen_result, 'wrong_attachment_of_lying_to_GEOM_UPRIGHT': wrong_upright_attachments,
             'valid_multi_samples': len(valid_multi)}
(D/'reports/association_preflight.json').write_text(json.dumps(preflight,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(preflight,ensure_ascii=False))
