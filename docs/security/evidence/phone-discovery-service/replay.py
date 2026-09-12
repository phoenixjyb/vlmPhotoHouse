#!/usr/bin/env python3
"""Internal-service replay; no endpoint, public wire fixture or live input."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-root',type=Path,required=True)
args=parser.parse_args();root=args.source_root.resolve(strict=True)
sys.path[:0]=[str(root/'backend'),str(root/'tests/security')]
from app.access.discovery import DiscoveryReads,ReadBudget,DiscoveryChanged,DiscoveryInvalid,digest
from app.access.discovery_provider import MemoryIndexProvider
from app.access.service import AccessService,AccessDenied
from phone_discovery_fixture import create,reviewed,TOKEN,OTHER,NOW,MAXIMUM

checks=[]
db=create(sqlite3.connect(':memory:'));access=AccessService(db,clock=lambda:NOW);index=reviewed(access)
provider=MemoryIndexProvider((index,));service=DiscoveryReads(access,provider,ReadBudget())
try:
    with ExitStack() as stack:
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system','builtins.open','os.open'):
            stack.enter_context(patch(target,side_effect=AssertionError('No external IO')))
        before=db.serialize()
        with patch.object(provider,'get',side_effect=AssertionError('Index accessed before authorization')):
            try: service.facets(OTHER,'family-a')
            except AccessDenied: pass
            else: raise AssertionError('Foreign owner admitted')
        checks.append('foreign_owner_denied_before_provider')
        facets=service.facets(TOKEN,'family-a',page_size=1);binding=facets['binding']
        assert facets['pinned_person_ids']==['302','301'] and facets['catalog_assets']==4
        checks.append('scoped_counts_and_ordered_reviewed_shortcuts')
        def search(filters,**args):return service.search(TOKEN,'family-a',binding=binding,filters=filters,**args)
        filters={'people':{'ids':['301','302'],'match':'all'},'tags':{'ids':['501','502'],'match':'all'},'locations':['601'],
                 'caption':'family','date':{'from':'2025-12-01','to':'2025-12-01'},'media':['image']}
        combined=search(filters);assert [r['id'] for r in combined['items']]==['103']
        checks.append('six_filter_combination')
        assert search({'caption':'Sample Child','people':{'ids':['301'],'match':'any'}})['items']==[]
        checks.append('caption_and_dnn_are_not_person_approval')
        all_rows=search({});assert all_rows['items'][0]['id']==str(MAXIMUM)
        assert all_rows['items'][0]['kind']=='other'
        checks.append('lossless_native_64_bit_asset_and_kind')
        first=search({},page_size=2)
        second=search({},page=2,page_size=2,fingerprint=first['fingerprint'])
        assert [a['id'] for a in second['items']]==['102','101']
        checks.append('stable_bound_pagination')
        try:search({},page=2,page_size=1,fingerprint=first['fingerprint'])
        except DiscoveryChanged:pass
        else:raise AssertionError('Mixed page size accepted')
        checks.append('mixed_page_size_refused')
        try:access.require(TOKEN,'family-a','media.original.read')
        except AccessDenied:pass
        else:raise AssertionError('Original access granted')
        assert not all_rows['originals_allowed']
        checks.append('no_original_grant')
        assert db.serialize()==before
        checks.append('service_queries_do_not_change_database')
        # Explicit synthetic test mutation, not a discovery service write.
        access.logout(TOKEN)
        with patch.object(provider,'get',side_effect=AssertionError('Index after revocation')):
            try:search({})
            except AccessDenied:pass
            else:raise AssertionError('Revoked session admitted')
        checks.append('next_request_revocation')
        receipt={'status':'PASS_INTERNAL_SERVICE_ONLY','checks':checks,'check_count':len(checks),
                 'internal_facets_sha256':digest(facets),'internal_combined_result_sha256':digest(combined),
                 'coverage':facets['coverage'],'catalog_assets':facets['catalog_assets'],'indexed_assets':facets['indexed_assets'],
                 'wire_contract_frozen':False,'endpoint_mounted':False,'real_data_accessed':False,'listener_started':False}
    print(json.dumps(receipt,sort_keys=True,indent=2))
finally:db.close()
