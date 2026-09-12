#!/usr/bin/env python3
"""Resumable full-snapshot preparation; no listener, activation, or live DB writes."""
import argparse
from contextlib import closing,contextmanager,ExitStack
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time

import prepare_home_catalog as prep
import build_home_catalog
from home_preparation_resources import Guard,JobStopped
from app.home_catalog import MAX_CATALOG,MAX_VIDEO,validate_catalog,validate_video,identity
from app.home_feed import LIMITS,bounded_read,direct_path,unique,Refused

SCHEMA=1
CODE=('scripts/prepare_home_library.py','scripts/prepare_home_catalog.py',
      'scripts/home_preparation_resources.py','scripts/build_home_catalog.py',
      'backend/app/home_catalog.py','backend/app/home_feed.py')


def read_json(path, maximum=MAX_CATALOG):
    return json.loads(bounded_read(path,maximum),object_pairs_hook=unique)


def code_pin():
    return {name:prep.sha((prep.ROOT/name).read_bytes()) for name in CODE}


def profile(budget):
    # Configurable *preparation* budgets stay within the existing v2 output wire.
    values=asdict(budget)
    if any(type(v) is not int or v<=0 for v in values.values()):raise ValueError('invalid_budget')
    if (budget.output_bytes>MAX_VIDEO or budget.duration_seconds>86400 or budget.pixels>1000000000
            or budget.input_bytes>128*1024**3 or budget.process_seconds>86400 or budget.asset_seconds>172800):
        raise ValueError('budget_exceeds_review_envelope')
    if budget.process_seconds>budget.asset_seconds:raise ValueError('invalid_deadlines')
    return values


def publication_pin(path):
    prep.canonical(path)
    control=read_json(path/'control.json',4096);raw=bounded_read(path/'catalog.json',MAX_CATALOG)
    catalog=validate_catalog(json.loads(raw,object_pairs_hook=unique))
    if (set(control)!= {'version','enabled','revision','catalog_sha256'} or control['version']!=2
            or type(control['enabled']) is not bool or control['revision']!=catalog['revision']
            or control['catalog_sha256']!=prep.sha(raw)):
        raise ValueError('invalid_previous_publication')
    return {'path':str(path),'revision':catalog['revision'],'catalog_sha256':prep.sha(raw)}


@contextmanager
def live_database(path):
    prep.canonical(path)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)) as c:
        c.execute('PRAGMA query_only=ON');start=time.monotonic()
        c.set_progress_handler(lambda:int(time.monotonic()-start>60),10000)
        yield c


def source_row(database,aid,source_root,kind):
    with live_database(database) as c:
        row=c.execute('SELECT path,mime,width,height,status FROM assets WHERE id=?',(aid,)).fetchone()
    if row is None or row[4] not in (None,'active'):return None
    path=Path(row[0]);direct_path(path)
    if not path.is_relative_to(source_root):raise ValueError('source_scope')
    prep.canonical(path);identity(path)
    current='photo' if (row[1] or '').startswith('image/') else 'video' if (row[1] or '').startswith('video/') else 'unsupported'
    if current!=kind:raise ValueError('source_kind_changed')
    return path,prep.sha(json.dumps(row).encode())


def connect(workspace,readonly=False):
    path=workspace/'state.sqlite'
    if path.exists():prep.canonical(path)
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2) if readonly else sqlite3.connect(path,timeout=2)
    c.row_factory=sqlite3.Row
    if readonly:c.execute('PRAGMA query_only=ON')
    else:c.execute('PRAGMA synchronous=FULL')
    return c


def meta(c,key,value=None):
    if value is None:
        row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None
    c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value)))


def seed_description(path,pin,kind):
    if kind not in ('legacy','library') or type(pin) is not str or len(pin)!=64:raise ValueError('invalid_seed')
    prep.canonical(path)
    name='journal.json' if kind=='legacy' else 'state.sqlite'
    if prep.file_hash(path/name,256*1024**2)!=pin:raise ValueError('seed_pin_mismatch')
    return {'path':str(path),'sha256':pin,'kind':kind}


