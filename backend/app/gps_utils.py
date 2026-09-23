from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import exifread


def _ratio_to_float(v: Any) -> float | None:
    try:
        if hasattr(v, "num") and hasattr(v, "den"):
            den = float(v.den)
            if den == 0:
                return None
            return float(v.num) / den
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if "/" in s:
            a, b = s.split("/", 1)
            den = float(b)
            if den == 0:
                return None
            return float(a) / den
        return float(s)
    except Exception:
        return None


def _dms_to_decimal(vals: list[Any], ref: str) -> float | None:
    if len(vals) < 3:
        return None
    d = _ratio_to_float(vals[0])
    m = _ratio_to_float(vals[1])
    s = _ratio_to_float(vals[2])
    if d is None or m is None or s is None:
        return None
    out = d + (m / 60.0) + (s / 3600.0)
    r = (ref or "").strip().upper()
    if r in ("S", "W"):
        out = -out
    return out


def _valid_lat_lon(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def parse_exif_gps(tags: dict[str, Any]) -> tuple[float, float] | None:
    lat_tag = tags.get("GPS GPSLatitude")
    lon_tag = tags.get("GPS GPSLongitude")
    lat_ref_tag = tags.get("GPS GPSLatitudeRef")
    lon_ref_tag = tags.get("GPS GPSLongitudeRef")
    if not lat_tag or not lon_tag:
        return None
    lat_vals = getattr(lat_tag, "values", lat_tag)
    lon_vals = getattr(lon_tag, "values", lon_tag)
    if not isinstance(lat_vals, (list, tuple)):
        lat_vals = [lat_vals]
    if not isinstance(lon_vals, (list, tuple)):
        lon_vals = [lon_vals]
    lat_ref = str(lat_ref_tag) if lat_ref_tag is not None else "N"
    lon_ref = str(lon_ref_tag) if lon_ref_tag is not None else "E"
    lat = _dms_to_decimal(list(lat_vals), lat_ref)
    lon = _dms_to_decimal(list(lon_vals), lon_ref)
    if not _valid_lat_lon(lat, lon):
        return None
    return float(lat), float(lon)


def read_image_gps(path: Path) -> tuple[float, float] | None:
    try:
        with path.open("rb") as f:
            tags = exifread.process_file(f, details=False)
        return parse_exif_gps(tags)
    except Exception:
        return None


def _parse_iso6709(value: str) -> tuple[float, float] | None:
    s = (value or "").strip()
    if not s:
        return None
    # Common alternate form: "lat,lon"
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) >= 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                if _valid_lat_lon(lat, lon):
                    return lat, lon
            except Exception:
                pass
    # ISO6709 style: +37.3317-122.0307+020.0/
    m = re.search(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        lat = float(m.group(1))
        lon = float(m.group(2))
    except Exception:
        return None
    if not _valid_lat_lon(lat, lon):
        return None
    return lat, lon


def parse_ffprobe_gps(info: dict[str, Any]) -> tuple[float, float] | None:
    candidate_keys = (
        "location",
        "location-eng",
        "com.apple.quicktime.location.ISO6709",
        "com.apple.quicktime.location.ISO6709-eng",
    )

    tag_dicts: list[dict[str, Any]] = []
    fmt = info.get("format") or {}
    if isinstance(fmt, dict) and isinstance(fmt.get("tags"), dict):
        tag_dicts.append(fmt["tags"])
    for s in info.get("streams") or []:
        if isinstance(s, dict) and isinstance(s.get("tags"), dict):
            tag_dicts.append(s["tags"])

    for tags in tag_dicts:
        lower_map = {str(k).lower(): v for k, v in tags.items()}
        for key in candidate_keys:
            val = lower_map.get(key.lower())
            if val is None:
                continue
            parsed = _parse_iso6709(str(val))
            if parsed is not None:
                return parsed
    return None


class VideoProbeError(ValueError):
    """A video failed the bounded metadata probe."""


MAX_VIDEO_BYTES = 16 * 1024 ** 3
MAX_VIDEO_DURATION_SEC = 24 * 60 * 60
MAX_VIDEO_PIXELS = 64 * 1024 * 1024
MAX_VIDEO_FPS = 120.0
MAX_PROBE_OUTPUT = 2 * 1024 * 1024


def probe_video_metadata(path: str | Path, timeout_sec: int = 10, *, strict: bool = False) -> dict:
    out: dict[str, float | None] = {
        "duration_sec": None,
        "fps": None,
        "gps_lat": None,
        "gps_lon": None,
    }
    try:
        source = Path(path)
        info = _bounded_ffprobe(source, timeout_sec)
    except Exception as error:
        if strict:
            raise error if isinstance(error, VideoProbeError) else VideoProbeError('video probe failed') from error
        return out

    # Duration / FPS from first video stream (fallback to format duration)
    vstreams = [
        s for s in (info.get("streams") or []) if isinstance(s, dict) and s.get("codec_type") == "video"
    ]
    vs = vstreams[0] if vstreams else None
    dur = None
    if isinstance(vs, dict):
        raw = vs.get("duration")
        if raw is not None:
            try:
                dur = float(raw)
            except Exception:
                dur = None
        if dur is None and isinstance(vs.get("tags"), dict):
            dtag = vs["tags"].get("DURATION")
            if dtag:
                try:
                    h, m, s = str(dtag).split(":")
                    dur = float(h) * 3600 + float(m) * 60 + float(s)
                except Exception:
                    pass
        r = vs.get("r_frame_rate") or vs.get("avg_frame_rate")
        if isinstance(r, str) and "/" in r:
            try:
                num_s, den_s = r.split("/", 1)
                num = float(num_s)
                den = float(den_s)
                if den != 0:
                    out["fps"] = num / den
            except Exception:
                pass
    if dur is None:
        fmt = info.get("format") or {}
        if isinstance(fmt, dict):
            f_dur = fmt.get("duration")
            if f_dur is not None:
                try:
                    dur = float(f_dur)
                except Exception:
                    dur = None
    out["duration_sec"] = dur

    if isinstance(vs, dict):
        out['width'] = vs.get('width')
        out['height'] = vs.get('height')
        out['video_codec'] = vs.get('codec_name')
    out['video_streams'] = len(vstreams)
    out['audio_streams'] = sum(1 for s in (info.get('streams') or [])
                               if isinstance(s, dict) and s.get('codec_type') == 'audio')
    out['format_name'] = str((info.get('format') or {}).get('format_name') or '')

    gps = parse_ffprobe_gps(info)
    if gps is not None:
        out["gps_lat"] = gps[0]
        out["gps_lon"] = gps[1]
    if strict:
        _validate_video_probe(source, out, info)
    return out


def _bounded_ffprobe(source: Path, timeout_sec: int) -> dict:
    try:
        stat_result = source.stat()
    except OSError as error:
        raise VideoProbeError('video source unavailable') from error
    if not source.is_file() or stat_result.st_size <= 0 or stat_result.st_size > MAX_VIDEO_BYTES:
        raise VideoProbeError('video size outside policy')
    cmd = ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file',
           '-enable_drefs', '0', '-use_absolute_path', '0', '-show_streams',
           '-show_format', '-of', 'json', str(source)]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) if os.name == 'nt' else 0
        process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=flags, start_new_session=(os.name != 'nt'))
        started = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic() - started > max(1, int(timeout_sec)):
                    raise VideoProbeError('video probe timed out')
                if stdout.tell() > MAX_PROBE_OUTPUT or stderr.tell() > 65536:
                    raise VideoProbeError('video probe output exceeded budget')
                time.sleep(0.01)
            if process.returncode or stdout.tell() > MAX_PROBE_OUTPUT or stderr.tell() > 65536:
                raise VideoProbeError('video probe failed')
            stdout.seek(0)
            raw = stdout.read(MAX_PROBE_OUTPUT + 1)
        finally:
            if process.poll() is None:
                try:
                    if os.name != 'nt':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except OSError:
                    pass
            process.wait()
    try:
        value = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError) as error:
        raise VideoProbeError('video probe metadata is invalid') from error
    if not isinstance(value, dict):
        raise VideoProbeError('video probe metadata shape invalid')
    return value


