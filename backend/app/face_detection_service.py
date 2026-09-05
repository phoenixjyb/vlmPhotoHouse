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
    def __init__(self, device: str):
        try:
            from insightface.app import FaceAnalysis  # type: ignore
            import onnxruntime as ort  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("insightface/onnxruntime not installed; cannot use InsightFace detection") from e

        det_pack = os.getenv('INSIGHTFACE_DET_PACK', 'buffalo_l')
        det_size = int(os.getenv('INSIGHTFACE_DET_SIZE', '640') or '640')
        self.runtime_name = 'onnxruntime'
        self.runtime_version = str(ort.__version__)
        self.requested_device = device

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
        self.app = FaceAnalysis(name=det_pack, allowed_modules=['detection'], providers=providers)
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
    }

@lru_cache()
def get_face_detection_provider() -> FaceDetectionProvider:
    s = get_settings()
    # Force stub in test mode unless overridden to keep CI fast
    if s.run_mode == 'tests' and os.getenv('FORCE_REAL_FACE_PROVIDER','0') not in ('1','true','yes'):
        return StubDetectionProvider()
    provider = s.face_detect_provider.lower() if hasattr(s,'face_detect_provider') else os.getenv('FACE_DETECT_PROVIDER','mtcnn').lower()
    device = s.embed_device
    if provider in ('insight', 'scrfd'):
        try:
            return InsightFaceDetectionProvider(device)
        except Exception as e:
            logging.getLogger('app').warning('InsightFace detection unavailable; falling back to stub detection provider', exc_info=True)
            return StubDetectionProvider()
    if provider in ('mtcnn','facenet'):
        try:
            return MTCNNDetectionProvider(device)
        except Exception as e:
            logging.getLogger('app').warning('MTCNN detection unavailable; falling back to stub detection provider', exc_info=True)
            return StubDetectionProvider()
    if provider == 'auto':
        for builder in (InsightFaceDetectionProvider, MTCNNDetectionProvider):
            try:
                return builder(device)  # type: ignore[misc]
            except Exception:
                continue
        logging.getLogger('app').warning('No real face detection provider available in auto mode; using stub')
        return StubDetectionProvider()
    logging.getLogger('app').warning(f"Unknown FACE_DETECT_PROVIDER '{provider}', using stub")
    return StubDetectionProvider()
