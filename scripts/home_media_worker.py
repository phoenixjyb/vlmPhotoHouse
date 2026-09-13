"""Small owned CPU worker. File data stays local; stdout contains metadata only."""
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import sys
import warnings

CHUNK_BYTES = 4 * 1024**2


class Deferred(Exception):
    pass


def fingerprint(path, maximum, chunks=False):
    before = path.stat(follow_symlinks=False)
    pin = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
        raise ValueError('source_size_or_type')
    digest = hashlib.sha256(); parts = []; size = 0
    with path.open('rb') as stream:
        if pin(os.fstat(stream.fileno())) != pin(before): raise ValueError('source_changed')
        while data := stream.read(CHUNK_BYTES):
            size += len(data)
            if size > maximum: raise ValueError('source_grew')
            digest.update(data)
            if chunks: parts.append(hashlib.sha256(data).hexdigest())
    if size != before.st_size or pin(path.stat(follow_symlinks=False)) != pin(before):
        raise ValueError('source_changed')
    return {'sha256': digest.hexdigest(), 'bytes': size, 'chunks': parts}


def configure_image(image, policy):
    width, height = image.size
    if image.format not in ('JPEG', 'PNG'): raise Deferred('photo_format_profile')
    if getattr(image, 'n_frames', 1) != 1: raise Deferred('animation_profile')
    source_limit = (policy['jpeg_source_pixels'] or policy['pixels']) if image.format == 'JPEG' else policy['pixels']
    if width * height > source_limit: raise Deferred('pixel_budget')
    decoded_limit = min(policy['pixels'], policy['decoded_pixels'])
    factor = 1
    if width * height > decoded_limit:
        if image.format != 'JPEG': raise Deferred('decoded_pixel_budget')
        # Progressive JPEG may allocate full-resolution coefficient buffers even
        # with reduced output. Keep that profile deferred, rather than relying
        # solely on a sampler to contain its decoder allocation.
        if image.info.get('progressive') or image.info.get('progression'):
            raise Deferred('progressive_jpeg_profile')
        factor = next((f for f in (2, 4, 8)
                       if math.ceil(width/f)*math.ceil(height/f) <= decoded_limit), None)
        if factor is None: raise Deferred('jpeg_subsampling_budget')
        # Floor requested dimensions so libjpeg selects at least this reduction.
        image.draft(image.mode, (max(1, width//factor), max(1, height//factor)))
    if image.width * image.height > decoded_limit: raise Deferred('decoded_pixel_budget')
    return {'format': image.format, 'source_size': [width, height],
            'decoded_size': list(image.size), 'subsampling': factor, 'reason': None}


def photo(source, policy, output=None, limits=None):
    from PIL import Image, ImageOps, ImageCms
    Image.MAX_IMAGE_PIXELS = max(policy['pixels'], policy['jpeg_source_pixels'])
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    try:
        with Image.open(source) as image:
            plan = configure_image(image, policy)
            if output is None: return plan
            icc = image.info.get('icc_profile')
            if icc and len(icc) > 1024**2: raise Deferred('icc_profile_budget')
            image.load()
            # Validate after load too; no automatic full-size fallback is allowed.
            if list(image.size) != plan['decoded_size']: raise ValueError('decoder_size_changed')
            upright = ImageOps.exif_transpose(image)
            if icc:
                converted = ImageCms.profileToProfile(upright, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                    ImageCms.createProfile('sRGB'), outputMode='RGBA' if 'A' in upright.mode else 'RGB')
                upright.close(); upright = converted
            try:
                if 'A' in upright.mode or 'transparency' in upright.info:
                    with upright.convert('RGBA') as rgba, Image.new('RGBA', upright.size, (0,0,0,255)) as canvas:
                        canvas.alpha_composite(rgba); rgb = canvas.convert('RGB')
                else: rgb = upright.convert('RGB')
                try:
                    for variant, (edge, pixels, maximum) in limits.items():
                        with rgb.copy() as derivative:
                            factor = min(1, edge/derivative.width, edge/derivative.height,
                                         math.sqrt(pixels/(derivative.width*derivative.height)))
                            derivative.thumbnail((max(1,int(derivative.width*factor)), max(1,int(derivative.height*factor))), Image.Resampling.LANCZOS)
                            with Image.frombytes('RGB', derivative.size, derivative.tobytes()) as clean:
                                clean.save(output/f'{variant}.jpg', 'JPEG', quality=86,
                                           progressive=False, optimize=False, exif=b'')
                        if (output/f'{variant}.jpg').stat().st_size > maximum: raise ValueError('preview_size')
                finally: rgb.close()
            finally: upright.close()
            return plan
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return {'reason': 'pixel_budget'}
    except Deferred as error:
        return {'reason': str(error)}


def main():
    if os.name != 'nt':
        try: os.nice(10)
        except OSError: pass
    try:
        operation, source = sys.argv[1], Path(sys.argv[2])
        if operation == 'hash': result = fingerprint(source, int(sys.argv[3]), sys.argv[4] == 'chunks')
        elif operation in ('photo-info', 'photo'):
            policy = json.loads(sys.argv[3])
            result = photo(source, policy, Path(sys.argv[4]) if operation == 'photo' else None,
                           json.loads(sys.argv[5]) if operation == 'photo' else None)
        else: raise ValueError('unknown_operation')
        print(json.dumps(result)); return 0
    except Exception:
        print('Owned media worker failed validation.', file=sys.stderr); return 2


if __name__ == '__main__': raise SystemExit(main())
