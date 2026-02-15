"""HTTP service exposing LVFace embeddings via FastAPI."""
import io
import logging
import os
from typing import Optional

import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
import uvicorn

from .face_embedding_service import LVFaceEmbeddingProvider

logger = logging.getLogger("app.lvface_service")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="LVFace Embedding Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

_PROVIDER: Optional[LVFaceEmbeddingProvider] = None
_MODEL_NAME: Optional[str] = None
_MODEL_DIM: Optional[int] = None
_DEVICE: Optional[str] = None


def _resolve_device() -> str:
    device = os.getenv("EMBED_DEVICE", "cuda")
    if device.startswith("cuda"):
        return "cuda"
    return "cpu"


def _load_provider() -> LVFaceEmbeddingProvider:
    global _PROVIDER, _MODEL_NAME, _MODEL_DIM, _DEVICE
    if _PROVIDER is not None:
        return _PROVIDER

    model_path = os.getenv("LVFACE_MODEL_PATH", "models/lvface.onnx")
    target_dim = int(os.getenv("FACE_EMBED_DIM", os.getenv("LVFACE_TARGET_DIM", "512")))
    device = _resolve_device()

    logger.info("Loading LVFace ONNX model from %s (dim=%s, device=%s)", model_path, target_dim, device)
    provider = LVFaceEmbeddingProvider(model_path, device, target_dim)

    _PROVIDER = provider
    _MODEL_NAME = os.path.basename(model_path)
    _MODEL_DIM = target_dim
    _DEVICE = device
    return provider


@app.on_event("startup")
async def _startup() -> None:
    try:
        provider = _load_provider()
        logger.info("LVFace service ready (model=%s, dim=%s)", _MODEL_NAME, _MODEL_DIM)
        # Light warmup
        dummy = Image.new("RGB", (112, 112), color=0)
        provider.embed_face(dummy)
    except Exception as exc:
        logger.exception("LVFace service failed to initialize: %s", exc)


@app.post("/embed")
async def embed_face(file: UploadFile = File(...)) -> JSONResponse:
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        payload = await file.read()
        image = Image.open(io.BytesIO(payload)).convert("RGB")
        vector = _load_provider().embed_face(image)
        return JSONResponse(
            {
                "embedding": vector.astype(np.float32).tolist(),
                "dim": int(vector.shape[0]),
                "model": _MODEL_NAME,
                "device": _DEVICE,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("LVFace embedding failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
async def health() -> JSONResponse:
    status = "ready" if _PROVIDER is not None else "initializing"
    return JSONResponse(
        {
            "status": status,
            "model": _MODEL_NAME,
            "dim": _MODEL_DIM,
            "device": _DEVICE,
        }
    )


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "LVFace Embedding Service",
            "version": "1.0.0",
            "endpoints": ["GET /health", "POST /embed"],
        }
    )


def main() -> None:
    host = os.getenv("LVFACE_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("LVFACE_SERVICE_PORT", os.getenv("LVFACE_SERVICE_DEFAULT_PORT", "8003")))
    logger.info("Starting LVFace service on %s:%s", host, port)
    uvicorn.run("app.lvface_http_service:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
