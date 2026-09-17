"""Production wiring: the reviewed artifact, the loader, and the mounted routes.

Synthetic SQLite and in-process ASGI only. These tests drive the *default* app
(`app.main.create_app`) rather than the standalone candidate factory, so they cover
the wiring the candidate capsule deliberately left out.
"""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi.testclient import TestClient
from app.access import discovery as d
from app.access import discovery_index as di
from app.access.discovery_provider import MemoryIndexProvider, ReviewedIndex
from app.access.discovery_transport import DiscoveryRuntime
from app.access.transport import AccessRuntime
from app.access.service import AccessService
from app.main import create_app
from phone_discovery_fixture import create, reviewed, TOKEN, OTHER, NOW

ORIGIN = 'https://photohouse.example.test'
BASE = '/libraries/family-a/discovery/v1'


def artifact(index, directory, name='index.json'):
    """Exactly the bytes the operator producer writes."""
    path = directory / name
    path.write_bytes(json.dumps(asdict(index), sort_keys=True, ensure_ascii=True,
                                separators=(',', ':')).encode())
    return path


class WiringFixture:
    """Synthetic database plus one reviewed index loaded from a real artifact file."""

    def __init__(self, directory):
        self.directory = directory
        self.database = directory / 'synthetic.sqlite'
        with sqlite3.connect(self.database) as db:
            create(db)
            self.index = reviewed(AccessService(db, clock=lambda: NOW))
        self.path = artifact(self.index, directory)
        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: NOW)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=.25)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA query_only=ON')
        try:
            yield db
        finally:
            db.close()

    def runtime(self, paths=None):
        return DiscoveryRuntime(access=self.access,
                                provider=di.load(tuple(paths or (self.path,))),
                                budget=d.ReadBudget())

    def app(self, *, discovery_runtime=None):
        return create_app(access_runtime=self.access, media_runtime=None,
                          discovery_runtime=discovery_runtime)


class DiscoveryWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Resolve: macOS /var is a symlink, and the loader refuses an aliased parent.
        self.directory = Path(self.temp.name).resolve()
        self.fixture = WiringFixture(self.directory)
        self.auth = {'Authorization': 'Bearer ' + TOKEN}

    def client(self, app):
        client = TestClient(app, base_url=ORIGIN)
        self.addCleanup(client.close)
        return client

    # --- mounting and the closed boundary -----------------------------------

    def test_default_app_mounts_exactly_two_discovery_routes(self):
        app = self.fixture.app()
        paths = {(m, r.path) for r in app.routes for m in getattr(r, 'methods', []) or []}
        self.assertIn(('GET', '/libraries/{library_id}/discovery/v1/facets'), paths)
        self.assertIn(('POST', '/libraries/{library_id}/discovery/v1/search'), paths)
        self.assertEqual(len(paths), 49)

    def test_boundary_admits_the_two_routes_and_refuses_their_neighbours(self):
        app = self.fixture.app(discovery_runtime=self.fixture.runtime())
        client = self.client(app)
        admitted = [('get', BASE + '/facets'), ('post', BASE + '/search')]
        for method, url in admitted:
            response = getattr(client, method)(url, headers=self.auth)
            self.assertNotEqual(response.status_code, 403, f'{method} {url}')
        refused = [('get', BASE + '/search'), ('post', BASE + '/facets'),
                   ('get', '/libraries/family-a/discovery/v2/facets'),
                   ('get', '/libraries/family-a/discovery/v1/facets/extra'),
                   ('get', '/libraries/family-a/discovery/v1')]
        for method, url in refused:
            response = getattr(client, method)(url, headers=self.auth)
            self.assertEqual(response.status_code, 403, f'{method} {url}')

    # --- closed by default --------------------------------------------------

    def test_without_a_runtime_credentials_are_refused_before_disclosure(self):
        client = self.client(self.fixture.app())
        response = client.get(BASE + '/facets')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(set(response.json()), {'error', 'detail'})

    def test_without_a_runtime_a_valid_principal_gets_unavailable(self):
        client = self.client(self.fixture.app())
        response = client.get(BASE + '/facets', headers=self.auth)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], 'discovery_unavailable')

    # --- the loaded artifact actually serves --------------------------------

    def test_loaded_artifact_serves_facets_and_search_for_a_member(self):
        client = self.client(self.fixture.app(discovery_runtime=self.fixture.runtime()))
        facets = client.get(BASE + '/facets', headers=self.auth)
        self.assertEqual(facets.status_code, 200, facets.text)
        self.assertEqual(facets.json()['version'], 1)
        self.assertEqual(facets.json()['pinned_person_ids'], ['302', '301'])
        search = client.post(BASE + '/search', headers=self.auth,
                             json={'binding': facets.json()['binding'], 'filters': {},
                                   'page': 1, 'page_size': 50, 'fingerprint': None})
        self.assertEqual(search.status_code, 200, search.text)
        self.assertEqual([x['id'] for x in search.json()['items']],
                         [str(2 ** 63 - 1), '103', '102', '101'])
        self.assertNotIn('not-a-real-path', search.text)

    def test_a_non_member_of_the_library_is_denied(self):
        client = self.client(self.fixture.app(discovery_runtime=self.fixture.runtime()))
        response = client.get(BASE + '/facets', headers={'Authorization': 'Bearer ' + OTHER})
        self.assertEqual(response.status_code, 401)

    def test_a_well_formed_but_wrong_digest_is_caught_by_the_service(self):
        # The loader validates shape only — it has no database, so it cannot recompute
        # the digest. The binding check that matters happens in the service.
        tampered = dict(asdict(self.fixture.index))
        tampered['source_digest'] = 'b' * 64
        path = artifact(ReviewedIndex(**tampered), self.directory, 'tampered.json')
        runtime = DiscoveryRuntime(access=self.fixture.access, provider=di.load((path,)),
                                   budget=d.ReadBudget())
        client = self.client(self.fixture.app(discovery_runtime=runtime))
        response = client.get(BASE + '/facets', headers=self.auth)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'discovery_changed')

    def test_a_stale_but_valid_artifact_reports_changed_not_stale_results(self):
        runtime = self.fixture.runtime()
        client = self.client(self.fixture.app(discovery_runtime=runtime))
        self.assertEqual(client.get(BASE + '/facets', headers=self.auth).status_code, 200)
        with sqlite3.connect(self.fixture.database) as db:
            db.execute("INSERT INTO assets VALUES(777,'not-a-real-path','active','image/jpeg',8,8,NULL,NULL)")
            db.execute("INSERT INTO access_asset_libraries VALUES(777,'family-a')")
        response = client.get(BASE + '/facets', headers=self.auth)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'discovery_changed')


class DiscoveryIndexLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        with sqlite3.connect(self.directory / 'synthetic.sqlite') as db:
            create(db)
            self.index = reviewed(AccessService(db, clock=lambda: NOW))
        self.path = artifact(self.index, self.directory)

    def refuse(self, payload, name='mutated.json'):
        path = self.directory / name
        path.write_bytes(payload if isinstance(payload, bytes)
                         else json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                         separators=(',', ':')).encode())
        with self.assertRaises(di.DiscoveryIndexRefused):
            di.load((path,))

    def test_round_trip_preserves_the_reviewed_index(self):
        provider = di.load((self.path,))
        loaded = provider.get('family-a')
        self.assertEqual(asdict(loaded), asdict(self.index))
        self.assertIsNone(provider.get('family-b'))

    def test_duplicate_json_keys_are_refused(self):
        self.refuse(b'{"library_id":"family-a","library_id":"family-b"}')

    def test_nonfinite_constants_are_refused(self):
        raw = json.dumps(asdict(self.index), sort_keys=True).encode()
        self.refuse(raw.replace(b'"1"', b'NaN', 1))

    def test_an_unexpected_key_set_is_refused(self):
        broken = dict(asdict(self.index)); broken['extra'] = 1
        self.refuse(broken)

    def test_an_indexed_set_outside_the_scope_is_refused(self):
        broken = dict(asdict(self.index)); broken['scope_ids'] = ['101']
        self.refuse(broken)

    def test_a_malformed_digest_is_refused(self):
        broken = dict(asdict(self.index)); broken['source_digest'] = 'not-a-digest'
        self.refuse(broken)

    def test_an_unsupported_enabled_field_is_refused(self):
        broken = dict(asdict(self.index)); broken['enabled'] = ['media', 'themes']
        self.refuse(broken)

    def test_disabled_media_is_refused(self):
        broken = dict(asdict(self.index)); broken['enabled'] = ['date']
        self.refuse(broken)

    def test_a_relative_or_aliased_path_is_refused(self):
        aliased = self.directory / '..' / self.directory.name / 'index.json'
        for path in (Path('index.json'), aliased, str(self.path)):
            with self.assertRaises(di.DiscoveryIndexRefused):
                di.load((path,))

    def test_an_empty_or_non_tuple_path_set_is_refused(self):
        for paths in (tuple(), [self.path], (self.path, 'x')):
            with self.assertRaises(di.DiscoveryIndexRefused):
                di.load(paths)

    def test_an_oversized_artifact_is_refused(self):
        path = self.directory / 'huge.json'
        path.write_bytes(b'{' + b' ' * (4 * 1024 ** 2 + 1) + b'}')
        with self.assertRaises(di.DiscoveryIndexRefused):
            di.load((path,))

    def test_a_missing_artifact_is_refused(self):
        with self.assertRaises(di.DiscoveryIndexRefused):
            di.load((self.directory / 'absent.json',))

    def test_a_shared_budget_is_reused_across_artifacts(self):
        budget = d.ReadBudget()
        provider = di.load((self.path,), budget=budget)
        self.assertIsNotNone(provider.get('family-a'))
        with self.assertRaises(di.DiscoveryIndexRefused):
            di.load((self.path,), budget=object())


if __name__ == '__main__':
    unittest.main()
