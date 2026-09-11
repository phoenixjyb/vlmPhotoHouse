"""Synthetic fixtures only. Never imported by runtime/provider code."""
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.access.schema import apply_schema
from app.access.credentials import session_digest
from app.access.service import AccessService
from app.access.discovery import ReadBudget, scoped_source, digest
from app.access.discovery_provider import ReviewedIndex,ReviewedPerson,ReviewedFace,ReviewedPlace

NOW=2_000_000_000
TOKEN='a'*43
SECOND='b'*43
OTHER='c'*43
RELOGIN='d'*43
MAXIMUM=2**63-1


def create(connection):
    db=connection;db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,status TEXT,mime TEXT,width INTEGER,height INTEGER,duration_sec REAL,taken_at TEXT);
CREATE TABLE captions(id INTEGER PRIMARY KEY,asset_id INTEGER,text TEXT,user_edited INTEGER,superseded INTEGER);
CREATE TABLE face_detections(id INTEGER PRIMARY KEY,asset_id INTEGER,person_id INTEGER,label_source TEXT);
CREATE TABLE tags(id INTEGER PRIMARY KEY,name TEXT,type TEXT);
CREATE TABLE asset_tags(id INTEGER PRIMARY KEY,asset_id INTEGER,tag_id INTEGER,source TEXT);
CREATE TABLE asset_tag_blocks(id INTEGER PRIMARY KEY,asset_id INTEGER,tag_id INTEGER);
''')
    apply_schema(db.execute)
    for account,phone in [('one','+12025550101'),('two','+12025550102'),('foreign','+12025550103')]:
        db.execute('INSERT INTO access_accounts VALUES(?,?,?,?)',(account,phone,'unused-synthetic-hash','active'))
    db.execute("INSERT INTO access_libraries VALUES('family-a','active','one')")
    db.execute("INSERT INTO access_libraries VALUES('family-b','active','foreign')")
    for account,library,role in [('one','family-a','viewer'),('two','family-a','owner'),('foreign','family-b','owner')]:
        db.execute('INSERT INTO access_memberships VALUES(?,?,?,?,1,NULL,0,?)',(account,library,'approved',role,account))
    db.execute("INSERT INTO access_operators VALUES('foreign')")
    for token,account in [(TOKEN,'one'),(SECOND,'two'),(OTHER,'foreign'),(RELOGIN,'one')]:
        db.execute('INSERT INTO access_sessions VALUES(?,?,?,0)',(session_digest(token),account,NOW+3600))
    for aid,library,mime,when,status in [(101,'family-a','image/jpeg','2026-01-02','active'),
            (102,'family-a','video/mp4',None,None),(103,'family-a','image/jpeg','2025-12-01','active'),
            (MAXIMUM,'family-a','application/octet-stream','2026-05-05','active'),
            (201,'family-b','image/jpeg','2026-01-01','active'),(999,'family-a','image/jpeg',None,'hidden')]:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,8,8,NULL,?)',(aid,'not-a-real-path',status,mime,when))
        db.execute('INSERT INTO access_asset_libraries VALUES(?,?)',(aid,library))
    db.executemany('INSERT INTO captions VALUES(?,?,?,0,0)',[(1,101,'Portrait at home.'),(2,103,'Ｆａｍｉｌｙ at park.'),(3,MAXIMUM,'Sample Child at park.'),(4,201,'Foreign caption secret')])
    db.executemany('INSERT INTO face_detections VALUES(?,?,?,?)',[(1,101,301,'manual'),(2,103,301,'manual'),(3,103,302,'manual'),(4,MAXIMUM,301,'dnn'),(5,201,401,'manual')])
    db.executemany('INSERT INTO tags VALUES(?,?,?)',[(501,'Park / 公园','scene'),(502,'Favorite / 收藏','custom'),(503,'Blocked / 屏蔽','person'),(504,'Foreign secret','scene')])
    db.executemany('INSERT INTO asset_tags VALUES(?,?,?,?)',[(1,101,502,'manual'),(2,103,501,'cap'),(3,103,502,'manual'),(4,MAXIMUM,501,'cap'),(5,101,503,'img'),(6,201,504,'manual')])
    db.execute('INSERT INTO asset_tag_blocks VALUES(1,101,503)');db.commit()
    return db


def reviewed(access,*,library='family-a',token=TOKEN,**changes):
    # Only the fixture constructs its review after an authorized scoped read.
    with ReadBudget().attempt(access.db,lambda:False) as (_,read):
        with access._transaction():
            access._require(token,library,'library.read'); source=scoped_source(library,read)
    index=ReviewedIndex(library,'1',tuple(str(a[0]) for a in source['assets']),tuple(str(a[0]) for a in source['assets']),digest(source),
        people=(ReviewedPerson(library,'301','Sample Child / 示例儿童',('Sample Child','示例儿童')),
                ReviewedPerson(library,'302','Sample Adult / 示例成人',('Sample Adult','示例成人'))),
        pinned_ids=('302','301'),assignments=(ReviewedFace('1','101','301'),ReviewedFace('2','103','301'),ReviewedFace('3','103','302')),
        places=(ReviewedPlace(library,'601','Example region / 示例地区'),),regions=(('101','601'),('103','601'),(str(MAXIMUM),'601')))
    return replace(index,**changes)