class Seed:
    """A caller-reviewed immutable checkpoint hash is the provenance trust anchor."""
    def __init__(self,description,job,stack):
        self.path=Path(description['path']);self.description=description
        stack.enter_context(prep.workspace_lock(self.path))
        seed_description(self.path,description['sha256'],description['kind'])
        if description['kind']=='legacy':
            raw_state=bounded_read(self.path/'journal.json',MAX_CATALOG)
            if prep.sha(raw_state)!=description['sha256']:raise ValueError('seed_pin_mismatch')
            state=json.loads(raw_state,object_pairs_hook=unique);self.legacy=state['items'];self.c=None
            raw=bounded_read(self.path/'base.json',MAX_CATALOG);base=validate_catalog(json.loads(raw,object_pairs_hook=unique))
            fingerprint=state['fingerprint']
            expected={'base_sha256','database_path_sha256','source_root','script_sha256',
                      'ffmpeg_sha256','ffprobe_sha256','pillow_version','budget'}
            if set(fingerprint)!=expected:raise ValueError('seed_provenance_incomplete')
            for name in ('base_sha256','database_path_sha256','script_sha256','ffmpeg_sha256','ffprobe_sha256'):
                if type(fingerprint[name]) is not str or len(fingerprint[name])!=64:raise ValueError('seed_provenance_incomplete')
            profile(prep.Budget(**fingerprint['budget']))
            if (prep.sha(raw)!=fingerprint['base_sha256'] or fingerprint['source_root']!=job['source_root']
                    or fingerprint['database_path_sha256']!=prep.sha(job['database'].encode())):
                raise ValueError('seed_provenance_mismatch')
            self.ids={a['id']:a['kind'] for a in base['assets']}
            self.revision=base['revision']
        else:
            self.legacy=None;self.c=stack.enter_context(closing(connect(self.path,True)))
            old=read_json(self.path/'job.json',1024**2)
            if meta(self.c,'job_sha256')!=prep.sha((self.path/'job.json').read_bytes()):raise ValueError('seed_job_pin_mismatch')
            if old['database']!=job['database'] or old['source_root']!=job['source_root']:raise ValueError('seed_provenance_mismatch')
            if prep.sha(bounded_read(self.path/'base/catalog.json',MAX_CATALOG))!=old['base_sha256']:raise ValueError('seed_base_mismatch')
            self.revision=old['revision']
        if self.revision>=job['revision']:raise ValueError('revision_not_newer_than_seed')

    def item(self,aid,kind):
        if self.legacy is not None:
            value=self.legacy.get(str(aid))
            if not value or value['state']!='ready':return None
            if self.ids.get(aid)!=kind:raise ValueError('seed_kind_mismatch')
            directory=prep.attempt_path(self.path,value['directory'],aid)
            return directory,value['result']
        row=self.c.execute("SELECT * FROM items WHERE id=? AND status='ready'",(aid,)).fetchone()
        if not row:return None
        if row['kind']!=kind:raise ValueError('seed_kind_mismatch')
        return prep.attempt_path(self.path,row['directory'],aid),json.loads(row['result'])

    def verify_pin(self):
        seed_description(self.path,self.description['sha256'],self.description['kind'])


