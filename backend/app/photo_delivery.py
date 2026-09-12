"""Bounded, lazy photo derivatives shared by explicitly configured HTTP runtimes.

Originals are never modified. No worker, cache or filesystem discovery at import.
The caller must authorize and pin a local source before invoking this service.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from .home_feed import LIMITS, Refused, bounded_read, direct_path, jpeg_dimensions
import stat


def identity(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path: raise Refused()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

PHOTO_BYTES = 64 * 1024**2
PHOTO_PIXELS = 256_000_000


def source_pin(path, roots, expected=None):
    direct_path(path)
    resolved = path.resolve(strict=True)
    if resolved != path or not any(resolved.is_relative_to(root.resolve(strict=True)) for root in roots):
        raise Refused(404, 'source_unavailable')
    pin = identity(path)
    if expected is not None and list(pin) != list(expected): raise Refused(409, 'source_changed')
    return pin


class PhotoCache:
    def __init__(self, root, *, worker=None, interpreter=None, budget_bytes=512*1024**2,
                 timeout=15, guard_factory=None):
        self.root = direct_path(root)
        self.worker = direct_path(worker or Path(__file__).resolve().parents[2]/'scripts/home_media_worker.py')
        self.interpreter = interpreter or sys.executable
        if not 12*1024**2 <= budget_bytes <= 8*1024**3 or not 1 <= timeout <= 15: raise ValueError('Invalid cache budget')
        self.budget, self.timeout = budget_bytes, timeout
        self.slot = threading.Lock()
        self.guard_factory = guard_factory

    def render(self, source, roots, pin, variant):
        if variant not in LIMITS: raise Refused(400, 'invalid_variant')
        source_pin(source, roots, pin)
        if not 0 < pin[2] <= PHOTO_BYTES: raise Refused(404, 'unsupported_photo')
        if any(self.root == p or self.root.is_relative_to(p) or p.is_relative_to(self.root) for p in roots):
            raise Refused()
        flags = os.O_RDONLY | getattr(os,'O_BINARY',0) | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0)
        with os.fdopen(os.open(source, flags),'rb') as stream:
            info = os.fstat(stream.fileno())
            if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns) != tuple(pin): raise Refused(409,'source_changed')
            raw = self.render_opened(stream, pin, str(source), variant)
            source_pin(source, roots, pin)
            return raw

    def render_opened(self, opened, pin, namespace, variant):
        """Caller supplies a currently authorized descriptor; never reopen its path."""
        if variant not in LIMITS or not 0 < pin[2] <= PHOTO_BYTES: raise Refused(404, 'unsupported_photo')
        key = hashlib.sha256(json.dumps([namespace, list(pin), variant, 'jpeg86-v1']).encode()).hexdigest()
        target = self.root/(key+'.jpg')
        # One bounded worker, no unbounded pending queue. Cache hits need no decoder.
        if not self.slot.acquire(blocking=False): raise Refused(429, 'busy')
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.root.resolve(strict=True) != self.root: raise Refused()
            marker = self.root/'.photohouse-photo-cache-v1'
            if not marker.exists():
                if any(self.root.iterdir()): raise Refused(503, 'cache_not_owned')
                with marker.open('xb') as stream: stream.write(b'PhotoHouse photo cache v1\n')
            if bounded_read(marker,128) != b'PhotoHouse photo cache v1\n': raise Refused()
            if os.name != 'nt' and self.root.stat().st_mode & 0o077: raise Refused(503,'cache_permissions')
            if target.exists():
                try:
                    raw = bounded_read(target, LIMITS[variant][2]); self.validate(raw, variant)
                except (Refused, OSError):
                    target.unlink(missing_ok=True)
                else:
                    os.utime(target, None)
                    return raw
            self.evict(LIMITS[variant][2])
            from importlib.util import spec_from_file_location, module_from_spec
            spec = spec_from_file_location('photohouse_owned_resources', self.worker.parent/'home_preparation_resources.py')
            module = module_from_spec(spec); spec.loader.exec_module(module)
            guard = self.guard_factory(self.root) if self.guard_factory else module.Guard(self.root, 2*1024**3)
            guard(force=True)
            policy = dict(pixels=20_000_000, jpeg_source_pixels=PHOTO_PIXELS, decoded_pixels=20_000_000)
            with tempfile.TemporaryDirectory(prefix='render-', dir=self.root) as temporary:
                output = Path(temporary)
                # Snapshot only this requested photo into the private temporary worker
                # directory. This avoids path substitution between authorization and decode.
                snapshot = output/'source'
                actual = lambda: tuple(getattr(os.fstat(opened.fileno()), k) for k in ('st_dev','st_ino','st_size','st_mtime_ns'))
                if actual() != tuple(pin): raise Refused(409, 'source_changed')
                opened.seek(0)
                with snapshot.open('xb') as target_stream:
                    remaining = pin[2]
                    while remaining:
                        part = opened.read(min(65536, remaining))
                        if not part: raise Refused(409, 'source_changed')
                        target_stream.write(part); remaining -= len(part)
                if actual() != tuple(pin): raise Refused(409, 'source_changed')
                command = [str(self.interpreter), '-B', str(self.worker), 'photo', str(snapshot),
                           json.dumps(policy), str(output), json.dumps({variant: LIMITS[variant]})]
                # Bounded files prevent pipe backpressure and terminal output. Worker is owned.
                with (output/'out').open('wb') as stdout, (output/'err').open('wb') as stderr:
                    process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                        creationflags=0x08000000 if os.name == 'nt' else 0)
                    started = time.monotonic()
                    try:
                        while process.poll() is None:
                            guard(process)
                            if time.monotonic()-started > self.timeout: raise Refused(503, 'preview_timeout')
                            time.sleep(0.05)
                        if process.returncode != 0: raise Refused(404, 'unsupported_photo')
                    finally:
                        if process.poll() is None: process.kill()
                        process.wait(timeout=5)
                produced = output/(variant+'.jpg')
                if not produced.exists(): raise Refused(404, 'unsupported_photo')
                raw = bounded_read(produced, LIMITS[variant][2]); self.validate(raw, variant)
                if actual() != tuple(pin): raise Refused(409, 'source_changed')
                produced.replace(target)
                return raw
        except Exception as error:
            if 'module' in locals() and isinstance(error, module.JobStopped):
                raise Refused(503, 'resource_pressure') from None
            raise
        finally:
            self.slot.release()

    def evict(self, reserve):
        files = []
        import re
        for path in self.root.glob('*.jpg'):
            if not re.fullmatch('[0-9a-f]{64}\.jpg',path.name): raise Refused(503,'cache_not_owned')
            if len(files) >= 100000: raise Refused()
            pin = identity(path)
            files.append((pin[3], path, pin[2]))
        total = sum(item[2] for item in files)
        for _, path, size in sorted(files):
            if total+reserve <= self.budget: break
            path.unlink(); total -= size
        if total+reserve > self.budget: raise Refused(503, 'cache_full')

    @staticmethod
    def validate(raw, variant):
        w,h = jpeg_dimensions(raw); edge,pixels,maximum = LIMITS[variant]
        if not 0 < len(raw) <= maximum or max(w,h)>edge or w*h>pixels: raise Refused()
