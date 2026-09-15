#!/usr/bin/env python3
"""Create a metadata-only people review proposal; never approves or publishes it."""
import argparse,hashlib,json,sqlite3,sys,time
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from app.home_feed import direct_path,bounded_read,unique
from app.home_catalog import validate_catalog
from home_people_review import propose,load_review,MAX_REVIEW

def build(database,catalog_path,roster_path):
    for p in (database,catalog_path,roster_path): direct_path(p)
    raw=bounded_read(catalog_path,64*1024**2);catalog=validate_catalog(json.loads(raw,object_pairs_hook=unique))
    roster,_=load_review(roster_path);start=time.monotonic()
    def budget():
        if time.monotonic()-start>30: raise ValueError('review_time_budget')
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024*1024)
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096');db.execute('BEGIN')
        db.set_progress_handler(lambda:int(time.monotonic()-start>30),1000)
        definitions=dict(db.execute("SELECT name,type FROM sqlite_master WHERE name IN ('assets','persons','face_detections')"))
        if definitions!={'assets':'table','persons':'table','face_detections':'table'}:raise ValueError('schema_not_table')
        db.set_authorizer(lambda action,*args:sqlite3.SQLITE_OK if action in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_TRANSACTION) else sqlite3.SQLITE_DENY)
        active=set()
        for row in db.execute("SELECT id FROM assets WHERE status IS NULL OR status='active'"):
            budget()
            if len(active)>=1000000:raise ValueError('asset_budget')
            active.add(row[0])
        selected={a['id'] for a in catalog['assets']}
        if not selected<=active:raise ValueError('selected_asset_changed')
        result=propose(db,selected,hashlib.sha256(raw).hexdigest(),roster,budget)
        db.execute('ROLLBACK')
    packed=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    if len(packed)>MAX_REVIEW or bounded_read(catalog_path,64*1024**2)!=raw:raise ValueError('review_bound_or_drift')
    return packed

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('database','catalog','roster','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    try:
        direct_path(a.output);raw=build(a.database,a.catalog,a.roster)
        with a.output.open('xb') as f:f.write(raw)
        print(json.dumps(dict(review_sha256=hashlib.sha256(raw).hexdigest(),approved=False,published=False)));return 0
    except Exception:print('People review refused');return 2
if __name__=='__main__':raise SystemExit(main())
