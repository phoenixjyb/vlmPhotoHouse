from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache
from typing import Optional, Protocol

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


def _tmp_dir() -> str:
    data_root = os.getenv("VLM_DATA_ROOT", r"E:\VLM_DATA")
    tmp_dir = os.getenv("VLM_TMP_DIR", os.path.join(data_root, "tmp"))
    try:
        os.makedirs(tmp_dir, exist_ok=True)
    except Exception:
        return tempfile.gettempdir()
    return tmp_dir


class ImageTagProvider(Protocol):
    def generate_tags(self, image: Image.Image, max_tags: int = 8) -> list[dict[str, object]]: ...
    def get_model_name(self) -> str: ...


class HTTPImageTagProvider:
    def __init__(self, service_url: str = "http://127.0.0.1:8112"):
        self.service_url = str(service_url or "").rstrip("/")
        self.model_name = "http-image-tag-service"
        try:
            with httpx.Client(timeout=3.0, trust_env=False) as client:
                res = client.get(f"{self.service_url}/health")
            if res.status_code == 200:
                model = str((res.json() or {}).get("model") or "").strip()
                if model:
                    self.model_name = model
        except Exception:
            logger.warning("Image tag service health check failed: %s", self.service_url, exc_info=True)

    def generate_tags(self, image: Image.Image, max_tags: int = 8) -> list[dict[str, object]]:
        tmp_path: Optional[str] = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".png", dir=_tmp_dir())
            os.close(fd)
            image.save(tmp_path, format="PNG")
            with httpx.Client(timeout=60.0, trust_env=False) as client:
                with open(tmp_path, "rb") as f:
                    files = {"file": ("image.png", f, "image/png")}
                    data = {"max_tags": str(max(1, int(max_tags or 8)))}
                    res = client.post(f"{self.service_url}/tag", files=files, data=data)
            if res.status_code != 200:
                raise RuntimeError(f"Image tag service error: {res.status_code} - {res.text}")
            payload = res.json() or {}
            model = str(payload.get("model") or "").strip()
            if model:
                self.model_name = model
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
                entry: dict[str, object] = {"name": name}
                if score is not None:
                    entry["score"] = score
                out.append(entry)
            return out[: max(1, int(max_tags or 8))]
        except httpx.RequestError as e:
            raise RuntimeError(f"Image tag service connection failed: {e}") from e
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def get_model_name(self) -> str:
        return self.model_name


class StubImageTagProvider:
    def __init__(self):
        self.model_name = "stub-image-tags"

    def generate_tags(self, image: Image.Image, max_tags: int = 8) -> list[dict[str, object]]:
        width, height = image.size
        orientation = "landscape" if width > height else "portrait"
        tags = [{"name": orientation, "score": 0.1}, {"name": "photo", "score": 0.05}]
        return tags[: max(1, int(max_tags or 8))]

    def get_model_name(self) -> str:
        return self.model_name


@lru_cache()
def get_image_tag_provider() -> ImageTagProvider:
    from .config import get_settings, settings as settings_obj

    settings = settings_obj or get_settings()
    provider_name = str(getattr(settings, "image_tag_provider", "stub") or "stub").lower()
    if getattr(settings, "run_mode", "") == "tests":
        return StubImageTagProvider()
    if provider_name in ("auto",):
        provider_name = "http" if str(getattr(settings, "image_tag_service_url", "")).strip() else "stub"
    if provider_name == "http":
        service_url = getattr(settings, "image_tag_service_url", None) or os.getenv("IMAGE_TAG_SERVICE_URL", "http://127.0.0.1:8112")
        try:
            return HTTPImageTagProvider(service_url)
        except Exception:
            logger.warning("HTTP image tag provider failed; falling back to stub", exc_info=True)
            return StubImageTagProvider()
    return StubImageTagProvider()
