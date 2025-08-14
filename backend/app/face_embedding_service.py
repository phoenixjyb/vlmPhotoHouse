import hashlib
import os
import time
from functools import lru_cache
from typing import Protocol, Optional
import numpy as np
from PIL import Image
from .config import get_settings
import logging

class FaceEmbeddingProvider(Protocol):
    def embed_face(self, image: Image.Image) -> np.ndarray: ...

class StubFaceEmbeddingProvider:
    def __init__(self, dim: int):
        self.dim = dim
    def embed_face(self, image: Image.Image) -> np.ndarray:
        buf = image.resize((64,64)).tobytes()
        h = hashlib.sha256(buf).digest()
        need = self.dim
        raw = (h * (need // len(h) + 1))[:need]
        arr = np.frombuffer(raw, dtype=np.uint8).astype('float32')
        arr = (arr - 127.5) / 128.0
        n = np.linalg.norm(arr)
        if n > 0:
            arr /= n
        return arr

class FacenetFaceEmbeddingProvider:
    """Provider using facenet-pytorch InceptionResnetV1 pretrained on VGGFace2.

    Optional dependency:
      pip install facenet-pytorch torch torchvision
    """
    def __init__(self, device: str):
        try:
            from facenet_pytorch import InceptionResnetV1  # type: ignore
            import torch  # type: ignore
        except Exception as e:  # pragma: no cover - only hit when lib missing
            raise RuntimeError("facenet-pytorch not available. Install with 'pip install facenet-pytorch torch torchvision' to use face_embed_provider=facenet") from e
        self.torch = torch
        self.device = device if device in ("cuda", "cpu") else "cpu"
        t0 = time.time()
        self.model = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
        try:  # pragma: no cover metrics side-effect
            import app.metrics as m
            m.face_embedding_model_load_seconds.labels('facenet').observe(time.time()-t0)
        except Exception:
            pass
        # Standard Facenet embedding dimension is 512
        self.dim = 512

    def embed_face(self, image: Image.Image) -> np.ndarray:  # pragma: no cover - requires heavy deps
        import torchvision.transforms as T  # type: ignore
        tfm = T.Compose([
            T.Resize((160,160)),
            T.ToTensor(),
            T.Normalize(mean=[0.5,0.5,0.5], std=[0.5,0.5,0.5]),
        ])
        x = tfm(image).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            emb = self.model(x).cpu().numpy()[0].astype('float32')
        # L2 normalize
        n = np.linalg.norm(emb)
        if n > 0:
            emb /= n
        return emb

class InsightFaceEmbeddingProvider:
    """Provider using insightface. Optional dependency:
      pip install insightface onnxruntime
    """
    def __init__(self, device: str):
        try:
            import insightface  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("insightface not available. Install with 'pip install insightface onnxruntime' to use face_embed_provider=insight") from e
        self.device = device
        # Use a lightweight default model
        t0 = time.time()
        self.app = insightface.app.FaceAnalysis(name='buffalo_l')
        self.app.prepare(ctx_id=0 if device=='cuda' else -1)
        try:  # pragma: no cover
            import app.metrics as m
            m.face_embedding_model_load_seconds.labels('insight').observe(time.time()-t0)
        except Exception:
            pass
        self.dim = 512

    def embed_face(self, image: Image.Image) -> np.ndarray:  # pragma: no cover
        import numpy as _np
        im = _np.array(image.convert('RGB'))
        # run detection+embedding even though we already have a crop; treat full frame
        feats = self.app.get(im)
        if not feats:
            # fallback: deterministic stub to avoid failing pipeline
            logging.getLogger('app').warning('InsightFace returned no embedding for crop; falling back to stub hash')
            return StubFaceEmbeddingProvider(self.dim).embed_face(image)
        # choose first face (crop already isolated)
        emb = feats[0].embedding.astype('float32')
        n = np.linalg.norm(emb)
        if n > 0:
            emb /= n
        return emb

class LVFaceEmbeddingProvider:
    """ONNX-based LVFace provider.

    Expects an ONNX model (LVFACE_MODEL_PATH) producing a 1xD embedding from a 112x112 RGB input.
    """
    def __init__(self, model_path: str, device: str, target_dim: int):
        import onnxruntime as ort  # type: ignore
        t0 = time.time()
        providers = []
        if device=='cuda' and 'CUDAExecutionProvider' in ort.get_available_providers():
            providers.append('CUDAExecutionProvider')
        providers.append('CPUExecutionProvider')
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.target_dim = target_dim
        try:  # pragma: no cover
            import app.metrics as m
            m.face_embedding_model_load_seconds.labels('lvface').observe(time.time()-t0)
        except Exception:
            pass

    def embed_face(self, image: Image.Image) -> np.ndarray:  # pragma: no cover heavy
        import numpy as _np
        im = image.convert('RGB').resize((112,112))
        arr = _np.asarray(im).astype('float32') / 255.0
        arr = arr.transpose(2,0,1)[None, ...]  # NCHW
        out = self.session.run(None, {self.input_name: arr})[0]
        vec = out[0].astype('float32')
        if self.target_dim < vec.shape[0]:
            vec = vec[:self.target_dim]
        elif self.target_dim > vec.shape[0]:
            need = self.target_dim - vec.shape[0]
            h = hashlib.sha256(vec.tobytes()).digest()
            raw = (h * (need // len(h) + 1))[:need]
            pad = np.frombuffer(raw, dtype=np.uint8).astype('float32')
            pad = (pad - 127.5)/128.0
            vec = np.concatenate([vec, pad])
        n = np.linalg.norm(vec)
        if n>0:
            vec /= n
        return vec

@lru_cache()
def get_face_embedding_provider() -> FaceEmbeddingProvider:
    s = get_settings()
    provider_req = s.face_embed_provider.lower()
    run_mode = s.run_mode
    device_req = s.embed_device.lower()

    # In test runs always force stub unless explicitly overridden (keeps CI fast & deterministic)
    if run_mode == 'tests' and os.getenv('FORCE_REAL_FACE_PROVIDER','0') not in ('1','true','yes'):
        return StubFaceEmbeddingProvider(s.face_embed_dim)

    # Auto provider selection: try insightface then facenet then stub
    if provider_req in ('auto','best'):
        for candidate in ('insight','facenet','stub'):
            os.environ['FACE_EMBED_PROVIDER'] = candidate  # update for introspection
            try:
                _prov = _build_provider(candidate, device_req, s.face_embed_dim)
                logging.getLogger('app').info(f"face embedding provider auto-selected: {candidate}")
                return _prov
            except Exception:
                continue
        return StubFaceEmbeddingProvider(s.face_embed_dim)

    try:
        return _build_provider(provider_req, device_req, s.face_embed_dim)
    except Exception:
        logging.getLogger('app').warning(f"Falling back to stub face embedding provider (requested '{provider_req}' unavailable)", exc_info=True)
        return StubFaceEmbeddingProvider(s.face_embed_dim)


def _build_provider(provider: str, device_req: str, target_dim: int) -> FaceEmbeddingProvider:
    provider = provider.lower()
    if provider == 'stub':
        return StubFaceEmbeddingProvider(target_dim)
    if provider == 'facenet':
        # GPU detection / fallback
        if device_req == 'cuda':
            try:
                import torch  # type: ignore
                if not torch.cuda.is_available():  # pragma: no cover
                    logging.getLogger('app').warning('CUDA requested for facenet but not available; using CPU')
                    device = 'cpu'
                else:
                    device = 'cuda'
            except Exception:
                device = 'cpu'
        else:
            device = 'cpu'
        facenet = FacenetFaceEmbeddingProvider(device)
        if target_dim != facenet.dim:
            base_dim = facenet.dim
            def _wrap(image: Image.Image, inner=facenet):
                vec = inner.embed_face(image)
                if target_dim == base_dim:
                    return vec
                if target_dim < base_dim:
                    return vec[:target_dim]
                need = target_dim - base_dim
                h = hashlib.sha256(vec.tobytes()).digest()
                raw = (h * (need // len(h) + 1))[:need]
                pad = np.frombuffer(raw, dtype=np.uint8).astype('float32')
                pad = (pad - 127.5)/128.0
                out = np.concatenate([vec, pad])
                n = np.linalg.norm(out)
                if n>0:
                    out /= n
                return out
            class Adapted(FaceEmbeddingProvider):
                def embed_face(self, image: Image.Image) -> np.ndarray:
                    return _wrap(image)
            return Adapted()
        return facenet
    if provider == 'insight':
        ins = InsightFaceEmbeddingProvider('cuda' if device_req=='cuda' else 'cpu')
        return ins
    if provider == 'lvface':
        from .config import get_settings as _gs
        s = _gs()
        return LVFaceEmbeddingProvider(s.lvface_model_path, 'cuda' if device_req=='cuda' else 'cpu', target_dim)
    raise RuntimeError(f'Unknown provider {provider}')
