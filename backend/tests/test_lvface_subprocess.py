"""Test for LVFace subprocess provider."""
import os
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image
import numpy as np


def _fake_lvface_install(tmp_path):
    lvface_dir = tmp_path / 'LVFace'
    model_dir = lvface_dir / 'models'
    model_dir.mkdir(parents=True)
    (model_dir / 'model.onnx').write_bytes(b'model')
    (lvface_dir / 'inference.py').write_text('# fake', encoding='utf-8')
    python_exe = lvface_dir / 'python.exe'
    python_exe.write_bytes(b'python')
    return lvface_dir, python_exe


def test_legacy_inference_never_generates_dummy_embedding(
    tmp_path, monkeypatch
):
    from app.lvface_subprocess import LVFaceSubprocessProvider

    lvface_dir, python_exe = _fake_lvface_install(tmp_path)
    observed = {}

    def fake_run(args, **_kwargs):
        observed['command'] = args[2]
        return SimpleNamespace(
            returncode=1,
            stdout='',
            stderr='real inference failed',
        )

    monkeypatch.setattr(subprocess, 'run', fake_run)
    provider = LVFaceSubprocessProvider(
        str(lvface_dir), 'model.onnx', 128, python_exe=str(python_exe)
    )

    with pytest.raises(RuntimeError, match='LVFace inference failed'):
        provider.embed_face(Image.new('RGB', (112, 112)))

    assert 'np.random.randn' not in observed['command']
    assert 'Used dummy embedding' not in observed['command']


@pytest.mark.parametrize(
    ('stdout', 'message'),
    [
        ('not-json', 'invalid JSON'),
        ('[0.0, 1.0]', 'invalid embedding shape'),
        ('[' + ','.join(['0.0'] * 128) + ']', 'non-normalized embedding'),
    ],
)
def test_subprocess_output_is_validated(
    tmp_path, monkeypatch, stdout, message
):
    from app.lvface_subprocess import LVFaceSubprocessProvider

    lvface_dir, python_exe = _fake_lvface_install(tmp_path)
    monkeypatch.setattr(
        subprocess,
        'run',
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=stdout, stderr=''
        ),
    )
    provider = LVFaceSubprocessProvider(
        str(lvface_dir), 'model.onnx', 128, python_exe=str(python_exe)
    )

    with pytest.raises(RuntimeError, match=message):
        provider.embed_face(Image.new('RGB', (112, 112)))

@pytest.mark.skipif(not os.getenv('LVFACE_EXTERNAL_DIR'), 
                   reason='Set LVFACE_EXTERNAL_DIR to test subprocess provider')
def test_lvface_subprocess_provider():
    """Test LVFace subprocess provider with external installation."""
    from app.lvface_subprocess import LVFaceSubprocessProvider
    
    lvface_dir = os.getenv('LVFACE_EXTERNAL_DIR')
    model_name = os.getenv('LVFACE_MODEL_NAME', 'lvface.onnx')
    target_dim = int(os.getenv('FACE_EMBED_DIM', '128'))
    
    provider = LVFaceSubprocessProvider(lvface_dir, model_name, target_dim)
    
    # Create a test image
    image = Image.new('RGB', (112, 112), (128, 128, 128))
    
    # Get embedding
    embedding = provider.embed_face(image)
    
    # Verify properties
    assert embedding.shape == (target_dim,)
    assert embedding.dtype == np.float32
    
    # Check normalization (should be close to 1.0)
    norm = np.linalg.norm(embedding)
    assert 0.9 <= norm <= 1.1
    
    # Test with different image should give different embedding
    image2 = Image.new('RGB', (112, 112), (200, 50, 100))
    embedding2 = provider.embed_face(image2)
    
    # Should be different embeddings
    cosine_sim = np.dot(embedding, embedding2)
    assert cosine_sim < 0.99  # Not identical

def test_lvface_integration_via_config():
    """Test that face embedding service can use subprocess provider."""
    if not os.getenv('LVFACE_EXTERNAL_DIR'):
        pytest.skip('Set LVFACE_EXTERNAL_DIR to test integration')
    
    # Set environment for lvface with external dir
    os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
    os.environ['LVFACE_EXTERNAL_DIR'] = os.getenv('LVFACE_EXTERNAL_DIR', '')
    os.environ['LVFACE_MODEL_NAME'] = os.getenv('LVFACE_MODEL_NAME', 'lvface.onnx')
    os.environ['FORCE_REAL_FACE_PROVIDER'] = '1'  # Override test mode stub fallback
    
    # Clear cache to pick up new settings
    from app.face_embedding_service import get_face_embedding_provider
    from app.config import get_settings
    get_face_embedding_provider.cache_clear()
    get_settings.cache_clear()
    
    provider = get_face_embedding_provider()
    
    # Test that it's using the subprocess provider
    from app.lvface_subprocess import LVFaceSubprocessProvider
    assert isinstance(provider, LVFaceSubprocessProvider)
    
    # Test embedding generation
    image = Image.new('RGB', (112, 112), (100, 150, 200))
    embedding = provider.embed_face(image)
    
    target_dim = int(os.getenv('FACE_EMBED_DIM', '128'))
    assert embedding.shape == (target_dim,)
    assert 0.9 <= np.linalg.norm(embedding) <= 1.1
