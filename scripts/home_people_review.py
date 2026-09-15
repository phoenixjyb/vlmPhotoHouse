"""Read-only, catalog-bound review of explicit people and existing manual labels.

Proposals are not approvals. No faces, embeddings or media bytes are read.
"""
import hashlib
import json
from pathlib import Path
from app.home_feed import exact, integer, bounded_read, unique
from app.home_discovery import text, ids

MAX_REVIEW=2*1024**2

def load_review(path):
    raw=bounded_read(path,MAX_REVIEW)
    return json.loads(raw,object_pairs_hook=unique),hashlib.sha256(raw).hexdigest()

def validate_roster(roster):
    exact(roster,('people','pinned_person_ids'))
    if type(roster['people']) is not list or not 1<=len(roster['people'])<=32: raise ValueError('people_limit')
    seen=set()
    for person in roster['people']:
        exact(person,('id','stored_name','label','aliases'))
        if not integer(person['id'],1,2**31-1) or person['id'] in seen: raise ValueError('person_id')
        seen.add(person['id']);text(person['stored_name'],256,True);text(person['label'],256,True)
        if type(person['aliases']) is not list or len(person['aliases'])>8: raise ValueError('aliases')
        for alias in person['aliases']: text(alias,128,True)
        if len(set(person['aliases']))!=len(person['aliases']): raise ValueError('duplicate_alias')
    ids(roster['pinned_person_ids'],32,seen)
    return seen

def propose(db,selected,catalog_sha256,roster,budget):
    people=validate_roster(roster);marks=','.join('?' for _ in people)
    names=dict(db.execute('SELECT id,display_name FROM persons WHERE id IN ('+marks+')',tuple(sorted(people))))
    if any(names.get(p['id'])!=p['stored_name'] for p in roster['people']): raise ValueError('person_name_changed')
    assignments=[]
    for fid,aid,pid,source in db.execute('SELECT id,asset_id,person_id,label_source FROM face_detections WHERE person_id IN ('+marks+') AND label_source=? ORDER BY id',(*sorted(people),'manual')):
        budget()
        if aid in selected:
            if len(assignments)>=10000: raise ValueError('assignment_budget')
            assignments.append(dict(face_id=fid,asset_id=aid,person_id=pid,label_source=source))
    return dict(version=1,catalog_sha256=catalog_sha256,roster=roster,assignments=assignments)

def approved_people(db,rows,digest,review_path,approval_path,budget):
    review,review_sha=load_review(review_path);approval,_=load_review(approval_path)
    exact(approval,('version','review_sha256','approve_roster','approve_assignments'))
    if (type(approval['version']) is not int or approval['version']!=1 or approval['review_sha256']!=review_sha
        or approval['approve_roster'] is not True or approval['approve_assignments'] is not True): raise ValueError('people_approval_required')
    exact(review,('version','catalog_sha256','roster','assignments'))
    if type(review['version']) is not int or review['version']!=1 or review['catalog_sha256']!=digest: raise ValueError('people_catalog_changed')
    known=validate_roster(review['roster']);assignments=review['assignments']
    if type(assignments) is not list or len(assignments)>10000: raise ValueError('assignment_budget')
    names=dict(db.execute('SELECT id,display_name FROM persons WHERE id IN ('+','.join('?' for _ in known)+')',tuple(sorted(known))))
    if any(names.get(p['id'])!=p['stored_name'] for p in review['roster']['people']): raise ValueError('person_name_changed')
    seen=set();by_asset={}
    for record in assignments:
        budget();exact(record,('face_id','asset_id','person_id','label_source'))
        if any(not integer(record[k],1,2**31-1) for k in ('face_id','asset_id','person_id')):raise ValueError('invalid_assignment')
        if record['face_id'] in seen or record['person_id'] not in known or record['asset_id'] not in rows or record['label_source']!='manual':raise ValueError('unreviewed_assignment')
        actual=db.execute('SELECT asset_id,person_id,label_source FROM face_detections WHERE id=?',(record['face_id'],)).fetchone()
        if actual!=(record['asset_id'],record['person_id'],'manual'): raise ValueError('assignment_changed')
        seen.add(record['face_id']);by_asset.setdefault(record['asset_id'],set()).add(record['person_id'])
    for aid,people in by_asset.items():rows[aid].update(person_ids=sorted(people),people_provenance='reviewed_assignments')
    return [{k:p[k] for k in ('id','label','aliases')} for p in review['roster']['people']],review['roster']['pinned_person_ids'],review_sha
