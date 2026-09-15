"""Offline manifest contract tests; no temporary files, model calls, or network.

Run with PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <tests> -p test_manifests.py -v.
Mutations and malformed images exist only in memory; history/resources stay read-only.
"""
from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import socket
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('offline_build_manifests', ROOT / 'tools/build_manifests.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = m.load_sources({})
        cls.pilot, cls.regression, cls.derivation = m.assemble(cls.sources)

    def changed(self):
        return copy.deepcopy(self.sources)

    def assert_rejected(self, sources, pattern):
        with self.assertRaisesRegex(m.ManifestError, pattern):
            m.assemble(sources)

    def test_strata_and_order(self):
        expected = [r['item_id'] for r in self.sources['diagnostic']]
        expected += [r['item_id'] for r in self.sources['full'] if r['taxonomy'] == m.MULTI]
        self.assertEqual([r['item_id'] for r in self.pilot], expected)
        self.assertEqual(len(set(expected)), 115)
        self.assertEqual(Counter(r['experiment_stratum'] for r in self.pilot),
                         {'normal_negative': 55, 'ground_lying': 60})
        counts = m.count_summary(self.pilot, self.regression)
        self.assertEqual(counts['strata'], {
            'floor_sitting_normal_negative': {'row_count': 55, 'group_count': 9},
            'single_ground_lying': {'row_count': 55, 'group_count': 9},
            'multi_ground_lying': {'row_count': 5, 'group_count': 1},
        })
        self.assertEqual(counts['pilot_group_count'], 19)
        for number, row in enumerate(self.pilot, 1):
            self.assertEqual(row['request_id'], f'V5_B0_PILOT_{number:04d}')
            self.assertEqual(row['phase'], 'pilot')
            self.assertEqual(row['experiment_role'], 'PILOT_DEV_115')
            self.assertEqual(row['operational_id'], row['diagnostic_id'])

    def test_all_full_crop_fields_preserved(self):
        for source_name in ('full', 'crop'):
            lookup = {r['item_id']: r for r in self.sources[source_name]}
            for row in self.pilot:
                for key, value in lookup[row['item_id']].items():
                    self.assertEqual(row[key], value, (row['item_id'], key))
        self.assertEqual(Counter(r['source_split'] for r in self.pilot),
                         {'NEW_DESIGN': 55, 'DEV': 60})

    def test_diagnostic_metadata_preserved(self):
        for original, row in zip(self.sources['diagnostic'], self.pilot[:110]):
            self.assertEqual(row['diagnostic_original_id'], original['diagnostic_id'])
            self.assertEqual(row['diagnostic_original_selection_basis'], original['selection_basis'])
            for key, value in original.items():
                if key not in ('diagnostic_id', 'selection_basis'):
                    self.assertEqual(row[key], value)
        self.assertTrue(all(not r['diagnostic_original_id'] for r in self.pilot[110:]))

    def test_regression_independent_identity_group_and_source(self):
        row, = self.regression
        original, = [r for r in self.sources['screen'] if r['operational_id'] == m.REGRESSION_ID]
        for key, value in original.items():
            self.assertEqual(row[key], value, key)
        self.assertEqual(row['source_split'], 'NEW_SCREEN')
        self.assertEqual(row['v3_split'], 'V3_SCREEN')
        self.assertEqual(row['item_id'], m.REGRESSION_ITEM)
        self.assertEqual(row['request_id'], 'V5_B0_REGRESSION_0001')
        self.assertEqual(row['phase'], 'regression')
        self.assertEqual(row['experiment_role'], 'KNOWN_FAILURE_DEVELOPMENT_REGRESSION')
        self.assertNotIn(row['item_id'], {r['item_id'] for r in self.pilot})
        self.assertNotIn(row['group_id'], {r['group_id'] for r in self.pilot})
        self.assertTrue(self.derivation['derived'])
        self.assertEqual(self.derivation['source_field'], 'expected_high_priority')
        self.assertEqual(row['expected_v4_outcome'], original['expected_high_priority'])
        self.assertFalse(self.derivation['gt_relabelled'])

    def test_existing_regression_outcome_preserved_not_derived(self):
        sources = self.changed()
        row = next(r for r in sources['screen'] if r['operational_id'] == m.REGRESSION_ID)
        row['expected_v4_outcome'] = row['expected_high_priority']
        _, regression, derivation = m.assemble(sources)
        self.assertFalse(derivation['derived'])
        self.assertEqual(regression[0]['expected_v4_outcome'], row['expected_v4_outcome'])

    def test_unselected_screen_is_identity_only(self):
        sources = self.changed()
        sources['screen'] = [r if r['operational_id'] == m.REGRESSION_ID else
                             {key: r[key] for key in ('operational_id', 'item_id')}
                             for r in sources['screen']]
        self.assertEqual(m.assemble(sources), (self.pilot, self.regression, self.derivation))

    def test_duplicate_identities_rejected(self):
        for source_name in ('diagnostic', 'full', 'crop', 'screen'):
            with self.subTest(source=source_name):
                sources = self.changed()
                sources[source_name][1] = dict(sources[source_name][0])
                self.assert_rejected(sources, 'duplicate')

    def test_missing_rows_rejected(self):
        for source_name in ('diagnostic', 'full', 'crop', 'screen'):
            with self.subTest(source=source_name):
                sources = self.changed()
                sources[source_name].pop()
                self.assert_rejected(sources, 'expected .* rows')

    def test_missing_selected_full_or_crop_match_rejected(self):
        item = self.pilot[0]['item_id']
        for source_name in ('full', 'crop'):
            with self.subTest(source=source_name):
                sources = self.changed()
                next(r for r in sources[source_name] if r['item_id'] == item)['item_id'] = 'MISSING_REPLACEMENT'
                self.assert_rejected(sources, 'missing full/crop match')

    def test_missing_required_fields_rejected(self):
        for key in ('group_id', 'expected_v4_outcome', 'source_split', 'gt_source',
                    'image_sha256', 'prompt_sha256', 'full_view_path', 'crop_view_sha256'):
            with self.subTest(field=key):
                sources = self.changed()
                row = next(r for r in sources['crop'] if r['item_id'] == self.pilot[0]['item_id'])
                row.pop(key)
                self.assert_rejected(sources, 'missing|conflict')

    def test_diagnostic_full_gt_and_split_conflicts_rejected(self):
        for key in ('ground_truth', 'gt_type', 'gt_source', 'source_split', 'taxonomy',
                    'group_id', 'prompt_sha256', 'image_sha256'):
            with self.subTest(field=key):
                sources = self.changed()
                sources['diagnostic'][0][key] = 'CORRUPTED'
                self.assert_rejected(sources, 'diagnostic/full conflict')

    def test_full_crop_gt_and_split_conflicts_rejected(self):
        for key in ('expected_v4_outcome', 'ground_truth', 'source_split', 'diagnostic_id'):
            with self.subTest(field=key):
                sources = self.changed()
                next(r for r in sources['crop'] if r['item_id'] == self.pilot[0]['item_id'])[key] = 'CORRUPTED'
                self.assert_rejected(sources, 'full/crop conflict')

    def test_outcome_conflicts_rejected_even_when_full_and_crop_agree(self):
        sources = self.changed()
        for source_name in ('full', 'crop'):
            next(r for r in sources[source_name] if r['item_id'] == self.pilot[0]['item_id'])['expected_v4_outcome'] = m.GROUND
        self.assert_rejected(sources, 'ground_truth/outcome conflict')

    def test_multi_duplicate_diagnostic_selection_rejected(self):
        sources = self.changed()
        multi = next(r for r in sources['full'] if r['taxonomy'] == m.MULTI)
        sources['diagnostic'][0]['item_id'] = multi['item_id']
        self.assert_rejected(sources, 'deduplicated pilot must contain 115')

    def test_multi_group_count_rejected(self):
        sources = self.changed()
        item = self.pilot[-1]['item_id']
        for source_name in ('full', 'crop'):
            next(r for r in sources[source_name] if r['item_id'] == item)['group_id'] = 'OTHER_MULTI_GROUP'
        self.assert_rejected(sources, 'multi group_count must equal one')

    def test_regression_missing_wrong_or_duplicate_identity_rejected(self):
        for mutation in ('missing', 'wrong', 'duplicate'):
            with self.subTest(mutation=mutation):
                sources = self.changed()
                row = next(r for r in sources['screen'] if r['operational_id'] == m.REGRESSION_ID)
                if mutation == 'missing':
                    row['operational_id'] = 'WRONG_OPERATIONAL_ID'
                elif mutation == 'wrong':
                    row['item_id'] = 'WRONG_ITEM_ID'
                else:
                    sources['screen'][0] = dict(row)
                self.assert_rejected(sources, 'identity|duplicate')

    def test_regression_conflicting_or_missing_gt_rejected(self):
        for field, value in (('expected_high_priority', None), ('expected_high_priority', m.NORMAL),
                             ('expected_v4_outcome', ''), ('expected_v4_outcome', m.NORMAL),
                             ('ground_truth', 'negative')):
            with self.subTest(field=field, value=value):
                sources = self.changed()
                row = next(r for r in sources['screen'] if r['operational_id'] == m.REGRESSION_ID)
                if value is None:
                    row.pop(field)
                else:
                    row[field] = value
                self.assert_rejected(sources, 'conflict|missing')

    def test_regression_group_overlap_rejected(self):
        sources = self.changed()
        row = next(r for r in sources['screen'] if r['operational_id'] == m.REGRESSION_ID)
        row['group_id'] = self.pilot[0]['group_id']
        self.assert_rejected(sources, 'regression group leaks')

    def test_forbidden_split_and_resource_paths_rejected(self):
        for split in ('VAL', 'V3_VAL', 'HOLDOUT'):
            row = dict(self.pilot[0], source_split=split)
            with self.assertRaisesRegex(m.ManifestError, 'forbidden split'):
                m.validate_source(row, 'pilot')
        for path in ('/offline/val/image.jpg', '/offline/manifests/v3_holdout.csv',
                     '/offline/prepared_val/image.jpg', 'relative.jpg'):
            with self.assertRaises(m.ManifestError):
                m.check_path(path)

    def test_image_and_view_hash_anomalies_rejected(self):
        for _, hash_key in m.RESOURCE_FIELDS:
            with self.subTest(field=hash_key):
                with self.assertRaisesRegex(m.ManifestError, 'SHA256 mismatch'):
                    m.verify_blob('/memory/selected', b'corrupted', self.pilot[0][hash_key])

    def test_view_dimensions_format_and_encoding_rejected(self):
        for fmt, size in (('PNG', (448, 336)), ('JPEG', (447, 336)), ('JPEG', (448, 335))):
            with self.subTest(format=fmt, size=size):
                stream = io.BytesIO()
                m.Image.new('RGB', size).save(stream, fmt)
                data = stream.getvalue()
                with self.assertRaisesRegex(m.ManifestError, '448x336 JPEG'):
                    m.verify_blob('/memory/view', data, m.sha256_bytes(data), view=True)
        data = b'not an image'
        with self.assertRaisesRegex(m.ManifestError, 'invalid image encoding'):
            m.verify_blob('/memory/view', data, m.sha256_bytes(data), view=True)

    def test_valid_jpeg_in_memory(self):
        stream = io.BytesIO()
        m.Image.new('RGB', (448, 336)).save(stream, 'JPEG', quality=70)
        data = stream.getvalue()
        m.verify_blob('/memory/view', data, m.sha256_bytes(data), view=True)

    def test_missing_selected_resource_rejected(self):
        with mock.patch.object(Path, 'read_bytes', side_effect=FileNotFoundError('synthetic missing')):
            with self.assertRaisesRegex(m.ManifestError, 'missing/unreadable dependency'):
                m.verify_resources(self.regression, {})

    def test_existing_output_refusal_precedes_source_reads(self):
        for existing_kind in ('file', 'dangling_symlink'):
            with self.subTest(kind=existing_kind):
                with mock.patch.object(Path, 'exists', return_value=existing_kind == 'file'), \
                     mock.patch.object(Path, 'is_symlink', return_value=existing_kind == 'dangling_symlink'), \
                     mock.patch.object(m, 'load_sources') as load, \
                     mock.patch.object(m, 'write_exclusive') as write:
                    with self.assertRaisesRegex(m.ManifestError, 'refusing to overwrite'):
                        m.build()
                    load.assert_not_called()
                    write.assert_not_called()

    def test_actual_selected_resources_and_complete_bindings_offline(self):
        # One selected-only real read/verification, with network and file writes denied.
        bindings = {}
        original_read = Path.read_bytes
        opened = []
        allowed = set(m.SOURCES.values())
        allowed.update(path for pair in m.PREPARATION.values() for path in pair)
        allowed.update(Path(r[key]) for r in self.pilot + self.regression for key, _ in m.RESOURCE_FIELDS)

        def guarded_read(path):
            self.assertIn(path, allowed, f'unselected/unauthorized file read: {path}')
            opened.append(path)
            return original_read(path)

        with mock.patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')), \
             mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')), \
             mock.patch.object(socket, 'getaddrinfo', side_effect=AssertionError('network forbidden')), \
             mock.patch.object(Path, 'read_bytes', guarded_read), \
             mock.patch.object(Path, 'write_text', side_effect=AssertionError('disk writes forbidden')):
            sources = m.load_sources(bindings)
            pilot, regression, _ = m.assemble(sources)
            preparation = m.verify_preparation(bindings)
            checks = m.verify_resources(pilot + regression, bindings)
        self.assertEqual(set(opened), allowed)
        self.assertEqual(set(bindings), {str(p) for p in allowed})
        self.assertEqual(len(checks), 116 * 4)
        self.assertEqual(len({r['request_id'] for r in checks}), 116)
        self.assertEqual(Counter(r['field'] for r in checks), {k: 116 for k, _ in m.RESOURCE_FIELDS})
        for phase in ('pilot', 'regression'):
            self.assertEqual(preparation[phase]['preprocess']['jpeg_quality'], 70)
            self.assertFalse(preparation[phase]['bytes_reencoded'])
            self.assertFalse(preparation[phase]['producer_executed'])

    def test_csv_json_roundtrip_all_source_values(self):
        for rows in (self.pilot, self.regression):
            json_rows = json.loads(m.json_text(rows))
            csv_rows = list(csv.DictReader(io.StringIO(m.csv_text(rows))))
            self.assertEqual(json_rows, rows)
            for original, encoded in zip(rows, csv_rows):
                for key, value in original.items():
                    self.assertEqual(encoded[key], value)

    def test_csv_duplicate_columns_and_missing_values_rejected(self):
        for data in (b'item_id,item_id\na,b\n', b'item_id,group_id\na\n',
                     b'item_id\na,b\n', b''):
            with self.assertRaises(m.ManifestError):
                m.parse_csv(data, 'in_memory')

    def test_dependency_changes_during_run_rejected(self):
        path = m.SOURCES['diagnostic']
        with mock.patch.object(Path, 'read_bytes', side_effect=[b'first', b'changed']):
            bindings = {}
            m.read_bound(path, bindings)
            with self.assertRaisesRegex(m.ManifestError, 'dependency changed'):
                m.read_bound(path, bindings)

    def test_generated_artifacts_when_present(self):
        if not all(path.exists() for path in m.OUTPUTS):
            self.skipTest('Run the builder, then repeat this suite to verify saved artifacts.')
        expected_sets = (self.pilot, self.regression)
        for offset, expected in zip((0, 2), expected_sets):
            self.assertEqual(json.loads(m.OUTPUTS[offset].read_text()), expected)
            self.assertEqual(m.OUTPUTS[offset + 1].read_text(), m.csv_text(expected))
        audit = json.loads(m.OUTPUTS[4].read_text())
        self.assertEqual(audit['counts'], m.count_summary(self.pilot, self.regression))
        for path in m.OUTPUTS[:4]:
            self.assertEqual(m.sha256_bytes(path.read_bytes()), audit['output_sha256'][str(path)])
        self.assertEqual(audit['regression_expected_v4_outcome_binding'], self.derivation)
        self.assertEqual(audit['resource_check_count'], 464)
        for flag in ('noVAL', 'noholdout', 'no_inference', 'no_preflight', 'no_network',
                     'no_ollama', 'unverified_localization', 'source_fields_unchanged'):
            self.assertTrue(audit['scope'][flag], flag)
        self.assertFalse(audit['scope']['pixel_semantics_verified'])
        self.assertFalse(audit['scope']['gt_relabelled'])
        with self.assertRaisesRegex(m.ManifestError, 'refusing to overwrite'):
            m.build()


if __name__ == '__main__':
    unittest.main()
