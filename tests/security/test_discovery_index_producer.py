"""Offline producer for the reviewed discovery index; synthetic SQLite only.

The load-bearing property is parity: the artifact this tool emits must be the one
the protected discovery service computes for itself, so the producer reads
through the service's own scoped_source, digest and read budget.
"""
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import asdict
import hashlib
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests' / 'security')]

from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider, ReviewedFace, ReviewedIndex, ReviewedPerson, ReviewedPlace
from app.access.service import AccessService, AccessDenied
from phone_discovery_fixture import create, reviewed, TOKEN, OTHER, NOW
import prepare_access_discovery_index as producer


class ProducerTests(unittest.TestCase):
    def test_schema_or_configuration_refusal_closes_database_handle(self):
        empty = self.tmp / 'empty.sqlite'
        sqlite3.connect(empty).close()
        connect = sqlite3.connect
        opened = []
        def tracking(*args, **kwargs):
            db = connect(*args, **kwargs)
            opened.append(db)
            return db
        with patch.object(producer.sqlite3, 'connect', side_effect=tracking):
            with self.assertRaises(producer.Refused):
                producer.open_read_only(empty, time.monotonic())
            with patch.object(producer, 'configure', side_effect=RuntimeError('synthetic configuration error')):
                with self.assertRaises(RuntimeError):
                    producer.open_read_only(self.database, time.monotonic())
        self.assertEqual(len(opened), 2)
        for db in opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute('SELECT 1')

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.database = self.tmp / 'access.sqlite3'
        connection = create(sqlite3.connect(str(self.database)))
        connection.commit()
        connection.close()
        self.count = 0

    # helpers ---------------------------------------------------------------
    def produce(self, library='family-a', revision='1', out=None, database=None):
        self.count += 1
        target = out or (self.tmp / f'index{self.count}.json')
        captured = io.StringIO()
        with redirect_stderr(io.StringIO()), redirect_stdout(captured):
            code = producer.main(['--database', str(database or self.database), '--library', library,
                                  '--revision', revision, '--out', str(target)] +
                                 (['--review', str(self.review_path)] if hasattr(self, 'review_path') else []))
        return code, target, json.loads(captured.getvalue() or '{}')

    def write_review(self, *, enabled=None, source_fields=None, library='family-a', digest=None):
        value = asdict(reviewed(self.access_service(), library=library))
        value['library_id'] = library
        value.pop('revision', None)
        value.pop('scope_ids', None)
        for item in value['people'] + value['places']:
            item.pop('library_id', None)
        value['source_digest'] = digest or value['source_digest']
        value['enabled'] = enabled or ['people', 'date', 'caption', 'tags', 'locations', 'media']
        value['source_fields'] = source_fields if source_fields is not None else {'caption': 'current_source', 'tags': 'current_source'}
        self.review_path = self.tmp / 'review.json'
        self.review_path.write_text(json.dumps(value, sort_keys=True), encoding='utf-8')
        return self.review_path

    def artifact(self, out):
        raw = json.loads(out.read_bytes())
        value = dict(raw)
        value['people'] = tuple(ReviewedPerson(item['library_id'], item['id'], item['label'], tuple(item['aliases']), item['allow_zero']) for item in value['people'])
        value['assignments'] = tuple(ReviewedFace(**item) for item in value['assignments'])
        value['places'] = tuple(ReviewedPlace(**item) for item in value['places'])
        value['regions'] = tuple(tuple(item) for item in value['regions'])
        for key in ('scope_ids', 'indexed_ids', 'pinned_ids', 'enabled'):
            value[key] = tuple(value[key])
        return raw, ReviewedIndex(**value)

    def access_service(self):
        connection = sqlite3.connect(str(self.database))
        self.addCleanup(connection.close)
        connection.execute('PRAGMA foreign_keys=ON')
        return AccessService(connection, clock=lambda: NOW)

    def service(self, *indexes):
        return d.DiscoveryReads(self.access_service(), MemoryIndexProvider(indexes), d.ReadBudget())

    def search(self, service, filters, token=TOKEN, library='family-a'):
        binding = service.facets(token, library)['binding']
        return service.search(token, library, binding=binding, filters=filters)

    def ids(self, result):
        return [row['id'] for row in result['items']]

    def update(self, sql, args=()):
        connection = sqlite3.connect(str(self.database))
        try:
            connection.execute(sql, args)
            connection.commit()
        finally:
            connection.close()

    def refuse(self, **kwargs):
        code, _, _ = self.produce(**kwargs)
        self.assertNotEqual(code, 0)

    # tests -----------------------------------------------------------------
    def test_produced_digest_and_scope_match_the_service_projection(self):
        code, out, receipt = self.produce()
        self.assertEqual(code, 0)
        raw, index = self.artifact(out)
        service_index = reviewed(self.access_service())
        self.assertEqual(index.source_digest, service_index.source_digest)
        self.assertEqual(index.scope_ids, service_index.scope_ids)
        self.assertEqual(raw['source_digest'], service_index.source_digest)
        self.assertEqual(receipt['completed'], True)
        self.assertEqual(receipt['existing_database_modified'], False)
        self.assertEqual(receipt['source_digest'], index.source_digest)
        self.assertEqual(receipt['catalog_assets'], len(index.scope_ids))

    def test_produced_artifact_serves_date_and_media_filters(self):
        _, out, _ = self.produce()
        _, index = self.artifact(out)
        service = self.service(index)
        facets = service.facets(TOKEN, 'family-a')
        self.assertEqual((facets['catalog_assets'], facets['indexed_assets']), (4, 4))
        self.assertEqual(facets['enabled'], ['date', 'media'])
        self.assertEqual(self.ids(self.search(service, {'date': {'from': '2026-01-02', 'to': '2026-01-02'}})), ['101'])
        self.assertEqual(self.ids(self.search(service, {'date': {'from': '2025-12-01', 'to': '2026-01-02'}})), ['103', '101'])
        self.assertEqual(self.ids(self.search(service, {'media': ['video']})), ['102'])
        self.assertEqual(self.ids(self.search(service, {'media': ['image', 'video']})), ['103', '102', '101'])
        self.assertEqual(self.ids(self.search(service, {'media': ['other']})), ['9223372036854775807'])

    def test_explicit_review_enables_people_caption_tags_and_places(self):
        self.write_review()
        _, out, _ = self.produce()
        _, index = self.artifact(out)
        self.assertEqual(index.enabled, ('people', 'date', 'caption', 'tags', 'locations', 'media'))
        service = self.service(index)
        self.assertEqual([item['id'] for item in service.facets(TOKEN, 'family-a', facet='people')['items']], ['301', '302'])
        self.assertEqual([item['id'] for item in service.facets(TOKEN, 'family-a', facet='locations')['items']], ['601'])
        result = self.search(service, {'people': {'ids': ['302'], 'match': 'any'},
                                       'tags': {'ids': ['501'], 'match': 'any'},
                                       'locations': ['601'], 'caption': 'family'})
        self.assertEqual(self.ids(result), ['103'])

    def test_review_requires_explicit_native_caption_and_tag_declarations(self):
        self.write_review(source_fields={})
        self.refuse()
        self.write_review(enabled=['date', 'caption', 'media'], source_fields={})
        self.refuse()

    def test_review_is_bound_to_current_library_projection(self):
        self.write_review()
        wrong_library = json.loads(self.review_path.read_text(encoding='utf-8'))
        wrong_library['library_id'] = 'family-b'
        self.review_path.write_text(json.dumps(wrong_library), encoding='utf-8')
        self.refuse()
        self.write_review()
        self.update("INSERT INTO assets VALUES(104,'p','active','image/jpeg',8,8,NULL,'2026-06-06')")
        self.update('INSERT INTO access_asset_libraries VALUES(104,?)', ('family-a',))
        self.refuse(revision='2')

    def test_artifact_carries_no_review_content(self):
        _, out, _ = self.produce()
        raw, index = self.artifact(out)
        for field in ('people', 'pinned_ids', 'assignments', 'places', 'regions'):
            self.assertEqual(raw[field], [], field)
            self.assertEqual(getattr(index, field), (), field)
        self.assertEqual(producer.ENABLED, ('date', 'media'))
        self.assertEqual(index.enabled, ('date', 'media'))
        facets = self.service(index).facets(TOKEN, 'family-a')
        self.assertEqual(facets['pinned_people'], [])
        self.assertEqual(self.service(index).facets(TOKEN, 'family-a', facet='people')['items'], [])

    def test_one_new_asset_invalidates_the_artifact_until_it_is_rederived(self):
        _, out, _ = self.produce()
        _, index = self.artifact(out)
        service = self.service(index)
        self.assertEqual(service.facets(TOKEN, 'family-a')['catalog_assets'], 4)
        self.update("INSERT INTO assets VALUES(104,'p','active','image/jpeg',8,8,NULL,'2026-06-06')")
        self.update('INSERT INTO access_asset_libraries VALUES(104,?)', ('family-a',))
        self.assertRaises(d.DiscoveryChanged, self.search, service, {'media': ['image']})
        code, again, _ = self.produce(revision='2')
        self.assertEqual(code, 0)
        _, reindex = self.artifact(again)
        fresh = self.service(reindex)
        self.assertEqual(fresh.facets(TOKEN, 'family-a')['catalog_assets'], 5)
        self.assertEqual(self.ids(self.search(fresh, {'date': {'from': '2026-06-06', 'to': '2026-06-06'}})), ['104'])

    def test_authorization_precedes_the_provider(self):
        _, out, _ = self.produce()
        _, index = self.artifact(out)
        service = self.service(index)
        for call in (lambda: service.facets(OTHER, 'family-a'),
                     lambda: self.search(service, {'media': ['image']}, token=OTHER)):
            with self.assertRaises(AccessDenied):
                call()

    def test_artifact_is_bound_to_its_own_library_only(self):
        _, out, _ = self.produce(library='family-b')
        _, index = self.artifact(out)
        self.assertEqual(index.library_id, 'family-b')
        service = self.service(index)
        self.assertEqual(service.facets(OTHER, 'family-b')['catalog_assets'], 1)
        # The same provider holds no index for the other library, so it is unavailable.
        self.assertRaises(d.DiscoveryUnavailable, service.facets, TOKEN, 'family-a')

    def test_database_is_unchanged_by_production(self):
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        code, out, _ = self.produce()
        self.assertEqual(code, 0)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before)
        self.assertFalse(any(self.database.with_name(self.database.name + s).exists()
                             for s in ('-wal', '-shm', '-journal')))
        self.assertTrue(out.exists())

    def test_refuses_to_overwrite_an_existing_output(self):
        code, out, _ = self.produce()
        self.assertEqual(code, 0)
        kept = out.read_bytes()
        self.refuse(out=out)
        self.assertEqual(out.read_bytes(), kept)

    def test_refuses_implicit_or_indirect_paths(self):
        self.assertRaises(producer.Refused, producer.direct, Path('relative.sqlite3'))
        self.assertRaises(producer.Refused, producer.direct, self.tmp / '..' / 'x.json')
        self.refuse(database=Path('access.sqlite3'))
        self.refuse(out=Path('index.json'))
        self.refuse(out=self.tmp / '..' / 'escape.json')

    def test_projection_cannot_write_or_call_unreviewed_functions(self):
        with closing(producer.open_read_only(self.database, time.monotonic())) as db:
            for statement in ('CREATE TABLE refuse_probe(value)', 'DELETE FROM assets',
                              'UPDATE assets SET mime=?', 'DROP TABLE tags'):
                with self.assertRaises(sqlite3.DatabaseError, msg=statement):
                    db.execute(statement, ('image/png',) if 'UPDATE' in statement else ())
            self.assertEqual(producer.authorize(sqlite3.SQLITE_SELECT, None, None), sqlite3.SQLITE_OK)
            self.assertEqual(producer.authorize(sqlite3.SQLITE_FUNCTION, None, 'length'), sqlite3.SQLITE_OK)
            self.assertEqual(producer.authorize(sqlite3.SQLITE_FUNCTION, None, 'load_extension'), sqlite3.SQLITE_DENY)
            self.assertEqual(producer.authorize(sqlite3.SQLITE_INSERT, 'assets', None), sqlite3.SQLITE_DENY)
            self.assertEqual(producer.authorize(sqlite3.SQLITE_PRAGMA, 'foreign_keys', None), sqlite3.SQLITE_DENY)

    def test_refuses_unusable_revisions_libraries_and_schema(self):
        self.assertRaises(producer.Refused, producer.revision, '0')
        self.assertRaises(producer.Refused, producer.revision, 'abc')
        self.assertRaises(producer.Refused, producer.revision, '9223372036854775808')
        self.assertRaises(producer.Refused, producer.library, '')
        self.assertRaises(producer.Refused, producer.library, 'x' * 129)
        self.refuse(revision='0')
        self.refuse(revision='abc')
        self.refuse(library='no-such-library')
        empty = self.tmp / 'empty.sqlite3'
        sqlite3.connect(str(empty)).close()
        self.refuse(database=empty)


if __name__ == '__main__':
    unittest.main()
