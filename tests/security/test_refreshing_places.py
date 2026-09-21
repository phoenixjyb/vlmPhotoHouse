"""Refreshing protected place membership over a current authorized scope."""
from dataclasses import asdict, replace
import math
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests/security')]

from app.access import discovery as d
from app.access.discovery_index import DiscoveryIndexRefused, index as load_index, load
from app.access.discovery_provider import MemoryIndexProvider, ProjectedIndex, RefreshingPlaceIndex, RegionRule
from app.access.service import AccessDenied, AccessService
from phone_discovery_fixture import create, MAXIMUM, NOW, OTHER, TOKEN
import prepare_access_places as places


REGIONS = {'version': 1, 'places': [
    {'id': '601', 'label': 'Example coast', 'south': -1, 'west': -1, 'north': 1, 'east': 1},
    {'id': '602', 'label': 'Example islands', 'south': -10, 'west': 170, 'north': 10, 'east': -170},
]}


class RefreshingPlaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.path = self.root / 'synthetic.sqlite'
        self.db = create(sqlite3.connect(self.path)); self.addCleanup(self.db.close)
        self.db.execute('ALTER TABLE assets ADD COLUMN gps_lat REAL')
        self.db.execute('ALTER TABLE assets ADD COLUMN gps_lon REAL')
        self.db.execute('UPDATE assets SET gps_lat=0,gps_lon=0 WHERE id=101')
        self.db.execute('UPDATE assets SET gps_lat=2,gps_lon=179 WHERE id=102')
        self.db.commit(); self.access = AccessService(self.db, clock=lambda: NOW)

    def index(self, **changes):
        return places.derive(self.db, 'family-a', '1', places.regions(REGIONS), refresh=True)[0]

    def service(self, index=None, budget=None):
        return d.DiscoveryReads(self.access, MemoryIndexProvider((index or self.index(),)), budget or d.ReadBudget())

    def add_asset(self, asset_id, library='family-a', status='active', taken='2026-01-04', lat=0, lon=0):
        self.db.execute('INSERT INTO assets(id,path,status,mime,width,height,duration_sec,taken_at) VALUES(?,?,?,?,8,8,NULL,?)',
                        (asset_id, 'upload-path', status, 'image/jpeg', taken))
        self.db.execute('INSERT INTO access_asset_libraries VALUES(?,?)', (asset_id, library))
        self.db.execute('UPDATE assets SET gps_lat=?,gps_lon=? WHERE id=?', (lat, lon, asset_id))
        self.db.commit()

    def test_new_assigned_upload_is_visible_after_fresh_facets_without_provider_replacement(self):
        service = self.service(); first = service.facets(TOKEN, 'family-a', facet='locations')
        self.add_asset(104)
        fresh = service.facets(TOKEN, 'family-a', facet='locations')
        self.assertNotEqual(first['binding'], fresh['binding'])
        self.assertEqual(fresh['catalog_assets'], 5)
        self.assertEqual(next(item for item in fresh['items'] if item['id'] == '601')['asset_count'], 2)

    def test_empty_refreshing_library_accepts_future_asset_moves(self):
        self.db.execute("DELETE FROM access_asset_libraries WHERE library_id='family-a'")
        self.db.commit()
        index = self.index()
        self.assertEqual(index.scope_ids, ())
        service = self.service(index)
        self.assertEqual(service.facets(TOKEN, 'family-a', facet='locations')['catalog_assets'], 0)
        self.db.execute("INSERT INTO access_asset_libraries VALUES(101,'family-a')")
        self.db.commit()
        fresh = service.facets(TOKEN, 'family-a', facet='locations')
        self.assertEqual(fresh['catalog_assets'], 1)
        self.assertEqual(next(item for item in fresh['items'] if item['id'] == '601')['asset_count'], 1)

    def test_pending_foreign_and_hidden_assets_are_excluded(self):
        self.add_asset(104, status='pending')
        self.add_asset(105, library='family-b')
        self.db.execute('INSERT INTO assets(id,path,status,mime,width,height,duration_sec,taken_at) VALUES(106,?,?,?,8,8,NULL,?)',
                        ('upload-path', 'active', 'image/jpeg', '2026-01-04'))
        self.db.execute('UPDATE assets SET gps_lat=0,gps_lon=0 WHERE id=106')
        self.db.execute('UPDATE assets SET gps_lat=0,gps_lon=0 WHERE id=999'); self.db.commit()
        result = self.service().facets(TOKEN, 'family-a', facet='locations')
        self.assertEqual(result['catalog_assets'], 4)
        self.assertEqual(next(item for item in result['items'] if item['id'] == '601')['asset_count'], 1)

    def test_gps_move_and_invalid_coordinates_refresh_membership(self):
        service = self.service(); self.assertEqual(next(i for i in service.facets(TOKEN, 'family-a', facet='locations')['items'] if i['id'] == '601')['asset_count'], 1)
        self.db.execute('UPDATE assets SET gps_lat=2,gps_lon=179 WHERE id=101'); self.db.commit()
        moved = service.facets(TOKEN, 'family-a', facet='locations')
        self.assertEqual({i['id']: i['asset_count'] for i in moved['items']}, {'601': 0, '602': 2})
        self.db.execute('UPDATE assets SET gps_lat=91,gps_lon=0 WHERE id=101'); self.db.commit()
        invalid = service.facets(TOKEN, 'family-a', facet='locations')
        self.assertEqual({i['id']: i['asset_count'] for i in invalid['items']}, {'601': 0, '602': 1})

    def test_date_change_refreshes_current_bounds(self):
        service = self.service(); before = service.facets(TOKEN, 'family-a', facet='locations')
        self.assertEqual((before['captured_date_bounds']['from'], before['captured_date_bounds']['to']), ('2025-12-01', '2026-05-05'))
        self.db.execute("UPDATE assets SET taken_at='2027-01-01' WHERE id=101"); self.db.commit()
        after = service.facets(TOKEN, 'family-a', facet='locations')
        self.assertEqual(after['captured_date_bounds']['from'], '2025-12-01')
        self.assertEqual(after['captured_date_bounds']['to'], '2027-01-01')

    def test_scope_deletion_refreshes_catalog_and_old_search_binding_is_rejected(self):
        service = self.service(); old = service.facets(TOKEN, 'family-a', facet='locations')
        self.db.execute('DELETE FROM access_asset_libraries WHERE asset_id=101'); self.db.commit()
        fresh = service.facets(TOKEN, 'family-a', facet='locations')
        self.assertEqual(fresh['catalog_assets'], 3)
        with self.assertRaises(d.DiscoveryChanged): service.search(TOKEN, 'family-a', binding=old['binding'], filters={})

    def test_fresh_binding_search_sees_new_asset_and_old_binding_returns_changed(self):
        service = self.service(); old = service.facets(TOKEN, 'family-a', facet='locations')
        self.add_asset(104)
        fresh = service.facets(TOKEN, 'family-a', facet='locations')
        with self.assertRaises(d.DiscoveryChanged): service.search(TOKEN, 'family-a', binding=old['binding'], filters={'locations': ['601']})
        result = service.search(TOKEN, 'family-a', binding=fresh['binding'], filters={'locations': ['601']})
        self.assertIn('104', [item['id'] for item in result['items']])

    def test_revocation_precedes_provider_read(self):
        class Provider:
            def get(self, _): raise AssertionError('provider must not be read')
        service = d.DiscoveryReads(self.access, Provider(), d.ReadBudget())
        self.db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id='one'"); self.db.commit()
        with self.assertRaises(AccessDenied): service.facets(TOKEN, 'family-a')
        with self.assertRaises(AccessDenied): service.facets(OTHER, 'family-a')

    def test_old_projected_index_remains_static_and_legacy_serialization_is_unchanged(self):
        old = places.derive(self.db, 'family-a', '1', places.regions(REGIONS), refresh=False)[0]
        self.assertIsInstance(old, ProjectedIndex); self.assertNotIsInstance(old, RefreshingPlaceIndex)
        self.assertNotIn('region_rules', asdict(old)); self.assertEqual(load_index(d.packed(asdict(old)), 100000), old)
        self.db.execute('UPDATE assets SET gps_lat=2,gps_lon=179 WHERE id=101'); self.db.commit()
        with self.assertRaises(d.DiscoveryChanged): self.service(old).facets(TOKEN, 'family-a')

    def test_malicious_rule_bounds_types_ids_count_policy_and_subset_refuse(self):
        good = self.index()
        for rules in (tuple([RegionRule('601', 2, 1, 1, 2)]),
                      tuple([RegionRule('999', -1, -1, 1, 1), RegionRule('602', -1, 170, 1, -170)]),
                      tuple([RegionRule('601', -1, -1, 1, 1), RegionRule('601', -1, -1, 1, 1)]),
                      tuple([RegionRule(str(i), -1, -1, 1, 1) for i in range(1, 130)]),
                      tuple([RegionRule('601', True, -1, 1, 1)]),
                      tuple([RegionRule('601', -1, -1, math.nan, 1)]),
                      tuple([RegionRule('601', -1, 1, 1, 1)])):
            with self.subTest(rules=rules), self.assertRaises(d.DiscoveryInvalid):
                d.validate(replace(good, region_rules=rules), 'family-a', 100000)
        with self.assertRaises(d.DiscoveryInvalid): d.validate(replace(good, refresh_policy='other'), 'family-a', 100000)
        with self.assertRaises(d.DiscoveryInvalid): d.validate(replace(good, indexed_ids=good.scope_ids[:-1]), 'family-a', 100000)
        with self.assertRaises(d.DiscoveryInvalid): d.validate(replace(good, enabled=('date', 'locations', 'media', 'people')), 'family-a', 100000)

    def test_refreshing_artifact_round_trips_through_loader_and_runtime(self):
        original = self.index(); path = self.root / 'refreshing.json'; path.write_bytes(d.packed(asdict(original)))
        loaded = load_index(path.read_bytes(), 100000)
        self.assertEqual(loaded, original); self.assertIsInstance(loaded, RefreshingPlaceIndex)
        self.assertEqual(load((path,)).get('family-a'), original)

    def test_loader_rejects_malformed_refresh_rules_and_unsupported_facets_are_empty(self):
        payload = asdict(self.index()); payload['region_rules'][0]['south'] = 'bad'
        with self.assertRaises(DiscoveryIndexRefused): load_index(d.packed(payload), 100000)
        service = self.service()
        self.assertEqual(service.facets(TOKEN, 'family-a', facet='people')['items'], [])
        self.assertEqual(service.facets(TOKEN, 'family-a', facet='tags')['items'], [])

    def test_preparation_and_service_are_read_only_and_do_not_expose_gps(self):
        before = self.path.read_bytes(); index, receipt = places.derive(self.db, 'family-a', '1', places.regions(REGIONS), refresh=True)
        self.assertEqual(self.path.read_bytes(), before); self.assertEqual(receipt['with_recorded_gps'], 2)
        result = self.service(index).facets(TOKEN, 'family-a', facet='locations')
        payload = d.packed(result)
        self.assertNotIn(b'gps_', payload); self.assertNotIn(b'coordinates', payload)
        self.assertNotIn(b'region_rules', payload); self.assertNotIn(b'south', payload)
        self.assertEqual(self.path.read_bytes(), before)

    def test_row_index_bytes_pair_and_time_budgets_fail_closed(self):
        initial = self.index(); bounded = self.service(initial, budget=d.ReadBudget(rows=8))
        bounded.facets(TOKEN, 'family-a')
        self.add_asset(104); self.add_asset(105); self.add_asset(106); self.add_asset(107)
        with self.assertRaises(d.DiscoveryUnavailable): bounded.facets(TOKEN, 'family-a')
        with self.assertRaises(d.DiscoveryUnavailable): self.service(budget=d.ReadBudget(index_bytes=1)).facets(TOKEN, 'family-a')
        overlap = replace(initial, region_rules=(
            RegionRule('601', -1, -1, 1, 1), RegionRule('602', -1, -1, 1, 1)))
        with self.assertRaises(d.DiscoveryUnavailable):
            d.refreshed_index(overlap, {'assets': [(1,)] * 2, 'coordinates': [('1', 0, 0), ('2', 0, 0)]}, lambda: None, 1)
        ticks = iter(range(100))
        with self.assertRaises(d.DiscoveryUnavailable):
            self.service(budget=d.ReadBudget(seconds=0.1, clock=lambda: next(ticks))).facets(TOKEN, 'family-a')


if __name__ == '__main__': unittest.main()
