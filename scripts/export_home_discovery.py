#!/usr/bin/env python3
"""Offline review/export only. No live defaults, original reads, models or listener."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.home_feed import bounded_read, direct_path, exact, integer, jpeg_dimensions, unique
from app.home_catalog import CHUNK_BYTES, validate_catalog
from app.home_discovery import validate_index

POLICY = 'discovery-export-1'
MAX_DB = 64 * 1024**2
MAX_JSON = 16 * 1024**2
MAX_MEDIA_FILE = 64 * 1024**2
MAX_MEDIA_TOTAL = 128 * 1024**2
MAX_ROWS = 100000
MAX_TOTAL_ROWS = 300000
DEADLINE_SECONDS = 30
TABLES = {
    'assets': ('id', 'status', 'taken_at'),
    'captions': ('id', 'asset_id', 'text', 'user_edited', 'superseded'),
    'persons': ('id',),
    'face_detections': ('id', 'asset_id', 'person_id', 'label_source'),
    'tags': ('id', 'name', 'type'),
    'asset_tags': ('id', 'asset_id', 'tag_id', 'source'),
    'asset_tag_blocks': ('id', 'asset_id', 'tag_id'),
}


class ExportError(ValueError):
    """Bounded diagnostic code; never put private values/paths in CLI errors."""


def require(condition, code='invalid_input'):
    if not condition:
        raise ExportError(code)


def packed(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum):
    return bounded_read(path, maximum)


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique)


def check_time(start):
    require(monotonic() - start <= DEADLINE_SECONDS, 'time_budget')


def id_list(value, maximum=100000):
    require(type(value) is list and len(value) <= maximum and all(integer(i, 1, 2**31-1) for i in value))
    require(value == sorted(set(value)), 'ids_must_be_unique_sorted')
    return set(value)


def snapshot_rows(raw, start):
    # Deserialize only an explicit standalone rollback-journal snapshot. No SQL
    # connection ever opens the input file or creates WAL/SHM alongside it.
    require(raw[:16] == b'SQLite format 3\x00' and len(raw) >= 100 and raw[18:20] == b'\x01\x01', 'standalone_snapshot_required')
    with closing(sqlite3.connect(':memory:')) as conn:
        conn.deserialize(raw)
        conn.execute('PRAGMA query_only=ON')
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_JSON)
        conn.set_progress_handler(lambda: int(monotonic()-start > DEADLINE_SECONDS), 1000)
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_TRANSACTION}
        conn.set_authorizer(lambda action, a, b, db, trigger: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        conn.execute('BEGIN')
        tables = {name:(kind,sql) for name,kind,sql in conn.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view')")}
        rows = {}; total = 0
        for table, columns in TABLES.items():
            check_time(start)
            definition = tables.get(table)
            require(definition is not None and definition[0] == 'table' and re.match(r'^\s*CREATE\s+TABLE\b',definition[1] or '',re.I), 'schema_missing_or_view')
            # Constants above, never identifiers supplied by input JSON.
            cursor = conn.execute('SELECT '+','.join(columns)+' FROM '+table+' ORDER BY id LIMIT ?', (MAX_ROWS+1,))
            values = cursor.fetchall(); total += len(values)
            require(len(values) <= MAX_ROWS and total <= MAX_TOTAL_ROWS, 'row_budget')
            require(all(integer(row[0], 1, 2**31-1) for row in values), 'invalid_database_id')
            require(len({row[0] for row in values}) == len(values), 'duplicate_database_id')
            rows[table] = [dict(zip(columns, row)) for row in values]
        conn.execute('ROLLBACK')
        return rows


def capture_day(value):
    if value is None or value == '':
        return None, 'missing'
    try:
        require(type(value) is str and len(value) <= 64)
        # Explicit ISO calendar date, optionally with a valid ISO time; retain
        # recorded local calendar day without timezone conversion or ingest fallback.
        require(len(value) >= 10 and value[4] == '-' and value[7] == '-')
        day = date.fromisoformat(value[:10]).isoformat()
        if len(value) != 10:
            require(value[10] in ('T', ' '))
            datetime.fromisoformat(value)
        return day, 'valid'
    except (ValueError, TypeError):
        return None, 'invalid'


def caption(rows):
    counts = Counter(); candidates = []
    for row in rows:
        if row['superseded'] not in (0, 1) or row['user_edited'] not in (0, 1):
            counts['invalid_flags'] += 1
        elif row['superseded']:
            counts['superseded'] += 1
        elif not isinstance(row['text'], str) or not row['text'].strip():
            counts['blank_or_invalid'] += 1
        else:
            candidates.append(row)
    edited = [r for r in candidates if r['user_edited'] == 1]
    chosen = edited if edited else candidates
    if len(chosen) != 1:
        return None, 'ambiguous' if chosen else 'missing', counts
    text = chosen[0]['text']
    if len(text.encode('utf-8')) > 4096:
        return None, 'oversized', counts
    if any(ord(c) < 32 and c not in '\n\t' for c in text):
        return None, 'invalid_text', counts
    return text, 'selected', counts


def build(database, candidate, request_path):
    start = monotonic()
    for path in (database, candidate, request_path):
        direct_path(path)
        require(path.resolve(strict=True) == path, 'indirect_input')
    require(candidate.is_dir(), 'candidate_directory_required')
    require(not any(Path(str(database)+suffix).exists() for suffix in ('-wal', '-shm', '-journal')), 'snapshot_sidecar_present')
    originals = { 'snapshot': read(database, MAX_DB), 'catalog': read(candidate/'catalog.json', MAX_JSON),
                 'control': read(candidate/'control.json', 4096), 'request': read(request_path, 2*1024**2) }
    request = parse(originals['request'])
    exact(request, ('version','catalog_sha256','selected_asset_ids','indexed_asset_ids','discovery_revision',
                    'copy_prepared','roster_review','assignment_review','region_review'))
    require(type(request['version']) is int and request['version'] == 1)
    require(integer(request['discovery_revision'], 1, 2**31-1) and type(request['copy_prepared']) is bool)
    require(request['catalog_sha256'] == sha(originals['catalog']), 'catalog_hash_mismatch')
    catalog = validate_catalog(parse(originals['catalog']))
    control = parse(originals['control']); exact(control, ('version','enabled','revision','catalog_sha256'))
    require(type(control['version']) is int and control['version'] == 2 and control['enabled'] is False
            and type(control['revision']) is int and control['revision'] == catalog['revision']
            and control['catalog_sha256'] == sha(originals['catalog']), 'disabled_candidate_required')
    selected = id_list(request['selected_asset_ids']); indexed = id_list(request['indexed_asset_ids'])
    require(selected == {a['id'] for a in catalog['assets']} and indexed <= selected, 'selection_mismatch')
    data = snapshot_rows(originals['snapshot'], start)
    assets = {a['id']: a for a in data['assets']}
    require(all(i in assets and assets[i]['status'] in ('active', None) for i in selected), 'hidden_missing_or_foreign_asset')

    roster = request['roster_review']; exact(roster, ('people','pinned_person_ids','unresolved_shortcut_count'))
    require(integer(roster['unresolved_shortcut_count'], 0, 32))
    require(type(roster['people']) is list and len(roster['people']) <= 5000)
    person_ids = {p['id'] for p in data['persons']}
    reviewed_people = set()
    for person in roster['people']:
        exact(person, ('id','label','aliases'))
        require(integer(person['id'], 1, 2**31-1) and person['id'] in person_ids and person['id'] not in reviewed_people, 'unresolved_or_duplicate_person')
        reviewed_people.add(person['id'])
    assignments = request['assignment_review']
    require(type(assignments) is list and len(assignments) <= MAX_ROWS)
    faces = {f['id']: f for f in data['face_detections']}; seen_faces = set(); by_person = defaultdict(set)
    for row in assignments:
        exact(row, ('face_id','asset_id','person_id','label_source'))
        require(all(integer(row[k], 1, 2**31-1) for k in ('face_id','asset_id','person_id')))
        expected = {'id': row['face_id'], 'asset_id': row['asset_id'], 'person_id': row['person_id'], 'label_source': row['label_source']}
        require(row['face_id'] not in seen_faces and faces.get(row['face_id']) == expected, 'assignment_evidence_changed')
        require(row['label_source'] == 'manual' and row['person_id'] in reviewed_people and row['asset_id'] in indexed, 'unreviewed_assignment')
        seen_faces.add(row['face_id']); by_person[row['asset_id']].add(row['person_id'])
    region = request['region_review']; exact(region, ('locations','assignments'))
    require(type(region['locations']) is list and len(region['locations']) <= 5000)
    location_ids = set()
    for place in region['locations']:
        exact(place, ('id','label'))
        require(integer(place['id'], 1, 2**31-1) and place['id'] not in location_ids)
        location_ids.add(place['id'])
    require(type(region['assignments']) is list and len(region['assignments']) <= MAX_ROWS)
    by_location = defaultdict(set)
    for row in region['assignments']:
        exact(row, ('asset_id','location_id'))
        require(integer(row['asset_id'], 1, 2**31-1) and integer(row['location_id'], 1, 2**31-1))
        require(row['asset_id'] in indexed and row['location_id'] in location_ids and row['location_id'] not in by_location[row['asset_id']], 'unreviewed_region')
        by_location[row['asset_id']].add(row['location_id'])

    captions = defaultdict(list); links = defaultdict(list)
    for row in data['captions']:
        if row['asset_id'] in indexed: captions[row['asset_id']].append(row)
    for row in data['asset_tags']:
        if row['asset_id'] in indexed: links[(row['asset_id'],row['tag_id'])].append(row)
    blocked = {(r['asset_id'],r['tag_id']) for r in data['asset_tag_blocks']}
    tags = {t['id']:t for t in data['tags']}; used_tags = set(); asset_tags = defaultdict(list)
    source_map = {'cap':'caption','img':'image','cap+img':'caption_image','manual':'manual','rule':'rule'}
    tag_reasons = Counter(); sources = Counter()
    for (aid, tid), rows in sorted(links.items()):
        check_time(start)
        if (aid,tid) in blocked: tag_reasons['blocked'] += len(rows); continue
        if len(rows) != 1: tag_reasons['duplicate_or_conflicting'] += len(rows); continue
        if tid not in tags: tag_reasons['missing_tag'] += 1; continue
        source = source_map.get(rows[0]['source'], 'unknown')
        asset_tags[aid].append({'id':tid,'source':source}); used_tags.add(tid); sources[source] += 1
    tag_roster = []
    for tid in sorted(used_tags):
        tag = tags[tid]
        kind = tag['type'] if tag['type'] in ('date','location','person','scene','custom') else 'unknown'
        tag_roster.append({'id':tid,'label':tag['name'],'kind':kind})
    rows = []; dates = Counter(); caption_states = Counter(); caption_exclusions = Counter()
    for aid in sorted(indexed):
        check_time(start)
        day, reason = capture_day(assets[aid]['taken_at']); dates[reason] += 1
        text, reason, exclusions = caption(captions[aid]); caption_states[reason] += 1; caption_exclusions.update(exclusions)
        rows.append({'id':aid,'person_ids':sorted(by_person[aid]),'people_provenance':'reviewed_assignments' if by_person[aid] else None,
                     'taken_day':day,'location_ids':sorted(by_location[aid]),'location_provenance':'reviewed_region' if by_location[aid] else None,
                     'tags':asset_tags[aid],'caption_text':text})

    # Only exact prepared variant paths from the candidate catalog are read.
    media = {}; media_pins = {}; readiness = defaultdict(Counter); total_media = 0
    for asset in catalog['assets']:
        check_time(start)
        for variant, descriptor in [*asset['previews'].items(), ('video',asset['video'])]:
            if descriptor is None: continue
            if descriptor['state'] != 'ready':
                readiness[variant][descriptor['reason']] += 1; continue
            if not request['copy_prepared']:
                if variant == 'video':
                    asset['video'] = {'state':'unavailable','reason':'not_prepared'}
                else:
                    asset['previews'][variant] = {'state':'unavailable','reason':'not_prepared'}
                readiness[variant]['not_copied'] += 1; continue
            name = f'prepared/{variant}/{asset["id"]}.'+('mp4' if variant == 'video' else 'jpg')
            raw = read(candidate/name, MAX_MEDIA_FILE); require(sha(raw) == descriptor['sha256'] and len(raw) == descriptor['bytes'], 'prepared_hash_mismatch')
            if variant == 'video':
                chunk_name = f'prepared/video/{asset["id"]}.chunks.json'
                chunk_raw = read(candidate/chunk_name, MAX_JSON)
                require(sha(chunk_raw) == descriptor['chunks_sha256'], 'chunk_manifest_hash_mismatch')
                require(parse(chunk_raw) == [sha(raw[i:i+CHUNK_BYTES]) for i in range(0,len(raw),CHUNK_BYTES)], 'chunk_hash_mismatch')
                media[chunk_name] = chunk_raw; total_media += len(chunk_raw)
            else:
                require(jpeg_dimensions(raw) == (descriptor['width'],descriptor['height']), 'prepared_dimensions_mismatch')
            media[name] = raw; total_media += len(raw)
            require(total_media <= MAX_MEDIA_TOTAL, 'media_budget')
            readiness[variant]['bytes_verified_ready'] += 1
    media_pins = {name:sha(raw) for name,raw in sorted(media.items())}
    validate_catalog(catalog); catalog_raw = packed(catalog)
    enabled = ['date','media','tags','caption']
    if reviewed_people: enabled.append('people')
    if location_ids: enabled.append('locations')
    index = {'version':1,'revision':request['discovery_revision'],'catalog_revision':catalog['revision'],
             'catalog_sha256':sha(catalog_raw),'enabled_filters':sorted(enabled),
             'people':sorted(roster['people'],key=lambda p:p['id']),'pinned_person_ids':roster['pinned_person_ids'],
             'tags':tag_roster,'locations':sorted(region['locations'],key=lambda p:p['id']),'assets':rows}
    validate_index(index,catalog,sha(catalog_raw))
    index_raw = packed(index)
    require(len(index_raw) <= MAX_JSON and len(catalog_raw) <= MAX_JSON, 'json_budget')
    coverage = {'catalog_assets':len(selected),'indexed_assets':len(indexed),'index_complete':indexed==selected,
                'unresolved_shortcuts':roster['unresolved_shortcut_count'],'reviewed_person_ids':len(reviewed_people),
                'approved_face_evidence_rows':len(seen_faces),'unreviewed_face_rows':sum(f['asset_id'] in indexed and f['id'] not in seen_faces for f in faces.values()),
                'metadata_with_values':{field:sum(bool(r[key]) for r in rows) for field,key in [('people','person_ids'),('date','taken_day'),('locations','location_ids'),('tags','tags'),('caption','caption_text')]},
                'dates':dict(dates),'caption_states':dict(caption_states),'caption_exclusions':dict(caption_exclusions),
                'tag_exclusions':dict(tag_reasons),'tag_sources':dict(sources),'media':{k:dict(v) for k,v in readiness.items()},
                'tag_kinds':dict(Counter(t['kind'] for t in tag_roster)),
                'catalog_media_kinds':dict(Counter(a['kind'] for a in catalog['assets'])),
                'metadata_completeness':'not_inferred','tag_generation_completeness':'unknown','media_validation':'hashes/dimensions only; codec and physical quality require prior preparation evidence'}
    coverage['metadata_without_values'] = {key:len(selected)-value for key,value in coverage['metadata_with_values'].items()}
    output_control = {'version':2,'enabled':False,'revision':catalog['revision'],'catalog_sha256':sha(catalog_raw)}
    output = {'catalog.json':catalog_raw,'discovery.json':index_raw,'control.json':packed(output_control),'coverage.json':packed(coverage),**media}
    plan = {'version':1,'policy':POLICY,'inputs':{key:sha(raw) for key,raw in sorted(originals.items())},
            'selection_sha256':sha(packed(request['selected_asset_ids'])),'prepared_input_hashes':media_pins,
            'catalog':catalog,'index':index,'coverage':coverage,'output_hashes':{name:sha(raw) for name,raw in sorted(output.items())}}
    check_time(start)
    # Detect input changes while building, including SQLite sidecars appearing.
    for key,path in [('snapshot',database),('catalog',candidate/'catalog.json'),('control',candidate/'control.json'),('request',request_path)]:
        require(read(path, MAX_DB if key=='snapshot' else MAX_JSON) == originals[key], 'input_changed')
    require(not any(Path(str(database)+suffix).exists() for suffix in ('-wal','-shm','-journal')), 'snapshot_sidecar_present')
    for name,digest in media_pins.items(): require(sha(read(candidate/name,MAX_MEDIA_FILE)) == digest, 'prepared_input_changed')
    check_time(start)
    return {'plan':plan,'plan_sha256':sha(packed(plan))}, output


def new_file(path, raw):
    direct_path(path)
    require(path.parent.resolve(strict=True) == path.parent, 'indirect_output')
    with path.open('xb') as stream:
        path.chmod(0o600); stream.write(raw)


def review(database, candidate, request_path, output):
    direct_path(output)
    require(not output.exists() and not output.is_symlink(), 'output_collision')
    require(output.parent.resolve(strict=True)==output.parent and not output.is_relative_to(candidate), 'unsafe_output')
    package,_ = build(database,candidate,request_path)
    raw = packed(package); require(len(raw)<=2*MAX_JSON, 'review_budget')
    new_file(output,raw)
    return {'plan_sha256':package['plan_sha256'],'coverage':package['plan']['coverage']}


def publish(database, candidate, request_path, review_path, approval_path, output):
    direct_path(output)
    require(not output.exists() and not output.is_symlink(), 'output_collision')
    require(output.parent.resolve(strict=True)==output.parent and not output.is_relative_to(candidate), 'unsafe_output')
    saved = parse(read(review_path,2*MAX_JSON)); exact(saved,('plan','plan_sha256'))
    require(sha(packed(saved['plan']))==saved['plan_sha256'], 'review_digest_mismatch')
    approval = parse(read(approval_path,4096))
    keys = ('approve_selection','approve_roster','approve_assignments','approve_regions','approve_metadata')
    exact(approval,('version','plan_sha256',*keys))
    require(type(approval['version']) is int and approval['version']==1 and all(approval[k] is True for k in keys), 'explicit_review_required')
    require(approval['plan_sha256']==saved['plan_sha256'], 'approval_mismatch')
    current,files = build(database,candidate,request_path)
    require(current==saved, 'review_inputs_changed')
    # Exclusive new directory; failures may leave a disabled partial attempt, never
    # replace another release or turn on a listener. No shared activation pointer.
    output.mkdir(mode=0o700)
    for name in ['control.json', *sorted(n for n in files if n!='control.json')]:
        path = output/name; path.parent.mkdir(parents=True,exist_ok=True,mode=0o700); new_file(path,files[name])
    (output/'prepared').mkdir(exist_ok=True,mode=0o700)
    return {'enabled':False,'plan_sha256':saved['plan_sha256'],'output_hashes':saved['plan']['output_hashes'],'coverage':saved['plan']['coverage']}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=['review','publish'])
    for name in ('database','candidate','request','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--review',type=Path); parser.add_argument('--approval',type=Path)
    args=parser.parse_args()
    try:
        if args.action=='review': result=review(args.database,args.candidate,args.request,args.output)
        else:
            require(args.review is not None and args.approval is not None,'review_and_approval_required')
            result=publish(args.database,args.candidate,args.request,args.review,args.approval,args.output)
        print(json.dumps(result,sort_keys=True)); return 0
    except Exception as error:
        code = str(error) if isinstance(error,ExportError) else 'snapshot_schema_or_query_refused' if isinstance(error,sqlite3.DatabaseError) else 'invalid_or_changed_input'
        print(json.dumps({'error':code,'enabled':False}),file=sys.stderr); return 2


if __name__=='__main__': raise SystemExit(main())