def create(database,source_root,workspace,ffmpeg,ffprobe,previous_publication,revision,
           budget=prep.Budget(),seed=None):
    for path in (database,source_root,ffmpeg,ffprobe,previous_publication):prep.canonical(path)
    direct_path(workspace);prep.canonical(workspace.parent)
    for path in (source_root,database,previous_publication)+((Path(seed['path']),) if seed else ()):
        if path.is_relative_to(workspace) or workspace.is_relative_to(path):raise ValueError('workspace_overlap')
    previous=publication_pin(previous_publication)
    if type(revision) is not int or not previous['revision']<revision<=2**31-1:raise ValueError('revision_not_new')
    budgets=profile(budget)
    workspace.mkdir(mode=0o700) # Never adopt a foreign/half-initialized directory.
    with prep.workspace_lock(workspace):
        exported=build_home_catalog.export(database,workspace/'base',revision)
        job={'version':SCHEMA,'database':str(database),'source_root':str(source_root),'revision':revision,
             'base_sha256':exported['catalog_sha256'],'previous':previous,'budget':budgets,'seed':seed,
             'ffmpeg':str(ffmpeg),'ffprobe':str(ffprobe),'ffmpeg_sha256':prep.file_hash(ffmpeg,256*1024**2),
             'ffprobe_sha256':prep.file_hash(ffprobe,256*1024**2),'pillow':importlib.metadata.version('Pillow'),'code':code_pin()}
        with ExitStack() as stack:
            if seed:Seed(seed,job,stack)
        prep.atomic_json(workspace/'job.json',job)
        catalog=read_json(workspace/'base/catalog.json')
        with closing(connect(workspace)) as c,c:
            c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            c.execute('CREATE TABLE items(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL,reason TEXT,source_hash TEXT,metadata_hash TEXT,directory TEXT,result TEXT,origin TEXT,attempts INTEGER NOT NULL DEFAULT 0)')
            c.executemany("INSERT INTO items(id,kind,status) VALUES(?,?,'pending')",[(a['id'],a['kind']) for a in catalog['assets']])
            meta(c,'job_sha256',prep.sha((workspace/'job.json').read_bytes()));meta(c,'status','created')
    return status(workspace)


def load_job(workspace):
    prep.canonical(workspace);job=read_json(workspace/'job.json',1024**2)
    if job['version']!=SCHEMA or job['code']!=code_pin() or job['pillow']!=importlib.metadata.version('Pillow'):
        raise ValueError('job_implementation_changed_use_fresh_job_and_pinned_carry')
    for name in ('ffmpeg','ffprobe'):
        if prep.file_hash(Path(job[name]),256*1024**2)!=job[name+'_sha256']:raise ValueError('tool_changed')
    if prep.sha(bounded_read(workspace/'base/catalog.json',MAX_CATALOG))!=job['base_sha256']:raise ValueError('base_changed')
    if publication_pin(Path(job['previous']['path']))!=job['previous']:raise ValueError('previous_publication_changed')
    profile(prep.Budget(**job['budget']))
    with closing(connect(workspace,True)) as c:
        if meta(c,'job_sha256')!=prep.sha((workspace/'job.json').read_bytes()):raise ValueError('job_changed')
    return job


def status(workspace):
    with closing(connect(workspace,True)) as c:
        counts=dict(c.execute('SELECT status,count(*) FROM items GROUP BY status').fetchall())
        reasons=dict(c.execute('SELECT reason,count(*) FROM items WHERE reason IS NOT NULL GROUP BY reason').fetchall())
        total=sum(counts.values());ready=counts.get('ready',0)
        verified_complete=(ready==total and meta(c,'status') in ('queue_drained','published_disabled') and bool(meta(c,'seed_verified')))
        return {'total':total,'ready':ready,'counts':counts,'reasons':reasons,'all_ready':ready==total,
                'verified_complete':verified_complete,
                'queue_drained':not (counts.get('pending',0)+counts.get('working',0)),'run_status':meta(c,'status'),
                'publication':meta(c,'publication'),'resources':meta(c,'resources')}


def validate_result(result,kind):
    if (type(result) is not dict or set(result)!= {'previews','video','source_sha256','seconds'}
            or type(result['source_sha256']) is not str or len(result['source_sha256'])!=64
            or (kind=='video')!=(result['video'] is not None)):
        raise ValueError('invalid_result')
    if result['video']:validate_video(result['video'])


