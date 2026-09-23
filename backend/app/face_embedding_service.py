import hashlib
import os
import time
import io
import httpx
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
        self.effective_provider = 'facenet-pytorch'
        self.requested_device = device
        self.effective_device = self.device
        t0 = time.time()
        self.model = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
        try:
            self.effective_device = str(next(self.model.parameters()).device)
        except Exception:
            self.effective_device = self.device
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
    def __init__(self, device: str, *, strict: bool = False):
        try:
            import insightface  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("insightface not available. Install with 'pip install insightface onnxruntime' to use face_embed_provider=insight") from e
        self.device = device
        self.requested_device = device
        self.effective_provider = 'insightface'
        model_root = os.path.abspath(os.path.expandvars(os.path.expanduser(
            os.getenv('INSIGHTFACE_ROOT', '~/.insightface')
        )))
        self.model_root = model_root
        model_dir = os.path.join(model_root, 'models', 'buffalo_l')
        if strict and not all(os.path.isfile(os.path.join(model_dir, name))
                              for name in ('det_10g.onnx', 'w600k_r50.onnx')):
            raise RuntimeError('Strict InsightFace embedding requires preinstalled local buffalo_l models')
        # Use a lightweight default model
        t0 = time.time()
        self.app = insightface.app.FaceAnalysis(name='buffalo_l', root=model_root)
        self.app.prepare(ctx_id=0 if device=='cuda' else -1)
        self.effective_device = _insightface_effective_device(self.app, device)
        self.strict = strict
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
            if self.strict:
                raise RuntimeError('Strict InsightFace inference found no face in the supplied crop')
            # Legacy mode retains its deterministic fallback for compatibility.
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
    def __init__(self, model_path: str, device: str, target_dim: int, *, strict: bool = False):
        import onnxruntime as ort  # type: ignore
        t0 = time.time()
        providers = []
        if device=='cuda' and 'CUDAExecutionProvider' in ort.get_available_providers():
            providers.append('CUDAExecutionProvider')
        providers.append('CPUExecutionProvider')
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.requested_device = device
        self.effective_provider = ','.join(self.session.get_providers())
        self.effective_device = 'cuda' if 'CUDAExecutionProvider' in self.session.get_providers() else 'cpu'
        self.input_name = self.session.get_inputs()[0].name
        self.target_dim = target_dim
        self.strict = strict
        if strict:
            output_shape = getattr(self.session.get_outputs()[0], 'shape', None)
            if (not output_shape or not isinstance(output_shape[-1], int)
                    or output_shape[-1] != target_dim):
                raise RuntimeError('Strict LVFace ONNX output dimension must be statically known and match FACE_EMBED_DIM')
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
        if self.strict and vec.shape != (self.target_dim,):
            raise RuntimeError('Strict LVFace ONNX output dimension differs from configured model dimension')
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


