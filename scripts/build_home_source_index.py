#!/usr/bin/env python3
"""Index selected originals without image re-encoding or a live database write.

Creates one new private file. This does not enable a feed or run bulk preparation.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.home_catalog import validate_catalog, identity, MAX_VIDEO
from app.home_feed import Refused, bounded_read, unique
from app.photo_delivery import source_pin, PHOTO_BYTES, PHOTO_PIXELS


def inspect_source(path,roots,kind,ffprobe=None):
    pin=source_pin(path,roots)
    if kind=='photo':
        if not 0<pin[2]<=PHOTO_BYTES:return None
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = PHOTO_PIXELS
        with Image.open(path) as image:
            if image.format not in ('JPEG','PNG') or getattr(image,'n_frames',1)!=1:return None
            w,h=image.size
            if max(w,h)>32768 or w*h>PHOTO_PIXELS:return None
            mime={'JPEG':'image/jpeg','PNG':'image/png'}[image.format]
        duration=audio=None
    elif kind=='video' and ffprobe:
        if not 0<pin[2]<=MAX_VIDEO:return None
        # Probe only. Never infer codecs from filenames or start an encoder.
        result=subprocess.run([str(ffprobe),'-v','error','-show_entries',
            'stream=codec_type,codec_name,profile,level,width,height,pix_fmt,color_transfer,avg_frame_rate,channels:stream_side_data=rotation:format=format_name,duration',
            '-of','json',str(path)],capture_output=True,timeout=15,
            creationflags=0x08000000 if sys.platform=='win32' else 0)
        if result.returncode or len(result.stdout)>65536:return None
        probe=json.loads(result.stdout);streams=probe.get('streams',[])
        video=[s for s in streams if s.get('codec_type')=='video'];audios=[s for s in streams if s.get('codec_type')=='audio']
        if len(video)!=1 or len(audios)>1 or len(streams)!=len(video)+len(audios):return None
        v=video[0];w,h=v.get('width',0),v.get('height',0)
        if (v.get('codec_name')!='h264' or v.get('profile') not in ('Constrained Baseline','Baseline','Main','High')
            or not 0<v.get('level',999)<=41 or v.get('pix_fmt')!='yuv420p'
            or v.get('color_transfer') in ('smpte2084','arib-std-b67') or v.get('side_data_list')
            or not 0<w<=1920 or not 0<h<=1920 or w*h>2073600):return None
        from fractions import Fraction
        if not 0<Fraction(v.get('avg_frame_rate','0'))<=30:return None
        if audios and (audios[0].get('codec_name')!='aac' or audios[0].get('profile')!='LC' or audios[0].get('channels',99)>2):return None
        if 'mp4' not in probe.get('format',{}).get('format_name','').split(','):return None
        duration=int(float(probe['format']['duration'])*1000)
        if not 0<duration<=86400000:return None
        mime='video/mp4';audio='aac' if audios else None
    else:return None
    source_pin(path,roots,pin)
    return dict(path=str(path),identity=list(pin),kind=kind,mime=mime,width=w,height=h,duration_ms=duration,audio_codec=audio)


def build(database,catalog_path,roots,output,ffprobe=None):
    if output in (database,catalog_path) or any(output.is_relative_to(p) for p in roots):raise ValueError('Output must be separate from originals and inputs')
    raw=bounded_read(catalog_path,64*1024**2);catalog=validate_catalog(json.loads(raw,object_pairs_hook=unique))
    counts=Counter();entries=[]
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        for a in catalog['assets']:
            row=c.execute("SELECT path FROM assets WHERE id=? AND (status IS NULL OR status='active')",(a['id'],)).fetchone()
            try:e=inspect_source(Path(row[0]),roots,a['kind'],ffprobe) if row else None
            except (Refused,OSError,ValueError,KeyError,ZeroDivisionError,subprocess.TimeoutExpired):e=None
            if e:entries.append(dict(id=a['id'],**e));counts[a['kind']+'_direct']+=1
            else:counts[a['kind']+'_prepared_or_unavailable']+=1
    value=dict(version=1,catalog_sha256=hashlib.sha256(raw).hexdigest(),assets=entries)
    data=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
    if len(data)>64*1024**2:raise ValueError('Index too large')
    # Never overwrite an active index or another operator's candidate.
    import os
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data)
    return dict(selected=len(catalog['assets']),indexed=len(entries),counts=dict(counts),sha256=hashlib.sha256(data).hexdigest(),activated=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('database','catalog','output'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--source-root',type=Path,action='append',required=True);p.add_argument('--ffprobe',type=Path)
    args=p.parse_args()
    try:
        for path in (args.database,args.catalog,args.output,*args.source_root):
            if not path.is_absolute():raise ValueError('Absolute inputs required')
        print(json.dumps(build(args.database,args.catalog,tuple(args.source_root),args.output,args.ffprobe)));return 0
    except Exception:print('Source indexing refused; no feed changed.',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