def copy_file(source,target,guard):
    before=identity(source)
    if target.exists():
        if prep.file_hash(target,before[2])!=prep.file_hash(source,before[2]):raise ValueError('existing_copy_changed')
        return
    guard(force=True,extra_disk=before[2])
    handle,name=tempfile.mkstemp(prefix='.copy-',dir=target.parent)
    temporary=Path(name)
    with os.fdopen(handle,'wb') as dest,source.open('rb') as src:
        info=os.fstat(src.fileno())
        if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)!=before:raise ValueError('copy_source_changed')
        while True:
            chunk=src.read(4*1024**2)
            if not chunk:break
            guard()
            if shutil.disk_usage(target.parent).free<guard.reserve+len(chunk):raise JobStopped('copy_disk_pressure')
            dest.write(chunk)
        dest.flush();os.fsync(dest.fileno())
    if identity(source)!=before:raise ValueError('copy_source_changed')
    if target.exists():raise ValueError('copy_target_appeared')
    temporary.rename(target)


def copy_result(directory,target,result,guard):
    prep.canonical(directory);prep.verify_ready(directory,result)
    for name in ('grid.jpg','display.jpg')+(('video.mp4','video.chunks.json') if result['video'] else ()):
        copy_file(directory/name,target/name,guard)
    prep.verify_ready(target,result)


