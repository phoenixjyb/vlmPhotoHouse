#!/usr/bin/env python3
"""Strict, unattended face worker for approved member uploads.

This worker is intentionally separate from ``TaskExecutor``.  It claims only
``face`` and ``face_embed`` tasks whose asset has upload provenance, an active
library mapping, and an approved upload receipt.  Detection and embedding are
real local providers; a missing model, an unverifiable provider, or a resource
guard failure is a task failure and never a stub result.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import base64
from contextlib import closing, contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REVISION = "a8d4c2e6f901"
TASK_TYPES = ("face", "face_embed")
MAX_INPUT = 256 * 1024**2
MAX_PIXELS = 64_000_000
MAX_OUTPUT = 8 * 1024**2
MAX_TASK_SECONDS = 180
MAX_RETRIES = 3
POLL_SECONDS = 2.0
MIN_FREE_RAM = 8 * 1024**3
MAX_RSS = 3 * 1024**3
MAX_CHILD_BYTES = 2 * 1024**3
MODEL_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
ERROR_CODES = {
    "asset_id_missing", "face_id_missing", "face_missing", "approval_scope",
    "source_scope", "source_changed", "source_hash_mismatch", "source_size_policy",
    "unsupported_media", "image_pixel_policy", "image_decode_failed", "embedding_invalid",
    "embedding_output_policy", "memory_guard", "rss_guard", "vram_guard",
    "resource_probe_unavailable", "gpu_probe_unavailable", "gpu_worker_busy",
    "detector_gpu_not_effective", "embedder_gpu_not_effective", "native_provider_not_verifiable", "gpu_identity_mismatch",
    "task_timeout", "inference_child_failed", "child_budget_unavailable", "provider_unavailable", "worker_error", "unsupported_schema",
    "required_table_missing", "execution_requires_child_budget",
}


class Refused(ValueError):
    pass


def direct_path(value: str | Path, *, directory: bool = False, new: bool = False) -> Path:
    path = Path(value)
    if (not path.is_absolute() or path == Path(path.anchor) or ".." in path.parts
            or path.anchor.startswith(("//", "\\\\")) or len(str(path)) > 4096
            or any(ord(c) < 32 for c in str(path))):
        raise Refused("invalid_path")
    if path.parent.resolve(strict=True) != path.parent:
        raise Refused("symlink_parent")
    if new and not os.path.lexists(path):
        return path
    try:
        info = path.lstat()
    except OSError as exc:
        raise Refused("path_unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or path.resolve(strict=True) != path:
        raise Refused("symlink_path")
    if (path.is_dir() if directory else path.is_file()) is False:
        raise Refused("unexpected_path_type")
    return path


def connect(database: Path, *, readonly: bool = True):
    mode = "ro" if readonly else "rw"
    db = sqlite3.connect(database.as_uri() + f"?mode={mode}", uri=True, timeout=5)
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA foreign_keys=ON")
    if readonly:
        db.execute("PRAGMA query_only=ON")
    return db


def schema(db):
    row = db.execute("SELECT version_num FROM alembic_version").fetchone()
    if not row or row[0] != REVISION:
        raise Refused("unsupported_schema")
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {"tasks", "assets", "access_uploads", "access_asset_libraries",
                "access_libraries", "face_detections", "face_embedding_artifacts"}
    if not required <= tables:
        raise Refused("required_table_missing")


def memory_ok() -> None:
    try:
        import psutil
        if psutil.virtual_memory().available < MIN_FREE_RAM:
            raise Refused("memory_guard")
        if psutil.Process().memory_info().rss > MAX_RSS:
            raise Refused("rss_guard")
    except ImportError:
        # On Windows the production environment includes psutil.  Refusing is
        # safer than claiming a bounded worker without a measurable guard.
        raise Refused("resource_probe_unavailable")


def gpu_ok(device: str, expected_uuid: str | None = None, expected_name: str | None = None) -> None:
    if not device.startswith("cuda"):
        return
    # NVML is optional in CI but mandatory when claiming a GPU execution lane.
    try:
        import pynvml  # type: ignore
        pynvml.nvmlInit()
        try:
            index = int(device.split(":", 1)[1]) if ":" in device else 0
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            actual_uuid = pynvml.nvmlDeviceGetUUID(handle)
            actual_name = pynvml.nvmlDeviceGetName(handle)
            actual_uuid = actual_uuid.decode() if isinstance(actual_uuid, bytes) else str(actual_uuid)
            actual_name = actual_name.decode() if isinstance(actual_name, bytes) else str(actual_name)
            if expected_uuid and actual_uuid != expected_uuid:
                raise Refused("gpu_identity_mismatch")
            if expected_name and actual_name != expected_name:
                raise Refused("gpu_identity_mismatch")
            if int(info.free) < 1024 * 1024**2:
                raise Refused("vram_guard")
        finally:
            pynvml.nvmlShutdown()
    except Refused:
        raise
    except Exception as exc:
        raise Refused("gpu_probe_unavailable") from exc


@contextmanager
def gpu_lock(database: Path, device: str):
    """Serialize GPU model residency with the other approved media worker."""
    if not device.startswith("cuda"):
        yield
        return
    lock = direct_path(str(database) + ".approved-gpu-worker.lock", new=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    stream = os.fdopen(os.open(lock, flags, 0o600), "r+b", buffering=0)
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise Refused("gpu_worker_busy") from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Refused("gpu_worker_busy") from exc
        yield
    finally:
        try:
            if os.name == "nt":
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
        finally:
            stream.close()


def source_sha(path: Path, expected: str, expected_size: int) -> None:
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
        raise Refused("source_changed")
    if expected_size <= 0 or expected_size > MAX_INPUT:
        raise Refused("source_size_policy")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise Refused("source_hash_mismatch")


def load_image(path: Path) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        raw = Image.open(path)
        raw.verify()
        raw = Image.open(path)
        if raw.width * raw.height > MAX_PIXELS:
            raise Refused("image_pixel_policy")
        return raw.convert("RGB")
    except Refused:
        raise
    except Exception as exc:
        raise Refused("image_decode_failed") from exc


def allowed_asset(db, asset_id: int, originals: Path):
    row = db.execute("""SELECT a.id,a.path,a.hash_sha256,a.file_size,a.mime,a.status,
        u.state,m.library_id,l.state
        FROM assets a JOIN access_uploads u ON u.asset_id=a.id
        JOIN access_asset_libraries m ON m.asset_id=a.id
        JOIN access_libraries l ON l.id=m.library_id
        WHERE a.id=?""", (asset_id,)).fetchone()
    if not row or row[5] not in (None, "active") or row[6] != "assigned" or row[8] != "active":
        raise Refused("approval_scope")
    path = direct_path(row[1])
    if not path.is_relative_to(originals) or path == originals:
        raise Refused("source_scope")
    if row[4] not in ("image/jpeg", "image/png"):
        raise Refused("unsupported_media")
    source_sha(path, str(row[2]), int(row[3]))
    return path


def claim(db, task_id: int) -> bool:
    cur = db.execute("UPDATE tasks SET state='running',started_at=datetime('now') "
                     "WHERE id=? AND state='pending' AND cancel_requested=0", (task_id,))
    db.commit()
    return cur.rowcount == 1


def eligible(db):
    return db.execute("""SELECT t.id,t.type,t.payload_json,t.retry_count
        FROM tasks t WHERE t.state='pending' AND t.cancel_requested=0
        AND (t.scheduled_at IS NULL OR t.scheduled_at<=CURRENT_TIMESTAMP)
        AND ((t.type='face' AND EXISTS (SELECT 1 FROM assets a JOIN access_uploads u ON u.asset_id=a.id AND u.state='assigned'
              JOIN access_asset_libraries m ON m.asset_id=a.id JOIN access_libraries l ON l.id=m.library_id AND l.state='active'
              WHERE json_extract(t.payload_json,'$.asset_id')=a.id))
          OR (t.type='face_embed' AND EXISTS (SELECT 1 FROM face_detections f JOIN assets a ON a.id=f.asset_id
              JOIN access_uploads u ON u.asset_id=a.id AND u.state='assigned' JOIN access_asset_libraries m ON m.asset_id=a.id
              JOIN access_libraries l ON l.id=m.library_id AND l.state='active'
              WHERE json_extract(t.payload_json,'$.face_id')=f.id)))
        ORDER BY t.priority,t.id LIMIT 1""").fetchone()


def preflight(database: Path, originals: Path, derived: Path, stop_file: Path) -> dict:
    direct_path(database); direct_path(originals, directory=True)
    direct_path(derived, directory=True); direct_path(stop_file, new=True)
    with closing(connect(database)) as db:
        schema(db)
        counts = dict(db.execute("SELECT type,count(*) FROM tasks WHERE state='pending' AND type IN ('face','face_embed') GROUP BY type"))
        claimable = db.execute("""SELECT count(*) FROM tasks t WHERE t.state='pending' AND t.type='face'
            AND t.cancel_requested=0 AND EXISTS (SELECT 1 FROM assets a JOIN access_uploads u ON u.asset_id=a.id AND u.state='assigned'
            JOIN access_asset_libraries m ON m.asset_id=a.id JOIN access_libraries l ON l.id=m.library_id AND l.state='active'
            WHERE json_extract(t.payload_json,'$.asset_id')=a.id)""").fetchone()[0]
    return {'preflight':'pass', 'activated':False, 'pending_face':int(counts.get('face',0)),
            'pending_face_embed':int(counts.get('face_embed',0)), 'approved_face_claimable':int(claimable),
            'execution':'requires --execute'}


def safe_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return text if text in ERROR_CODES else "worker_error"


def fail(db, task_id: int, retries: int, exc: BaseException) -> None:
    count = retries + 1
    state = "failed" if count < MAX_RETRIES else "dead"
    db.execute("""UPDATE tasks SET state=?,retry_count=?,last_error=?,finished_at=datetime('now')
        WHERE id=? AND state='running'""", (state, count, safe_error(exc), task_id))
    db.commit()


def npy_bytes(vector: np.ndarray) -> bytes:
    out = io.BytesIO()
    np.save(out, np.asarray(vector, dtype="float32"), allow_pickle=False)
    value = out.getvalue()
    if len(value) > MAX_OUTPUT:
        raise Refused("embedding_output_policy")
    return value


class Worker:
    def __init__(self, args):
        self.db_path = direct_path(args.database)
        self.originals = direct_path(args.originals, directory=True)
        self.derived = direct_path(args.derived, directory=True)
        self.stop = direct_path(args.stop_file, new=True)
        self.device = args.device
        self.gpu_uuid = args.gpu_uuid
        self.gpu_name = args.gpu_name
        if self.device.startswith("cuda") and (not self.gpu_uuid or not self.gpu_name):
            raise Refused("gpu_identity_mismatch")
        self.model_path = direct_path(args.model_path)
        self.model_version = args.model_version
        if not MODEL_VERSION_RE.fullmatch(self.model_version):
            raise Refused("invalid_model_version")
        self.model_name = args.model_name
        self.stop_requested = False
        self.detector = None
        self.embedder = None

    def providers(self):
        os.environ["PHOTOHOUSE_STRICT_INFERENCE"] = "1"
        os.environ["FACE_EMBED_DIM"] = "512"
        os.environ["INSIGHTFACE_ROOT"] = str(self._insight_root)
        if self.device.startswith("cuda:"):
            # Pin the reviewed physical index before importing either runtime;
            # both providers then see that card as logical CUDA device zero.
            os.environ["CUDA_VISIBLE_DEVICES"] = self.device.split(":", 1)[1]
        from backend.app.face_detection_service import InsightFaceDetectionProvider
        from backend.app.face_embedding_service import LVFaceEmbeddingProvider
        self.detector = InsightFaceDetectionProvider(self.device, strict=True)
        if self.device.startswith("cuda") and not self.detector.accelerated:
            raise Refused("detector_gpu_not_effective")
        self.embedder = LVFaceEmbeddingProvider(str(self.model_path), self.device, 512, strict=True)
        if self.device.startswith("cuda") and self.embedder.effective_device != "cuda":
            raise Refused("embedder_gpu_not_effective")
        effective = str(getattr(self.embedder, "effective_provider", ""))
        if self.device.startswith("cuda") and "CUDAExecutionProvider" not in effective:
            raise Refused("native_provider_not_verifiable")

    def run_face(self, db, task_id: int, payload: dict):
        asset_id = payload.get("asset_id")
        if type(asset_id) is not int:
            raise Refused("asset_id_missing")
        path = allowed_asset(db, asset_id, self.originals)
        image = load_image(path)
        detections = self.detector.detect(image)
        existing = db.execute("SELECT id,bbox_x,bbox_y,bbox_w,bbox_h FROM face_detections WHERE asset_id=?", (asset_id,)).fetchall()
        def iou(a,b):
            ax,ay,aw,ah=a; bx,by,bw,bh=b
            inter=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
            union=aw*ah+ bw*bh-inter
            return inter/union if union else 0
        face_ids = []
        for d in detections:
            box=(float(d.x),float(d.y),float(d.w),float(d.h))
            if any(iou(box, tuple(map(float, row[1:]))) >= .6 for row in existing):
                continue
            cur=db.execute("INSERT INTO face_detections(asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id,embedding_path,landmarks_json,landmark_model,label_source,label_score) VALUES(?,?,?,?,?,NULL,NULL,?,?,NULL,NULL)",
                           (asset_id,*box, json.dumps([[float(x),float(y)] for x,y in d.landmarks]) if d.landmarks else None, type(self.detector).__name__))
            new_id = int(cur.lastrowid)
            face_ids.append(new_id)
            existing.append((new_id, *box))
        crop_dir=self.derived/'faces'/'256'; crop_dir.mkdir(parents=True,exist_ok=True)
        created = []
        try:
            for face_id in face_ids:
                row=db.execute("SELECT bbox_x,bbox_y,bbox_w,bbox_h FROM face_detections WHERE id=?",(face_id,)).fetchone()
                x,y,w,h=map(float,row); crop=image.crop((max(0,int(x)),max(0,int(y)),min(image.width,int(x+w)),min(image.height,int(y+h))))
                crop.thumbnail((256,256)); target=crop_dir/f"{face_id}.jpg"; tmp=target.with_suffix('.tmp')
                crop.save(tmp,'JPEG',quality=85); os.replace(tmp,target); created.append(target)
                db.execute("INSERT OR IGNORE INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at) VALUES('face_embed',?,'pending',135,0,0,datetime('now'))", (json.dumps({'face_id':int(face_id)},sort_keys=True),))
            db.execute("UPDATE tasks SET state='finished',finished_at=datetime('now') WHERE id=?",(task_id,)); db.commit()
        except Exception:
            db.rollback()
            for target in created:
                try: target.unlink()
                except OSError: pass
            raise

    def run_embed(self, db, task_id: int, payload: dict):
        face_id=payload.get('face_id')
        if type(face_id) is not int: raise Refused('face_id_missing')
        row=db.execute("SELECT f.asset_id,f.bbox_x,f.bbox_y,f.bbox_w,f.bbox_h,a.path,a.hash_sha256,a.file_size FROM face_detections f JOIN assets a ON a.id=f.asset_id WHERE f.id=?",(face_id,)).fetchone()
        if not row: raise Refused('face_missing')
        allowed_asset(db,int(row[0]),self.originals)
        crop=direct_path(self.derived/'faces'/'256'/f'{face_id}.jpg')
        image=load_image(crop); vector=np.asarray(self.embedder.embed_face(image),dtype='float32').reshape(-1)
        if vector.shape != (512,) or not np.isfinite(vector).all() or not np.linalg.norm(vector): raise Refused('embedding_invalid')
        data=npy_bytes(vector); root=self.derived/'face_embeddings'/self.model_version; root.mkdir(parents=True,exist_ok=True)
        target=root/f'{face_id}.npy'; tmp=target.with_suffix('.tmp'); tmp.write_bytes(data); os.replace(tmp,target)
        digest=hashlib.sha256(data).hexdigest(); rel=target.relative_to(self.derived).as_posix()
        db.execute("""INSERT INTO face_embedding_artifacts(face_id,model,model_version,dim,alignment,storage_path,vector_checksum,status)
            VALUES(?,?,?,?,?,?,?,'shadow') ON CONFLICT(face_id,model_version) DO UPDATE SET storage_path=excluded.storage_path,vector_checksum=excluded.vector_checksum,status='shadow'""",
                   (face_id,self.model_name,self.model_version,512,'scrfd-crop-256',rel,digest))
        db.execute("UPDATE tasks SET state='finished',finished_at=datetime('now') WHERE id=?",(task_id,)); db.commit()

    def loop(self, once=False):
        while not self.stop_requested:
            if self.stop.exists(): break
            with closing(connect(self.db_path,readonly=False)) as db:
                schema(db); row=eligible(db)
            if not row:
                if once: return
                time.sleep(POLL_SECONDS); continue
            with gpu_lock(self.db_path, self.device):
                memory_ok(); gpu_ok(self.device, self.gpu_uuid, self.gpu_name); self.providers()
                with closing(connect(self.db_path,readonly=False)) as db:
                    schema(db); row=eligible(db)
                    if not row: continue
                    task_id, kind, payload_raw, retries=row
                    try: payload=json.loads(payload_raw)
                    except Exception: payload={}
                    if not isinstance(payload,dict) or not claim(db,int(task_id)): continue
                    try:
                        if kind=='face': self.run_face(db,int(task_id),payload)
                        else: self.run_embed(db,int(task_id),payload)
                    except Exception as exc: fail(db,int(task_id),int(retries),exc)


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--database',type=Path,required=True); p.add_argument('--originals',type=Path,required=True)
    p.add_argument('--derived',type=Path,required=True); p.add_argument('--stop-file',type=Path,required=True)
    p.add_argument('--model-path',type=Path,required=True); p.add_argument('--insightface-root',type=Path,required=True)
    p.add_argument('--device',choices=('cpu','cuda','cuda:0','cuda:1'),default='cpu')
    p.add_argument('--gpu-uuid'); p.add_argument('--gpu-name')
    p.add_argument('--model-name',default='LVFace-B_Glint360K.onnx'); p.add_argument('--model-version',required=True)
    p.add_argument('--once',action='store_true'); p.add_argument('--execute',action='store_true'); args=p.parse_args(argv)
    worker=Worker(args); worker._insight_root=direct_path(args.insightface_root,directory=True)
    if not args.execute:
        print(json.dumps(preflight(args.database,args.originals,args.derived,args.stop_file),sort_keys=True))
        return
    raise SystemExit('execution_requires_child_budget')


if __name__ == '__main__':
    main()
