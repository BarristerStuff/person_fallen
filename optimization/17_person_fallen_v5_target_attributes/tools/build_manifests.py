#!/usr/bin/env python3
"""Build the 115 DEV + one separate SCREEN regression manifests, entirely offline.

No historical code is imported or executed. Only the four explicit input CSVs,
two frozen preparation plans, two producer source files, and selected resources
are read. JPEG70 is preparation provenance, not an estimate from decoded pixels.
Existing outputs (including dangling symlinks) cause refusal before input reads.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
V13 = WORKSPACE / '13_person_fallen_v4_pose_attributes'
V14 = WORKSPACE / '14_person_fallen_v4_operational_freeze'
SOURCES = {
    'diagnostic': V13 / 'manifests/v4_diagnostic_110.csv',
    'full': V13 / 'manifests/v4_full_dev_436.csv',
    'crop': V13 / 'manifests/v4_full_dev_crop_manifest.csv',
    'screen': V14 / 'manifests/person_fallen_v4_operational_screen_crop.csv',
}
PREPARATION = {
    'pilot': (V13 / 'protocol/v4_full_dev_execution_plan.json',
              V13 / 'tools/run_person_crop_full_dev.py'),
    'regression': (V14 / 'protocol/final_operational_plan.json',
                   V14 / 'tools/run_operational_detector.py'),
}
REGRESSION_ID = 'PFV4_SCREEN_0066'
REGRESSION_ITEM = 'P4D_PLAN::PF_P4D_POS_CURLED_G003_V05'
MULTI = 'multi_person_one_lying'
GROUND = 'ALERT_GROUND_LYING'
NORMAL = 'NO_ALERT_NORMAL_POSE'
OUTPUTS = (
    ROOT / 'manifests/pilot115.json', ROOT / 'manifests/pilot115.csv',
    ROOT / 'manifests/regression1.json', ROOT / 'manifests/regression1.csv',
    ROOT / 'reports/source_audit.json',
)
RESOURCE_FIELDS = (
    ('image_path', 'image_sha256'), ('prompt_path', 'prompt_sha256'),
    ('full_view_path', 'full_view_sha256'), ('crop_view_path', 'crop_view_sha256'),
)
REQUIRED = (
    'item_id', 'group_id', 'taxonomy', 'source_split', 'v3_split', 'ground_truth',
    'gt_type', 'gt_source', 'image_path', 'image_sha256', 'prompt_path',
    'prompt_sha256',
)


class ManifestError(ValueError):
    """Fail closed: report the conflict to the main agent; never repair labels."""


def require(condition, message):
    if not condition:
        raise ManifestError(message)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def check_path(path):
    path = Path(path)
    require(path.is_absolute(), f'non-absolute source path: {path}')
    for candidate in (path, path.resolve()):
        require(not re.search(r'(^|[/_.-])(val|holdout)(?=$|[/_.-])',
                              str(candidate), re.I),
                f'forbidden VAL/Holdout path: {candidate}')
    return path


def read_bound(path, bindings):
    path = check_path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ManifestError(f'missing/unreadable dependency: {path}: {exc}') from exc
    digest = sha256_bytes(data)
    key = str(path)
    require(key not in bindings or bindings[key] == digest,
            f'dependency changed during verification: {path}')
    bindings[key] = digest
    return data


def parse_csv(data, name):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)),
            f'{name}: empty or duplicate CSV columns')
    rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows),
            f'{name}: malformed CSV row')
    return rows


def load_sources(bindings):
    return {name: parse_csv(read_bound(path, bindings), name)
            for name, path in SOURCES.items()}


def index_unique(rows, key, name):
    result = {}
    for row in rows:
        value = row.get(key)
        require(value, f'{name}: missing {key}')
        require(value not in result, f'{name}: duplicate {key}={value}')
        result[value] = row
    return result


def add_fields(row, additions):
    require(not (set(row) & set(additions)),
            f'{row.get("item_id")}: unexpected preexisting added fields')
    return {**row, **additions}


def validate_source(row, phase):
    for field in REQUIRED:
        require(row.get(field), f'{row.get("item_id")}: missing {field}')
    for field in ('source_split', 'v3_split'):
        require(not re.search(r'VAL|HOLDOUT', row[field], re.I),
                f'{row["item_id"]}: forbidden split {row[field]}')
    require(row['v3_split'] == ('V3_DEV' if phase == 'pilot' else 'V3_SCREEN'),
            f'{row["item_id"]}: wrong phase/split')
    outcome = row.get('expected_v4_outcome')
    require(outcome in (GROUND, NORMAL), f'{row["item_id"]}: missing/unknown GT outcome')
    require(row['ground_truth'] == ('positive' if outcome == GROUND else 'negative'),
            f'{row["item_id"]}: ground_truth/outcome conflict')
    require(row.get('view_count') == '2', f'{row["item_id"]}: expected two frozen views')
    for path_key, hash_key in RESOURCE_FIELDS:
        require(row.get(path_key), f'{row["item_id"]}: missing {path_key}')
        check_path(row[path_key])
        require(re.fullmatch(r'[0-9a-f]{64}', row.get(hash_key, '')),
                f'{row["item_id"]}: missing/invalid {hash_key}')
    require(row['full_view_path'] != row['crop_view_path'],
            f'{row["item_id"]}: full/crop path alias')


def assemble(sources):
    diagnostic, full, crop, screen = (sources[k] for k in ('diagnostic', 'full', 'crop', 'screen'))
    for name, rows, count in (('diagnostic', diagnostic, 110), ('full', full, 436),
                              ('crop', crop, 436), ('screen', screen, 76)):
        require(len(rows) == count, f'{name}: expected {count} rows, got {len(rows)}')
    di = index_unique(diagnostic, 'item_id', 'diagnostic')
    fi = index_unique(full, 'item_id', 'full')
    ci = index_unique(crop, 'item_id', 'crop')
    index_unique(diagnostic, 'diagnostic_id', 'diagnostic')
    index_unique(full, 'diagnostic_id', 'full')
    # Only identities of the 75 unselected SCREEN records are inspected.
    si = index_unique(screen, 'operational_id', 'screen')
    index_unique(screen, 'item_id', 'screen')
    multi = [row for row in full if row.get('taxonomy') == MULTI]
    require(len(multi) == 5, 'full: expected exactly five multi_person_one_lying rows')
    order = list(dict.fromkeys([row['item_id'] for row in diagnostic] +
                              [row['item_id'] for row in multi]))
    require(len(order) == 115, 'deduplicated pilot must contain 115 identities')
    pilot = []
    for number, item_id in enumerate(order, 1):
        require(item_id in fi and item_id in ci, f'{item_id}: missing full/crop match')
        base, view, original = fi[item_id], ci[item_id], di.get(item_id)
        for key, value in base.items():
            require(key in view and view[key] == value,
                    f'{item_id}: full/crop conflict in {key}')
        row = {**base, **{key: value for key, value in view.items() if key not in base}}
        # These two differences are source identity/selection metadata, never GT.
        if original:
            for key, value in original.items():
                if key in base and key not in ('diagnostic_id', 'selection_basis'):
                    require(base[key] == value, f'{item_id}: diagnostic/full conflict in {key}')
                elif key not in base:
                    if key in row:
                        require(row[key] == value, f'{item_id}: diagnostic/crop conflict in {key}')
                    else:
                        row[key] = value
        row = add_fields(row, {
            'diagnostic_original_id': original['diagnostic_id'] if original else '',
            'diagnostic_original_selection_basis': original['selection_basis'] if original else '',
            'operational_id': base['diagnostic_id'],
            'experiment_stratum': 'ground_lying' if base.get('expected_v4_outcome') == GROUND else 'normal_negative',
            'experiment_role': 'PILOT_DEV_115', 'phase': 'pilot',
            'request_id': f'V5_B0_PILOT_{number:04d}',
        })
        validate_source(row, 'pilot')
        pilot.append(row)
    normal = [r for r in pilot if r['experiment_stratum'] == 'normal_negative']
    single = [r for r in pilot if r['experiment_stratum'] == 'ground_lying' and r['taxonomy'] != MULTI]
    multiple = [r for r in pilot if r['taxonomy'] == MULTI]
    require(len(normal) == 55 and all(r['taxonomy'] == 'floor_sitting' for r in normal),
            'pilot: expected 55 floor_sitting normal_negative rows')
    require(len(single) == 55 and len(multiple) == 5 and
            all(r['experiment_stratum'] == 'ground_lying' for r in multiple),
            'pilot: expected 55 single and five multi ground_lying rows')
    require(all(r.get('diagnostic_class') == ('floor_sitting' if r['experiment_stratum'] == 'normal_negative' else 'lying')
                for r in pilot[:110]), 'diagnostic class/outcome conflict')
    require(len({r['group_id'] for r in multiple}) == 1, 'multi group_count must equal one')
    groups = [{r['group_id'] for r in subset} for subset in (normal, single, multiple)]
    require(not any(groups[i] & groups[j] for i in range(3) for j in range(i)),
            'group identity overlaps experiment strata')
    require(REGRESSION_ID in si, 'missing operational regression identity')
    regression_source = si[REGRESSION_ID]
    require(regression_source['item_id'] == REGRESSION_ITEM, 'regression item/operational identity mismatch')
    require(REGRESSION_ITEM not in order, 'regression must remain independent from pilot')
    require(regression_source['group_id'] not in set.union(*groups), 'regression group leaks into pilot')
    regression = dict(regression_source)
    derived = 'expected_v4_outcome' not in regression
    if derived:
        require(regression.get('expected_high_priority') == GROUND,
                'regression: missing/conflicting existing expected_high_priority')
        regression['expected_v4_outcome'] = regression['expected_high_priority']
    require(regression.get('expected_v4_outcome') == GROUND and
            regression.get('expected_high_priority', GROUND) == GROUND and
            regression.get('operational_class') == 'ground_lying', 'regression GT conflict')
    regression = add_fields(regression, {
        'experiment_stratum': 'ground_lying',
        'experiment_role': 'KNOWN_FAILURE_DEVELOPMENT_REGRESSION',
        'phase': 'regression', 'request_id': 'V5_B0_REGRESSION_0001',
    })
    validate_source(regression, 'regression')
    derivation = {
        'item_id': REGRESSION_ITEM, 'operational_id': REGRESSION_ID,
        'source_manifest': str(SOURCES['screen']),
        'target_field': 'expected_v4_outcome',
        'source_field': 'expected_high_priority' if derived else 'expected_v4_outcome',
        'value': regression['expected_v4_outcome'], 'derived': derived,
        'operation': 'exact_copy_of_existing_expected_label' if derived else 'preserve_existing',
        'gt_relabelled': False,
    }
    return pilot, [regression], derivation


def verify_blob(path, data, expected, image=False, view=False):
    require(sha256_bytes(data) == expected, f'SHA256 mismatch: {path}')
    if image or view:
        try:
            with Image.open(io.BytesIO(data)) as handle:
                if view:
                    require(handle.format == 'JPEG' and handle.size == (448, 336),
                            f'view must be 448x336 JPEG: {path}')
                handle.verify()
            # Decode to detect truncated payloads; this is not semantic inspection.
            with Image.open(io.BytesIO(data)) as handle:
                handle.load()
        except ManifestError:
            raise
        except Exception as exc:
            raise ManifestError(f'invalid image encoding: {path}: {exc}') from exc


def verify_resources(rows, bindings):
    checks = []
    for row in rows:
        for path_key, hash_key in RESOURCE_FIELDS:
            path = row[path_key]
            data = read_bound(path, bindings)
            verify_blob(path, data, row[hash_key], image=path_key == 'image_path',
                        view=path_key in ('full_view_path', 'crop_view_path'))
            checks.append({'request_id': row['request_id'], 'item_id': row['item_id'],
                           'field': path_key, 'path': path, 'sha256': bindings[path]})
    return checks


def verify_preparation(bindings):
    result = {}
    for phase, (plan, producer) in PREPARATION.items():
        prep = json.loads(read_bound(plan, bindings))['preprocess']
        require((prep.get('width'), prep.get('height'), prep.get('jpeg_quality')) == (448, 336, 70),
                f'{phase}: frozen preparation is not 448x336 JPEG70')
        source = read_bound(producer, bindings).decode('utf-8')
        require('"JPEG"' in source and 'quality=cfg["jpeg_quality"]' in source,
                f'{phase}: frozen producer does not bind JPEG quality to config')
        require(('CONFIG = ROOT / "protocol/v4_full_dev_execution_plan.json"' in source
                 if phase == 'pilot' else
                 'PLAN = ROOT / "protocol/final_operational_plan.json"' in source),
                f'{phase}: frozen producer/plan reference mismatch')
        result[phase] = {
            'plan_path': str(plan), 'producer_path': str(producer), 'preprocess': prep,
            'jpeg_quality_basis': 'FROZEN_PREPARATION_PLAN_AND_PRODUCER_SOURCE',
            'bytes_reencoded': False, 'quality_inferred_from_pixels': False,
            'producer_executed': False,
        }
    return result


def count_summary(pilot, regression):
    subsets = {
        'floor_sitting_normal_negative': [r for r in pilot if r['experiment_stratum'] == 'normal_negative'],
        'single_ground_lying': [r for r in pilot if r['experiment_stratum'] == 'ground_lying' and r['taxonomy'] != MULTI],
        'multi_ground_lying': [r for r in pilot if r['taxonomy'] == MULTI],
    }
    return {
        'pilot': len(pilot), 'regression': len(regression), 'selected_total': len(pilot) + len(regression),
        'diagnostic_retained': 110, 'full_multi_appended': 5, 'unselected_screen_identity_only': 75,
        'strata': {key: {'row_count': len(rows), 'group_count': len({r['group_id'] for r in rows})}
                   for key, rows in subsets.items()},
        'pilot_group_count': len({r['group_id'] for r in pilot}),
        'regression_group_count': len({r['group_id'] for r in regression}),
        'pilot_source_split': dict(Counter(r['source_split'] for r in pilot)),
        'regression_source_split': dict(Counter(r['source_split'] for r in regression)),
    }


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def csv_text(rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def refuse_existing(paths=OUTPUTS):
    existing = [str(path) for path in paths if path.exists() or path.is_symlink()]
    require(not existing, 'refusing to overwrite existing output(s): ' + ', '.join(existing))


def write_exclusive(payloads):
    """No staging writes elsewhere; exclusive creation also rejects race-time collisions.

    The audit is written last. A partial interrupted build is intentionally not
    auto-repaired and a subsequent run refuses its existing files.
    """
    refuse_existing(payloads)
    for path, text in payloads.items():
        require(path in OUTPUTS, f'write outside explicit output allowlist: {path}')
        with path.open('x', encoding='utf-8', newline='') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())


def build():
    refuse_existing()
    bindings = {}
    sources = load_sources(bindings)
    pilot, regression, derivation = assemble(sources)
    preparation = verify_preparation(bindings)
    checks = verify_resources(pilot + regression, bindings)
    texts = {OUTPUTS[0]: json_text(pilot), OUTPUTS[1]: csv_text(pilot),
             OUTPUTS[2]: json_text(regression), OUTPUTS[3]: csv_text(regression)}
    audit = {
        'status': 'PASS_OFFLINE_MECHANICAL_SOURCE_AND_HASH_VERIFICATION',
        'counts': count_summary(pilot, regression),
        'bindings': dict(sorted(bindings.items())),
        'source_manifests': {name: str(path) for name, path in SOURCES.items()},
        'resource_checks': checks, 'resource_check_count': len(checks),
        'unique_selected_resource_count': len({check['path'] for check in checks}),
        'frozen_view_preparation': preparation,
        'regression_expected_v4_outcome_binding': derivation,
        'diagnostic_metadata_binding': {
            'diagnostic_original_id': 'diagnostic.diagnostic_id',
            'diagnostic_original_selection_basis': 'diagnostic.selection_basis',
            'diagnostic_id': 'full.diagnostic_id', 'selection_basis': 'full.selection_basis',
            'operational_id': 'full.diagnostic_id (pilot); screen.operational_id (regression)',
            'diagnostic_only_fields': 'preserved under original names; absent for appended multi rows',
        },
        'scope': {
            'noVAL': True, 'noholdout': True, 'no_inference': True, 'no_preflight': True,
            'no_network': True, 'no_ollama': True, 'no_detector_execution': True,
            'no_human_review_required': True, 'human_review_performed': False,
            'pixel_semantics_verified': False, 'unverified_localization': True,
            'source_fields_unchanged': True, 'gt_relabelled': False,
            'regression_is_independent_evaluation': False,
            'notes': [
                'Read DEV manifest metadata; SCREEN read only to locate/validate the one requested identity.',
                'No unselected source image, generation prompt, full view, or crop view was opened.',
                'Only selected 116 rows: source image and generation prompt hashes plus full/crop hashes.',
                'Image decoding checks encoding only; both views are verified as 448x336 JPEG.',
                'JPEG70 is cited from frozen plans/producers; original JPEG bytes are unchanged.',
                'Frozen largest-person crop may not localize the lying target in multi-person scenes; localization is unverified.',
                'Synthetic GT is inherited, not human- or pixel-semantically verified.',
                'NEW_DESIGN and NEW_SCREEN are preserved; experiment role does not rewrite source split.',
                'Known failure SCREEN row is development regression only, not independent validation.',
                'Five multi-person rows represent one group, not five independent groups.',
                'No historical producer code was imported/executed; no model service or preflight was called.',
            ],
        },
        'output_sha256': {str(path): sha256_bytes(text.encode('utf-8')) for path, text in texts.items()},
    }
    texts[OUTPUTS[4]] = json_text(audit)
    write_exclusive(texts)
    return audit


def main():
    try:
        audit = build()
    except (ManifestError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f'BLOCKED: report to main agent; no label repair: {exc}', file=sys.stderr)
        return 1
    print(json_text({'status': audit['status'], 'counts': audit['counts']}), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
