#!/usr/bin/env python3
"""Offline, explicit-ID, resumable preparation. Never modifies a live publication.

A workspace owns checkpoints/derivatives. Publishing creates a NEW disabled
publication from the fixed base catalog. No service, network, jobs or DB writes.
"""
import argparse
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
import hashlib
import importlib.metadata
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
    hash_seconds: int = 60
    probe_seconds: int = 20
    decode_seconds: int = 120
    jpeg_source_pixels: int = 0  # Zero inherits the ordinary source-pixel budget.
    decoded_pixels: int = 40000000

@dataclass(frozen=True)
class VideoQuality:
    name: str
    max_width: int
    max_height: int
    target_bitrate: str
    max_bitrate: str
    audio_bitrate: str


MEDIA_WORKER = Path(__file__).with_name('home_media_worker.py')
PROFILES = {
    'pilot': Budget(),
    'library-sdr-v1': Budget(input_bytes=8*1024**3, output_bytes=4*1024**3,
        duration_seconds=900, process_seconds=5400, asset_seconds=7200,
        hash_seconds=900, probe_seconds=30, decode_seconds=1800,
        jpeg_source_pixels=256000000, decoded_pixels=16000000),
    'phone-sdr-v1': Budget(input_bytes=8*1024**3, output_bytes=4*1024**3,
        duration_seconds=900, process_seconds=5400, asset_seconds=7200,
        hash_seconds=900, probe_seconds=30, decode_seconds=1800,
        jpeg_source_pixels=256000000, decoded_pixels=16000000),
}
VIDEO_QUALITIES = {
    'library-sdr-v1': VideoQuality('library-sdr-v1', 1920, 1080, '2M', '8M', '128k'),
    'phone-sdr-v1': VideoQuality('phone-sdr-v1', 1280, 720, '2M', '3M', '96k'),
}
def quality_config(value=None):
    if value is None: return None
    if isinstance(value, str):
        try: value = VIDEO_QUALITIES[value]
        except KeyError: raise ValueError('invalid_video_quality') from None
    elif isinstance(value, dict):
        try: value = VideoQuality(**value)
        except (TypeError, KeyError): raise ValueError('invalid_video_quality') from None
    if not isinstance(value, VideoQuality) or value.name not in VIDEO_QUALITIES or value != VIDEO_QUALITIES[value.name]:
        raise ValueError('invalid_video_quality')
    return value


def canonical(path):
    direct_path(path)
    if path.resolve(strict=True) != path: raise PreparationError('unsupported')
    return path


def sha(data): return hashlib.sha256(data).hexdigest()


def file_fingerprint(path, maximum, *, seconds=60, guard=None, chunks=False):
    """Supervise even stalled native reads; never hash media on the coordinator."""
    pin = identity(path)
    if not 0 < pin[2] <= maximum: raise PreparationError('unsupported')
    try:
        raw = run_process([sys.executable, MEDIA_WORKER, 'hash', path, maximum,
                           'chunks' if chunks else 'digest'], path.parent,
                          Budget(process_seconds=seconds, reserve_bytes=0), guard=guard)
    except PreparationError as error:
        if error.reason == 'process_timeout': raise PreparationError('hash_timeout') from error
        raise
    value = json.loads(raw, object_pairs_hook=unique)
    if (identity(path) != pin or value['bytes'] != pin[2]
            or not re.fullmatch('[0-9a-f]{64}', value['sha256'])
            or len(value['chunks']) != (math.ceil(pin[2]/CHUNK_BYTES) if chunks else 0)
            or any(not re.fullmatch('[0-9a-f]{64}', h) for h in value['chunks'])):
        raise PreparationError()
    return value


def file_hash(path, maximum, *, seconds=60, guard=None):
    return file_fingerprint(path, maximum, seconds=seconds, guard=guard)['sha256']


def photo_info(source, directory, budget, guard=None, output=None):
    args = [sys.executable, MEDIA_WORKER, 'photo' if output else 'photo-info', source,
            json.dumps(asdict(budget))]
    if output: args += [output, json.dumps(LIMITS)]
    raw = run_process(args, directory, replace(budget, process_seconds=min(
        budget.process_seconds, budget.decode_seconds if output else budget.probe_seconds)), guard=guard)
    value = json.loads(raw, object_pairs_hook=unique)
    if output and value['reason']: raise PreparationError('unsupported')
    if output: atomic_json(output/'photo.decode.json', value)
    return value


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