def _validate_video_probe(source: Path, meta: dict, info: dict) -> None:
    streams = info.get('streams') or []
    videos = [s for s in streams if isinstance(s, dict) and s.get('codec_type') == 'video'
              and not s.get('disposition', {}).get('attached_pic')]
    audios = [s for s in streams if isinstance(s, dict) and s.get('codec_type') == 'audio']
    duration, width, height, fps = (meta.get(k) for k in ('duration_sec', 'width', 'height', 'fps'))
    formats = set(meta.get('format_name', '').split(','))
    metadata = [s for s in streams if isinstance(s, dict) and (
        s.get('codec_type') in {'data', 'subtitle', 'attachment'}
        or (s.get('codec_type') == 'video' and s.get('disposition', {}).get('attached_pic')))]
    if (len(videos) != 1 or len(audios) > 1
            or len(videos) + len(audios) + len(metadata) != len(streams)):
        raise VideoProbeError('unsupported video stream layout')
    if not isinstance(duration, (int, float)) or not 0 < duration <= MAX_VIDEO_DURATION_SEC:
        raise VideoProbeError('video duration outside policy')
    if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
        raise VideoProbeError('video dimensions unavailable')
    if width * height > MAX_VIDEO_PIXELS:
        raise VideoProbeError('video pixel budget exceeded')
    if not isinstance(fps, (int, float)) or not 0 < fps <= MAX_VIDEO_FPS:
        raise VideoProbeError('video frame-rate outside policy')
    if not formats.intersection({'mov', 'mp4', 'm4a', '3gp', '3g2', 'mj2'}):
        raise VideoProbeError('unsupported video container')
