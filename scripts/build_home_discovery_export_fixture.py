#!/usr/bin/env python3
"""Build synthetic SQLite + candidate + request. Never approve a real review."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_home_discovery_fixture import create as discovery_fixture
from export_home_discovery import packed, sha, review


def create(root):
    if not root.is_absolute() or root.exists(): raise ValueError('New absolute fixture directory required')
    root.mkdir(mode=0o700)
    candidate=root/'candidate'; discovery_fixture(candidate)
    control=json.loads((candidate/'control.json').read_text());control['enabled']=False
    (candidate/'control.json').write_bytes(packed(control))
    db=root/'snapshot.sqlite'
    with sqlite3.connect(db) as conn:
        conn.executescript('''
CREATE TABLE assets(id INTEGER PRIMARY KEY,status TEXT,taken_at TEXT);
CREATE TABLE captions(id INTEGER PRIMARY KEY,asset_id INTEGER,text TEXT,user_edited INTEGER,superseded INTEGER);
CREATE TABLE persons(id INTEGER PRIMARY KEY);
CREATE TABLE face_detections(id INTEGER PRIMARY KEY,asset_id INTEGER,person_id INTEGER,label_source TEXT);
CREATE TABLE tags(id INTEGER PRIMARY KEY,name TEXT,type TEXT);
CREATE TABLE asset_tags(id INTEGER PRIMARY KEY,asset_id INTEGER,tag_id INTEGER,source TEXT);
CREATE TABLE asset_tag_blocks(id INTEGER PRIMARY KEY,asset_id INTEGER,tag_id INTEGER);
INSERT INTO assets VALUES(101,'active','2026-01-02'),(102,NULL,NULL),(103,'active','2025-12-01T12:30:00'),(104,'active','2026-05-05'),(999,'hidden','2026-01-01');
INSERT INTO captions VALUES(1,101,'Portrait at home.',0,0),(2,103,'Ｆａｍｉｌｙ at park.',1,0),(3,103,'Old caption.',0,1),(4,104,'A caption mentions Sample Child at the park.',0,0);
INSERT INTO persons VALUES(201),(202);
INSERT INTO face_detections VALUES(1,101,202,'manual'),(2,103,201,'manual'),(3,103,202,'manual'),(4,104,201,'dnn');
INSERT INTO tags VALUES(301,'Park / 公园','scene'),(302,'Favorite / 收藏','custom'),(303,'Blocked / 已屏蔽','scene');
INSERT INTO asset_tags VALUES(1,101,302,'manual'),(2,103,301,'cap'),(3,103,302,'manual'),(4,104,301,'cap'),(5,101,303,'img');
INSERT INTO asset_tag_blocks VALUES(1,101,303);
''')
    index=json.loads((candidate/'discovery.json').read_text())
    request={'version':1,'catalog_sha256':sha((candidate/'catalog.json').read_bytes()),
             'selected_asset_ids':[101,102,103,104],'indexed_asset_ids':[101,102,103,104],
             'discovery_revision':7,'copy_prepared':True,
             'roster_review':{'people':index['people'],'pinned_person_ids':[202,201],'unresolved_shortcut_count':0},
             'assignment_review':[{'face_id':fid,'asset_id':aid,'person_id':pid,'label_source':'manual'} for fid,aid,pid in [(1,101,202),(2,103,201),(3,103,202)]],
             'region_review':{'locations':index['locations'],'assignments':[{'asset_id':aid,'location_id':401} for aid in (101,103,104)]}}
    (root/'request.json').write_bytes(packed(request))
    return root



if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=create(args.output)
    receipt=review(root/'snapshot.sqlite',root/'candidate',root/'request.json',root/'review.json')
    # Only this freshly created synthetic fixture receives a generated approval.
    approval={'version':1,'plan_sha256':receipt['plan_sha256'],**{k:True for k in ('approve_selection','approve_roster','approve_assignments','approve_regions','approve_metadata')}}
    (root/'synthetic-approval.json').write_bytes(packed(approval))
    print(json.dumps({'synthetic_only':True,'plan_sha256':receipt['plan_sha256']}))
