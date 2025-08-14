import os, pytest

pytestmark = pytest.mark.skip(reason="LVFace integration test requires model + onnxruntime; enable manually by removing skip")

def test_lvface_provider_import_only():
    os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
    os.environ['FORCE_REAL_FACE_PROVIDER'] = '1'
    from app.face_embedding_service import get_face_embedding_provider
    try:
        get_face_embedding_provider.cache_clear()  # type: ignore
    except Exception:
        pass
    prov = get_face_embedding_provider()
    # We cannot run inference without a real model file; just assert provider class name
    assert 'LVFace' in prov.__class__.__name__
