"""Internal protected service, real policy and synthetic SQLite; no transport freeze."""
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider,ReviewedPerson,ReviewedPlace,ReviewedFace
from app.access.service import AccessService,AccessDenied
from phone_discovery_fixture import create,reviewed,TOKEN,SECOND,OTHER,RELOGIN,NOW,MAXIMUM


class PhoneDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.db=create(sqlite3.connect(':memory:'));self.addCleanup(self.db.close)
        self.access=AccessService(self.db,clock=lambda:NOW)
        self.index=reviewed(self.access);self.budget=d.ReadBudget();self.install()
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system','builtins.open','os.open'):
            guard=patch(target,side_effect=AssertionError('External access forbidden'));guard.start();self.addCleanup(guard.stop)

    def install(self,index=None,budget=None):
        if index is not None:self.index=index
        self.provider=MemoryIndexProvider((self.index,))
        self.service=d.DiscoveryReads(self.access,self.provider,budget or self.budget)

    def update(self,sql,args=()):self.db.execute(sql,args);self.db.commit()
    def facets(self,**kwargs):return self.service.facets(TOKEN,'family-a',**kwargs)
    def search(self,filters=None,**kwargs):
        binding=kwargs.pop('binding',None) or self.facets()['binding']
        return self.service.search(TOKEN,'family-a',binding=binding,filters={} if filters is None else filters,**kwargs)
    def result_ids(self,filters):return [r['id'] for r in self.search(filters)['items']]

    def test_count_scope_pins_aliases_and_native_asset_shape(self):
        result=self.facets(page_size=1)
        self.assertEqual(result['pinned_person_ids'],['302','301']);self.assertEqual([r['id'] for r in result['pinned_people']],['302','301'])
        self.assertEqual(result['items'][0]['id'],'301');self.assertEqual(result['catalog_assets'],4)
        self.assertEqual(result['coverage']['people'],{'with_values':2,'without_values':2})
        self.assertEqual(result['metadata_completeness'],'not_inferred')
        assets=self.search();self.assertFalse(assets['originals_allowed'])
        self.assertEqual([r['id'] for r in assets['items']],[str(MAXIMUM),'103','102','101'])
        self.assertEqual([r['kind'] for r in assets['items']],['other','image','video','image'])
        self.assertEqual(assets['items'][-1]['thumbnail_url'],'/assets/101/thumbnail?library=family-a')
        for forbidden in ('Foreign','not-a-real-path','/home/','phone_login','password','embedding','gps'):
            self.assertNotIn(forbidden,d.packed((result,assets)).decode())
        with self.assertRaises(AccessDenied):self.access.require(TOKEN,'family-a','media.original.read')

    def test_missing_and_all_invalid_access_denied_before_provider_and_source(self):
        trace=[];self.db.set_trace_callback(trace.append)
        with patch.object(self.provider,'get',side_effect=AssertionError('Metadata read before policy')):
            for token,library in [(None,'family-a'),('bad','family-a'),(TOKEN,'family-b'),(TOKEN,'unknown'),(OTHER,'family-a'),(TOKEN,{}),(TOKEN,'x'*129)]:
                with self.assertRaises(AccessDenied):self.service.facets(token,library)
        self.assertFalse(any('SELECT a.id' in sql or 'FROM captions' in sql for sql in trace))

    def test_expiry_disabled_and_membership_states_precede_index_access(self):
        changes=[("UPDATE access_accounts SET state='disabled' WHERE id='one'", "UPDATE access_accounts SET state='active' WHERE id='one'"),
          ("UPDATE access_sessions SET revoked=1 WHERE account_id='one'", "UPDATE access_sessions SET revoked=0 WHERE account_id='one'"),
          ("UPDATE access_sessions SET expires_at=0 WHERE account_id='one'", f"UPDATE access_sessions SET expires_at={NOW+3600} WHERE account_id='one'"),
          ("UPDATE access_libraries SET state='closed' WHERE id='family-a'", "UPDATE access_libraries SET state='active' WHERE id='family-a'"),
          ("UPDATE access_memberships SET expires_at=0 WHERE account_id='one'", "UPDATE access_memberships SET expires_at=NULL WHERE account_id='one'")]
        changes += [(f"UPDATE access_memberships SET status='{s}' WHERE account_id='one'", "UPDATE access_memberships SET status='approved' WHERE account_id='one'") for s in ('requested','rejected','revoked')]
        for change,undo in changes:
            self.update(change)
            with patch.object(self.provider,'get',side_effect=AssertionError('No index read')):
                with self.assertRaises(AccessDenied):self.facets(binding='0'*64)
            self.update(undo)

    def test_source_mutations_reject_entire_snapshot_and_counts(self):
        changes=["UPDATE assets SET status='hidden' WHERE id=101", "UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101",
                 "UPDATE captions SET text='changed' WHERE id=1", "UPDATE face_detections SET person_id=302 WHERE id=1",
                 "INSERT INTO asset_tag_blocks VALUES(2,103,501)", "UPDATE tags SET name='changed' WHERE id=501",
                 "UPDATE assets SET taken_at='2025-01-01' WHERE id=101"]
        for sql in changes:
            self.db.execute('SAVEPOINT fixture')
            self.db.execute(sql);self.db.execute('RELEASE fixture')
            with self.assertRaises(d.DiscoveryChanged):self.facets()
            # Restore exact synthetic input without approving the changed record.
            original=create(sqlite3.connect(':memory:'));original.backup(self.db);original.close()
        self.update("UPDATE assets SET status='active' WHERE id=999")
        with self.assertRaises(d.DiscoveryChanged):self.facets()

    def test_binding_is_specific_to_account_session_membership_and_index(self):
        old=self.facets()['binding']
        for token in (SECOND,RELOGIN):
            with self.assertRaises(d.DiscoveryChanged):self.service.search(token,'family-a',binding=old,filters={})
        self.update("UPDATE access_memberships SET revision=revision+1 WHERE account_id='one'")
        with self.assertRaises(d.DiscoveryChanged):self.search(binding=old)
        current=self.facets()['binding'];self.install(replace(self.index,revision='2'))
        with self.assertRaises(d.DiscoveryChanged):self.search(binding=current)

    def test_reviewed_roster_and_assignment_are_separate_and_dnn_is_not_identity(self):
        self.assertEqual(self.result_ids({'caption':'sample child'}),[str(MAXIMUM)])
        self.assertEqual(self.result_ids({'caption':'sample child','people':{'ids':['301'],'match':'any'}}),[])
        self.install(replace(self.index,assignments=()))
        with self.assertRaises(d.DiscoveryUnavailable):self.facets()
        self.install(replace(self.index,people=tuple(replace(p,allow_zero=True) for p in self.index.people)))
        self.assertEqual(self.facets()['pinned_people'][0]['asset_count'],0)
        self.assertEqual(self.result_ids({'people':{'ids':['301'],'match':'any'}}),[])
        self.install(replace(self.index,assignments=(ReviewedFace('4',str(MAXIMUM),'301','dnn'),)))
        with self.assertRaises(d.DiscoveryUnavailable):self.facets()

    def test_foreign_roster_places_evidence_and_forged_provider_rejected(self):
        original=self.index
        for changed in (replace(original,library_id='family-b'),replace(original,people=(ReviewedPerson('family-b','401','Foreign secret'),)),
                        replace(original,places=(ReviewedPlace('family-b','601','Foreign secret'),)),
                        replace(original,assignments=(ReviewedFace('5','101','301'),)),replace(original,source_digest='0'*64)):
            with patch.object(self.provider,'get',return_value=changed):
                with self.assertRaises((d.DiscoveryUnavailable,d.DiscoveryChanged)):self.facets()
        for filters in ({'people':{'ids':['401'],'match':'any'}},{'tags':{'ids':['504'],'match':'any'}},{'locations':['999']}):
            with self.assertRaises(d.DiscoveryInvalid):self.search(filters)

    def test_all_six_filters_any_all_and_cross_category_and(self):
        self.assertEqual(self.result_ids({'people':{'ids':['301','302'],'match':'any'}}),['103','101'])
        self.assertEqual(self.result_ids({'people':{'ids':['301','302'],'match':'all'}}),['103'])
        filters={'people':{'ids':['301','302'],'match':'all'},'tags':{'ids':['501','502'],'match':'all'},'locations':['601'],
                 'media':['image'],'date':{'from':'2025-12-01','to':'2025-12-01'},'caption':'family'}
        self.assertEqual(self.result_ids(filters),['103'])
        filters['media']=['video'];self.assertEqual(self.result_ids(filters),[])

    def test_unicode_literal_inclusive_dates_and_missing_not_negative(self):
        self.assertEqual(self.result_ids({'caption':' ＦＡＭＩＬＹ '}),['103'])
        self.assertEqual(self.result_ids({'caption':'park home'}),[])
        self.assertEqual(self.result_ids({'caption':"%' OR 1=1 --"}),[])
        self.assertEqual(self.result_ids({'date':{'from':'2026-01-02','to':'2026-01-02'}}),['101'])
        self.assertEqual(self.result_ids({'date':{'from':None,'to':'2026-01-02'},'media':['video']}),[])
        self.assertEqual(self.result_ids({'media':['video']}),['102'])

    def test_caption_ambiguity_supersession_edit_priority_and_oversize(self):
        self.update("INSERT INTO captions VALUES(8,103,'second variant',0,0)")
        self.install(reviewed(self.access));self.assertEqual(self.result_ids({'caption':'family'}),[])
        self.update('UPDATE captions SET user_edited=1 WHERE id=2');self.install(reviewed(self.access))
        self.assertEqual(self.result_ids({'caption':'family'}),['103'])
        self.update('UPDATE captions SET superseded=1 WHERE id=2');self.install(reviewed(self.access))
        self.assertEqual(self.result_ids({'caption':'family'}),[])
        self.update('UPDATE captions SET text=? WHERE id=8',('字'*1400,));self.install(reviewed(self.access))
        self.assertEqual(self.result_ids({'caption':'字'}),[])

    def test_overlong_and_invalid_dates_never_become_valid_prefixes(self):
        valid='2026-01-02T12:30:00.123456+08:00'
        self.update('UPDATE assets SET taken_at=? WHERE id=101',(valid,));self.install(reviewed(self.access))
        self.assertEqual(next(a for a in self.search()['items'] if a['id']=='101')['taken_at'],valid)
        for invalid in ('2026-01-02T12:30:00.'+'1'*100,'2026-01-02\x00private-tail','2026-02-30'):
            self.update('UPDATE assets SET taken_at=? WHERE id=101',(invalid,));self.install(reviewed(self.access))
            self.assertIsNone(next(a for a in self.search()['items'] if a['id']=='101')['taken_at'])
            self.assertEqual(self.result_ids({'date':{'from':'2026-01-02','to':'2026-01-02'}}),[])

    def test_embedded_nul_captions_and_tag_names_do_not_hide_invalid_suffixes(self):
        self.update('UPDATE captions SET text=? WHERE id=2',('Family\x00hidden suffix',))
        self.update('UPDATE tags SET name=? WHERE id=501',('Park\x00hidden suffix',))
        self.install(reviewed(self.access))
        self.assertEqual(self.result_ids({'caption':'family'}),[])
        self.assertEqual([t['id'] for t in self.facets(facet='tags')['items']],['502'])
        self.assertNotIn('hidden suffix',d.packed(self.search()).decode())
        self.update('UPDATE captions SET text=? WHERE id=2',('Family\x00changed suffix',))
        with self.assertRaises(d.DiscoveryChanged):self.facets()

    def test_oversized_candidate_is_not_truncated_or_dropped_to_choose_fallback(self):
        self.update('UPDATE captions SET text=? WHERE id=2',(' '*9000+'private tail',))
        self.update("INSERT INTO captions VALUES(8,103,'fallback must not win',0,0)")
        self.install(reviewed(self.access));self.assertEqual(self.result_ids({'caption':'fallback'}),[])

    def test_block_duplicate_unknown_and_person_tags_keep_provenance(self):
        tags=self.facets(facet='tags')['items'];self.assertEqual([t['id'] for t in tags],['501','502'])
        self.assertEqual(tags[0]['provenance_counts'],{'caption':2})
        self.update("INSERT INTO asset_tags VALUES(7,102,501,'img')")
        self.update("INSERT INTO asset_tags VALUES(8,102,501,'manual')")
        self.update("INSERT INTO asset_tags VALUES(9,102,502,NULL)")
        self.update("UPDATE tags SET type='person' WHERE id=502")
        self.install(reviewed(self.access));tags=self.facets(facet='tags')['items']
        self.assertEqual(tags[1]['kind'],'person');self.assertEqual(tags[1]['provenance_counts']['unknown'],1)
        self.assertEqual(self.result_ids({'tags':{'ids':['501'],'match':'any'},'media':['video']}),[])
        self.assertEqual(self.result_ids({'people':{'ids':['301'],'match':'any'},'media':['video']}),[])

    def test_zero_partial_and_disabled_metadata_keep_full_scoped_browse(self):
        for selected in ((),('102',),self.index.scope_ids):
            self.install(replace(self.index,indexed_ids=selected,assignments=(),regions=(),people=tuple(replace(p,allow_zero=True) for p in self.index.people)))
            result=self.facets();self.assertEqual(result['indexed_assets'],len(selected));self.assertEqual(self.search()['total'],4)
        self.install(replace(self.index,enabled=('media',)))
        result=self.facets();self.assertEqual(result['items'],[]);self.assertEqual(result['pinned_people'],[])
        self.assertEqual(result['coverage']['caption']['with_values'],0)
        with self.assertRaises(d.DiscoveryInvalid):self.search({'caption':'family'})

    def test_paging_binding_and_fingerprint_prevent_mixed_results(self):
        binding=self.facets()['binding'];first=self.search(binding=binding,page_size=2)
        second=self.search(binding=binding,page_size=2,page=2,fingerprint=first['fingerprint'])
        self.assertEqual([x['id'] for x in second['items']],['102','101']);self.assertFalse(second['has_more'])
        with self.assertRaises(d.DiscoveryInvalid):self.search(binding=binding,page=2)
        with self.assertRaises(d.DiscoveryChanged):self.search({'media':['image']},binding=binding,page=2,page_size=2,fingerprint=first['fingerprint'])
        with self.assertRaises(d.DiscoveryChanged):self.search(binding=binding,page=2,page_size=1,fingerprint=first['fingerprint'])
        self.assertEqual(self.facets(binding=binding,page=2,page_size=1)['items'][0]['id'],'302')
        with self.assertRaises(d.DiscoveryInvalid):self.facets(page=2)

    def test_bad_types_ids_dates_and_limits_fail_no_silent_filter_drop(self):
        bad=[{'themes':[]},{'people':{'ids':['01'],'match':'any'}},{'people':{'ids':[301],'match':'any'}},
             {'people':{'ids':[True],'match':'any'}},{'tags':{'ids':['501','501'],'match':'all'}},
             {'people':{'ids':[str(MAXIMUM+1)],'match':'any'}},{'media':[]},{'media':['image','image']},
             {'date':{'from':'2026-02-30','to':None}},{'date':{'from':None,'to':None}},
             {'date':{'from':'2026-02-01','to':'2025-01-01'}},{'caption':'字'*171},{'caption':'\ud800'}]
        for filters in bad:
            with self.subTest(filters=filters),self.assertRaises(d.DiscoveryInvalid):self.search(filters)
        for args in ({'page':True},{'page':0},{'page_size':101},{'binding':'not-a-binding'}):
            with self.assertRaises(d.DiscoveryInvalid):self.search(**args)

    def test_maximum_string_ids_and_identifier_validation(self):
        self.assertEqual(d.identifier(str(MAXIMUM)),str(MAXIMUM))
        for value in (MAXIMUM,True,'0','-1','1.0','01',str(MAXIMUM+1)):
            with self.assertRaises(d.DiscoveryInvalid):d.identifier(value)
        self.assertEqual(self.search()['items'][0]['id'],str(MAXIMUM))

    def test_large_person_tag_place_ids_are_lossless(self):
        self.update('UPDATE face_detections SET person_id=? WHERE person_id=301',(MAXIMUM,))
        self.update('UPDATE tags SET id=? WHERE id=501',(MAXIMUM,))
        self.update('UPDATE asset_tags SET tag_id=? WHERE tag_id=501',(MAXIMUM,))
        index=reviewed(self.access)
        index=replace(index,people=tuple(replace(p,id=str(MAXIMUM)) if p.id=='301' else p for p in index.people),
                      pinned_ids=('302',str(MAXIMUM)),assignments=tuple(replace(a,person_id=str(MAXIMUM)) if a.person_id=='301' else a for a in index.assignments),
                      places=(ReviewedPlace('family-a',str(MAXIMUM),'Synthetic large region'),),regions=(('103',str(MAXIMUM)),))
        self.install(index)
        self.assertEqual(self.result_ids({'people':{'ids':[str(MAXIMUM)],'match':'all'},'tags':{'ids':[str(MAXIMUM)],'match':'all'},'locations':[str(MAXIMUM)]}),['103'])

    def test_unavailable_provider_and_missing_region_capability(self):
        with patch.object(self.provider,'get',return_value=None):
            with self.assertRaises(d.DiscoveryUnavailable):self.facets()
        self.install(replace(self.index,places=(),regions=(),enabled=tuple(f for f in d.FIELDS if f!='locations')))
        self.assertEqual(self.facets(facet='locations')['items'],[])
        with self.assertRaises(d.DiscoveryInvalid):self.search({'locations':['601']})
        self.assertEqual(self.facets()['captured_date_bounds'],{'from':'2025-12-01','to':'2026-05-05'})

    def test_denial_after_admitted_request_never_uses_old_binding_as_grant(self):
        old=self.facets()['binding'];self.access.logout(TOKEN)
        with patch.object(self.provider,'get',side_effect=AssertionError('No provider after logout')):
            with self.assertRaises(AccessDenied):self.search(binding=old)

    def test_budget_rows_bytes_response_time_cancel_and_shared_slots(self):
        for args in ({'rows':2},{'source_bytes':8},{'index_bytes':8},{'response_bytes':8}):
            self.install(budget=d.ReadBudget(**args))
            with self.assertRaises(d.DiscoveryUnavailable):self.facets()
            self.assertFalse(self.db.in_transaction)
        self.install(budget=d.ReadBudget(clock=iter([0,3,3]).__next__))
        with self.assertRaises(d.DiscoveryUnavailable):self.facets()
        budget=d.ReadBudget(concurrency=1);self.install(budget=budget)
        with budget.attempt(self.db,lambda:False):
            with self.assertRaises(d.DiscoveryBusy):self.facets()
        with self.assertRaises(d.DiscoveryCancelled):self.facets(cancelled=lambda:True)
        self.assertFalse(self.db.in_transaction);self.assertEqual(self.facets()['catalog_assets'],4)

    def test_cancel_during_work_rolls_back_and_does_not_return_partial_results(self):
        calls=0
        def cancelled():
            nonlocal calls
            calls+=1;return calls>12
        with self.assertRaises(d.DiscoveryCancelled):self.facets(cancelled=cancelled)
        self.assertFalse(self.db.in_transaction);self.assertEqual(self.facets()['catalog_assets'],4)

    def test_queries_have_no_sql_writes_and_provider_is_immutable(self):
        before=self.db.serialize();trace=[];self.db.set_trace_callback(trace.append)
        self.search();self.facets(facet='tags')
        self.db.set_trace_callback(None)
        self.assertEqual(self.db.serialize(),before)
        self.assertTrue(all(s.startswith(('SELECT','BEGIN','COMMIT')) for s in trace),trace)
        with self.assertRaises(Exception):self.index.library_id='family-b'
        with self.assertRaises(TypeError):self.provider._indexes['family-a']=self.index


