#!/usr/bin/env python3
"""Offline, explicit-ID, resumable preparation. Never modifies a live publication.

A workspace owns checkpoints/derivatives. Publishing creates a NEW disabled
publication from the fixed base catalog. No service, network, jobs or DB writes.
"""
import argparse
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from fractions import Fraction
import hashlib
import importlib.metadata
import io
import json
import math
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.home_catalog import CHUNK_BYTES, MAX_CATALOG, identity, validate_catalog, validate_video
from app.home_feed import LIMITS, Refused, bounded_read, direct_path, integer, jpeg_dimensions, unique


class PreparationError(Exception):
    def __init__(self, reason='preparation_failed'): self.reason = reason


@dataclass(frozen=True)
class Budget:
    input_bytes: int = 512 * 1024**2
    output_bytes: int = 64 * 1024**2
    pixels: int = 40000000
    duration_seconds: int = 60
    asset_seconds: int = 180
    process_seconds: int = 120
    reserve_bytes: int = 2 * 1024**3


def canonical(path):
    direct_path(path)
    if path.resolve(strict=True) != path: raise PreparationError('unsupported')
    return path


def sha(data): return hashlib.sha256(data).hexdigest()


def file_hash(path, maximum):
    pin = identity(path)
    if not 0 < pin[2] <= maximum: raise PreparationError('unsupported')
    total = hashlib.sha256(); start = time.monotonic()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(CHUNK_BYTES), b''):
            if time.monotonic()-start > 60: raise PreparationError()
            total.update(data)
    if identity(path) != pin: raise PreparationError()
    return total.hexdigest()