def precheck(source,kind,budget,directory,ffprobe,guard):
    info=identity(source)
    if info[2]>budget.input_bytes:return 'input_budget'
    if kind=='photo':
        from PIL import Image
        try:
            with Image.open(source) as image:
                if image.width*image.height>budget.pixels:return 'pixel_budget'
                if image.format not in ('JPEG','PNG'):return 'photo_format_profile'
                if getattr(image,'n_frames',1)!=1:return 'animation_profile'
        except (Image.DecompressionBombError,Image.DecompressionBombWarning):return 'pixel_budget'
    elif kind=='video':
        if source.suffix.lower() not in ('.mp4','.mov'):return 'container_profile'
        probe=prep.probe(ffprobe,source,directory,budget,guard=guard)
        videos=[s for s in probe.get('streams',[]) if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic')]
        if len(videos)!=1:return 'stream_layout_profile'
        video=videos[0];duration=float(probe['format']['duration'])
        if not math.isfinite(duration) or duration<=0:raise ValueError('bad_duration')
        if duration>budget.duration_seconds:return 'duration_budget'
        if video.get('color_transfer') in ('smpte2084','arib-std-b67'):return 'hdr_tonemap_profile'
        if video.get('pix_fmt') not in ('yuv420p','yuvj420p'):return 'pixel_format_profile'
        if int(video.get('width',0))*int(video.get('height',0))>budget.pixels:return 'pixel_budget'
        if video.get('sample_aspect_ratio') not in (None,'1:1'):return 'pixel_aspect_profile'
    else:return 'media_kind_profile'
    return None


def mark(c,aid,status,reason=None):
    with c:c.execute('UPDATE items SET status=?,reason=? WHERE id=?',(status,reason,aid))


def complete(c,aid,result,origin):
    with c:c.execute("UPDATE items SET status='ready',reason=NULL,result=?,source_hash=?,origin=? WHERE id=?",
                     (json.dumps(result),result['source_sha256'],json.dumps(origin),aid))


def run(workspace,retry_errors=False,max_items=None,max_seconds=None,guard=None):
    if any(v is not None and (type(v) is not int or v<1) for v in (max_items,max_seconds)):raise ValueError('invalid_run_limit')
    job=load_job(workspace);budget=prep.Budget(**job['budget'])
    guard=guard or Guard(workspace,budget.reserve_bytes,max_seconds=max_seconds)
    database=Path(job['database']);source_root=Path(job['source_root']);ffmpeg=Path(job['ffmpeg']);ffprobe=Path(job['ffprobe'])
    processed=0
    with prep.workspace_lock(workspace),ExitStack() as stack,closing(connect(workspace)) as c:
        if meta(c,'publication') or meta(c,'publication_build'):raise ValueError('publication_job_is_frozen_create_new_revision')
        seed=Seed(job['seed'],job,stack) if job['seed'] else None
        with c:meta(c,'status','running');meta(c,'seed_verified',False)
        try:
            for entry in c.execute('SELECT id,kind FROM items ORDER BY id DESC').fetchall():
                aid,kind=entry;guard(force=True,extra_disk=budget.output_bytes+14*1024**2)
                item=c.execute('SELECT * FROM items WHERE id=?',(aid,)).fetchone()
                if max_items is not None and processed>=max_items:raise JobStopped('qualification_item_limit')
                try:
                    row=source_row(database,aid,source_root,kind)
                    if row is None:mark(c,aid,'excluded','visibility_changed');continue
                    source,metadata_hash=row
                    if item['status'] in ('error','deferred') and not retry_errors:continue
                    if item['status'] in ('ready','working') and item['directory']:
                        directory=prep.attempt_path(workspace,item['directory'],aid)
                        receipt=directory/'receipt.json'
                        value=read_json(receipt,1024**2) if receipt.exists() else None
                        if value and value['job_sha256']==meta(c,'job_sha256') and value['metadata_hash']==metadata_hash:
                            result=value['result'];validate_result(result,kind)
                            if prep.file_hash(source,max(budget.input_bytes,identity(source)[2]))==result['source_sha256']:
                                prep.verify_ready(directory,result)
                                complete(c,aid,result,value['origin']);continue
                        if item['status']=='ready' and not value:raise ValueError('ready_receipt_missing')
                    # Pin each attempt before work. A verified receipt permits crash recovery
                    # between file completion and the SQLite ready transaction.
                    directory=Path(tempfile.mkdtemp(prefix=f'asset-{aid}-',dir=workspace))
                    with c:c.execute("UPDATE items SET status='working',reason=NULL,directory=?,metadata_hash=?,result=NULL,attempts=attempts+1 WHERE id=?",(directory.name,metadata_hash,aid))
                    result=None;origin={'kind':'prepared'}
                    inherited=seed.item(aid,kind) if seed else None
                    if inherited:
                        seed_directory,old_result=inherited;validate_result(old_result,kind)
                        if prep.file_hash(source,max(budget.input_bytes,identity(source)[2]))==old_result['source_sha256']:
                            copy_result(seed_directory,directory,old_result,guard)
                            result=old_result;origin={'kind':'carry','seed_sha256':job['seed']['sha256'],'seed_revision':seed.revision}
                    if result is None:
                        reason=precheck(source,kind,budget,directory,ffprobe,guard)
                        if reason:mark(c,aid,'deferred',reason);processed+=1;continue
                        result=prep.prepare_one(source,kind,directory,ffmpeg,ffprobe,budget,guard=guard)
                    validate_result(result,kind);prep.verify_ready(directory,result)
                    if source_row(database,aid,source_root,kind)!=(source,metadata_hash):raise ValueError('source_changed_during_attempt')
                    if prep.file_hash(source,max(budget.input_bytes,identity(source)[2]))!=result['source_sha256']:raise ValueError('source_changed_during_attempt')
                    prep.atomic_json(directory/'receipt.json',{'job_sha256':meta(c,'job_sha256'),'metadata_hash':metadata_hash,'result':result,'origin':origin})
                    complete(c,aid,result,origin);processed+=1
                except JobStopped:raise
                except FileNotFoundError:mark(c,aid,'error','source_missing');processed+=1
                except prep.PreparationError as error:
                    mark(c,aid,'deferred' if error.reason=='unsupported' else 'error','profile_review' if error.reason=='unsupported' else 'preparation_failed');processed+=1
                except (OSError,ValueError,KeyError,TypeError,Refused):
                    mark(c,aid,'error','verification_failed');processed+=1
            if seed:seed.verify_pin()
            with c:meta(c,'status','queue_drained');meta(c,'seed_verified',True)
        except (JobStopped,KeyboardInterrupt) as error:
            with c:meta(c,'status',str(error) if isinstance(error,JobStopped) else 'interrupted')
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,Refused):
            with c:meta(c,'status','job_verification_failed')
            raise
        finally:
            with c:meta(c,'resources',guard.summary())
    return status(workspace)


