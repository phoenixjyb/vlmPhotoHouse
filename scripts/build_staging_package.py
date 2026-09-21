#!/usr/bin/env python3
"""Build a source-only staging ZIP from an explicit immutable local Git commit.

Fixed file allowlist; no working-tree/config/data/venv discovery, dependency install,
network, extraction or deployment. The output hash must be reviewed separately.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = tuple(sorted([
    'backend/app/__init__.py', 'backend/app/main.py', 'backend/app/db.py',
    'backend/app/routers/ui.py', 'backend/app/ui/photohouse-icon.png',
    *('backend/app/access/'+name+'.py' for name in (
        '__init__','schema','provisioning','admission','runtime','provisioning_apply',
        'transport','credentials','members','recovery','owner_recovery','library','metadata','media',
        'boundary','service','bootstrap','stories','story_schema','people','management_schema','albums','management_import','face_jobs',
        'ownership_repair','tags',
        'discovery','discovery_provider','discovery_transport','discovery_index')),
    *('backend/app/access/'+name+'.py' for name in (
        'upload','upload_schema','upload_transport','duplicates','captions',
        'promotion','task_recovery','upload_review')),
    *('backend/app/ui/access/'+name for name in ('index.html','app.js','styles.css')),
    'backend/migrations/env.py', 'backend/alembic.ini',
    *('backend/migrations/versions/'+name+'.py' for name in (
        '0001_initial','402a07259e4a_sqlalchemy2_typing_refactor','5b6b4d1c2a3f_task_progress_cancel',
        '6f2a8c1d9b7e_embedding_metadata','7c1c2d4e5f6a_task_timing_columns',
        '8a2f1c3d4b5e_captions_multi_variants','9b1e7d2a5c6f_caption_status_and_variant_meta',
        'a1c9d4e5f8b2_face_assignment_events','a5d2e8f4b610_legacy_read_schema',
        'b6e3f9a5c721_offline_receipts','c7f4a9e2b610_family_stories','c4e7a2d9f1b3_versioned_face_embeddings',
        'd8e5b2f7a904_library_management','f2a6d8b4c915_protected_upload',
        'd2b7e4f6a901_album_drafts','e3a9b1c7d402_access_foundation','f4c1a8d2e703_access_admission')),
    'scripts/staging_app.py', 'scripts/provision_access.py', 'scripts/prepare_access_database.py',
    'scripts/prepare_access_discovery_index.py', 'scripts/prepare_access_places.py',
    'docs/security/PLACE_BROWSING_V24.md', 'docs/security/PLACE_REFRESH_V25.md',
    'scripts/check_access_environment.py', 'scripts/rehearse_fullsize_database.py',
    'scripts/apply_access_schema.py', 'docs/security/SCHEMA_APPLICATION.md',
    'backend/app/photo_delivery.py', 'backend/app/home_feed.py',
    'backend/app/home_catalog.py', 'backend/app/access/prepared_video.py',
    'scripts/export_protected_videos.py', 'docs/security/PROTECTED_PREPARED_MEDIA.md',
    'scripts/home_media_worker.py', 'scripts/home_preparation_resources.py',
    'backend/requirements-home-preparation.lock',
    'docs/security/ON_DEMAND_MEDIA.md',
    'backend/requirements-access.in', 'backend/requirements-access.lock',
    'backend/requirements-access-test.in', 'backend/requirements-access-test.lock',
    'docs/security/CPU_ENVIRONMENT.md', 'docs/security/PROTECTED_UPGRADE.md',
    'docs/security/staging-config.example.json', 'docs/security/OPERATOR_TOOL.md',
    'docs/security/DATABASE_PREPARATION.md', 'docs/security/FULLSIZE_REHEARSAL.md',
    'docs/security/CAPTION_WORKER.md', 'docs/security/OWNER_RECOVERY.md', 'docs/FAMILY_STORIES.md',
    'docs/security/ADMIN_UPLOAD_REVIEW.md', 'docs/security/OWNER_PEOPLE_REVIEW.md', 'docs/security/OWNER_FACE_ASSIGNMENT.md',
    'docs/security/OWNER_SETUP_GATE.md', 'docs/security/LIBRARY_MANAGEMENT.md',
    'docs/security/MANAGEMENT_IMPORT.md',
    'docs/security/OWNERSHIP_REPAIR.md',
    'docs/security/SCOPED_FACE_WORKER.md', 'docs/security/FACE_WORKER_QUALIFICATION.md',
    'backend/app/scoped_face_worker.py', 'docs/security/FACE_JOB_CONTROL.md',
]))


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.DEVNULL)


def source_files(commit):
    if not re.fullmatch('[0-9a-f]{40}',commit) or git('cat-file','-t',commit).strip() != b'commit':
        raise ValueError('Explicit full commit required')
    records = git('ls-tree','-r','-z','--full-tree',commit,'--',*FILES).split(b'\0')
    entries = {}
    for record in filter(None,records):
        identity,name = record.split(b'\t',1)
        mode,kind,oid = identity.decode('ascii').split()
        if mode not in ('100644','100755') or kind != 'blob':
            raise ValueError('Only regular source blobs are allowed')
        entries[name.decode('utf-8')] = oid
    if set(entries) != set(FILES):
        raise ValueError('Selected commit lacks required source files')
    sizes = {name:int(git('cat-file','-s',oid)) for name,oid in entries.items()}
    if any(size > 2_000_000 for size in sizes.values()) or sum(sizes.values()) > 16_000_000:
        raise ValueError('Source package size exceeded')
    return {name:git('cat-file','blob',entries[name]) for name in FILES}


def package_bytes(commit, files):
    if set(files) != set(FILES):
        raise ValueError('Exact source allowlist required')
    manifest = {'format_version':1,'source_commit':commit,'artifact_kind':'source_only_not_deployed',
        'migration_revision':'f2a6d8b4c915','dependencies_included':False,'private_configuration_included':False,
        'files':{name:hashlib.sha256(files[name]).hexdigest() for name in FILES}}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
        for name,data in [*sorted(files.items()),('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())]:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.create_system=3; info.external_attr=0o100644 << 16
            archive.writestr(info,data)
    return output.getvalue()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        if (not args.out.is_absolute() or '..' in args.out.parts
                or args.out.parent.resolve(strict=True) != args.out.parent):
            raise ValueError('Explicit direct output required')
        data=package_bytes(args.commit,source_files(args.commit))
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        with os.fdopen(os.open(args.out,flags,0o600),'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        print(json.dumps({'source_commit':args.commit,'source_files':len(FILES),
            'zip_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'deployed':False}))
        return 0
    except (ValueError,OSError,subprocess.CalledProcessError):
        print('Source packaging refused; no existing output was overwritten.')
        return 2


if __name__=='__main__':
    raise SystemExit(main())