def atomic_json(path, value):
    raw = json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()
    temporary = path.with_name(path.name+'.new')
    if temporary.is_symlink(): raise PreparationError()
    with temporary.open('wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


@contextmanager
def workspace_lock(root):
    path = root/'prepare.lock'
    if path.is_symlink(): raise PreparationError()
    with path.open('a+b') as stream:
        stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def run_process(args, directory, budget, output=None):
    """One child, no shell, one CPU thread requested by codec args, bounded logs/time.

    Windows BELOW_NORMAL priority; POSIX lower priority via os.nice in the worker
    entrypoint. Kill/wait only this owned child on timeout/output/log failure.
    """
    flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 0
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen([str(a) for a in args], stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, cwd=directory, creationflags=flags)
        start = time.monotonic()
        try:
            while process.poll() is None:
                if (time.monotonic()-start > budget.process_seconds
                        or os.fstat(stdout.fileno()).st_size > 2*1024**2
                        or os.fstat(stderr.fileno()).st_size > 65536
                        or (output is not None and output.exists() and output.stat().st_size > budget.output_bytes)
                        or shutil.disk_usage(directory).free < budget.reserve_bytes):
                    raise PreparationError()
                time.sleep(0.05)
            if process.returncode: raise PreparationError()
            if os.fstat(stdout.fileno()).st_size > 2*1024**2 or os.fstat(stderr.fileno()).st_size > 65536:
                raise PreparationError()
            stdout.seek(0); return stdout.read(2*1024**2+1)
        finally:
            if process.poll() is None: process.kill()
            process.wait()


def probe(binary, source, directory, budget):
    raw = run_process([binary, '-v', 'error', '-protocol_whitelist', 'file', '-f', 'mov', '-enable_drefs', '0', '-use_absolute_path', '0', '-export_all', '1', '-export_xmp', '1', '-show_streams', '-show_format', '-show_chapters',
                       '-of', 'json', source], directory, budget)
    return json.loads(raw, object_pairs_hook=unique)


def normalized_probe(value, expected_duration):
    streams = value.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    if len(videos) != 1 or len(audios) > 1 or len(videos)+len(audios) != len(streams) or value.get('chapters'):
        raise PreparationError()
    v = videos[0]; duration = float(value['format']['duration'])
    if (v.get('codec_name') != 'h264' or v.get('profile') not in ('Constrained Baseline', 'Baseline', 'Main', 'High')
            or v.get('pix_fmt') != 'yuv420p' or not 0 < int(v.get('level', 999)) <= 41
            or not 0 < Fraction(v.get('avg_frame_rate', '0')) <= 30
            or v.get('sample_aspect_ratio') not in ('1:1', None)
            or not math.isfinite(duration) or abs(duration-expected_duration) > max(0.25, expected_duration*.02)
            or any(a.get('codec_name') != 'aac' or a.get('profile') != 'LC' for a in audios)):
        raise PreparationError()
    # Standard muxer/codec descriptors only. No user tags, timestamps, GPS or display matrix.
    allowed_format = {'major_brand', 'minor_version', 'compatible_brands', 'encoder'}
    allowed_stream = {'language', 'handler_name', 'vendor_id', 'encoder'}
    if set(value['format'].get('tags', {}))-allowed_format: raise PreparationError()
    for stream in streams:
        if set(stream.get('tags', {}))-allowed_stream or stream.get('side_data_list'):
            raise PreparationError()
        tags = stream.get('tags', {})
        if tags.get('language', 'und') != 'und' or stream.get('disposition', {}).get('attached_pic', 0):
            raise PreparationError()
        if tags.get('handler_name', 'VideoHandler') not in ('VideoHandler','SoundHandler'):
            raise PreparationError()
    return v, duration, 'aac' if audios else None


def faststart(path):
    """Check top-level BMFF boxes: moov must precede mdat, no trailing partial box."""
    size = path.stat().st_size; offset = 0; boxes = []
    with path.open('rb') as stream:
        while offset < size:
            stream.seek(offset); header = stream.read(16)
            if len(header) < 8: raise PreparationError()
            length = int.from_bytes(header[:4], 'big'); kind = header[4:8]
            minimum = 8
            if length == 1: length = int.from_bytes(header[8:16], 'big'); minimum = 16
            elif length == 0: length = size-offset
            if length < minimum or offset+length > size: raise PreparationError()
            boxes.append(kind); offset += length
            if len(boxes) > 64: raise PreparationError()
    if not boxes or boxes[0] != b'ftyp' or boxes.count(b'moov') != 1 or b'mdat' not in boxes or boxes.index(b'moov') > boxes.index(b'mdat'):
        raise PreparationError()


def photo_worker(source, output, pixel_limit):
    from PIL import Image, ImageOps, ImageCms
    Image.MAX_IMAGE_PIXELS = pixel_limit
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    with Image.open(source) as image:
        if image.format not in ('JPEG', 'PNG') or getattr(image, 'n_frames', 1) != 1:
            raise PreparationError('unsupported')
        if image.width*image.height > pixel_limit: raise PreparationError('unsupported')
        image.load(); upright = ImageOps.exif_transpose(image)
        icc = image.info.get('icc_profile')
        if icc:
            if len(icc)>1024**2: raise PreparationError('unsupported')
            upright=ImageCms.profileToProfile(upright,ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                ImageCms.createProfile('sRGB'),outputMode='RGBA' if 'A' in upright.mode else 'RGB')
        # Flatten alpha on black. Avoid full-size alpha buffers for opaque originals.
        if 'A' in upright.mode or 'transparency' in upright.info:
            rgba=upright.convert('RGBA');canvas=Image.new('RGBA',rgba.size,(0,0,0,255))
            canvas.alpha_composite(rgba);rgb=canvas.convert('RGB')
        else: rgb=upright.convert('RGB')
        for variant, (edge, pixels, maximum) in LIMITS.items():
            derivative = rgb.copy()
            factor = min(1, edge/derivative.width, edge/derivative.height,
                         math.sqrt(pixels/(derivative.width*derivative.height)))
            derivative.thumbnail((max(1,int(derivative.width*factor)), max(1,int(derivative.height*factor))), Image.Resampling.LANCZOS)
            clean = Image.frombytes('RGB', derivative.size, derivative.tobytes())
            clean.save(output/f'{variant}.jpg', 'JPEG', quality=86, progressive=False, optimize=False, exif=b'')


def previews(directory):
    result = {}
    for variant, (_, _, maximum) in LIMITS.items():
        data = bounded_read(directory/f'{variant}.jpg', maximum)
        width, height = jpeg_dimensions(data)
        result[variant] = {'state':'ready','width':width,'height':height,'bytes':len(data),'sha256':sha(data)}
    return result


def prepare_one(source, kind, output, ffmpeg, ffprobe, budget):
    began = time.monotonic(); before = identity(source)
    def remaining():
        seconds = int(budget.asset_seconds-(time.monotonic()-began))
        if seconds < 1: raise PreparationError()
        return replace(budget,process_seconds=min(budget.process_seconds,seconds))
    source_hash = file_hash(source, budget.input_bytes)
    if kind == 'photo':
        run_process([sys.executable, Path(__file__).resolve(), '_photo', source, output, str(budget.pixels)], output, remaining())
        result = {'previews':previews(output),'video':None}
    elif kind == 'video':
        if source.suffix.lower() not in ('.mp4','.mov'): raise PreparationError('unsupported')
        original = probe(ffprobe, source, output, remaining())
        duration = float(original['format']['duration'])
        videos = [s for s in original.get('streams', []) if s.get('codec_type') == 'video' and not s.get('disposition',{}).get('attached_pic')]
        if (not math.isfinite(duration) or not 0 < duration <= budget.duration_seconds or len(videos) != 1
                or int(videos[0].get('width', 0))*int(videos[0].get('height', 0)) > budget.pixels
                or videos[0].get('pix_fmt') not in ('yuv420p','yuvj420p')
                or videos[0].get('sample_aspect_ratio') not in (None,'1:1')
                or videos[0].get('color_transfer') in ('smpte2084','arib-std-b67')):
            raise PreparationError('unsupported')
        target = output/'video.mp4'
        args = [ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-n','-threads','1','-filter_threads','1','-hwaccel','none','-protocol_whitelist','file','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',source,
                '-map',f"0:{videos[0]['index']}",'-map','0:a:0?','-map_metadata','-1','-map_metadata:s','-1','-map_chapters','-1','-sn','-dn',
                '-vf',"scale=w='min(1920,iw)':h='min(1080,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,fps=30,format=yuv420p",
                '-c:v','libx264','-threads','1','-preset','fast','-crf','23','-profile:v','high','-level:v','4.1',
                '-c:a','aac','-b:a','128k','-ac','2','-ar','48000',
                '-metadata:s:v:0','handler_name=VideoHandler','-metadata:s:a:0','handler_name=SoundHandler',
                '-metadata:s','language=und','-movflags','+faststart','-fs',str(budget.output_bytes),target]
        run_process(args, output, remaining(), target)
        v, actual_duration, audio = normalized_probe(probe(ffprobe,target,output,remaining()), duration)
        faststart(target)
        # Full bounded decode, not merely an ffprobe/header success.
        run_process([ffmpeg,'-v','error','-xerror','-nostdin','-threads','1','-protocol_whitelist','file','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',target,'-f','null','-'], output, remaining())
        frame = output/'poster.png'
        run_process([ffmpeg,'-v','error','-nostdin','-n','-threads','1','-protocol_whitelist','file','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',target,'-frames:v','1','-threads','1',frame], output, remaining())
        run_process([sys.executable, Path(__file__).resolve(), '_photo', frame, output, str(budget.pixels)], output, remaining())
        video_hash = file_hash(target, budget.output_bytes); hashes = []
        with target.open('rb') as stream:
            for chunk in iter(lambda: stream.read(CHUNK_BYTES), b''): hashes.append(sha(chunk))
        chunk_bytes = json.dumps(hashes).encode(); (output/'video.chunks.json').write_bytes(chunk_bytes)
        video = {'state':'ready','mime':'video/mp4','video_codec':'h264','audio_codec':audio,
                 'width':v['width'],'height':v['height'],'duration_ms':round(actual_duration*1000),
                 'bytes':target.stat().st_size,'sha256':video_hash,'chunks_sha256':sha(chunk_bytes)}
        validate_video(video); result = {'previews':previews(output),'video':video}
    else: raise PreparationError('unsupported')
    if identity(source) != before or file_hash(source,budget.input_bytes) != source_hash: raise PreparationError()
    remaining()
    result.update(source_sha256=source_hash,seconds=round(time.monotonic()-began,3))
    return result


def verify_ready(directory, result):
    if previews(directory) != result['previews']: raise PreparationError()
    if result['video']:
        video = result['video']; validate_video(video)
        if file_hash(directory/'video.mp4', video['bytes']) != video['sha256']: raise PreparationError()
        raw = bounded_read(directory/'video.chunks.json',1024**2)
        if sha(raw) != video['chunks_sha256']: raise PreparationError()
        hashes = json.loads(raw)
        with (directory/'video.mp4').open('rb') as stream:
            actual = [sha(chunk) for chunk in iter(lambda:stream.read(CHUNK_BYTES),b'')]
        if actual != hashes: raise PreparationError()


def run(database, source_root, base_catalog, workspace, asset_ids, ffmpeg, ffprobe, budget=Budget(), retry_failed=False):
    for path in (database,source_root,base_catalog,ffmpeg,ffprobe): canonical(path)
    direct_path(workspace)
    if (workspace.is_relative_to(source_root) or source_root.is_relative_to(workspace)
            or database.is_relative_to(workspace) or base_catalog.is_relative_to(workspace)):
        raise PreparationError()
    if not 1 <= len(asset_ids) <= 16 or len(set(asset_ids)) != len(asset_ids) or not all(integer(i,1,2**31-1) for i in asset_ids): raise PreparationError()
    base_raw = bounded_read(base_catalog,MAX_CATALOG); base = validate_catalog(json.loads(base_raw,object_pairs_hook=unique))
    if any(p['state'] == 'ready' for a in base['assets'] for p in a['previews'].values()) or any(a['video'] and a['video']['state']=='ready' for a in base['assets']): raise PreparationError()
    by_id = {a['id']:a for a in base['assets']}
    if any(i not in by_id for i in asset_ids): raise PreparationError()
    canonical(workspace.parent)
    workspace.mkdir(mode=0o700,exist_ok=True); canonical(workspace)
    with workspace_lock(workspace):
        if shutil.disk_usage(workspace).free < budget.reserve_bytes+budget.output_bytes: raise PreparationError()
        fingerprint = {'base_sha256':sha(base_raw),'database_path_sha256':sha(str(database).encode()),'source_root':str(source_root),
            'script_sha256':sha(Path(__file__).read_bytes()),'ffmpeg_sha256':file_hash(ffmpeg,256*1024**2),'ffprobe_sha256':file_hash(ffprobe,256*1024**2),
            'pillow_version':importlib.metadata.version('Pillow'),'budget':budget.__dict__}
        journal = workspace/'journal.json'
        if journal.exists():
            state = json.loads(bounded_read(journal,MAX_CATALOG),object_pairs_hook=unique)
            if state.get('fingerprint') != fingerprint: raise PreparationError()
        else:
            # Workspace must be ours alone; never adopt unknown files.
            if any(p.name != 'prepare.lock' for p in workspace.iterdir()): raise PreparationError()
            state = {'fingerprint':fingerprint,'items':{}}
            (workspace/'base.json').write_bytes(base_raw); atomic_json(journal,state)
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=2)) as conn:
            conn.execute('PRAGMA query_only=ON')
            rows = {r[0]:r for r in conn.execute('SELECT id,path,mime,status FROM assets WHERE id IN ('+','.join('?' for _ in asset_ids)+')',asset_ids)}
        for aid in asset_ids:
            key = str(aid); old = state['items'].get(key)
            if old and old['state']=='unavailable' and not retry_failed: continue
            try:
                row = rows.get(aid)
                if row is None or row[3] not in (None,'active'): raise PreparationError('source_missing')
                source = Path(row[1]); direct_path(source)
                if not source.is_relative_to(source_root): raise PreparationError('unsupported')
                canonical(source)
                kind = 'photo' if (row[2] or '').startswith('image/') else 'video' if (row[2] or '').startswith('video/') else 'unsupported'
                if kind != by_id[aid]['kind']: raise PreparationError('unsupported')
                if old and old['state']=='ready':
                    if file_hash(source,budget.input_bytes) != old['result']['source_sha256']: raise PreparationError()
                    verify_ready(attempt_path(workspace,old['directory'],aid),old['result']); continue
                # Unique directory: interrupted/unverified attempts are retained, never overwritten or adopted.
                if shutil.disk_usage(workspace).free < budget.reserve_bytes+budget.output_bytes+14*1024**2: raise PreparationError()
                attempt = Path(tempfile.mkdtemp(prefix=f'asset-{aid}-',dir=workspace))
                result = prepare_one(source,kind,attempt,ffmpeg,ffprobe,budget)
                verify_ready(attempt,result)
                state['items'][key] = {'state':'ready','directory':attempt.name,'result':result}
            except FileNotFoundError:
                state['items'][key] = {'state':'unavailable','reason':'source_missing'}
            except PreparationError as error:
                state['items'][key] = {'state':'unavailable','reason':error.reason}
            except (OSError,ValueError,KeyError,TypeError,Refused):
                state['items'][key] = {'state':'unavailable','reason':'preparation_failed'}
            atomic_json(journal,state)
        return state