def publish(workspace,output,allow_partial=False,guard=None):
    job=load_job(workspace);direct_path(output);prep.canonical(output.parent)
    for p in (workspace,Path(job['source_root']),Path(job['database']),Path(job['previous']['path'])):
        if output.is_relative_to(p) or p.is_relative_to(output):raise ValueError('publication_overlap')
    budget=prep.Budget(**job['budget']);guard=guard or Guard(workspace,budget.reserve_bytes)
    with prep.workspace_lock(workspace),closing(connect(workspace)) as c, publication_status(c,guard):
        if meta(c,'publication'):raise ValueError('published_job_is_immutable')
        if job['seed'] and not meta(c,'seed_verified'):raise ValueError('seed_run_not_verified')
        building=meta(c,'publication_build')
        if output.exists() and (not building or building['path']!=str(output)):raise ValueError('publication_exists')
        guard(force=True)
        # Current visible metadata must match the pinned full snapshot. A scope
        # change requires a fresh job/revision with pinned carry, never stale media.
        check=Path(tempfile.mkdtemp(prefix='scope-',dir=workspace))/'base'
        current=build_home_catalog.export(Path(job['database']),check,job['revision'])
        if current['catalog_sha256']!=job['base_sha256']:raise ValueError('scope_changed_create_fresh_job_with_carry')
        catalog=read_json(workspace/'base/catalog.json');ready=[];total=0
        for asset in catalog['assets']:
            item=c.execute('SELECT * FROM items WHERE id=?',(asset['id'],)).fetchone()
            if item['status']=='ready':
                row=source_row(Path(job['database']),asset['id'],Path(job['source_root']),asset['kind'])
                result=json.loads(item['result']);validate_result(result,asset['kind'])
                if row is None or row[1]!=item['metadata_hash'] or prep.file_hash(row[0],max(budget.input_bytes,identity(row[0])[2]))!=result['source_sha256']:raise ValueError('source_changed')
                directory=prep.attempt_path(workspace,item['directory'],asset['id'])
                receipt=read_json(directory/'receipt.json',1024**2)
                if (receipt['job_sha256']!=meta(c,'job_sha256') or receipt['result']!=result
                        or receipt['metadata_hash']!=item['metadata_hash']):raise ValueError('receipt_mismatch')
                prep.verify_ready(directory,result)
                asset.update(previews=result['previews'],video=result['video'])
                total+=sum(m['bytes'] for m in result['previews'].values())+(result['video']['bytes'] if result['video'] else 0)
                ready.append((asset['id'],directory,result));guard(force=True)
            else:
                if not allow_partial:raise ValueError('library_not_all_ready')
                reason='source_missing' if item['reason']=='source_missing' else 'preparation_failed' if item['status']=='error' else 'not_prepared'
                asset['previews']={name:{'state':'unavailable','reason':reason} for name in LIMITS}
                if asset['kind']=='video':asset['video']={'state':'unavailable','reason':reason}
        validate_catalog(catalog)
        raw=json.dumps(catalog,separators=(',',':')).encode()
        if len(raw)>MAX_CATALOG:raise ValueError('catalog_too_large')
        owner={'path':str(output),'job_sha256':meta(c,'job_sha256'),'catalog_sha256':prep.sha(raw)}
        if building and building!=owner:raise ValueError('publication_resume_mismatch')
        if shutil.disk_usage(output.parent).free<total+len(raw)+budget.reserve_bytes:raise JobStopped('publication_disk_pressure')
        if not building:
            with c:meta(c,'publication_build',owner);meta(c,'status','publishing_disabled')
        if not output.exists():
            output.mkdir(mode=0o700);prep.atomic_json(output/'build-owner.json',owner)
        else:
            prep.canonical(output)
            if read_json(output/'build-owner.json',4096)!=owner:raise ValueError('publication_owner_mismatch')
        expected_control={'version':2,'enabled':False,'revision':job['revision'],'catalog_sha256':prep.sha(raw)}
        if (output/'control.json').exists() and read_json(output/'control.json',4096)!=expected_control:
            raise ValueError('publication_control_changed')
        for name in ('grid','display','video'):
            folder=output/'prepared'/name
            folder.mkdir(parents=True,exist_ok=True);prep.canonical(folder)
        for aid,directory,result in ready:
            for variant in LIMITS:
                target=output/'prepared'/variant/f'{aid}.jpg';copy_file(directory/f'{variant}.jpg',target,guard)
                if prep.file_hash(target,result['previews'][variant]['bytes'])!=result['previews'][variant]['sha256']:raise ValueError('copy_hash_mismatch')
            if result['video']:
                for suffix,key in (('mp4','sha256'),('chunks.json','chunks_sha256')):
                    target=output/'prepared/video'/f'{aid}.{suffix}';copy_file(directory/f'video.{suffix}',target,guard)
                    if prep.file_hash(target,MAX_VIDEO if suffix=='mp4' else 1024**2)!=result['video'][key]:raise ValueError('copy_hash_mismatch')
        final=Path(tempfile.mkdtemp(prefix='scope-final-',dir=workspace))/'base'
        if build_home_catalog.export(Path(job['database']),final,job['revision'])['catalog_sha256']!=job['base_sha256']:raise ValueError('scope_changed_during_publication')
        if (output/'catalog.json').exists():
            if bounded_read(output/'catalog.json',MAX_CATALOG)!=raw:raise ValueError('publication_catalog_changed')
        else:(output/'catalog.json').write_bytes(raw)
        if not (output/'control.json').exists():prep.atomic_json(output/'control.json',expected_control)
        result={'path':str(output),'revision':job['revision'],'catalog_sha256':prep.sha(raw),'enabled':False,'ready':len(ready),'total':len(catalog['assets'])}
        with c:meta(c,'publication',result);meta(c,'publication_build',False);meta(c,'status','published_disabled')
    return result