def run_process(args, directory, budget, output=None, guard=None):
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
                if guard is not None: guard(process)
                if time.monotonic()-start > budget.process_seconds: raise PreparationError('process_timeout')
                if (os.fstat(stdout.fileno()).st_size > 2*1024**2
                        or os.fstat(stderr.fileno()).st_size > 65536
                        or (output is not None and output.exists() and output.stat().st_size > budget.output_bytes)
                        or shutil.disk_usage(directory).free < budget.reserve_bytes):
                    raise PreparationError()
                time.sleep(0.05)
            if guard is not None: guard(process)
            if time.monotonic()-start > budget.process_seconds: raise PreparationError('process_timeout')
            if ((output is not None and output.exists() and output.stat().st_size > budget.output_bytes)
                    or shutil.disk_usage(directory).free < budget.reserve_bytes):
                raise PreparationError()
            if process.returncode: raise PreparationError()
            if os.fstat(stdout.fileno()).st_size > 2*1024**2 or os.fstat(stderr.fileno()).st_size > 65536:
                raise PreparationError()
            stdout.seek(0); return stdout.read(2*1024**2+1)
        finally:
            if process.poll() is None: process.kill()
            process.wait()


def probe(binary, source, directory, budget, guard=None):
    raw = run_process([binary, '-v', 'error', '-protocol_whitelist', 'file', '-f', 'mov', '-enable_drefs', '0', '-use_absolute_path', '0', '-export_all', '1', '-export_xmp', '1', '-show_streams', '-show_format', '-show_chapters',
                       '-of', 'json', source], directory, replace(budget,process_seconds=min(budget.process_seconds,budget.probe_seconds)), guard=guard)
    try: return json.loads(raw, object_pairs_hook=unique)
    except (ValueError,UnicodeError) as error: raise PreparationError('probe_metadata_invalid') from error


def normalized_probe(value, expected_duration, quality=None):
    quality = quality_config(quality)
    streams = value.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    if len(videos) != 1 or len(audios) > 1 or len(videos)+len(audios) != len(streams) or value.get('chapters'):
        raise PreparationError()
    v = videos[0]; duration = float(value['format']['duration'])
    if (v.get('codec_name') != 'h264' or v.get('profile') not in ('Constrained Baseline', 'Baseline', 'Main', 'High')
            or v.get('pix_fmt') != 'yuv420p' or not 0 < int(v.get('level', 999)) <= 41
            or v.get('color_range') not in (None, 'unknown', 'tv')
            or not 0 < Fraction(v.get('avg_frame_rate', '0')) <= 30
            or v.get('sample_aspect_ratio') not in ('1:1', None)
            or not math.isfinite(duration) or abs(duration-expected_duration) > max(0.25, min(1.0, expected_duration*.02))
            or any(a.get('codec_name') != 'aac' or a.get('profile') != 'LC' for a in audios)):
        raise PreparationError()
    if quality is not None and (int(v.get('width', 0)) > quality.max_width or int(v.get('height', 0)) > quality.max_height):
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
    # Retain the legacy private worker entry point while sharing bounded decoding.
    from home_media_worker import photo
    value = photo(source, asdict(Budget(pixels=pixel_limit)), output, LIMITS)
    if value['reason']: raise PreparationError('unsupported')


def previews(directory):
    result = {}
    for variant, (_, _, maximum) in LIMITS.items():
        data = bounded_read(directory/f'{variant}.jpg', maximum)
        width, height = jpeg_dimensions(data)
        result[variant] = {'state':'ready','width':width,'height':height,'bytes':len(data),'sha256':sha(data)}
    return result


def video_encoder_args(encoder='libx264', gpu=0, quality=None):
    quality = quality_config(quality)
    if encoder not in ('libx264','h264_nvenc') or type(gpu) is not int or not 0 <= gpu <= 15:
        raise ValueError('invalid_video_encoder')
    if encoder == 'libx264':
        if gpu != 0: raise ValueError('cpu_encoder_has_no_gpu')
        args = ['-c:v','libx264','-threads','1','-preset','fast']
        args += (['-b:v',quality.target_bitrate,'-maxrate',quality.max_bitrate,'-bufsize','6M'] if quality and quality.name == 'phone-sdr-v1' else ['-crf','23'])
        return args + ['-profile:v','high','-level:v','4.1']
    # Explicit device, no lookahead/AQ CUDA work. CPU decode/scale preserves the
    # tested orientation and range path; one NVENC session accelerates encoding.
    return ['-c:v','h264_nvenc','-gpu',str(gpu),'-preset','p4','-tune','hq',
            '-rc','vbr','-cq','23','-b:v',quality.target_bitrate if quality and quality.name == 'phone-sdr-v1' else '0','-maxrate',quality.max_bitrate if quality else '8M','-bufsize','6M' if quality and quality.name == 'phone-sdr-v1' else '16M',
            '-rc-lookahead','0','-spatial_aq','0','-temporal_aq','0','-bf','2',
            '-profile:v','high','-level:v','4.1']


