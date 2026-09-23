import os, random, logging
from typing import Protocol, List, Optional, Tuple
from functools import lru_cache
from dataclasses import dataclass
from PIL import Image
from .config import get_settings

@dataclass
class DetectedFace:
    x: float
    y: float
    w: float
    h: float
    landmarks: Optional[Tuple[Tuple[float, float], ...]] = None

class FaceDetectionProvider(Protocol):
    def detect(self, image: Image.Image) -> List[DetectedFace]: ...

class StubDetectionProvider:
    def __init__(self):
        self.runtime_name = 'builtin'
        self.runtime_version = None
        self.requested_device = None
        self.effective_device = 'stub'
        self.available_execution_providers = ('StubDetectionProvider',)
        self.execution_providers = ('StubDetectionProvider',)
        self.effective_execution_provider = 'StubDetectionProvider'
        self.accelerated = False

    def detect(self, image: Image.Image) -> List[DetectedFace]:
        # produce 1-3 random boxes
        w, h = image.size
        out: List[DetectedFace] = []
        for _ in range(random.randint(1,3)):
            fw = random.uniform(0.15, 0.35) * w
            fh = random.uniform(0.15, 0.35) * h
            fx = random.uniform(0, max(1, w - fw))
            fy = random.uniform(0, max(1, h - fh))
            out.append(DetectedFace(fx, fy, fw, fh))
        return out

class MTCNNDetectionProvider:
    def __init__(self, device: str):
        try:
            from facenet_pytorch import MTCNN  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("facenet-pytorch not installed; cannot use MTCNN for face detection") from e
        import torch  # type: ignore
        self.runtime_name = 'torch'
        self.runtime_version = str(torch.__version__)
        self.requested_device = device
        if device == 'cuda' and torch.cuda.is_available():
            self.device = 'cuda'
        else:
            if device == 'cuda':
                logging.getLogger('app').warning('CUDA requested for MTCNN but not available; using CPU')
            self.device = 'cpu'
        self.effective_device = self.device
        self.available_execution_providers = (
            ('torch-cuda', 'torch-cpu') if torch.cuda.is_available() else ('torch-cpu',)
        )
        self.execution_providers = (f'torch-{self.device}',)
        self.effective_execution_provider = self.execution_providers[0]
        self.accelerated = self.device == 'cuda'
        self.mtcnn = MTCNN(keep_all=True, device=self.device)
    def detect(self, image: Image.Image) -> List[DetectedFace]:  # pragma: no cover heavy
        import numpy as np
        boxes, probs, points = self.mtcnn.detect(image, landmarks=True)
        out: List[DetectedFace] = []
        if boxes is None:
            return out
        for index, (x1, y1, x2, y2) in enumerate(boxes):
            x1 = float(max(0,x1)); y1 = float(max(0,y1))
            x2 = float(max(x1+1,x2)); y2 = float(max(y1+1,y2))
            landmarks = None
            if points is not None and index < len(points):
                landmarks = tuple(
                    (float(point[0]), float(point[1])) for point in points[index]
                )
            out.append(DetectedFace(x1, y1, x2 - x1, y2 - y1, landmarks))
        return out

