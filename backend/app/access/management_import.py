"""Offline explicit ownership import, shared by sealed planning and atomic apply.

No HTTP route, automatic ownership guess, migration, media access or worker control.
"""
import hashlib
import re
import sqlite3
import time

from .provisioning import PlanRejected, _json, _library

MAX_ENTITIES = 500
MAX_LINKS = 200000
FIELDS = {'library_id','operator_account_id','person_ids','album_ids',
          'include_orphan_people','include_empty_albums','quiescence_reference'}


def _ids(values):
    if not isinstance(values,list) or len(values)>MAX_ENTITIES:
        raise PlanRejected('Explicit bounded entity selection required')
    if any(not isinstance(value,str) or not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>2**63-1 for value in values):
        raise PlanRejected('Invalid entity selection')
    ids = [int(value) for value in values]
    if ids != sorted(set(ids)):
        raise PlanRejected('Sorted unique entity selection required')
    return ids


def management_state(state, target, *, imported=False):
    # Exact entity IDs bound output, but legacy joins may still scan large tables.
    # This private offline connection has no caller-owned progress handler.
    deadline = time.monotonic() + 30
    state.access.db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        return _management_state(state, target, imported=imported, deadline=deadline)
    except sqlite3.OperationalError as exc:
        if str(exc) == 'interrupted':
            raise PlanRejected('Import review budget exceeded') from None
        raise
    finally:
        state.access.db.set_progress_handler(None, 0)