def prepare_one(source, kind, output, ffmpeg, ffprobe, budget, guard=None, encoder='libx264', gpu=0, quality=None):
    quality = quality_config(quality)
    encoder_args = video_encoder_args(encoder, gpu, quality)
    began = time.monotonic(); before = identity(source)
    def remaining():
        seconds = int(budget.asset_seconds-(time.monotonic()-began))
        if seconds < 1: raise PreparationError()
        return replace(budget,process_seconds=min(budget.process_seconds,seconds))
    source_hash = file_hash(source, budget.input_bytes, seconds=min(budget.hash_seconds,remaining().process_seconds), guard=guard)
    if kind == 'photo':
        photo_info(source, output, remaining(), guard, output=output)
        result = {'previews':previews(output),'video':None}
    elif kind == 'video':
        if source.suffix.lower() not in ('.mp4','.mov'): raise PreparationError('unsupported')
        original = probe(ffprobe, source, output, remaining(), guard=guard)
        duration = float(original['format']['duration'])
        videos = [s for s in original.get('streams', []) if s.get('codec_type') == 'video' and not s.get('disposition',{}).get('attached_pic')]
        if (not math.isfinite(duration) or not 0 < duration <= budget.duration_seconds or len(videos) != 1
                or int(videos[0].get('width', 0))*int(videos[0].get('height', 0)) > budget.pixels
                or videos[0].get('pix_fmt') not in ('yuv420p','yuvj420p')
                or videos[0].get('sample_aspect_ratio') not in (None,'1:1')
                or videos[0].get('color_transfer') in ('smpte2084','arib-std-b67')):
            raise PreparationError('unsupported')
        target = output/'video.mp4'
        # Convert samples as well as encoder range signaling. format=yuv420p
        # alone can retain full-range H.264 VUI from a yuvj420p MOV source.
        args = [ffmpeg,'-hide_banner','-loglevel','error','-xerror','-err_detect','explode','-nostdin','-n','-threads','1','-filter_threads','1','-hwaccel','none','-protocol_whitelist','file','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',source,
                '-map',f"0:{videos[0]['index']}",'-map','0:a:0?','-map_metadata','-1','-map_metadata:s','-1','-map_chapters','-1','-sn','-dn',
                '-vf',f"scale=w='min({quality.max_width if quality else 1920},iw)':h='min({quality.max_height if quality else 1080},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2:in_range=auto:out_range=tv,setsar=1,fps=30,format=yuv420p",
                *encoder_args,
                '-color_range','tv',
                '-c:a','aac','-b:a',quality.audio_bitrate if quality else '128k','-ac','2','-ar','48000',
                '-metadata:s:v:0','handler_name=VideoHandler','-metadata:s:a:0','handler_name=SoundHandler',
                '-metadata:s','language=und','-movflags','+faststart',target]
        # Do not use -fs: it can return success after truncating a near-complete
        # stream. The supervisor rejects oversized output during AND after exit.
        try:
            run_process(args, output, remaining(), target, guard=guard)
        except PreparationError:
            if encoder == 'h264_nvenc':
                from home_preparation_resources import JobStopped
                raise JobStopped('nvenc_encode_failed') from None
            raise
        v, actual_duration, audio = normalized_probe(probe(ffprobe,target,output,remaining(),guard=guard), duration, quality)
        faststart(target)
        # Full bounded decode, not merely an ffprobe/header success.
        run_process([ffmpeg,'-v','error','-xerror','-err_detect','explode','-nostdin','-threads','1','-protocol_whitelist','file','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',target,'-f','null','-'], output, replace(remaining(),process_seconds=min(remaining().process_seconds,budget.decode_seconds)), guard=guard)
        frame = output/'poster.png'
        run_process([ffmpeg,'-v','error','-nostdin','-n','-threads','1','-protocol_whitelist','file','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',target,'-frames:v','1','-threads','1',frame], output, remaining(), guard=guard)
        photo_info(frame, output, remaining(), guard, output=output)
        fingerprint = file_fingerprint(target, budget.output_bytes, seconds=min(budget.hash_seconds,remaining().process_seconds), guard=guard, chunks=True)
        video_hash, hashes = fingerprint['sha256'], fingerprint['chunks']
        chunk_bytes = json.dumps(hashes).encode(); (output/'video.chunks.json').write_bytes(chunk_bytes)
        video = {'state':'ready','mime':'video/mp4','video_codec':'h264','audio_codec':audio,
                 'width':v['width'],'height':v['height'],'duration_ms':round(actual_duration*1000),
                 'bytes':target.stat().st_size,'sha256':video_hash,'chunks_sha256':sha(chunk_bytes)}
        validate_video(video); result = {'previews':previews(output),'video':video}
    else: raise PreparationError('unsupported')
    if identity(source) != before or file_hash(source,budget.input_bytes,seconds=min(budget.hash_seconds,remaining().process_seconds),guard=guard) != source_hash: raise PreparationError()
    remaining()
    result.update(source_sha256=source_hash,seconds=round(time.monotonic()-began,3))
    return result