@contextmanager
def publication_status(c,guard):
    frozen=bool(meta(c,'publication'))
    try:yield
    except (JobStopped,KeyboardInterrupt) as error:
        if not frozen:
            with c:meta(c,'status',str(error) if isinstance(error,JobStopped) else 'publication_interrupted')
        raise
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,Refused):
        if not frozen:
            with c:meta(c,'status','publication_verification_failed')
        raise
    finally:
        if not frozen:
            with c:meta(c,'resources',guard.summary())


def main(argv=None):
    if os.name!='nt':
        try:os.nice(10)
        except OSError:pass
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('create')
    for name in ('database','source-root','workspace','ffmpeg','ffprobe','previous-publication'):init.add_argument('--'+name,type=Path,required=True)
    init.add_argument('--revision',type=int,required=True);init.add_argument('--budget-json',type=Path)
    init.add_argument('--carry-workspace',type=Path);init.add_argument('--carry-sha256');init.add_argument('--carry-kind',choices=('legacy','library'))
    run_parser=sub.add_parser('run');run_parser.add_argument('--workspace',type=Path,required=True)
    run_parser.add_argument('--retry-errors',action='store_true');run_parser.add_argument('--max-items',type=int);run_parser.add_argument('--max-seconds',type=int)
    stat=sub.add_parser('status');stat.add_argument('--workspace',type=Path,required=True)
    pub=sub.add_parser('publish');pub.add_argument('--workspace',type=Path,required=True);pub.add_argument('--output',type=Path,required=True);pub.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.command=='create':
            seed=None
            if any((args.carry_workspace,args.carry_sha256,args.carry_kind)):
                if not all((args.carry_workspace,args.carry_sha256,args.carry_kind)):raise ValueError('all_carry_fields_required')
                seed=seed_description(args.carry_workspace,args.carry_sha256,args.carry_kind)
            budget=prep.Budget(**read_json(args.budget_json,4096)) if args.budget_json else prep.Budget()
            result=create(args.database,args.source_root,args.workspace,args.ffmpeg,args.ffprobe,args.previous_publication,args.revision,budget,seed)
        elif args.command=='run':result=run(args.workspace,args.retry_errors,args.max_items,args.max_seconds)
        elif args.command=='status':result=status(args.workspace)
        else:result=publish(args.workspace,args.output,args.allow_partial)
        print(json.dumps(result))
        return 0 if args.command!='run' or result['verified_complete'] else 3
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,prep.PreparationError,Refused,JobStopped):
        print('Preparation job refused or stopped; inspect private status. No live publication changed.',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