def attempt_path(workspace, name, aid):
    if type(name) is not str or not re.fullmatch(r'asset-'+str(aid)+r'-[a-z0-9_]{8}',name): raise PreparationError()
    return canonical(workspace/name)


def publish(workspace, output):
    canonical(workspace); direct_path(output)
    canonical(output.parent)
    if output.exists() or output.is_relative_to(workspace): raise PreparationError()
    with workspace_lock(workspace):
        state = json.loads(bounded_read(workspace/'journal.json',MAX_CATALOG),object_pairs_hook=unique)
        source_root = Path(state['fingerprint']['source_root'])
        if output.is_relative_to(source_root) or source_root.is_relative_to(output): raise PreparationError()
        raw = bounded_read(workspace/'base.json',MAX_CATALOG)
        if sha(raw) != state['fingerprint']['base_sha256']: raise PreparationError()
        base = validate_catalog(json.loads(raw,object_pairs_hook=unique))
        # Verify everything before creating the new disabled publication.
        for asset in base['assets']:
            item = state['items'].get(str(asset['id']))
            if item is None: continue
            if item['state'] == 'ready':
                directory = attempt_path(workspace,item['directory'],asset['id'])
                if directory.parent != workspace: raise PreparationError()
                verify_ready(directory,item['result'])
                asset.update(previews=item['result']['previews'],video=item['result']['video'])
            else:
                missing = {'state':'unavailable','reason':item['reason']}
                asset['previews'] = {v:dict(missing) for v in LIMITS}
                if asset['kind']=='video': asset['video']=dict(missing)
        validate_catalog(base)
        # New output is never a live config target; failures leave an incomplete, unservable directory.
        total = sum(sum(m['bytes'] for m in a['previews'].values() if m['state']=='ready')+(a['video']['bytes'] if a['video'] and a['video']['state']=='ready' else 0) for a in base['assets'])
        if shutil.disk_usage(output.parent).free < total+Budget().reserve_bytes: raise PreparationError()
        output.mkdir(mode=0o700)
        for variant in ('grid','display','video'): (output/'prepared'/variant).mkdir(parents=True)
        for asset in base['assets']:
            item = state['items'].get(str(asset['id']))
            if item is None or item['state'] != 'ready': continue
            directory = workspace/item['directory']
            for variant in LIMITS:
                target=output/'prepared'/variant/f"{asset['id']}.jpg"
                shutil.copyfile(directory/f'{variant}.jpg',target)
                meta=asset['previews'][variant]
                if file_hash(target,meta['bytes']) != meta['sha256']: raise PreparationError()
            if asset['video']:
                for suffix in ('mp4','chunks.json'):
                    target=output/'prepared/video'/f"{asset['id']}.{suffix}"
                    shutil.copyfile(directory/f'video.{suffix}',target)
                    maximum=asset['video']['bytes'] if suffix=='mp4' else 1024**2
                    expected=asset['video']['sha256' if suffix=='mp4' else 'chunks_sha256']
                    if file_hash(target,maximum) != expected: raise PreparationError()
        raw = json.dumps(base,separators=(',',':')).encode()
        (output/'catalog.json').write_bytes(raw)
        atomic_json(output/'control.json',{'version':2,'enabled':False,'revision':base['revision'],'catalog_sha256':sha(raw)})
        return {'assets':len(base['assets']),'ready':sum(i['state']=='ready' for i in state['items'].values()),'enabled':False}


