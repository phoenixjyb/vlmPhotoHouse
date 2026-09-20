"""Private, immutable prepared-video index. No encoding or anonymous feed access.

An offline export binds each asset to its source identity and validated H.264
output. The HTTP owner supplies current authorization before touching this index.
At most four readers hold one verified 4 MiB chunk apiece.
"""
import hashlib
import json
import os
from pathlib import Path
import threading

from ..home_catalog import CHUNK_BYTES, identity, validate_video, digest
from ..home_feed import bounded_read, unique, Refused
from .transport import TransportError

MAX_INDEX = 64 * 1024**2


def pin(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def direct(path):
    if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
        raise ValueError('Explicit direct path required')
    if path.resolve(strict=True) != path:
        raise ValueError('Direct path required')
    return path


class PreparedVideos:
    def __init__(self, index, sha256, root):
        direct(index); direct(root)
        if not digest(sha256) or index.is_relative_to(root):
            raise ValueError('Separate pinned index required')
        before = identity(index)
        raw = bounded_read(index, MAX_INDEX)
        if hashlib.sha256(raw).hexdigest() != sha256 or identity(index) != before:
            raise ValueError('Prepared index changed')
        value = json.loads(raw, object_pairs_hook=unique)
        if (set(value) != {'version', 'assets'} or type(value['version']) is not int
                or value['version'] != 1 or type(value['assets']) is not list
                or len(value['assets']) > 100000):
            raise ValueError('Invalid prepared index')
        self.entries = {}
        for item in value['assets']:
            if type(item) is not dict or set(item) != {'id', 'source_identity', 'directory', 'video'}:
                raise ValueError('Invalid prepared entry')
            aid, source, directory = item['id'], item['source_identity'], item['directory']
            if (type(aid) is not int or not 1 <= aid <= 2**63-1 or aid in self.entries
                    or type(source) is not list or len(source) != 4
                    or any(type(n) is not int or n < 0 for n in source) or source[2] == 0
                    or type(directory) is not str or not directory or len(directory) > 128
                    or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in directory)):
                raise ValueError('Invalid prepared entry')
            validate_video(item['video'])
            if item['video']['state'] != 'ready': raise ValueError('Ready records only')
            self.entries[aid] = item
        self.index, self.root, self.index_pin = index, root, before
        self.slots = threading.BoundedSemaphore(4)

    def current(self):
        if identity(self.index) != self.index_pin:
            raise TransportError(409, 'Prepared index changed')
        direct(self.root)

    def open(self, aid, source_pin):
        if not self.slots.acquire(blocking=False):
            raise TransportError(429, 'Playback busy')
        try:
            self.current()
            item = self.entries.get(aid)
            if item is None: raise TransportError(404, 'Video not prepared')
            if tuple(item['source_identity']) != source_pin:
                raise TransportError(409, 'Media changed')
            return PreparedReader(self, item)
        except BaseException:
            self.slots.release()
            raise


class PreparedReader:
    def __init__(self, owner, item):
        self.owner, self.stream, self.closed = owner, None, False
        folder = direct(owner.root / item['directory'])
        self.path = folder / 'video.mp4'
        self.meta = item['video']
        chunks = bounded_read(folder / 'video.chunks.json', 1024**2)
        if hashlib.sha256(chunks).hexdigest() != self.meta['chunks_sha256']:
            raise TransportError(409, 'Prepared media changed')
        self.hashes = json.loads(chunks)
        if (type(self.hashes) is not list or len(self.hashes) != (self.meta['bytes']+CHUNK_BYTES-1)//CHUNK_BYTES
                or not all(digest(h) for h in self.hashes)):
            raise TransportError(409, 'Prepared media changed')
        self.identity = identity(self.path)
        if self.identity[2] != self.meta['bytes']: raise TransportError(409, 'Prepared media changed')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        fd = os.open(self.path, flags)
        try:
            self.stream = os.fdopen(fd, 'rb')
        except BaseException:
            os.close(fd)
            raise
        try:
            self.check()
        except BaseException:
            self.stream.close()
            raise

    def check(self):
        self.owner.current()
        if identity(self.path) != self.identity or pin(os.fstat(self.stream.fileno())) != self.identity:
            raise TransportError(409, 'Prepared media changed')

    def chunk(self, index):
        self.check()
        self.stream.seek(index * CHUNK_BYTES)
        data = self.stream.read(CHUNK_BYTES)
        self.check()
        if hashlib.sha256(data).hexdigest() != self.hashes[index]:
            raise TransportError(409, 'Prepared media changed')
        return data

    def close(self):
        if not self.closed:
            self.closed = True
            self.stream.close()
            self.owner.slots.release()
