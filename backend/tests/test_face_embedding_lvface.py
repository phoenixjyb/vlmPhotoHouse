import os, numpy as np
import pytest
from PIL import Image

@pytest.mark.skipif(not os.path.exists(os.getenv('LVFACE_MODEL_PATH','models/lvface.onnx')),
    reason='LVFace ONNX model not present')
@pytest.mark.skipif(os.getenv('FACE_EMBED_PROVIDER','')!='lvface', reason='Set FACE_EMBED_PROVIDER=lvface to run')
@pytest.mark.parametrize('dim', [128, 256])
def test_lvface_embedding_dims(dim):
    os.environ['FACE_EMBED_DIM'] = str(dim)
    # Clear provider cache
    from app.face_embedding_service import get_face_embedding_provider
    get_face_embedding_provider.cache_clear()  # type: ignore
    # Also clear settings cache so updated FACE_EMBED_DIM is picked up
    from app.config import get_settings
    try:
        get_settings.cache_clear()  # type: ignore
    except Exception:
        pass
    prov = get_face_embedding_provider()
    im = Image.new('RGB',(112,112),(123,50,200))
    vec = prov.embed_face(im)
    assert vec.shape[0] == dim
    n = np.linalg.norm(vec)
    assert 0.9 < n < 1.1