def main(argv=None):
    if os.name != 'nt':
        try: os.nice(10)
        except OSError: pass
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command',required=True)
    worker = sub.add_parser('_photo'); worker.add_argument('source',type=Path);worker.add_argument('output',type=Path);worker.add_argument('pixels',type=int)
    prep = sub.add_parser('prepare')
    for name in ('database','source-root','base-catalog','workspace','ffmpeg','ffprobe'): prep.add_argument('--'+name,type=Path,required=True)
    prep.add_argument('--asset-ids',required=True);prep.add_argument('--retry-failed',action='store_true')
    pub = sub.add_parser('publish');pub.add_argument('--workspace',type=Path,required=True);pub.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='_photo': photo_worker(args.source,args.output,args.pixels);return 0
        if args.command=='publish': result=publish(args.workspace,args.output)
        else:
            state=run(args.database,args.source_root,args.base_catalog,args.workspace,[int(s) for s in args.asset_ids.split(',')],args.ffmpeg,args.ffprobe,retry_failed=args.retry_failed)
            result={'requested':len(args.asset_ids.split(',')),'ready':sum(i['state']=='ready' for i in state['items'].values()),'unavailable':sum(i['state']=='unavailable' for i in state['items'].values()),'live_publication_changed':False}
        print(json.dumps(result));return 0
    except Exception:
        print('Offline preparation failed; inspect private checkpoint; no live publication changed',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