class InsightFaceDetectionProvider:
    def __init__(self, device: str, *, strict: bool = False):
        try:
            from insightface.app import FaceAnalysis  # type: ignore
            import onnxruntime as ort  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("insightface/onnxruntime not installed; cannot use InsightFace detection") from e

        det_pack = os.getenv('INSIGHTFACE_DET_PACK', 'buffalo_l')
        det_size = int(os.getenv('INSIGHTFACE_DET_SIZE', '640') or '640')
        model_root = os.path.abspath(os.path.expandvars(os.path.expanduser(
            os.getenv('INSIGHTFACE_ROOT', '~/.insightface')
        )))
        if strict:
            model_dir = os.path.join(model_root, 'models', det_pack)
            if not os.path.isfile(os.path.join(model_dir, 'det_10g.onnx')):
                raise RuntimeError('Strict InsightFace detection requires a preinstalled local SCRFD model')
        self.runtime_name = 'onnxruntime'
        self.runtime_version = str(ort.__version__)
        self.requested_device = device
        self.model_root = model_root
        self.model_pack = det_pack

        providers = ['CPUExecutionProvider']
        ctx_id = -1
        if device.startswith('cuda'):
            preload_dlls = getattr(ort, 'preload_dlls', None)
            if callable(preload_dlls):
                try:
                    # On Windows this lets ORT reuse the CUDA/cuDNN DLLs bundled
                    # with the compatible PyTorch wheel before a session exists.
                    preload_dlls()
                except Exception:
                    logging.getLogger('app').warning(
                        'Failed to preload CUDA libraries for InsightFace; '
                        'provider discovery will determine whether GPU is usable',
                        exc_info=True,
                    )
            available = ort.get_available_providers()
            if 'CUDAExecutionProvider' in available:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                ctx_id = 0
            else:
                logging.getLogger('app').warning('CUDA requested for InsightFace but CUDAExecutionProvider unavailable; using CPU')

        self.available_execution_providers = tuple(ort.get_available_providers())
        self.min_score = float(os.getenv('INSIGHTFACE_MIN_DET_SCORE', '0.35') or '0.35')
        self.app = FaceAnalysis(
            name=det_pack,
            root=model_root,
            allowed_modules=['detection'],
            providers=providers,
        )
        self.app.prepare(ctx_id=ctx_id, det_size=(det_size, det_size))
        self.execution_providers = self._session_execution_providers()
        self.effective_execution_provider = (
            self.execution_providers[0] if self.execution_providers else None
        )
        self.accelerated = (
            self.effective_execution_provider == 'CUDAExecutionProvider'
            if self.effective_execution_provider is not None
            else None
        )
        self.effective_device = (
            'cuda:0'
            if self.accelerated is True
            else 'cpu' if self.accelerated is False else None
        )

    def _session_execution_providers(self) -> Tuple[str, ...]:
        """Return providers from the prepared SCRFD session, not configuration."""
        discovered: List[str] = []
        for model in getattr(self.app, 'models', {}).values():
            session = getattr(model, 'session', None)
            get_providers = getattr(session, 'get_providers', None)
            if not callable(get_providers):
                continue
            for provider in get_providers():
                if provider not in discovered:
                    discovered.append(provider)
        return tuple(discovered)

    def detect(self, image: Image.Image) -> List[DetectedFace]:  # pragma: no cover heavy
        import numpy as np
        rgb = np.asarray(image.convert('RGB'))
        # InsightFace expects BGR ndarray
        bgr = rgb[:, :, ::-1]
        out: List[DetectedFace] = []
        for f in self.app.get(bgr):
            score = float(getattr(f, 'det_score', 1.0))
            if score < self.min_score:
                continue
            x1, y1, x2, y2 = f.bbox.tolist()
            x1 = float(max(0, x1)); y1 = float(max(0, y1))
            x2 = float(max(x1 + 1, x2)); y2 = float(max(y1 + 1, y2))
            raw_landmarks = getattr(f, 'kps', None)
            landmarks = None
            if raw_landmarks is not None:
                landmarks = tuple(
                    (float(point[0]), float(point[1])) for point in raw_landmarks
                )
            out.append(DetectedFace(x1, y1, x2 - x1, y2 - y1, landmarks))
        return out


def describe_detection_runtime(provider: FaceDetectionProvider) -> dict:
    """Describe the detector runtime without triggering inference."""
    execution_providers = tuple(getattr(provider, 'execution_providers', ()))
    effective_provider = getattr(provider, 'effective_execution_provider', None)
    if effective_provider is None and execution_providers:
        effective_provider = execution_providers[0]
    return {
        'runtime': getattr(provider, 'runtime_name', None),
        'runtime_version': getattr(provider, 'runtime_version', None),
        'requested_device': getattr(provider, 'requested_device', None),
        'effective_device': getattr(provider, 'effective_device', None),
        'available_execution_providers': list(
            getattr(provider, 'available_execution_providers', ())
        ),
        'execution_providers': list(execution_providers),
        'effective_execution_provider': effective_provider,
        'accelerated': getattr(provider, 'accelerated', None),
        'model_root': getattr(provider, 'model_root', None),
        'model_pack': getattr(provider, 'model_pack', None),
        'provider': type(provider).__name__,
    }

