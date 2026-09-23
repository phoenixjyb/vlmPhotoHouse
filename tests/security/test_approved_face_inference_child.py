"""Deterministic, injected-provider tests for the isolated face child."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import approved_face_inference_child as child


class FakeDetector:
    requested_device = 'cuda'
    effective_execution_provider = 'CUDAExecutionProvider'

    def __init__(self, faces=None):
        self.faces = faces if faces is not None else [SimpleNamespace(
            x=2.1, y=3.2, w=10.2, h=11.4, landmarks=((3, 4), (6, 7)))]

    def detect(self, image):
        return self.faces


class FakeEmbedder:
    requested_device = 'cuda'
    effective_provider = 'CUDAExecutionProvider,CPUExecutionProvider'

    def __init__(self, vector=None):
        self.vector = np.arange(1, 513, dtype=np.float32) if vector is None else vector

    def embed_face(self, image):
        return self.vector


def setup(tmp_path, size=(32, 24)):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / 'source.png'
    Image.new('RGB', size, (30, 80, 120)).save(source)
    stage = tmp_path / 'stage'
    stage.mkdir()
    return source, stage, stage / 'receipt.json'


def test_detect_writes_bounded_crop_and_compact_receipt(tmp_path):
    source, stage, receipt = setup(tmp_path)
    result = child.run('detect', source, stage, receipt,
                       detector=FakeDetector(), insightface_root=stage)
    assert result['operation'] == 'detect'
    assert result['provider'] == 'CUDAExecutionProvider'
    assert result['effective_device'] == 'cuda:0'
    assert result['faces'][0]['bbox'] == [2, 3, 11, 12]
    crop = Image.open(stage / 'face-00.jpg')
    assert crop.size == (256, 256)
    assert json.loads(receipt.read_text()) == result


def test_embed_writes_finite_unit_512_float32_npy(tmp_path):
    source, stage, receipt = setup(tmp_path)
    model = tmp_path / 'model.onnx'
    model.write_bytes(b'fake checkpoint')
    result = child.run('embed', source, stage, receipt,
                       embedder=FakeEmbedder(), model_path=model)
    vector = np.load(stage / 'embedding.npy', allow_pickle=False)
    assert vector.shape == (512,)
    assert vector.dtype == np.float32
    assert np.isfinite(vector).all()
    assert np.linalg.norm(vector) == pytest.approx(1.0)
    assert result['effective_device'] == 'cuda'
    assert json.loads(receipt.read_text()) == result


@pytest.mark.parametrize('provider', [
    SimpleNamespace(requested_device='cuda', effective_execution_provider='CPUExecutionProvider'),
    SimpleNamespace(requested_device='cpu', effective_execution_provider='CUDAExecutionProvider'),
])
def test_non_cuda_provider_is_refused(tmp_path, provider):
    source, stage, receipt = setup(tmp_path)
    with pytest.raises(child.Refused, match='cuda|logical'):
        child.run('detect', source, stage, receipt, detector=provider,
                  insightface_root=stage)


def test_input_size_pixel_count_and_face_count_are_bounded(tmp_path, monkeypatch):
    source, stage, receipt = setup(tmp_path)
    monkeypatch.setattr(child, 'MAX_INPUT_BYTES', 4)
    with pytest.raises(child.Refused, match='input_size'):
        child.run('detect', source, stage, receipt, detector=FakeDetector(),
                  insightface_root=stage)

    source, stage, receipt = setup(tmp_path / 'pixels', (100, 100))
    monkeypatch.setattr(child, 'MAX_INPUT_BYTES', 256 * 1024**2)
    monkeypatch.setattr(child, 'MAX_PIXELS', 999)
    with pytest.raises(child.Refused, match='pixel_count'):
        child.run('detect', source, stage, receipt, detector=FakeDetector(),
                  insightface_root=stage)

    source, stage, receipt = setup(tmp_path / 'faces')
    monkeypatch.setattr(child, 'MAX_FACES', 0)
    with pytest.raises(child.Refused, match='face_count'):
        child.run('detect', source, stage, receipt, detector=FakeDetector(),
                  insightface_root=stage)


def test_bad_boxes_and_nonfinite_vectors_fail_closed(tmp_path):
    source, stage, receipt = setup(tmp_path)
    face = SimpleNamespace(x=float('nan'), y=0, w=1, h=1, landmarks=None)
    with pytest.raises(child.Refused, match='non_finite'):
        child.run('detect', source, stage, receipt, detector=FakeDetector([face]),
                  insightface_root=stage)

    source, stage, receipt = setup(tmp_path / 'embed')
    vector = np.ones(512, dtype=np.float32)
    vector[0] = np.inf
    model = tmp_path / 'embed' / 'model.onnx'
    model.write_bytes(b'fake checkpoint')
    with pytest.raises(child.Refused, match='shape_or_values'):
        child.run('embed', source, stage, receipt, embedder=FakeEmbedder(vector),
                  model_path=model)


def test_receipt_must_be_new_and_inside_stage(tmp_path):
    source, stage, receipt = setup(tmp_path)
    with pytest.raises(child.Refused, match='inside_stage'):
        child.run('detect', source, stage, tmp_path / 'receipt.json',
                  detector=FakeDetector(), insightface_root=stage)
    receipt.write_text('{}')
    with pytest.raises(child.Refused, match='new_file'):
        child.run('detect', source, stage, receipt,
                  detector=FakeDetector(), insightface_root=stage)


def test_source_does_not_import_database_or_network_clients():
    source = (ROOT / 'scripts' / 'approved_face_inference_child.py').read_text()
    for forbidden in ('sqlite3', 'socket', 'requests', 'httpx', 'urllib'):
        assert forbidden not in source


def test_probe_uses_only_synthetic_image_and_loads_both_providers(tmp_path):
    _, stage, receipt = setup(tmp_path)
    detector = FakeDetector()
    embedder = FakeEmbedder()
    checkpoint = tmp_path / 'model.onnx'
    checkpoint.write_bytes(b'fake checkpoint')
    result = child.run('probe', None, stage, receipt, insightface_root=stage,
                       model_path=checkpoint, detector=detector, embedder=embedder)
    assert result['operation'] == 'probe'
    assert result['provider'] == 'CUDAExecutionProvider'
    assert result['effective_device'] == 'cuda:0'
    assert result['embedding_device'] == 'cuda'
    assert result['outputs'] == []
    assert sorted(path.name for path in stage.iterdir()) == ['receipt.json']
