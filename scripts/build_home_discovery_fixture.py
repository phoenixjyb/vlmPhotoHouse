#!/usr/bin/env python3
"""Create synthetic discovery and v2 media together, never a real index or listener."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from build_home_catalog_fixture import build
from app.home_catalog import validate_catalog
from app.home_discovery import validate_index


def create(output):
    build(output)
    catalog=json.loads((output/'catalog.json').read_text())
    missing={'state':'unavailable','reason':'not_prepared'}
    catalog['assets'][:0]=[{'id':i,'kind':kind,'label':'Synthetic '+kind,'width':None,'height':None,
                          'previews':{'grid':dict(missing),'display':dict(missing)},'video':dict(missing) if kind=='video' else None}
                         for i,kind in ((104,'video'),(103,'photo'))]
    validate_catalog(catalog);raw=json.dumps(catalog).encode();(output/'catalog.json').write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest()
    (output/'control.json').write_text(json.dumps({'version':2,'enabled':True,'revision':1,'catalog_sha256':digest}))
    def row(aid,people,when,locations,tags,caption):
        return {'id':aid,'person_ids':people,'people_provenance':'reviewed_assignments' if people else None,
                'taken_day':when,'location_ids':locations,'location_provenance':'reviewed_region' if locations else None,
                'tags':[{'id':tid,'source':source} for tid,source in tags],'caption_text':caption}
    index={'version':1,'revision':7,'catalog_revision':1,'catalog_sha256':digest,
           'enabled_filters':['people','date','locations','media','tags','caption'],
           'people':[{'id':201,'label':'Sample Adult / 示例成人','aliases':['Sample Adult','示例成人']},
                     {'id':202,'label':'Sample Child / 示例儿童','aliases':['Sample Child','示例儿童']}],
           'pinned_person_ids':[202,201],
           'tags':[{'id':301,'label':'Park / 公园','kind':'scene'},{'id':302,'label':'Favorite / 收藏','kind':'custom'}],
           'locations':[{'id':401,'label':'Example Region / 示例地区'}],
           'assets':[row(104,[201],'2026-05-05',[401],[(301,'caption')],'A caption mentions Sample Child at the park.'),
                     row(103,[201,202],'2025-12-01',[401],[(301,'caption'),(302,'manual')],'Ｆａｍｉｌｙ at park.'),
                     row(102,[],None,[],[],None),
                     row(101,[202],'2026-01-02',[401],[(302,'manual')],'Portrait at home.')]}
    validate_index(index,catalog,digest)
    raw=json.dumps(index,ensure_ascii=False).encode();(output/'discovery.json').write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps({'discovery_sha256':create(args.output),'synthetic_only':True,'listener_started':False}))
