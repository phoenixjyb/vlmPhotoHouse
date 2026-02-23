from __future__ import annotations

import json
import re
import subprocess
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


def probe_video_metadata(path: str | Path, timeout_sec: int = 10) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "duration_sec": None,
        "fps": None,
        "gps_lat": None,
        "gps_lon": None,
    }
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=max(1, int(timeout_sec)),
        )
        if result.returncode != 0 or not result.stdout:
            return out
        info = json.loads(result.stdout)
    except Exception:
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

    gps = parse_ffprobe_gps(info)
    if gps is not None:
        out["gps_lat"] = gps[0]
        out["gps_lon"] = gps[1]
    return out
