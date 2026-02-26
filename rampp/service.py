from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, ImageStat

app = FastAPI(title="RAM++ Tag Service", version="0.1.0")


def _service_model_name() -> str:
    return os.getenv("RAMPP_MODEL_NAME", "ram-plus")


def _tmp_dir() -> str:
    root = os.getenv("VLM_TMP_DIR", tempfile.gettempdir())
    os.makedirs(root, exist_ok=True)
    return root


def _stub_tags(image: Image.Image, max_tags: int) -> list[dict[str, object]]:
    width, height = image.size
    orientation = "landscape" if width >= height else "portrait"
    brightness = float(ImageStat.Stat(image.convert("L")).mean[0]) if width and height else 127.0
    light_tag = "night" if brightness < 85 else ("sunny" if brightness > 170 else "indoor")
    tags = [
        {"name": orientation, "score": 0.15},
        {"name": light_tag, "score": 0.12},
        {"name": "photo", "score": 0.05},
    ]
    return tags[: max(1, int(max_tags or 8))]


def _tags_from_external_script(image_path: Path, max_tags: int) -> list[dict[str, object]]:
    raw_script = str(os.getenv("RAMPP_TAG_SCRIPT", "") or "").strip()
    script = Path(raw_script).expanduser() if raw_script else (Path(__file__).resolve().parent / "adapter_rampp.py")
    if not script.exists():
        raise FileNotFoundError(f"RAMPP_TAG_SCRIPT not found: {script}")
    default_py = Path(__file__).resolve().parent / ".venv-rampp" / "Scripts" / "python.exe"
    py_exe = os.getenv("RAMPP_PYTHON_EXE") or (str(default_py) if default_py.exists() else "python")
    cmd = [
        py_exe,
        str(script),
        "--image",
        str(image_path),
        "--max-tags",
        str(max(1, int(max_tags or 8))),
    ]
    run = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    raw_out = str(run.stdout or "").strip()
    payload: dict[str, object] | None = None
    try:
        payload = json.loads(raw_out or "{}")
    except Exception:
        for line in reversed(raw_out.splitlines()):
            line = str(line or "").strip()
            if not line.startswith("{") or not line.endswith("}"):
                continue
            try:
                payload = json.loads(line)
                break
            except Exception:
                continue
    if payload is None:
        raise RuntimeError(f"RAMPP adapter emitted non-JSON output: {raw_out[:500]}")
    raw_tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    out: list[dict[str, object]] = []
    for item in raw_tags:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            score = float(item.get("score")) if item.get("score") is not None else None
        except Exception:
            score = None
        row: dict[str, object] = {"name": name}
        if score is not None:
            row["score"] = score
        out.append(row)
    return out[: max(1, int(max_tags or 8))]


@app.get("/health")
def health() -> dict[str, object]:
    mode = os.getenv("RAMPP_MODE", "stub").strip().lower() or "stub"
    checkpoint = str(os.getenv("RAMPP_CHECKPOINT", "") or "").strip()
    return {
        "status": "ok",
        "mode": mode,
        "model": _service_model_name(),
        "script": os.getenv("RAMPP_TAG_SCRIPT", ""),
        "python": os.getenv("RAMPP_PYTHON_EXE", ""),
        "cuda_device": os.getenv("RAMPP_CUDA_DEVICE", ""),
        "checkpoint": checkpoint,
        "checkpoint_exists": bool(checkpoint and Path(checkpoint).exists()),
    }


@app.post("/tag")
async def tag_image(file: UploadFile = File(...), max_tags: int = Form(8)) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")
    max_tags = max(1, min(int(max_tags or 8), 32))
    suffix = Path(file.filename).suffix or ".png"
    tmp_root = _tmp_dir()
    fd, tmp_name = tempfile.mkstemp(suffix=suffix, dir=tmp_root)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        data = await file.read()
        tmp_path.write_bytes(data)
        mode = os.getenv("RAMPP_MODE", "stub").strip().lower() or "stub"
        with Image.open(tmp_path) as im:
            image = im.convert("RGB")
            tags = _stub_tags(image, max_tags=max_tags)
        if mode in ("script", "external"):
            tags = _tags_from_external_script(tmp_path, max_tags=max_tags)
        return {"model": _service_model_name(), "tags": tags}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"RAMPP script failed: {e.stderr or e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
