import copy, csv, importlib.util, json, shutil, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runner',ROOT/'tools/run_v7_b0r1c.py')
r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

# Mechanical reports and exact set coverage.
sem=json.loads((ROOT/'reports/semantic_equivalence.json').read_text())
inv=json.loads((ROOT/'reports/required_p1_target_inventory.json').read_text())
rep=json.loads((ROOT/'reports/old_crop_reproducibility.json').read_text())
qa=json.loads((ROOT/'reports/crop_qa_complete.json').read_text())
eq=json.loads((ROOT/'reports/inherited_prefix_equivalence.json').read_text())
assert sem['SEMANTIC_EQUIVALENCE_TO_PARENT']=='PASS'
assert inv['union_required_targets']==377 and inv['old_crop_plan_targets']==319 and inv['old_plan_missing_targets']==58
assert rep['checked']==319 and rep['exact_sha_match']==319 and rep['gate']=='PASS'
assert qa['planned']==qa['valid']==qa['required_targets']==377 and qa['required_without_crop']==0 and qa['duplicate_crop_bindings']==0 and qa['unexpected_crop_bindings']==0 and qa['gate']=='PASS'
assert eq['payload_equivalent']==eq['raw_verified']==4 and eq['gate']=='PASS'

rows=list(csv.DictReader((ROOT/'manifests/pilot156.csv').open()))
xs=r.verify_inherited_prefix(rows)
assert len(xs)==4 and [x['row_index'] for x in xs]==[1,2,3,4]
assert all(x['parent_request_id'].startswith('V7_B0R1_pilot_000') for x in xs)
assert f'V7_B0R1C_pilot_{5:04d}_P1_background_0'=='V7_B0R1C_pilot_0005_P1_background_0'

# Ledger metadata for inherited rows must not break duplicate-ID accounting.
with tempfile.TemporaryDirectory() as td:
 t=Path(td); (t/'ledger.jsonl').write_text(json.dumps({'state':'INHERITED_PARENT','parent_request_id':xs[0]['parent_request_id']})+'\n')
 assert r.existing_ids(t)==set()

# Cryptographic inheritance tampering is rejected before any network call.
oldD=r.D
with tempfile.TemporaryDirectory() as td:
 t=Path(td); (t/'protocol').mkdir(); (t/'reports').mkdir(); (t/'prompt').mkdir(); (t/'schema').mkdir()
 shutil.copy(ROOT/'protocol/INHERITED_PILOT_PREFIX.json',t/'protocol/INHERITED_PILOT_PREFIX.json')
 shutil.copy(ROOT/'reports/inherited_prefix_equivalence.json',t/'reports/inherited_prefix_equivalence.json')
 r.D=t
 bad=json.loads((t/'protocol/INHERITED_PILOT_PREFIX.json').read_text()); bad['rows'][0]['payload_sha256']='0'*64
 (t/'protocol/INHERITED_PILOT_PREFIX.json').write_text(json.dumps(bad))
 try:
  r.verify_inherited_prefix(rows)
  raise AssertionError('tampered prefix accepted')
 except RuntimeError as e:
  assert str(e)=='INHERITED_PREFIX_PAYLOAD_MISMATCH'
 finally:
  r.D=oldD

# Required early stops cover grouped ground/crawling taxonomies.
assert r.should_stop_pilot([{'taxonomy':'crawling_quadruped_support','image_decision':'ALERT_GROUND_LYING'}],{})=='CRAWLING_IRREVERSIBLE_FP'
print('B0R1C_PROTOCOL_TESTS_PASS')
