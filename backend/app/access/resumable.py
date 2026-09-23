"""Disk-backed, account-bound transfers. Bounded chunks; no whole-file buffering.

Each transfer has an OS-held file lock (released on process death), and an explicit
migration-owned SQLite ledger. Bytes are fsynced before advancing offset. A crash
leaving extra bytes is repaired by truncating to the committed offset. Completion
records the receipt and transfer state in the same transaction, so a lost reply
cannot duplicate even a subsequently approved upload.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
import struct

from .service import AccessService, AccessDenied
from .transport import TransportError
from .upload import dimensions, sniff, MAX_PIXELS, _identity

CHUNK_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 256 * 1024 * 1024
MAX_VIDEO_BYTES = 16 * 1024 * 1024 * 1024
FIELDS = 'id,account_id,request_id,batch,filename,bytes,sha256,kind,offset,state,asset_id,created_at'
HEX32 = re.compile('[0-9a-f]{32}')
HEX64 = re.compile('[0-9a-f]{64}')


def file_digest(stream):
    stream.seek(0); digest = hashlib.sha256()
    while chunk := stream.read(65536): digest.update(chunk)
    return digest.hexdigest()


def media_header(stream, size, kind):
    stream.seek(0); head = stream.read(min(size, 1024 * 1024))
    if kind == 'image':
        try: mime, suffix = sniff(head)
        except AccessDenied: raise TransportError(415, 'Unsupported media') from None
        shape = dimensions(head, mime)
        if shape is None or min(shape) < 1 or shape[0] * shape[1] > MAX_PIXELS:
            raise TransportError(415, 'Unsupported image dimensions')
        return mime, suffix, shape
    # ISO BMFF container check only, not decoder or playback acceptance. Never
    # interpret supplied URLs or invoke a media/network subprocess on the API path.
    if len(head) < 16 or head[4:8] != b'ftyp': raise TransportError(415, 'Unsupported video')
    ftyp = struct.unpack('>I', head[:4])[0]
    if not 16 <= ftyp <= min(len(head), 4096): raise TransportError(415, 'Unsupported video')
    brands = {head[i:i+4] for i in [8, *range(16, ftyp, 4)]}
    if not brands & {b'isom',b'iso2',b'iso4',b'iso5',b'iso6',b'mp41',b'mp42',b'avc1',b'qt  ',b'M4V '}:
        raise TransportError(415, 'Unsupported video')
    position = 0; seen = set()
    for _ in range(10000):
        if position == size: break
        stream.seek(position); box = stream.read(16)
        if len(box) < 8: raise TransportError(415, 'Invalid video container')
        length = struct.unpack('>I', box[:4])[0]; header = 8
        if length == 1:
            if len(box) < 16: raise TransportError(415, 'Invalid video container')
            length = struct.unpack('>Q', box[8:16])[0]; header = 16
        elif length == 0: length = size-position
        if length < header or position+length > size: raise TransportError(415, 'Invalid video container')
        if length > header: seen.add(box[4:8])
        position += length
    if position != size or not {b'moov',b'mdat'} <= seen: raise TransportError(415, 'Invalid video container')
    return ('video/quicktime','.mov',(None,None)) if b'qt  ' in brands else ('video/mp4','.mp4',(None,None))


class Transfers:
    def __init__(self, upload): self.upload = upload

    def actor(self, token):
        with self.upload.access.connection_factory() as db:
            return AccessService(db, clock=self.upload.access.clock).uploader(token)[0]

    def service(self, db): return AccessService(db, clock=self.upload.access.clock)

    def row(self, db, token, identifier, service):
        if not isinstance(identifier, str) or not HEX32.fullmatch(identifier): raise TransportError(404, 'Upload unavailable')
        session = service._session(token)
        if not service._may_submit(session['account_id']): raise AccessDenied('Access denied')
        found = db.execute('SELECT '+FIELDS+' FROM access_upload_transfers WHERE id=? AND account_id=?',
                           (identifier,session['account_id'])).fetchone()
        if not found: raise TransportError(404, 'Upload unavailable')
        return dict(zip(FIELDS.split(','),found))

    @staticmethod
    def result(row):
        return dict(upload_id=row['id'], bytes=row['bytes'], offset=row['offset'],
                    chunk_bytes=CHUNK_BYTES, state=row['state'],
                    asset_id=str(row['asset_id']) if row['asset_id'] is not None else None)

    def create(self, token, body):
        expected = {'request_id','batch','filename','bytes','sha256','kind'}
        if type(body) is not dict or set(body) != expected: raise TransportError(400,'Invalid request')
        for key, regex in (('request_id',HEX32),('batch',HEX32),('sha256',HEX64)):
            if not isinstance(body[key],str) or not regex.fullmatch(body[key]): raise TransportError(400,'Invalid request')
        name = body['filename']
        if (not isinstance(name,str) or not 1 <= len(name) <= 200 or any(ord(c)<32 or c in '/\\' for c in name)
                or name in {'.','..'} or not isinstance(body['kind'],str) or body['kind'] not in {'image','video'} or type(body['bytes']) is not int):
            raise TransportError(400,'Invalid request')
        cap = MAX_IMAGE_BYTES if body['kind']=='image' else MAX_VIDEO_BYTES
        if not 1 <= body['bytes'] <= cap: raise TransportError(413,'Upload too large')
        with self.upload.access.connection_factory() as db:
            access=self.service(db)
            with access._transaction(write=True):
                account=access._session(token)['account_id']
                if not access._may_submit(account): raise AccessDenied('Access denied')
                old=db.execute('SELECT '+FIELDS+' FROM access_upload_transfers WHERE account_id=? AND request_id=?',
                               (account,body['request_id'])).fetchone()
                if old:
                    row=dict(zip(FIELDS.split(','),old))
                    if any(row[key]!=body[key] for key in expected): raise TransportError(409,'Upload request changed')
                    return self.result(row)
                identifier=secrets.token_hex(16)
                db.execute('''INSERT INTO access_upload_transfers
                    (id,account_id,request_id,batch,filename,bytes,sha256,kind,offset,state,created_at)
                    VALUES (?,?,?,?,?,?,?,?,0,'uploading',?)''',
                    (identifier,account,body['request_id'],body['batch'],name,body['bytes'],body['sha256'],body['kind'],access._now()))
                return self.result(self.row(db,token,identifier,access))

    def get(self, token, identifier):
        with self.upload.access.connection_factory() as db:
            access=self.service(db)
            with access._transaction(): return self.result(self.row(db,token,identifier,access))

    @contextmanager
    def lock(self, token, identifier):
        self.get(token,identifier)  # Authenticate and bind account before any filesystem IO.
        root=self.upload.incoming_root / '.transfers'
        root.mkdir(parents=True,exist_ok=True)
        if root.resolve()!=root: raise TransportError(503,'Upload storage unavailable')
        path=root/(identifier+'.lock')
        fd=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        locked=False
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or path.resolve()!=path: raise OSError('Invalid lock')
            if os.name=='nt':
                import msvcrt
                if os.fstat(fd).st_size==0: os.write(fd,b'0')
                os.lseek(fd,0,0);msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
            yield root/(identifier+'.part')
        except BlockingIOError: raise TransportError(429,'Upload busy') from None
        finally:
            if locked:
                if os.name=='nt':
                    os.lseek(fd,0,0);msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
                else: fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

    @contextmanager
    def part(self,path):
        fd=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'r+b') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or path.resolve()!=path: raise OSError('Invalid part')
            yield stream

    def append(self,token,identifier,offset,data,digest):
        if type(offset) is not int or offset<0 or not isinstance(data,bytes) or not 0<len(data)<=CHUNK_BYTES:
            raise TransportError(400,'Invalid chunk')
        if not isinstance(digest,str) or not HEX64.fullmatch(digest) or hashlib.sha256(data).hexdigest()!=digest:
            raise TransportError(422,'Chunk checksum mismatch')
        with self.lock(token,identifier) as path:
            with self.upload.access.connection_factory() as db:
                access=self.service(db)
                with access._transaction(write=True):
                    row=self.row(db,token,identifier,access)
                    if row['state']!='uploading' or offset!=row['offset']: raise TransportError(409,'Refresh upload offset')
                    if offset+len(data)>row['bytes']: raise TransportError(413,'Chunk exceeds declared size')
                    with self.part(path) as stream:
                        if os.fstat(stream.fileno()).st_size<offset: raise TransportError(409,'Upload storage changed')
                        stream.truncate(offset);stream.seek(offset);stream.write(data);stream.flush();os.fsync(stream.fileno())
                    # Session and membership checked again at the commit boundary.
                    self.row(db,token,identifier,access)
                    db.execute('UPDATE access_upload_transfers SET offset=? WHERE id=?',(offset+len(data),identifier))
                    row['offset']=offset+len(data)
                    return self.result(row)

    def cancel(self,token,identifier):
        with self.lock(token,identifier) as path:
            with self.upload.access.connection_factory() as db:
                access=self.service(db)
                with access._transaction(write=True):
                    row=self.row(db,token,identifier,access)
                    if row['state']=='complete': raise TransportError(409,'Upload already received')
                    db.execute("UPDATE access_upload_transfers SET state='cancelled' WHERE id=?",(identifier,))
                    row['state']='cancelled'
            # Only this transfer's staged data; a crash here leaves removable scratch.
            if path.exists():
                if path.resolve()!=path or not stat.S_ISREG(path.lstat().st_mode): raise OSError('Invalid part')
                path.unlink()
            return self.result(row)

    def complete(self,token,identifier):
        with self.lock(token,identifier) as path:
            with self.upload.access.connection_factory() as db:
                access=self.service(db)
                with access._transaction(): row=self.row(db,token,identifier,access)
            if row['state']=='complete': return self.result(row)
            if row['state']!='uploading' or row['offset']!=row['bytes']: raise TransportError(409,'Upload incomplete')
            with self.part(path) as stream:
                pin=_identity(os.fstat(stream.fileno()))
                if pin[2]!=row['bytes']: raise TransportError(409,'Upload storage changed')
                if file_digest(stream)!=row['sha256']: raise TransportError(422,'File checksum mismatch')
                mime,suffix,shape=media_header(stream,row['bytes'],row['kind'])
                if _identity(os.fstat(stream.fileno()))!=pin: raise TransportError(409,'Upload storage changed')
            with self.upload.access.connection_factory() as db:
                access=self.service(db)
                with access._transaction(write=True):
                    row=self.row(db,token,identifier,access)
                    from .service import incoming_label
                    session=access._session(token);label=incoming_label(session['display_name'],session['account_id'])
                    existing=access._incoming_upload(token,row['sha256'])
                    if existing:
                        if existing['bytes']!=row['bytes'] or existing['mime']!=mime: raise TransportError(409,'Upload changed')
                        asset=existing['asset_id']
                    else:
                        target=self.upload.incoming_root/label/row['batch']/(row['sha256']+suffix)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        if target.parent.resolve()!=target.parent or _identity(path.lstat())!=pin: raise OSError('Upload storage changed')
                        try: os.link(path,target)
                        except FileExistsError:
                            # A prior crashed completion may have published the same complete
                            # inode. Never overwrite or silently trust another file.
                            if (target.lstat().st_dev,target.lstat().st_ino)!=(pin[0],pin[1]): raise TransportError(409,'Upload storage needs review')
                        receipt=access._record_upload_in_transaction(token,label,row['batch'],target,row['filename'],row['sha256'],row['bytes'],mime,shape)
                        asset=int(receipt['asset_id'])
                    db.execute("UPDATE access_upload_transfers SET state='complete',asset_id=? WHERE id=?",(asset,identifier))
                    row.update(state='complete',asset_id=asset)
            # A hardlink was published (or account-private content reused). Never remove it.
            path.unlink()
            return self.result(row)
