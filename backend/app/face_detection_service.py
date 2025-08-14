import os, random, logging
from typing import Protocol, List
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

class FaceDetectionProvider(Protocol):
    def detect(self, image: Image.Image) -> List[DetectedFace]: ...

class StubDetectionProvider:
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
        if device == 'cuda' and torch.cuda.is_available():
            self.device = 'cuda'
        else:
            if device == 'cuda':
                logging.getLogger('app').warning('CUDA requested for MTCNN but not available; using CPU')
            self.device = 'cpu'
        self.mtcnn = MTCNN(keep_all=True, device=self.device)
    def detect(self, image: Image.Image) -> List[DetectedFace]:  # pragma: no cover heavy
        import numpy as np
        boxes, probs = self.mtcnn.detect(image)
        out: List[DetectedFace] = []
        if boxes is None:
            return out
        for (x1, y1, x2, y2) in boxes:
            x1 = float(max(0,x1)); y1 = float(max(0,y1))
            x2 = float(max(x1+1,x2)); y2 = float(max(y1+1,y2))
            out.append(DetectedFace(x1, y1, x2 - x1, y2 - y1))
        return out

@lru_cache()
def get_face_detection_provider() -> FaceDetectionProvider:
    s = get_settings()
    # Force stub in test mode unless overridden to keep CI fast
    if s.run_mode == 'tests' and os.getenv('FORCE_REAL_FACE_PROVIDER','0') not in ('1','true','yes'):
        return StubDetectionProvider()
    provider = os.getenv('FACE_DETECT_PROVIDER', 'mtcnn').lower()
    device = s.embed_device
    if provider in ('mtcnn','facenet','auto'):
        try:
            return MTCNNDetectionProvider(device)
        except Exception as e:
            logging.getLogger('app').warning('Falling back to stub detection provider', exc_info=True)
            return StubDetectionProvider()
    logging.getLogger('app').warning(f"Unknown FACE_DETECT_PROVIDER '{provider}', using stub")
    return StubDetectionProvider()
