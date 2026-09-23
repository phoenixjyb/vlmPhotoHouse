#!/usr/bin/env python3
"""Bounded, single-owner face detection and shadow-embedding lane.

Only approved upload tasks are claimed. Inference happens in a hard-limited
strict-CUDA child. This lane never assigns a person or activates a vector for
automatic identity matching.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from approved_face_queue import (QueueRefused, claim, record_failure,
                                 recover_owned, select_candidate, validate_schema,
                                 verify_claim)
from run_approved_image_embed_worker import (direct_path, gpu_free_memory, identity,
                                             kernel_lock, run_supervised, sha256_file,
                                             _safe_output_dir, _sqlite)

CHILD = ROOT / 'scripts' / 'approved_face_inference_child.py'
DEVICE = 'cuda:1'
MODEL = 'LVFace-B_Glint360K.onnx'
VERSION = 'lvface-b-glint360k-scrfd-crop-d512-v1'
DETECTOR_HASH = '5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91'
EMBEDDER_HASH = '9d834ed8e927fd35b9123b2bf97c40aad05785b1f9ecfb1c4c1f6242d38d1382'
MAX_TASK_SECONDS = 180
MAX_INPUT_BYTES = 256 * 1024**2
MAX_CROP_BYTES = 2 * 1024**2
MAX_RECEIPT_BYTES = 64 * 1024
MAX_VECTOR_BYTES = 128 * 1024
POLL_SECONDS = 2


class Refused(ValueError):
    pass


def _model(path, expected, maximum):
    path = direct_path(path)
    if sha256_file(path, maximum) != expected:
        raise Refused('model_checksum')
    return path, identity(path)


def _config(args):
    database = direct_path(args.database)
    originals = direct_path(args.originals, directory=True)
    derived = direct_path(args.derived, directory=True)
    root = direct_path(args.insightface_root, directory=True)
    detector, detector_id = _model(root / 'models' / 'buffalo_l' / 'det_10g.onnx',
                                   DETECTOR_HASH, 256 * 1024**2)
    embedder, embedder_id = _model(args.model_path, EMBEDDER_HASH, 1024**3)
    stop = direct_path(args.stop_file, new=True)
    if stop in (database, detector, embedder) or stop.is_relative_to(originals):
        raise Refused('stop_file_scope')
    if not re.fullmatch(r'GPU-[0-9a-fA-F-]{36}', args.gpu_uuid or ''):
        raise Refused('gpu_uuid_required')
    with closing(_sqlite(database)) as db:
        validate_schema(db)
        pending = db.execute("SELECT type,count(*) FROM tasks WHERE type IN ('face','face_embed') AND state='pending' GROUP BY type").fetchall()
        foreign_running = db.execute("SELECT count(*) FROM tasks WHERE type IN ('face','face_embed') AND state='running' AND coalesce(last_error,'')!='approved_face_v38'").fetchone()[0]
        if foreign_running:
            raise Refused('foreign_running_face_tasks')
    return {'database': database, 'originals': originals, 'derived': derived,
            'root': root, 'detector': detector, 'detector_id': detector_id,
            'embedder': embedder, 'embedder_id': embedder_id, 'stop': stop,
            'pending': dict(pending), 'gpu_uuid': args.gpu_uuid}


def _environment(root):
    keep = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE',
            'LOCALAPPDATA', 'APPDATA', 'PROGRAMDATA', 'VIRTUAL_ENV', 'PATHEXT',
            'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'HOME',
            'LD_LIBRARY_PATH', 'CUDA_PATH', 'CUDA_PATH_V12_8', 'CUDNN_PATH'}
    env = {key: value for key, value in os.environ.items() if key in keep}
    env.update({'CUDA_VISIBLE_DEVICES': '1', 'INSIGHTFACE_ROOT': str(root),
                'PHOTOHOUSE_NO_DOTENV': '1', 'PHOTOHOUSE_STRICT_INFERENCE': '1',
                'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
                'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1'})
    return env


def _child(operation, stage, config, image=None):
    gpu_free_memory(DEVICE, config['gpu_uuid'])
    receipt = stage / 'receipt.json'
    argv = [sys.executable, '-I', '-B', str(CHILD), operation,
            '--stage', str(stage), '--receipt', str(receipt)]
    if image is not None:
        argv.extend(('--image', str(image)))
    if operation in ('detect', 'probe'):
        argv.extend(('--insightface-root', str(config['root'])))
    if operation in ('embed', 'probe'):
        argv.extend(('--model-path', str(config['embedder'])))
    run_supervised(argv, env=_environment(config['root']), derived=config['derived'],
                   deadline=time.monotonic() + MAX_TASK_SECONDS)
    if (receipt.is_symlink() or not receipt.is_file()
            or not 0 < receipt.stat().st_size <= MAX_RECEIPT_BYTES):
        raise Refused('receipt_invalid')
    result = json.loads(receipt.read_bytes())
    if (type(result) is not dict or result.get('operation') != operation
            or result.get('provider') != 'CUDAExecutionProvider'
            or result.get('effective_device') != ('cuda' if operation == 'embed' else 'cuda:0')):
        raise Refused('provider_receipt_invalid')
    return result


def _source(candidate, originals):
    source = direct_path(candidate['path'])
    if source == originals or not source.is_relative_to(originals):
        raise Refused('source_scope')
    if source.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
        raise Refused('source_media_profile')
    if (type(candidate['bytes']) is not int or not 0 < candidate['bytes'] <= MAX_INPUT_BYTES
            or source.stat().st_size != candidate['bytes']
            or sha256_file(source, MAX_INPUT_BYTES) != candidate['sha256']):
        raise Refused('source_changed')
    return source, identity(source)


def _input_for(candidate, config, source):
    if candidate['kind'] == 'face':
        return source, identity(source), candidate['sha256']
    crop_dir = _safe_output_dir(config['derived'], 'faces', '256')
    crop = direct_path(crop_dir / f"{candidate['face_id']}.jpg")
    if not 0 < crop.stat().st_size <= MAX_CROP_BYTES:
        raise Refused('crop_size')
    return crop, identity(crop), sha256_file(crop, MAX_CROP_BYTES)


def _receipt(result, candidate, input_hash, stage, config):
    if result.get('input_sha256') != input_hash:
        raise Refused('receipt_source_mismatch')
    if candidate['kind'] == 'face':
        if result.get('model_root') != str(config['root']):
            raise Refused('detection_model_mismatch')
        faces = result.get('faces')
        if type(faces) is not list or len(faces) > 64 or result.get('outputs') != [f'face-{i:02d}.jpg' for i in range(len(faces))]:
            raise Refused('detection_receipt_invalid')
        checked = []
        for index, face in enumerate(faces):
            box = face.get('bbox') if type(face) is dict else None
            if (type(box) is not list or len(box) != 4
                    or any(type(x) is not int or x < 0 for x in box)
                    or box[2] == 0 or box[3] == 0
                    or face.get('crop') != f'face-{index:02d}.jpg'):
                raise Refused('detection_box_invalid')
            points = face.get('landmarks')
            if points is not None and (type(points) is not list or len(points) > 5
                                       or any(type(p) is not list or len(p) != 2
                                              or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                                              for p in points)):
                raise Refused('landmarks_invalid')
            crop = direct_path(stage / face['crop'])
            if not 0 < crop.stat().st_size <= MAX_CROP_BYTES:
                raise Refused('crop_size')
            from PIL import Image
            with Image.open(crop) as image:
                image.verify()
                if image.format != 'JPEG' or image.size != (256, 256):
                    raise Refused('crop_profile')
            checked.append((tuple(box), points, crop))
        return checked
    if (result.get('dimension') != 512 or result.get('outputs') != ['embedding.npy']
            or result.get('model_path') != str(config['embedder'])):
        raise Refused('embedding_receipt_invalid')
    vector = direct_path(stage / 'embedding.npy')
    if not 0 < vector.stat().st_size <= MAX_VECTOR_BYTES:
        raise Refused('vector_size')
    import numpy as np
    value = np.load(vector, allow_pickle=False)
    if (value.shape != (512,) or value.dtype != np.float32
            or not np.isfinite(value).all()
            or not .999 <= float(np.linalg.norm(value)) <= 1.001):
        raise Refused('vector_invalid')
    return vector


def _iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    overlap = max(0, min(ax+aw, bx+bw)-max(ax,bx)) * max(0, min(ay+ah,by+bh)-max(ay,by))
    union = aw*ah + bw*bh - overlap
    return overlap/union if union > 0 else 0


def _journal_path(config, task_id):
    return config['derived'] / f'.approved-face-{task_id}.journal.json'


def _write_journal(config, candidate, outputs):
    journal = _journal_path(config, candidate['task_id'])
    if os.path.lexists(journal):
        raise Refused('unrecovered_journal')
    payload = {'task_id': candidate['task_id'], 'kind': candidate['kind'],
               'outputs': [str(path.relative_to(config['derived'])) for path in outputs]}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    with journal.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return journal


def _recover_journals(config, db):
    for journal in config['derived'].glob('.approved-face-*.journal.json'):
        journal = direct_path(journal)
        if journal.stat().st_size > 8192:
            raise Refused('journal_invalid')
        payload = json.loads(journal.read_bytes())
        if (type(payload) is not dict or type(payload.get('task_id')) is not int
                or payload.get('kind') not in ('face','face_embed')
                or type(payload.get('outputs')) is not list or len(payload['outputs']) > 64):
            raise Refused('journal_invalid')
        task = db.execute('SELECT type,state,last_error FROM tasks WHERE id=?', (payload['task_id'],)).fetchone()
        if not task or task[0] != payload['kind']:
            raise Refused('journal_task_mismatch')
        if task[1] == 'finished':
            journal.unlink(); continue
        if task[1] != 'running' or task[2] != 'approved_face_v38':
            raise Refused('journal_ownership_mismatch')
        for raw in payload['outputs']:
            rel = Path(raw)
            if (rel.is_absolute() or '..' in rel.parts or not re.fullmatch(
                    r'(?:faces/256|face_embeddings/lvface-b-glint360k-scrfd-crop-d512-v1)/[1-9][0-9]*\.(?:jpg|npy)', rel.as_posix())):
                raise Refused('journal_path_invalid')
            target = config['derived'] / rel
            if os.path.lexists(target):
                # A committed row is never deleted, even if the task state was
                # subsequently changed by a different operator.
                face_id = int(target.stem)
                if rel.parts[0] == 'faces':
                    referenced = db.execute('SELECT 1 FROM face_detections WHERE id=?', (face_id,)).fetchone()
                else:
                    referenced = db.execute('SELECT 1 FROM face_embedding_artifacts WHERE face_id=? AND model_version=? AND storage_path=?',
                                            (face_id, VERSION, rel.as_posix())).fetchone()
                if referenced:
                    raise Refused('journal_output_referenced')
                direct_path(target).unlink()
        journal.unlink()


def _publish_detection(db, config, candidate, detections, published):
    existing = [tuple(row) for row in db.execute('SELECT bbox_x,bbox_y,bbox_w,bbox_h FROM face_detections WHERE asset_id=?',
                                                  (candidate['asset_id'],)).fetchall()]
    new = []
    for box, points, crop in detections:
        if any(_iou(box, prior) >= .6 for prior in existing):
            continue
        cursor = db.execute('''INSERT INTO face_detections
            (asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id,embedding_path,landmarks_json,landmark_model,label_source,label_score)
            VALUES(?,?,?,?,?,NULL,NULL,?,'SCRFD-buffalo_l',NULL,NULL)''',
            (candidate['asset_id'], *box, json.dumps(points) if points else None))
        face_id = int(cursor.lastrowid)
        final = _safe_output_dir(config['derived'], 'faces', '256') / f'{face_id}.jpg'
        if os.path.lexists(final):
            raise Refused('face_target_exists')
        new.append((face_id, crop, final))
        existing.append(box)
    journal = _write_journal(config, candidate, [row[2] for row in new])
    for face_id, crop, final in new:
        os.replace(crop, final); published.append(final)
        db.execute("""INSERT INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at)
            VALUES('face_embed',?,'pending',135,0,0,CURRENT_TIMESTAMP)""",
            (json.dumps({'face_id': face_id}, sort_keys=True),))
    return journal


def _publish_embedding(db, config, candidate, vector, published):
    face_id = candidate['face_id']
    if db.execute('SELECT 1 FROM face_embedding_artifacts WHERE face_id=? AND model_version=?',
                  (face_id, VERSION)).fetchone():
        raise Refused('artifact_already_exists')
    final = _safe_output_dir(config['derived'], 'face_embeddings', VERSION) / f'{face_id}.npy'
    if os.path.lexists(final):
        raise Refused('vector_target_exists')
    journal = _write_journal(config, candidate, [final])
    checksum = hashlib.sha256(vector.read_bytes()).hexdigest()
    os.replace(vector, final); published.append(final)
    db.execute('''INSERT INTO face_embedding_artifacts
        (face_id,model,model_version,dim,alignment,storage_path,vector_checksum,status)
        VALUES(?,?,?,?,?,?,?,'shadow')''',
        (face_id, MODEL, VERSION, 512, 'scrfd-crop-256',
         final.relative_to(config['derived']).as_posix(), checksum))
    return journal


def _process(candidate, config):
    source, source_id = _source(candidate, config['originals'])
    selected, selected_id, input_hash = _input_for(candidate, config, source)
    if (identity(config['detector']) != config['detector_id']
            or identity(config['embedder']) != config['embedder_id']):
        raise Refused('model_changed')
    journal_before = os.path.lexists(_journal_path(config, candidate['task_id']))
    if journal_before:
        raise Refused('unrecovered_journal')
    stage = Path(tempfile.mkdtemp(prefix='.approved-face-', dir=config['derived']))
    published = []
    journal = None
    committed = False
    try:
        operation = 'detect' if candidate['kind'] == 'face' else 'embed'
        receipt = _child(operation, stage, config, selected)
        result = _receipt(receipt, candidate, input_hash, stage, config)
        if (identity(source) != source_id or identity(selected) != selected_id
                or sha256_file(source, MAX_INPUT_BYTES) != candidate['sha256']
                or sha256_file(selected, MAX_INPUT_BYTES) != input_hash
                or identity(config['detector']) != config['detector_id']
                or identity(config['embedder']) != config['embedder_id']):
            raise Refused('source_or_model_changed')
        with closing(_sqlite(config['database'], writable=True)) as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                validate_schema(db)
                if not verify_claim(db, candidate):
                    raise Refused('approval_or_claim_changed')
                if os.path.lexists(config['stop']):
                    raise Refused('stop_requested')
                if operation == 'detect':
                    journal = _publish_detection(db, config, candidate, result, published)
                else:
                    journal = _publish_embedding(db, config, candidate, result, published)
                done = db.execute("UPDATE tasks SET state='finished',finished_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=? AND state='running' AND last_error='approved_face_v38' AND cancel_requested=0",
                                  (candidate['task_id'],)).rowcount
                if done != 1:
                    raise Refused('claim_lost')
                db.commit(); committed = True
            except BaseException:
                db.rollback(); raise
        if journal is not None:
            journal.unlink()
        return True
    finally:
        if not committed:
            for path in published:
                try: path.unlink()
                except OSError: pass
            # The publisher can fail after writing its journal but before
            # returning its path to this frame.
            if not journal_before:
                pending_journal = _journal_path(config, candidate['task_id'])
                try: pending_journal.unlink()
                except OSError: pass
        shutil.rmtree(stage, ignore_errors=True)


def _probe(config):
    with kernel_lock(config['database'], blocking=True):
        stage = Path(tempfile.mkdtemp(prefix='.approved-face-probe-', dir=config['derived']))
        try:
            result = _child('probe', stage, config)
            if result.get('embedding_device') != 'cuda' or result.get('outputs') != []:
                raise Refused('provider_probe_invalid')
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    return {'provider': 'CUDAExecutionProvider', 'physical_device': DEVICE,
            'gpu_uuid': config['gpu_uuid'], 'hard_child_memory_mib': 4096}


def run(args):
    config = _config(args)
    result = {'preflight': 'pass', 'activated': False, 'pending': config['pending'],
              'detector_sha256': DETECTOR_HASH, 'embedder_sha256': EMBEDDER_HASH,
              'model_version': VERSION, **_probe(config)}
    if not args.execute:
        return result
    if os.path.lexists(config['stop']):
        raise Refused('stop_requested')
    # Separate lifetime lock prevents two copies of this lane from recovering
    # one another. The shared GPU lock is acquired only for each child task.
    lifetime = direct_path(str(config['database']) + '.approved-face-owner.lock', new=True)
    with lifetime.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            try: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError: raise Refused('another_face_owner') from None
        else:
            import fcntl
            try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError: raise Refused('another_face_owner') from None
        try:
            with closing(_sqlite(config['database'], writable=True)) as db:
                _recover_journals(config, db)
                recovered = recover_owned(db)
            result['recovered_owned'] = recovered
            while not os.path.lexists(config['stop']):
                with closing(_sqlite(config['database'])) as db:
                    candidate = select_candidate(db)
                if candidate is None:
                    if args.once: break
                    time.sleep(POLL_SECONDS); continue
                with kernel_lock(config['database'], blocking=True):
                    with closing(_sqlite(config['database'], writable=True)) as db:
                        if not claim(db, candidate):
                            continue
                    try:
                        _process(candidate, config)
                        result['processed'] = result.get('processed', 0) + 1
                    except Exception as error:
                        code = 'source_changed' if isinstance(error, Refused) and str(error).startswith('source') else 'worker_error'
                        with closing(_sqlite(config['database'], writable=True)) as db:
                            record_failure(db, candidate, code)
                        result['failed'] = result.get('failed', 0) + 1
                if args.once: break
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
    result['activated'] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database','originals','derived','stop-file','insightface-root','model-path','gpu-uuid'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), sort_keys=True))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, (Refused, QueueRefused)) else 'worker_failure'
        print(json.dumps({'face_pipeline': 'refused', 'reason': code[:64]}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
