"""Strict inference mode rejects placeholder output and reports effective runtime."""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app import face_detection_service as detection
from app import face_embedding_service as face_embedding
from app.vector_index import EmbeddingService


def test_strict_image_embedding_requires_explicit_local_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setenv('PHOTOHOUSE_STRICT_INFERENCE', 'true')
    monkeypatch.delenv('PHOTOHOUSE_IMAGE_EMBEDDING_CHECKPOINT', raising=False)
    with pytest.raises(RuntimeError, match='existing local'):
        EmbeddingService('clip-ViT-B-32', 'stub-clip', 2)
    with pytest.raises(RuntimeError, match='refuses a stub'):
        EmbeddingService('stub-clip', 'stub-clip', 2)

    # Existing callers preserve their legacy deterministic stub behavior.
    legacy = EmbeddingService('stub-clip', 'stub-clip', 2, strict=False)
    assert np.array_equal(legacy.embed_image('unused'), legacy.embed_image('unused'))


def test_strict_image_embedding_reports_real_provider_and_fails_inference(monkeypatch, tmp_path):
    checkpoint = tmp_path / 'clip.bin'
    checkpoint.write_bytes(b'synthetic-local-checkpoint')
    monkeypatch.setenv('PHOTOHOUSE_IMAGE_EMBEDDING_CHECKPOINT', str(checkpoint))

    class FakeTensor:
        def to(self, _device): return self
        def norm(self, **_kwargs): return self
        def __truediv__(self, _other): return self
        def cpu(self): return self
        def numpy(self): return np.array([[0.6, 0.8]], dtype=np.float32)

    class Model:
        text_projection = np.zeros((1, 2), dtype=np.float32)
        def parameters(self): return iter([types.SimpleNamespace(device='cpu')])
        def encode_image(self, _image): return FakeTensor()

    class PreprocessResult:
        def unsqueeze(self, _axis): return self
        def to(self, _device): return self

    fake_open_clip = types.ModuleType('open_clip')
    calls = {}
    def create_model(name, *, pretrained, device):
        calls.update(name=name, pretrained=pretrained, device=device)
        return Model(), None, lambda _image: PreprocessResult()
    fake_open_clip.create_model_and_transforms = create_model
    fake_open_clip.get_tokenizer = lambda _name: lambda _texts: None
    monkeypatch.setitem(sys.modules, 'open_clip', fake_open_clip)

    service = EmbeddingService('clip-ViT-B-32', 'stub-clip', 2, 'cpu', strict=True)
    assert calls['pretrained'] == str(checkpoint)
    assert service.describe_runtime() == {
        'image_model': 'clip-ViT-B-32', 'requested_device': 'cpu',
        'effective_provider': 'open_clip', 'effective_device': 'cpu', 'strict': True,
    }
    assert service._clip_model is not None

    service._clip_model.encode_image = lambda _image: (_ for _ in ()).throw(ValueError('bad inference'))
    with pytest.raises(RuntimeError, match='inference failed'):
        service.embed_image('unused')


def test_strict_detection_refuses_stub_and_unavailable_provider(monkeypatch):
    monkeypatch.setenv('PHOTOHOUSE_STRICT_INFERENCE', 'true')
    settings = types.SimpleNamespace(run_mode='tests', face_detect_provider='stub', embed_device='cpu')
    monkeypatch.setattr(detection, 'get_settings', lambda: settings)
    detection.get_face_detection_provider.cache_clear()
    with pytest.raises(RuntimeError, match='refuses stub'):
        detection.get_face_detection_provider()

    settings.face_detect_provider = 'insight'
    monkeypatch.setattr(detection, 'InsightFaceDetectionProvider',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('unavailable')))
    detection.get_face_detection_provider.cache_clear()
    with pytest.raises(RuntimeError, match='provider unavailable'):
        detection.get_face_detection_provider(strict=True)

    # Non-strict test mode remains deterministic and visibly identifies the stub.
    detection.get_face_detection_provider.cache_clear()
    provider = detection.get_face_detection_provider(strict=False)
    assert detection.describe_detection_runtime(provider)['effective_device'] == 'stub'
    detection.get_face_detection_provider.cache_clear()


def test_strict_face_embedding_refuses_stub_and_invalid_vectors(monkeypatch):
    monkeypatch.setenv('PHOTOHOUSE_STRICT_INFERENCE', 'true')
    settings = types.SimpleNamespace(run_mode='tests', face_embed_provider='stub',
                                     embed_device='cpu', face_embed_dim=4)
    monkeypatch.setattr(face_embedding, 'get_settings', lambda: settings)
    face_embedding.get_face_embedding_provider.cache_clear()
    with pytest.raises(RuntimeError, match='refuses stub'):
        face_embedding.get_face_embedding_provider()

    legacy = face_embedding.get_face_embedding_provider(strict=False)
    assert isinstance(legacy, face_embedding.StubFaceEmbeddingProvider)

    checked = face_embedding._StrictFaceEmbeddingProvider(
        types.SimpleNamespace(embed_face=lambda _image: np.zeros(4, dtype=np.float32)), 4)
    with pytest.raises(RuntimeError, match='zero embedding'):
        checked.embed_face(None)
    assert face_embedding.describe_face_embedding_runtime(legacy)['provider'] == 'StubFaceEmbeddingProvider'
    face_embedding.get_face_embedding_provider.cache_clear()


def test_strict_lvface_rejects_model_dimension_adaptation(monkeypatch, tmp_path):
    model_path = tmp_path / 'lvface.onnx'
    model_path.write_bytes(b'synthetic-onnx-placeholder')

    class FakeSession:
        def get_providers(self): return ['CPUExecutionProvider']
        def get_inputs(self): return [types.SimpleNamespace(name='input')]
        def get_outputs(self): return [types.SimpleNamespace(shape=[1, 512])]

    fake_ort = types.ModuleType('onnxruntime')
    fake_ort.__version__ = 'synthetic'
    fake_ort.get_available_providers = lambda: ['CPUExecutionProvider']
    fake_ort.InferenceSession = lambda *_args, **_kwargs: FakeSession()
    monkeypatch.setitem(sys.modules, 'onnxruntime', fake_ort)

    with pytest.raises(RuntimeError, match='dimension must be statically known'):
        face_embedding.LVFaceEmbeddingProvider(str(model_path), 'cpu', 128, strict=True)


def test_strict_lvface_cuda_index_routes_to_cuda_provider(monkeypatch, tmp_path):
    model_path = tmp_path / 'lvface.onnx'
    model_path.write_bytes(b'synthetic-local-model')
    monkeypatch.delenv('LVFACE_SERVICE_URL', raising=False)
    monkeypatch.delenv('LVFACE_EXTERNAL_DIR', raising=False)
    monkeypatch.setattr(sys.modules['app.config'], 'get_settings', lambda: types.SimpleNamespace(
        lvface_service_url='', lvface_external_dir='', lvface_model_path=str(model_path)))
    calls = []
    def fake_provider(_model_path, device, dimension, *, strict):
        calls.append((device, dimension, strict))
        return types.SimpleNamespace(effective_device='cuda', effective_provider='CUDAExecutionProvider')
    monkeypatch.setattr(face_embedding, 'LVFaceEmbeddingProvider', fake_provider)
    provider = face_embedding._build_provider('lvface', 'cuda:0', 512, strict=True)
    assert provider.effective_device == 'cuda'
    assert calls == [('cuda', 512, True)]