def verify_ready(directory, result, budget=Budget(), guard=None, quality=None):
    if previews(directory) != result['previews']: raise PreparationError()
    if result['video']:
        video = result['video']; validate_video(video); quality = quality_config(quality)
        if quality and (video['width'] > quality.max_width or video['height'] > quality.max_height): raise PreparationError()
        actual = file_fingerprint(directory/'video.mp4', video['bytes'],
                                  seconds=budget.hash_seconds, guard=guard, chunks=True)
        if actual['sha256'] != video['sha256']: raise PreparationError()
        raw = bounded_read(directory/'video.chunks.json',1024**2)
        if sha(raw) != video['chunks_sha256'] or actual['chunks'] != json.loads(raw): raise PreparationError()


def run(database, source_root, base_catalog, workspace, asset_ids, ffmpeg, ffprobe, budget=Budget(), retry_failed=False, quality=None):
    quality = quality_config(quality)
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
            'script_sha256':sha(Path(__file__).read_bytes()+MEDIA_WORKER.read_bytes()),'ffmpeg_sha256':file_hash(ffmpeg,256*1024**2),'ffprobe_sha256':file_hash(ffprobe,256*1024**2),
            'pillow_version':importlib.metadata.version('Pillow'),'budget':budget.__dict__}
        if quality: fingerprint['quality'] = asdict(quality)
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
                    verify_ready(attempt_path(workspace,old['directory'],aid),old['result'],quality=quality); continue
                # Unique directory: interrupted/unverified attempts are retained, never overwritten or adopted.
                if shutil.disk_usage(workspace).free < budget.reserve_bytes+budget.output_bytes+14*1024**2: raise PreparationError()
                attempt = Path(tempfile.mkdtemp(prefix=f'asset-{aid}-',dir=workspace))
                result = prepare_one(source,kind,attempt,ffmpeg,ffprobe,budget,quality=quality)
                verify_ready(attempt,result,quality=quality)
                state['items'][key] = {'state':'ready','directory':attempt.name,'result':result}
            except FileNotFoundError:
                state['items'][key] = {'state':'unavailable','reason':'source_missing'}
            except PreparationError as error:
                state['items'][key] = {'state':'unavailable','reason':error.reason if error.reason in ('source_missing','unsupported') else 'preparation_failed'}
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
    prep.add_argument('--profile',choices=PROFILES,default=None)
    pub = sub.add_parser('publish');pub.add_argument('--workspace',type=Path,required=True);pub.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='_photo': photo_worker(args.source,args.output,args.pixels);return 0
        if args.command=='publish': result=publish(args.workspace,args.output)
        else:
            selected=args.profile or 'pilot'
            state=run(args.database,args.source_root,args.base_catalog,args.workspace,[int(s) for s in args.asset_ids.split(',')],args.ffmpeg,args.ffprobe,budget=PROFILES[selected],retry_failed=args.retry_failed,quality=VIDEO_QUALITIES.get(selected) if selected=='phone-sdr-v1' else None)
            result={'requested':len(args.asset_ids.split(',')),'ready':sum(i['state']=='ready' for i in state['items'].values()),'unavailable':sum(i['state']=='unavailable' for i in state['items'].values()),'live_publication_changed':False}
        print(json.dumps(result));return 0
    except Exception:
        print('Offline preparation failed; inspect private checkpoint; no live publication changed',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