class LVFaceHTTPProvider:
    """HTTP-based LVFace embedding provider."""

    def __init__(self, service_url: str, target_dim: int, *, strict: bool = False,
                 expected_model: str | None = None):
        self.service_url = service_url.rstrip('/')
        self.target_dim = target_dim
        self.strict = strict
        self.expected_model = expected_model
        self.effective_model = None
        self.effective_provider = 'lvface-http'
        self.effective_device = None
        self.logger = logging.getLogger('app.lvface_http_provider')
        try:
            with httpx.Client(timeout=5.0, proxies={}) as client:
                resp = client.get(f"{self.service_url}/health")
                if resp.status_code == 200:
                    info = resp.json()
                    self.effective_device = str(info.get('effective_device') or info.get('device') or '') or None
                    self.effective_model = str(info.get('model') or info.get('model_name') or '') or None
                    self.logger.info(
                        "Connected to LVFace service %s (device=%s)",
                        info.get('status', 'unknown'),
                        info.get('device', 'unknown'))
                else:
                    self.logger.warning(
                        "LVFace service health check failed: %s", resp.status_code)
        except Exception as exc:
            self.logger.warning("LVFace HTTP service not immediately available: %s", exc)

    def embed_face(self, image: Image.Image) -> np.ndarray:
        buffer = io.BytesIO()
        image.convert('RGB').resize((112, 112)).save(buffer, format='PNG')
        buffer.seek(0)
        payload = buffer.getvalue()
        try:
            with httpx.Client(timeout=20.0, proxies={}) as client:
                files = {'file': ('face.png', payload, 'image/png')}
                response = client.post(f"{self.service_url}/embed", files=files)
            if response.status_code != 200:
                raise RuntimeError(
                    f"LVFace HTTP error {response.status_code}: {response.text[:200]}")
            data = response.json()
            response_model = str(data.get('model') or data.get('model_name') or '') or None
            if self.strict and response_model and response_model != self.effective_model:
                raise RuntimeError('Strict LVFace service model identity changed after health check')
            vector = data.get('embedding') or data.get('vector') or []
            arr = np.array(vector, dtype=np.float32)
            if arr.size == 0:
                raise ValueError('Empty embedding returned from LVFace HTTP service')
            if self.strict and arr.shape != (self.target_dim,):
                raise RuntimeError('Strict LVFace service output dimension differs from configured model dimension')
            if self.target_dim < arr.shape[0]:
                arr = arr[:self.target_dim]
            elif self.target_dim > arr.shape[0]:
                need = self.target_dim - arr.shape[0]
                digest = hashlib.sha256(arr.tobytes()).digest()
                raw = (digest * (need // len(digest) + 1))[:need]
                pad = np.frombuffer(raw, dtype=np.uint8).astype('float32')
                pad = (pad - 127.5) / 128.0
                arr = np.concatenate([arr, pad])
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            return arr
        except Exception as exc:
            self.logger.error("LVFace HTTP embedding failure: %s", exc)
            raise

@lru_cache()
def get_face_embedding_provider(*, strict: bool | None = None) -> FaceEmbeddingProvider:
    s = get_settings()
    strict_mode = _strict_inference_enabled() if strict is None else bool(strict)
    provider_req = s.face_embed_provider.lower()
    run_mode = s.run_mode
    device_req = s.embed_device.lower()

    # In test runs always force stub unless explicitly overridden (keeps CI fast & deterministic)
    if (not strict_mode and run_mode == 'tests'
            and os.getenv('FORCE_REAL_FACE_PROVIDER','0') not in ('1','true','yes')):
        return StubFaceEmbeddingProvider(s.face_embed_dim)

    if strict_mode and provider_req == 'stub':
        raise RuntimeError('Strict inference refuses stub face embeddings')

    # Auto provider selection keeps legacy stub fallback only outside strict mode.
    if provider_req in ('auto','best'):
        errors = []
        candidates = ('lvface','insight','facenet') if strict_mode else ('lvface','insight','facenet','stub')
        for candidate in candidates:
            try:
                _prov = _build_provider(candidate, device_req, s.face_embed_dim, strict=strict_mode)
                logging.getLogger('app').info(f"face embedding provider auto-selected: {candidate}")
                return _StrictFaceEmbeddingProvider(_prov, s.face_embed_dim) if strict_mode else _prov
            except Exception as exc:
                errors.append(exc)
                continue
        if strict_mode:
            raise RuntimeError('Strict face embedding found no usable real provider') from errors[-1]
        return StubFaceEmbeddingProvider(s.face_embed_dim)

    try:
        provider = _build_provider(provider_req, device_req, s.face_embed_dim, strict=strict_mode)
        return _StrictFaceEmbeddingProvider(provider, s.face_embed_dim) if strict_mode else provider
    except Exception as exc:
        if strict_mode:
            raise RuntimeError(f"Strict face embedding provider {provider_req!r} unavailable") from exc
        logging.getLogger('app').warning(f"Falling back to stub face embedding provider (requested '{provider_req}' unavailable)", exc_info=True)
        return StubFaceEmbeddingProvider(s.face_embed_dim)


def _build_provider(provider: str, device_req: str, target_dim: int, *, strict: bool = False) -> FaceEmbeddingProvider:
    provider = provider.lower()
    cuda_requested = device_req == 'cuda' or (strict and device_req.startswith('cuda:'))
    if provider == 'stub':
        if strict:
            raise RuntimeError('Strict inference refuses stub face embeddings')
        return StubFaceEmbeddingProvider(target_dim)
    if provider == 'facenet':
        if strict:
            raise RuntimeError('Strict inference does not enable FaceNet because pretrained weights may download at startup')
        # GPU detection / fallback
        if cuda_requested:
            try:
                import torch  # type: ignore
                if not torch.cuda.is_available():  # pragma: no cover
                    if strict:
                        raise RuntimeError('Strict face embedding requires CUDA but CUDA is unavailable')
                    logging.getLogger('app').warning('CUDA requested for facenet but not available; using CPU')
                    device = 'cpu'
                else:
                    device = 'cuda'
            except Exception:
                if strict:
                    raise RuntimeError('Strict face embedding could not verify CUDA availability')
                device = 'cpu'
        else:
            device = 'cpu'
        facenet = FacenetFaceEmbeddingProvider(device)
        if target_dim != facenet.dim:
            if strict:
                raise RuntimeError(f'Strict face embedding dimension mismatch: model={facenet.dim}, configured={target_dim}')
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
        ins = InsightFaceEmbeddingProvider('cuda' if cuda_requested else 'cpu', strict=strict)
        if strict and ins.effective_device not in ('cuda', 'cpu'):
            raise RuntimeError('Strict InsightFace embedding did not report its effective device')
        if strict and device_req.startswith('cuda') and ins.effective_device != 'cuda':
            raise RuntimeError('Strict InsightFace embedding did not activate CUDA')
        if strict and target_dim != ins.dim:
            raise RuntimeError(f'Strict face embedding dimension mismatch: model={ins.dim}, configured={target_dim}')
        return ins
    if provider == 'lvface':
        from .config import get_settings as _gs
        s = _gs()

        lvface_service_url = os.getenv('LVFACE_SERVICE_URL') or getattr(s, 'lvface_service_url', '')
        if lvface_service_url:
            expected_model = str(getattr(s, 'lvface_model_name', os.getenv('LVFACE_MODEL_NAME', '')) or '')
            provider_obj = LVFaceHTTPProvider(lvface_service_url, target_dim,
                                              strict=strict, expected_model=expected_model or None)
            provider_obj.requested_device = device_req
            if strict and provider_obj.effective_device not in ('cpu', 'cuda', 'cuda:0', 'cuda:1'):
                raise RuntimeError('Strict LVFace HTTP provider did not report its effective device')
            if strict and (not provider_obj.effective_model
                           or (expected_model and provider_obj.effective_model != expected_model)):
                raise RuntimeError('Strict LVFace HTTP provider did not report the expected model identity')
            if strict and device_req.startswith('cuda') and not provider_obj.effective_device.startswith('cuda'):
                raise RuntimeError('Strict LVFace HTTP provider did not activate CUDA')
            return provider_obj

        lvface_external_dir = os.getenv('LVFACE_EXTERNAL_DIR') or getattr(s, 'lvface_external_dir', '')
        if lvface_external_dir:
            if strict:
                raise RuntimeError('Strict inference refuses LVFace subprocess: execution bounds, effective device, and model provenance are not reported')
            from .lvface_subprocess import LVFaceSubprocessProvider
            model_name = os.getenv('LVFACE_MODEL_NAME', 'lvface.onnx')
            python_exe = os.getenv('LVFACE_PYTHON_EXE', '').strip() or None
            provider_obj = LVFaceSubprocessProvider(lvface_external_dir, model_name, target_dim, python_exe=python_exe)
            provider_obj.effective_provider = 'lvface-subprocess'
            provider_obj.effective_device = 'cuda' if provider_obj.cuda_visible_devices else 'unknown'
            provider_obj.requested_device = device_req
            if strict and provider_obj.effective_device == 'unknown':
                raise RuntimeError('Strict LVFace subprocess does not report a verifiable effective device')
            if strict and device_req.startswith('cuda') and provider_obj.effective_device != 'cuda':
                raise RuntimeError('Strict LVFace subprocess did not activate CUDA')
            return provider_obj

        model_path = str(s.lvface_model_path)
        if strict and (not os.path.isabs(model_path) or not os.path.isfile(model_path)):
            raise RuntimeError('Strict LVFace ONNX requires an existing absolute local model path')
        provider_obj = LVFaceEmbeddingProvider(model_path, 'cuda' if cuda_requested else 'cpu', target_dim, strict=strict)
        if strict and device_req.startswith('cuda') and provider_obj.effective_device != 'cuda':
            raise RuntimeError('Strict LVFace ONNX provider did not activate CUDA')
        return provider_obj
    raise RuntimeError(f'Unknown provider {provider}')


class _StrictFaceEmbeddingProvider:
    """Validate provider output so invalid or zero embeddings cannot be stored."""
    def __init__(self, inner: FaceEmbeddingProvider, dimension: int):
        self._inner = inner
        self.dim = dimension

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def embed_face(self, image: Image.Image) -> np.ndarray:
        vec = np.asarray(self._inner.embed_face(image), dtype=np.float32)
        if vec.ndim != 1 or vec.shape[0] != self.dim:
            raise RuntimeError('Strict face provider returned an unexpected embedding shape')
        if not np.isfinite(vec).all() or float(np.linalg.norm(vec)) == 0.0:
            raise RuntimeError('Strict face provider returned an invalid or zero embedding')
        return vec


def _strict_inference_enabled() -> bool:
    return os.getenv('PHOTOHOUSE_STRICT_INFERENCE', '').strip().lower() in ('1', 'true', 'yes', 'on')


def describe_face_embedding_runtime(provider: FaceEmbeddingProvider) -> dict:
    return {
        'provider': getattr(provider, 'effective_provider', type(provider).__name__),
        'requested_device': getattr(provider, 'requested_device', getattr(provider, 'device', None)),
        'effective_device': getattr(provider, 'effective_device', getattr(provider, 'device', None)),
        'dimension': getattr(provider, 'dim', getattr(provider, 'target_dim', None)),
    }


def _insightface_effective_device(app, requested: str) -> str | None:
    providers = []
    for model in getattr(app, 'models', {}).values():
        session = getattr(model, 'session', None)
        get_providers = getattr(session, 'get_providers', None)
        if callable(get_providers):
            providers.extend(get_providers())
    return 'cuda' if 'CUDAExecutionProvider' in providers else 'cpu' if providers else None