def _strict_inference_enabled() -> bool:
    return os.getenv('PHOTOHOUSE_STRICT_INFERENCE', '').strip().lower() in ('1', 'true', 'yes', 'on')


@lru_cache()
def get_face_detection_provider(*, strict: bool | None = None) -> FaceDetectionProvider:
    s = get_settings()
    strict_mode = _strict_inference_enabled() if strict is None else bool(strict)
    # Force stub in test mode unless overridden to keep CI fast
    if (not strict_mode and s.run_mode == 'tests'
            and os.getenv('FORCE_REAL_FACE_PROVIDER','0') not in ('1','true','yes')):
        return StubDetectionProvider()
    provider = s.face_detect_provider.lower() if hasattr(s,'face_detect_provider') else os.getenv('FACE_DETECT_PROVIDER','mtcnn').lower()
    device = s.embed_device
    if strict_mode and provider in ('stub', 'builtin'):
        raise RuntimeError('Strict inference refuses stub face detection')
    if provider in ('insight', 'scrfd'):
        try:
            result = InsightFaceDetectionProvider(device, strict=strict_mode)
            if strict_mode and result.effective_device not in ('cpu', 'cuda:0'):
                raise RuntimeError('Strict face detection provider did not report its effective device')
            if strict_mode and device.startswith('cuda') and not result.accelerated:
                raise RuntimeError('Requested CUDA face detection provider is not effective')
            return result
        except Exception as e:
            if strict_mode:
                raise RuntimeError('Strict InsightFace detection provider unavailable') from e
            logging.getLogger('app').warning('InsightFace detection unavailable; falling back to stub detection provider', exc_info=True)
            return StubDetectionProvider()
    if provider in ('mtcnn','facenet'):
        if strict_mode:
            raise RuntimeError('Strict inference does not enable MTCNN because its pretrained weights may download at startup')
        try:
            result = MTCNNDetectionProvider(device)
            if strict_mode and device.startswith('cuda') and not result.accelerated:
                raise RuntimeError('Requested CUDA face detection provider is not effective')
            return result
        except Exception as e:
            if strict_mode:
                raise RuntimeError('Strict MTCNN face detection provider unavailable') from e
            logging.getLogger('app').warning('MTCNN detection unavailable; falling back to stub detection provider', exc_info=True)
            return StubDetectionProvider()
    if provider == 'auto':
        errors = []
        builders = (InsightFaceDetectionProvider,) if strict_mode else (InsightFaceDetectionProvider, MTCNNDetectionProvider)
        for builder in builders:
            try:
                result = builder(device, strict=strict_mode) if strict_mode else builder(device)  # type: ignore[misc]
                if strict_mode and result.effective_device not in ('cpu', 'cuda:0'):
                    raise RuntimeError('Strict face detection provider did not report its effective device')
                if strict_mode and device.startswith('cuda') and not result.accelerated:
                    raise RuntimeError('Requested CUDA face detection provider is not effective')
                return result
            except Exception as exc:
                errors.append(exc)
                continue
        if strict_mode:
            raise RuntimeError('Strict face detection found no usable real provider') from errors[-1]
        logging.getLogger('app').warning('No real face detection provider available in auto mode; using stub')
        return StubDetectionProvider()
    if strict_mode:
        raise RuntimeError(f"Strict inference refuses unknown face detection provider {provider!r}")
    logging.getLogger('app').warning(f"Unknown FACE_DETECT_PROVIDER '{provider}', using stub")
    return StubDetectionProvider()
