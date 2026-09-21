"""Read-only GPS region preparation, dependency freshness and current access."""
from contextlib import redirect_stdout, redirect_stderr, contextmanager
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests/security')]
from app.access import discovery as d
from app.access.discovery_index import index as load_index, load, DiscoveryIndexRefused
from app.access.discovery_provider import MemoryIndexProvider, ProjectedIndex
from app.access.service import AccessService, AccessDenied
from phone_discovery_fixture import create, reviewed, TOKEN, OTHER, NOW
import prepare_access_places as places
import prepare_access_discovery_index as producer

REGIONS = {'version': 1, 'places': [
    {'id': '601', 'label': 'Example coast / 示例海岸', 'south': -1, 'north': 1, 'west': -1, 'east': 1},
    {'id': '602', 'label': 'Example islands', 'south': -10, 'north': 10, 'west': 170, 'east': -170},
]}


class ProjectedPlaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.path = self.root / 'synthetic.sqlite'
        self.db = create(sqlite3.connect(self.path)); self.addCleanup(self.db.close)
        self.db.execute('ALTER TABLE assets ADD COLUMN gps_lat REAL')
        self.db.execute('ALTER TABLE assets ADD COLUMN gps_lon REAL')
        self.db.execute('UPDATE assets SET gps_lat=0,gps_lon=0 WHERE id IN (101,201,999)')
        self.db.execute('UPDATE assets SET gps_lat=2,gps_lon=179 WHERE id=102')
        self.db.commit()
        self.access = AccessService(self.db, clock=lambda: NOW)

    def prepared(self):
        return places.derive(self.db, 'family-a', '1', places.regions(REGIONS))[0]

    def service(self, index=None):
        return d.DiscoveryReads(self.access, MemoryIndexProvider((index or self.prepared(),)), d.ReadBudget())

    def test_records_only_scoped_valid_coordinates_and_keeps_zero(self):
        index, receipt = places.derive(self.db, 'family-a', '1', places.regions(REGIONS))
        self.assertEqual(index.regions, (('101', '601'), ('102', '602')))
        self.assertEqual(receipt, {'catalog_assets': 4, 'with_recorded_gps': 2,
            'without_valid_gps': 2, 'with_named_place': 2, 'gps_outside_named_places': 0})
        payload = d.packed(asdict(index))
        self.assertNotIn(b'gps_lat', payload); self.assertNotIn(b'coordinates', payload)
        self.assertEqual(load_index(payload, 100000), index)
        self.assertEqual(self.service(index).facets(TOKEN, 'family-a', facet='locations')['coverage']['locations'],
                         {'with_values': 2, 'without_values': 2})

    def test_place_date_media_combination_and_paging(self):
        service = self.service(); binding = service.facets(TOKEN, 'family-a', facet='locations')['binding']
        result = service.search(TOKEN, 'family-a', binding=binding,
            filters={'locations': ['601'], 'date': {'from': '2026-01-01', 'to': '2026-01-03'}, 'media': ['image']})
        self.assertEqual([row['id'] for row in result['items']], ['101'])
        result = service.search(TOKEN, 'family-a', binding=binding, filters={'locations': ['601'], 'media': ['video']})
        self.assertEqual(result['total'], 0)
        first = service.search(TOKEN, 'family-a', binding=binding, filters={'locations': ['601', '602']}, page_size=1)
        second = service.search(TOKEN, 'family-a', binding=binding, filters={'locations': ['601', '602']}, page_size=1,
                                page=2, fingerprint=first['fingerprint'])
        self.assertEqual([first['items'][0]['id'], second['items'][0]['id']], ['102', '101'])

    def test_caption_face_and_tag_work_does_not_invalidate_location_index(self):
        service = self.service(); before = service.facets(TOKEN, 'family-a', facet='locations')
        self.db.execute("UPDATE captions SET text='New synthetic caption'")
        self.db.execute('UPDATE face_detections SET person_id=0')
        self.db.execute("UPDATE tags SET name='New synthetic tag'"); self.db.commit()
        self.assertEqual(service.facets(TOKEN, 'family-a', facet='locations'), before)

    def test_location_correction_requires_new_revision(self):
        service = self.service()
        self.db.execute('UPDATE assets SET gps_lon=90 WHERE id=101'); self.db.commit()
        with self.assertRaises(d.DiscoveryChanged): service.facets(TOKEN, 'family-a')
        new = replace(self.prepared(), revision='2')
        self.assertEqual(self.service(new).facets(TOKEN, 'family-a', facet='locations')['items'][0]['asset_count'], 0)

    def test_scope_and_date_changes_are_never_served_as_stale_results(self):
        for sql in ("UPDATE assets SET taken_at='2024-01-01' WHERE id=101",
                    "DELETE FROM access_asset_libraries WHERE asset_id=101"):
            service = self.service()
            self.db.execute(sql); self.db.commit()
            with self.assertRaises(d.DiscoveryChanged): service.facets(TOKEN, 'family-a')

    def test_revocation_and_cross_library_denied_before_provider_read(self):
        class Provider:
            def get(self, _): raise AssertionError('Provider must not be read')
        service = d.DiscoveryReads(self.access, Provider(), d.ReadBudget())
        with self.assertRaises(AccessDenied): service.facets(OTHER, 'family-a')
        self.db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id='one'"); self.db.commit()
        with self.assertRaises(AccessDenied): service.facets(TOKEN, 'family-a')

    def test_invalid_coordinates_are_unknown_and_outside_is_distinct(self):
        for lat, lon in [(None, 0), (91, 0), (0, -181), (float('inf'), 0), ('bad', 0)]:
            self.db.execute('UPDATE assets SET gps_lat=?,gps_lon=? WHERE id=101', (lat, lon)); self.db.commit()
            _, receipt = places.derive(self.db, 'family-a', '1', places.regions(REGIONS))
            self.assertEqual(receipt['without_valid_gps'], 3)
        self.db.execute('UPDATE assets SET gps_lat=50,gps_lon=50 WHERE id=101'); self.db.commit()
        _, receipt = places.derive(self.db, 'family-a', '1', places.regions(REGIONS))
        self.assertEqual(receipt['gps_outside_named_places'], 1)
        self.assertEqual(receipt['without_valid_gps'], 2)

    def test_antimeridian_and_closed_boundaries(self):
        region = places.regions(REGIONS)[1]
        for lon in (170, 179, 180, -180, -179, -170): self.assertTrue(places.contains(region, 10, lon))
        self.assertFalse(places.contains(region, 0, 0))
        self.assertFalse(places.contains(region, 11, 179))

    def test_region_validation(self):
        for field, value in [('south', True), ('north', float('nan')), ('east', 181), ('west', -1), ('id', '01'), ('label', '')]:
            record = json.loads(json.dumps(REGIONS)); record['places'][0][field] = value
            # west=-1 is valid; make east equal for the empty interval case.
            if field == 'west': record['places'][0]['east'] = value
            with self.assertRaises((producer.Refused, d.DiscoveryInvalid)): places.regions(record)
        with self.assertRaises(producer.Refused): places.regions({'version': 1, 'places': REGIONS['places'] * 2})

    def test_projected_artifact_through_closed_http_boundary(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.access.transport import AccessRuntime
        from app.access.discovery_transport import DiscoveryRuntime
        @contextmanager
        def connection():
            db = sqlite3.connect(self.path)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA query_only=ON')
            try: yield db
            finally: db.close()
        origin = 'https://photohouse.example.test'
        access = AccessRuntime(connection, origin, clock=lambda: NOW)
        path = self.root / 'projected.json'; path.write_bytes(d.packed(asdict(self.prepared())))
        runtime = DiscoveryRuntime(access, load((path,)), d.ReadBudget())
        app = create_app(access_runtime=access, media_runtime=None, discovery_runtime=runtime)
        base = '/libraries/family-a/discovery/v1'
        with TestClient(app, base_url=origin) as client:
            self.assertEqual(client.get(base + '/facets?facet=locations').status_code, 401)
            headers = {'Authorization': 'Bearer ' + TOKEN}
            facets = client.get(base + '/facets?facet=locations', headers=headers)
            self.assertEqual(facets.status_code, 200)
            self.assertIn('no-store', facets.headers['cache-control'])
            self.assertNotIn('gps_', facets.text); self.assertNotIn('coordinates', facets.text)
            result = client.post(base + '/search', headers=headers, json={
                'binding': facets.json()['binding'], 'filters': {'locations': ['601']},
                'page': 1, 'page_size': 24, 'fingerprint': None})
            self.assertEqual(result.status_code, 200)
            self.assertEqual([r['id'] for r in result.json()['items']], ['101'])
            self.db.execute('UPDATE assets SET gps_lon=90 WHERE id=101'); self.db.commit()
            self.assertEqual(client.get(base + '/facets?facet=locations', headers=headers).status_code, 409)

    def test_legacy_index_keeps_old_identity_and_freshness_policy(self):
        old = reviewed(self.access)
        self.assertNotIn('projection', asdict(old))
        self.assertEqual(load_index(d.packed(asdict(old)), 100000), old)
        service = self.service(old)
        self.db.execute("UPDATE captions SET text='changed' WHERE id=1"); self.db.commit()
        with self.assertRaises(d.DiscoveryChanged): service.facets(TOKEN, 'family-a')

    def test_projected_metadata_dependencies_cannot_be_disabled(self):
        from app.access.discovery_provider import ReviewedPerson
        index = replace(self.prepared(), people=(ReviewedPerson('family-a', '301', 'Sample', allow_zero=True),))
        with self.assertRaises(d.DiscoveryInvalid): d.validate(index, 'family-a', 100000)
        value = asdict(self.prepared()); value['projection'] = 'anything'
        with self.assertRaises(DiscoveryIndexRefused): load_index(d.packed(value), 100000)

    def test_cli_audit_and_output_are_read_only_and_never_overwrite(self):
        before = self.path.read_bytes(); region_path = self.root / 'regions.json'
        region_path.write_text(json.dumps(REGIONS)); output = self.root / 'places.json'
        base = ['--database', str(self.path), '--library', 'family-a']
        with redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(places.main(base + ['--audit']), 0)
        self.assertEqual(json.loads(stream.getvalue())['with_recorded_gps'], 2)
        args = base + ['--regions', str(region_path), '--out', str(output), '--revision', '1']
        with redirect_stdout(io.StringIO()): self.assertEqual(places.main(args), 0)
        accepted = output.read_bytes(); self.assertIsInstance(load((output,)).get('family-a'), ProjectedIndex)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(places.main(args), 2)
        self.assertEqual(output.read_bytes(), accepted); self.assertEqual(self.path.read_bytes(), before)

    def test_date_media_projection_skips_unrelated_tables(self):
        statements = []
        self.db.set_trace_callback(statements.append)
        index, _ = producer.derive(self.db, 'family-a', '1', projection='enabled-v2')
        self.service(index).facets(TOKEN, 'family-a')
        self.db.set_trace_callback(None)
        reads = ' '.join(s for s in statements if s.startswith('SELECT'))
        for table in ('captions', 'face_detections', 'asset_tags', 'gps_lat'):
            self.assertNotIn(table, reads)

    def test_30000_assets_with_background_caption_volume_fit_existing_budget(self):
        # More caption rows than the source row budget. A place-only request
        # must not inspect them, even while captioning changes them.
        self.db.executemany('INSERT INTO assets(id,status,mime,taken_at,gps_lat,gps_lon) VALUES(?,?,?,?,?,?)',
            ((i, 'active', 'image/jpeg', '2026-01-01', 0, 0) for i in range(1000, 31000)))
        self.db.executemany('INSERT INTO access_asset_libraries VALUES(?,?)', ((i, 'family-a') for i in range(1000, 31000)))
        self.db.executemany('INSERT INTO captions VALUES(?,?,?,0,0)', ((i, 1000, 'background') for i in range(1000, 102000)))
        self.db.commit()
        start = time.monotonic(); service = self.service(); preparation = time.monotonic() - start
        start = time.monotonic(); result = service.facets(TOKEN, 'family-a', facet='locations'); elapsed = time.monotonic() - start
        self.assertEqual(result['catalog_assets'], 30004)
        self.assertEqual(result['items'][0]['asset_count'], 30001)
        print(f'Synthetic 30004 assets: preparation={preparation:.3f}s facets={elapsed:.3f}s; default 2s/16MiB budget')


if __name__ == '__main__': unittest.main()
