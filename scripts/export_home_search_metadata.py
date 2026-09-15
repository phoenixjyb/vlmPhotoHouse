#!/usr/bin/env python3
"""Explicit read-only, metadata-only snapshot bound to an existing Home catalog.

No media copies, live DB writes, person inference, region inference or activation.
Use an OS memory envelope for real Windows export/qualification.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.home_catalog import validate_catalog
from app.home_discovery import validate_index
from app.home_feed import bounded_read, direct_path, unique
from export_home_discovery import caption, capture_day, packed

MAX_ROWS = 1_000_000
MAX_BYTES = 64 * 1024**2
MAX_SECONDS = 120


def build(database, catalog_path, revision, *, tag_lookup=False, people_review=None, people_approval=None):
    if bool(people_review) != bool(people_approval):raise ValueError('people_review_pair_required')
    reviewed_people=[];pinned_people=[];people_review_sha=None
    start = time.monotonic()
    def budget():
        if time.monotonic() - start > MAX_SECONDS:
            raise ValueError('metadata_time_budget')
    for p in (database, catalog_path):
        direct_path(p)
        if p.resolve(strict=True) != p: raise ValueError('indirect_input')
    raw = bounded_read(catalog_path, MAX_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    catalog = validate_catalog(json.loads(raw, object_pairs_hook=unique))
    selected = {a['id'] for a in catalog['assets']}
    rows = {}; scanned = Counter(); captions = Counter(); tag_exclusions = Counter()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA cache_size=-4096')
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
        db.set_progress_handler(lambda: int(time.monotonic() - start > MAX_SECONDS), 1000)
        db.execute('BEGIN')
        definitions = {name:(kind,sql) for name,kind,sql in db.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view')")}
        required = ('assets','captions','tags','asset_tags','asset_tag_blocks') + (('persons','face_detections') if people_review else ())
        if any(t not in definitions or definitions[t][0] != 'table' or not (definitions[t][1] or '').lstrip().upper().startswith('CREATE TABLE') for t in required): raise ValueError('schema_not_table')
        # No caller-provided SQL; deny mutation, extension/function execution and attachment.
        db.set_authorizer(lambda action, a, b, name, trigger: sqlite3.SQLITE_OK if action in
            (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_TRANSACTION) else sqlite3.SQLITE_DENY)
        def each(table, columns, order='id'):
            for values in db.execute('SELECT ' + columns + ' FROM ' + table + ' ORDER BY ' + order):
                scanned[table] += 1
                if sum(scanned.values()) > MAX_ROWS: raise ValueError('metadata_row_budget')
                if scanned[table] % 256 == 0: budget()
                yield values
        for aid, status, taken in each('assets','id,status,taken_at'):
            if aid not in selected: continue
            if status not in (None,'active'): raise ValueError('hidden_selected_asset')
            day, _ = capture_day(taken)
            rows[aid] = dict(id=aid,person_ids=[],people_provenance=None,taken_day=day,
                location_ids=[],location_provenance=None,tags=[],caption_text=None)
        if set(rows) != selected: raise ValueError('missing_selected_asset')
        current = None; group = []
        def save():
            if current in rows:
                text, reason, _ = caption(group); rows[current]['caption_text'] = text; captions[reason] += 1
        for cid, aid, text, edited, superseded in each('captions','id,asset_id,text,user_edited,superseded','asset_id,id'):
            if aid != current: save(); current = aid; group = []
            if aid in selected:
                if len(group) >= 100: raise ValueError('caption_versions_budget')
                group.append(dict(id=cid,text=text,user_edited=edited,superseded=superseded))
        save()
        captions['missing'] += len(selected) - sum(captions.values())
        tags = {tid:dict(id=tid,label=name,kind=kind if kind in ('date','location','person','scene','custom') else 'unknown')
                for tid,name,kind in each('tags','id,name,type')}
        if len(tags) > 100000: raise ValueError('tag_input_budget')
        blocked = {(aid,tid) for _,aid,tid in each('asset_tag_blocks','id,asset_id,tag_id') if aid in selected}
        links = {}; duplicates = set()
        for _,aid,tid,source in each('asset_tags','id,asset_id,tag_id,source'):
            if aid not in selected: continue
            key = (aid,tid)
            if key in links: duplicates.add(key)
            else: links[key] = source
        source_map = {'cap':'caption','img':'image','cap+img':'caption_image','manual':'manual','rule':'rule'}
        used = set()
        for (aid,tid), source in sorted(links.items()):
            if (aid,tid) in blocked: tag_exclusions['blocked'] += 1; continue
            if (aid,tid) in duplicates: tag_exclusions['conflicting'] += 1; continue
            if tid not in tags: tag_exclusions['missing_tag'] += 1; continue
            rows[aid]['tags'].append(dict(id=tid,source=source_map.get(source,'unknown'))); used.add(tid)
        if people_review:
            from home_people_review import approved_people
            reviewed_people,pinned_people,people_review_sha=approved_people(db,rows,digest,people_review,people_approval,budget)
        db.execute('ROLLBACK')
    # Never truncate a tag roster or claim incomplete tag matching as complete.
    tag_overflow = len(used) > (10000 if tag_lookup else 5000)
    unpublished_tags = len(used) if tag_overflow else 0
    if tag_overflow:
        used = set()
        for row in rows.values(): row['tags'] = []
    index = dict(version=2 if tag_lookup else 1,revision=revision,catalog_revision=catalog['revision'],catalog_sha256=digest,
        enabled_filters=['caption','date','media'] + (['tags'] if used else []) + (['people'] if reviewed_people else []),people=reviewed_people,pinned_person_ids=pinned_people,
        tags=[tags[i] for i in sorted(used)],locations=[],assets=[rows[i] for i in sorted(rows)])
    if tag_lookup:
        from app.home_tag_discovery import validate_tag_index
        validate_tag_index(index,catalog,digest)
    else: validate_index(index,catalog,digest)
    output = packed(index)
    if len(output) > MAX_BYTES: raise ValueError('metadata_byte_budget')
    if bounded_read(catalog_path,MAX_BYTES) != raw: raise ValueError('catalog_changed')
    budget()
    coverage = dict(catalog_assets=len(selected),indexed_assets=len(rows),
        metadata_with_values={k:sum(bool(r[f]) for r in rows.values()) for k,f in
            [('caption','caption_text'),('date','taken_day'),('tags','tags')]},
        caption_states=dict(captions),tag_exclusions=dict(tag_exclusions),
        people_enabled=bool(reviewed_people),people_review_sha256=people_review_sha,locations_enabled=False,unresolved_shortcuts=max(0,7-len(pinned_people)),
        tags_enabled=bool(used),unpublished_tag_count=unpublished_tags,tag_roster_overflow=tag_overflow,
        rows_scanned=dict(scanned),elapsed_seconds=round(time.monotonic()-start,3))
    return output,dict(policy='home-search-tags-2' if tag_lookup else 'home-search-metadata-1',catalog_sha256=digest,
        index_sha256=hashlib.sha256(output).hexdigest(),index_bytes=len(output),coverage=coverage,
        media_copied=False,activated=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','catalog','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--revision',type=int,required=True)
    p.add_argument('--people-review',type=Path);p.add_argument('--people-approval',type=Path)
    p.add_argument('--tag-lookup',action='store_true')
    a=p.parse_args()
    try:
        direct_path(a.output)
        if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir(): raise ValueError('output_collision')
        raw,report=build(a.database,a.catalog,a.revision,tag_lookup=a.tag_lookup,people_review=a.people_review,people_approval=a.people_approval)
        with a.output.open('xb') as f: a.output.chmod(0o600); f.write(raw)
        print(json.dumps(report));return 0
    except Exception:
        print('Metadata export refused; inputs, scope or resource bounds failed',file=sys.stderr);return 2
if __name__=='__main__': raise SystemExit(main())
