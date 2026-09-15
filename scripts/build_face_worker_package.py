#!/usr/bin/env python3
"""Build a fixed, source-only face assignment worker ZIP from an explicit local commit.

No .env, credentials, database, media, model weights, environment, HTTP entry
point, migrations, extraction, deployment or service control in this package.
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
    *('backend/app/'+name+'.py' for name in ('__init__','db','scoped_face_worker')),
    *('backend/app/access/'+name+'.py' for name in (
        '__init__','face_jobs','provisioning','service','credentials')),
    'scripts/run_face_worker.py', 'docs/security/FACE_JOB_CONTROL.md',
    'docs/security/SCOPED_FACE_WORKER.md',
]))


def git(*args):
    return subprocess.check_output(['git',*args], cwd=ROOT, stderr=subprocess.DEVNULL)


def source_files(commit):
    if not re.fullmatch('[0-9a-f]{40}',commit) or git('cat-file','-t',commit).strip()!=b'commit':
        raise ValueError('Explicit immutable local commit required')
    entries = {}
    for row in filter(None,git('ls-tree','-r','-z',commit,'--',*FILES).split(b'\0')):
        identity,name = row.split(b'\t',1)
        mode,kind,oid = identity.decode('ascii').split()
        if mode not in ('100644','100755') or kind!='blob':
            raise ValueError('Regular source blobs required')
        entries[name.decode('utf-8')] = oid
    if set(entries)!=set(FILES):
        raise ValueError('Worker source files missing')
    sizes = [int(git('cat-file','-s',oid)) for oid in entries.values()]
    if any(size>512_000 for size in sizes) or sum(sizes)>2_000_000:
        raise ValueError('Worker source budget exceeded')
    return {name:git('cat-file','blob',entries[name]) for name in FILES}


def package_bytes(commit, files):
    if not re.fullmatch('[0-9a-f]{40}',commit) or set(files)!=set(FILES):
        raise ValueError('Exact worker source manifest required')
    manifest = {'format_version':1,'source_commit':commit,'artifact_kind':'face_assignment_worker_source_only',
        'activated':False,'dependencies_included':False,'private_configuration_included':False,
        'http_listener_included':False,
        'files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}}
    output = io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
        for name,data in [*sorted(files.items()),('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())]:
            info = zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.create_system=3; info.external_attr=0o100644 << 16
            archive.writestr(info,data)
    return output.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if (not args.out.is_absolute() or '..' in args.out.parts
                or args.out.parent.resolve(strict=True)!=args.out.parent):
            raise ValueError('Explicit direct output required')
        data = package_bytes(args.commit,source_files(args.commit))
        flags = os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        with os.fdopen(os.open(args.out,flags,0o600),'wb') as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
        print(json.dumps({'source_commit':args.commit,'files':len(FILES),'bytes':len(data),
                          'sha256':hashlib.sha256(data).hexdigest(),'activated':False}))
        return 0
    except Exception:
        print('Worker packaging refused; existing output was not overwritten.')
        return 2


if __name__=='__main__':
    raise SystemExit(main())