class TransactionSnapshotTests(unittest.TestCase):
    def test_wal_change_after_authorization_may_finish_but_next_request_refuses(self):
        cases=[("UPDATE access_memberships SET status='revoked' WHERE account_id='one'",AccessDenied),
               ("UPDATE assets SET status='hidden' WHERE id=101",d.DiscoveryChanged),
               ("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101",d.DiscoveryChanged)]
        for change,error in cases:
            with self.subTest(change=change),tempfile.TemporaryDirectory(prefix='phone-discovery-wal-') as temporary:
                path=Path(temporary)/'synthetic.sqlite';reader=create(sqlite3.connect(path));writer=sqlite3.connect(path)
                try:
                    reader.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA foreign_keys=ON')
                    access=AccessService(reader,clock=lambda:NOW);index=reviewed(access)
                    provider=MemoryIndexProvider((index,));service=d.DiscoveryReads(access,provider,d.ReadBudget())
                    def interleave(library):
                        writer.execute(change);writer.commit();return index
                    with patch.object(provider,'get',side_effect=interleave):
                        admitted=service.facets(TOKEN,'family-a')
                    self.assertEqual(admitted['catalog_assets'],4)
                    with self.assertRaises(error):service.facets(TOKEN,'family-a',binding=admitted['binding'])
                    self.assertFalse(reader.in_transaction)
                finally:reader.close();writer.close()


if __name__=='__main__':unittest.main()