def _management_state(state, target, *, imported, deadline):
    if not isinstance(target,dict) or set(target)!=FIELDS:
        raise PlanRejected('Invalid management import')
    library = _library(target['library_id']);actor = target['operator_account_id']
    if not isinstance(actor,str) or len(actor)!=36:
        raise PlanRejected('Explicit operator required')
    for key in ('include_orphan_people','include_empty_albums'):
        if type(target[key]) is not bool:
            raise PlanRejected('Explicit unlinked-record decision required')
    if not isinstance(target['quiescence_reference'],str) or not re.fullmatch('[A-Za-z0-9_-]{3,80}',target['quiescence_reference']):
        raise PlanRejected('Independent writer shutdown reference required')
    people,albums = _ids(target['person_ids']),_ids(target['album_ids'])
    if not 1<=len(people)+len(albums)<=MAX_ENTITIES:
        raise PlanRejected('Select a bounded nonempty batch')
    db=state.access.db;now=state.access._now()
    if db.execute('PRAGMA journal_mode').fetchone()[0]!='delete' or db.execute('''SELECT 1 FROM tasks
        WHERE state='running' OR (state='pending' AND type IN
        ('face','face_embed','person_cluster','person_recluster','person_label_propagate')) LIMIT 1''').fetchone():
        raise PlanRejected('Offline database and stopped writers required')
    owner=db.execute('''SELECT m.revision FROM access_memberships m
        JOIN access_accounts a ON a.id=m.account_id JOIN access_libraries l ON l.id=m.library_id
        JOIN access_operators o ON o.account_id=m.account_id WHERE m.account_id=? AND m.library_id=?
        AND m.role='owner' AND m.status='approved' AND a.state='active' AND l.state='active'
        AND (m.expires_at IS NULL OR m.expires_at>?)''',(actor,library,now)).fetchone()
    if not owner: raise PlanRejected('Selected active operator and owner required')
    audience=db.execute('''SELECT m.account_id,m.status,m.role,m.revision,m.expires_at,m.originals,a.state
        FROM access_memberships m JOIN access_accounts a ON a.id=m.account_id
        WHERE m.library_id=? ORDER BY m.account_id LIMIT 10001''',(library,)).fetchall()
    if len(audience)>10000: raise PlanRejected('Audience review budget exceeded')
    current=[r for r in audience if r[1]=='approved' and r[6]=='active' and (r[4] is None or r[4]>now)]
    digest=hashlib.sha256();links=0;orphans=0;empty=0

    def feed(value):
        if time.monotonic()>deadline: raise PlanRejected('Import review budget exceeded')
        digest.update(_json(value));digest.update(b'\n')

    def ownership(kind, identity):
        row=db.execute(f'SELECT library_id,creator_id,revision FROM access_{kind}_libraries WHERE {kind}_id=?',(identity,)).fetchone()
        if (row!=(library,actor,1) if imported else row is not None):
            raise PlanRejected('Entity ownership changed or already assigned')

    for person in people:
        ownership('person',person)
        row=db.execute('''SELECT id,display_name,face_count,embedding_path,created_at,updated_at FROM persons WHERE id=?
            AND length(coalesce(display_name,''))<=128 AND typeof(display_name) IN ('null','text')
            AND length(coalesce(embedding_path,''))<=4096 AND typeof(embedding_path) IN ('null','text')
            AND length(coalesce(created_at,''))<=128 AND length(coalesce(updated_at,''))<=128''',(person,)).fetchone()
        if row is None: raise PlanRejected('Missing person or metadata requires separate correction')
        feed(['person',row]);count=0
        for face in db.execute('''SELECT f.id,f.asset_id,f.label_source,f.label_score,f.created_at,a.status,s.library_id
            FROM face_detections f LEFT JOIN assets a ON a.id=f.asset_id
            LEFT JOIN access_asset_libraries s ON s.asset_id=f.asset_id WHERE f.person_id=? ORDER BY f.id''',(person,)):
            if face[6]!=library: raise PlanRejected('Person has foreign or unmapped references')
            count+=1;links+=1
            if links>MAX_LINKS: raise PlanRejected('Import link budget exceeded')
            feed(face)
        if not count:
            if not target['include_orphan_people']: raise PlanRejected('Orphan import requires explicit review')
            orphans+=1
    themes={'custom','birthday','trip','growing_up','grandparents','year_in_review','seasonal'}
    for album in albums:
        ownership('album',album)
        row=db.execute('''SELECT id,title,title_zh,description,theme,status,cover_asset_id,source_kind,source_ref,created_at,updated_at
            FROM albums WHERE id=? AND length(title)<=160 AND typeof(title)='text'
            AND length(coalesce(title_zh,''))<=160 AND typeof(title_zh) IN ('null','text')
            AND length(coalesce(description,''))<=1000 AND typeof(description) IN ('null','text')
            AND length(coalesce(source_kind,''))<=128 AND length(coalesce(source_ref,''))<=4096
            AND length(coalesce(created_at,''))<=128 AND length(coalesce(updated_at,''))<=128''',(album,)).fetchone()
        if row is None or row[5]!='draft' or not isinstance(row[1],str) or not row[1].strip() or row[4] not in themes:
            raise PlanRejected('Only compatible draft albums can be imported')
        if len(row[1])>160 or len(row[2] or '')>160 or len(row[3] or '')>1000:
            raise PlanRejected('Album metadata requires separate correction')
        feed(['album',row]);selected=[];positions=[]
        for item in db.execute('''SELECT aa.asset_id,aa.position,a.status,s.library_id FROM album_assets aa
            LEFT JOIN assets a ON a.id=aa.asset_id LEFT JOIN access_asset_libraries s ON s.asset_id=aa.asset_id
            WHERE aa.album_id=? ORDER BY aa.position,aa.id''',(album,)):
            if item[3]!=library or item[2] not in (None,'active'):
                raise PlanRejected('Album has inactive, foreign or unmapped references')
            selected.append(item[0]);positions.append(item[1]);feed(item);links+=1
            if len(selected)>60 or links>MAX_LINKS: raise PlanRejected('Album selection exceeds supported bounds')
        if len(set(selected))!=len(selected) or len(set(positions))!=len(positions):
            raise PlanRejected('Album order requires separate correction')
        if row[6] is not None and row[6] not in selected:
            raise PlanRejected('Album cover requires separate correction')
        if not selected:
            if not target['include_empty_albums']: raise PlanRejected('Empty album import requires explicit review')
            empty+=1
    return {'operator_revision':str(owner[0]),'entity_state':state._mac('management-import-state',digest.hexdigest()),
            'audience_state':state._mac('management-import-audience',audience),
            'people_count':len(people),'album_count':len(albums),'orphan_people_count':orphans,'empty_album_count':empty,
            'reference_count':links,'current_album_readers':len(current) if albums else 0,
            'current_people_managers':sum(r[2]=='owner' for r in current) if people else 0,
            'originals_granted':False,'memberships_changed':False,'legacy_records_changed':False,'media_writes':False}


def apply_management(state, target):
    """Caller holds the reviewed write reservation and commits receipt/audit."""
    if not state.access.db.in_transaction: raise PlanRejected('Write reservation required')
    library,actor=target['library_id'],target['operator_account_id']
    for kind in ('person','album'):
        ids=target['person_ids' if kind=='person' else 'album_ids']
        state.access.db.executemany(f'''INSERT INTO access_{kind}_libraries({kind}_id,library_id,creator_id,revision)
            VALUES(?,?,?,1)''',((int(identity),library,actor) for identity in ids))
