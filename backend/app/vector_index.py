import numpy as np
from typing import List, Tuple, Dict, Optional, Any
from pathlib import Path
import threading
import logging

logger = logging.getLogger("vector_index")

class InMemoryVectorIndex:
    def __init__(self, dim: int):
        self.dim = dim
        self._lock = threading.Lock()
        self._vectors: Dict[int, np.ndarray] = {}
    def add(self, ids: List[int], vectors: np.ndarray):
        assert vectors.shape[0] == len(ids)
        with self._lock:
            for i, vid in enumerate(ids):
                self._vectors[vid] = vectors[i]
    def search(self, query: np.ndarray, k: int = 10) -> List[Tuple[int,float]]:
        # brute force cosine similarity
        if query.ndim == 1:
            q = query / (np.linalg.norm(query)+1e-9)
        else:
            q = query[0] / (np.linalg.norm(query[0])+1e-9)
        sims = []
        with self._lock:
            for vid, vec in self._vectors.items():
                v = vec / (np.linalg.norm(vec)+1e-9)
                sims.append((vid, float(np.dot(q, v))))
        sims.sort(key=lambda x: x[1], reverse=True)
        return sims[:k]
    def __len__(self):
        return len(self._vectors)
    def clear(self):
        with self._lock:
            self._vectors.clear()

class FaissVectorIndex:
    """FAISS flat index wrapper with ID mapping (simple, rebuild required for deletions)."""
    def __init__(self, dim: int, path: str | None = None):
        import faiss  # type: ignore
        self.dim = dim
        self.path = path
        self._index = faiss.IndexFlatIP(dim)
        self._ids: list[int] = []  # position -> asset id
        self._id_to_pos: dict[int,int] = {}
        self._lock = threading.Lock()
        if path and Path(path).exists():
            try:
                self.load(path)
            except Exception:
                logger.warning("Failed loading existing FAISS index; starting fresh", exc_info=True)
    def add(self, ids: List[int], vectors: np.ndarray):
        import faiss  # type: ignore
        # ensure normalized for IP similarity
        vecs = vectors.astype('float32')
        norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
        vecs = vecs / norms
        with self._lock:
            idx = self._index
            idx.add(vecs)  # type: ignore[attr-defined]
            base = len(self._ids)
            for i, vid in enumerate(ids):
                self._ids.append(vid)
                self._id_to_pos[vid] = base + i
    def search(self, query: np.ndarray, k: int = 10) -> List[Tuple[int,float]]:
        import faiss  # type: ignore
        if query.ndim == 1:
            q = query.reshape(1,-1)
        else:
            q = query
        q = q.astype('float32')
        q = q / (np.linalg.norm(q, axis=1, keepdims=True)+1e-9)
        with self._lock:
            idx = self._index
            D, I = idx.search(q, k)  # type: ignore[attr-defined]
        results: List[Tuple[int,float]] = []
        for dist, idx in zip(D[0], I[0]):
            if idx < 0 or idx >= len(self._ids):
                continue
            results.append((self._ids[idx], float(dist)))
        return results
    def __len__(self):
        return len(self._ids)
    def clear(self):
        import faiss  # type: ignore
        with self._lock:
            self._index.reset()
            self._ids.clear()
            self._id_to_pos.clear()
    def save(self, path: str | None = None):
        import faiss, json  # type: ignore
        p = path or self.path
        if not p:
            return
        meta = {'ids': self._ids, 'dim': self.dim}
        with self._lock:
            faiss.write_index(self._index, p + '.faiss')
            with open(p + '.meta.json','w') as f:
                json.dump(meta, f)
    def load(self, path: str):
        import faiss, json  # type: ignore
        with open(path + '.meta.json') as f:
            meta = json.load(f)
        self._ids = meta['ids']
        self.dim = meta['dim']
        self._id_to_pos = {vid:i for i,vid in enumerate(self._ids)}
        self._index = faiss.read_index(path + '.faiss')

def load_index_from_embeddings(session_factory, index: InMemoryVectorIndex, limit: int | None = None):
    """Populate index from embeddings table (image modality)."""
    from .db import Embedding  # local import to avoid circular
    import numpy as np
    count = 0
    with session_factory() as session:
        q = session.query(Embedding).filter(Embedding.modality=='image')
        if limit:
            q = q.limit(limit)
        rows = q.all()
        ids = []
        vecs = []
        for r in rows:
            try:
                arr = np.load(r.storage_path).astype('float32')
                ids.append(r.asset_id)
                vecs.append(arr)
            except Exception:
                continue
        if ids:
            index.add(ids, np.stack(vecs))
            count = len(ids)
    return count
def load_faiss_index_from_embeddings(session_factory, index: FaissVectorIndex, limit: int | None = None):
    from .db import Embedding
    count = 0
    with session_factory() as session:
        q = session.query(Embedding).filter(Embedding.modality=='image')
        if limit:
            q = q.limit(limit)
        rows = q.all()
        ids=[]; vecs=[]
        for r in rows:
            try:
                arr = np.load(r.storage_path).astype('float32')
                ids.append(r.asset_id)
                vecs.append(arr)
            except Exception:
                continue
        if ids:
            index.add(ids, np.stack(vecs))
            count = len(ids)
    return count

class EmbeddingService:
    """Pluggable embedding service supporting stub, sentence-transformers (text), and CLIP (image & text).

    Model name conventions:
    - stub-* : deterministic pseudo embeddings (fast, for tests)
    - clip-* : try to load OpenAI CLIP via "open_clip" or "clip" libraries, fallback to stub
    - any other string for text: attempt sentence-transformers
    """
    def __init__(self, image_model: str, text_model: str, dim: int, device: str = 'cpu'):
        self.image_model = image_model
        self.text_model = text_model
        self.dim = dim
        self.device = device
        self._text_model_impl: Optional[Any] = None
        self._clip_model: Optional[Any] = None
        self._clip_preprocess: Optional[Any] = None
        # Load text model if real
        if not text_model.startswith("stub") and not text_model.startswith("clip"):
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self._text_model_impl = SentenceTransformer(text_model, device=self.device)
                try:
                    self.dim = self._text_model_impl.get_sentence_embedding_dimension()  # type: ignore
                except Exception:
                    pass
                logger.info(f"Loaded sentence-transformers model '{text_model}' for text embeddings (dim={self.dim})")
            except Exception as e:
                logger.warning(f"Falling back to stub text embeddings for model '{text_model}': {e}")
        # Load CLIP if requested for either modality
        if image_model.startswith('clip') or text_model.startswith('clip'):
            # try open_clip first
            loaded = False
            try:
                import open_clip  # type: ignore
                model_name = 'ViT-B-32'
                pretrained = 'openai'
                if '-' in image_model:
                    # allow clip-ViT-L-14 for example
                    parts = image_model.split('-',1)[1]
                    if parts:
                        model_name = parts
                self._clip_model, _, self._clip_preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained, device=self.device)
                self._clip_tokenizer = open_clip.get_tokenizer(model_name)
                # set dimension from model (text projection dimension)
                try:
                    self.dim = int(self._clip_model.text_projection.shape[1])  # type: ignore
                except Exception:
                    pass
                loaded = True
                logger.info(f"Loaded open_clip model {model_name} (dim={self.dim}) on {self.device}")
            except Exception as e:
                logger.warning(f"open_clip load failed ({e}); trying fallback clip lib")
            if not loaded:
                try:
                    import clip  # type: ignore
                    model_name = 'ViT-B/32'
                    m, preprocess = clip.load(model_name, device=self.device)
                    self._clip_model = m
                    self._clip_preprocess = preprocess
                    # attempt to infer dim
                    try:
                        self.dim = int(self._clip_model.text_projection.shape[1])  # type: ignore
                    except Exception:
                        pass
                    loaded = True
                    logger.info(f"Loaded clip model {model_name} (dim={self.dim}) on {self.device}")
                except Exception as e:
                    logger.warning(f"Falling back to stub embeddings: clip load failed ({e})")

    # ---- Internal deterministic stubs ----
    def _stub_from_key(self, key: str, dim: Optional[int] = None) -> np.ndarray:
        d = dim or self.dim
        rng = np.random.default_rng(abs(hash(key)) % (2**32))
        return rng.random(d).astype('float32')

    # ---- Public API ----
    def embed_image(self, path: str) -> np.ndarray:
        # CLIP path if model loaded
        if self._clip_model is not None and self._clip_preprocess is not None:
            try:
                from PIL import Image  # local import
                image = Image.open(path).convert('RGB')
                image_in = self._clip_preprocess(image).unsqueeze(0)
                import torch  # type: ignore
                with torch.no_grad():
                    feats = self._clip_model.encode_image(image_in.to(self.device))  # type: ignore
                    feats = feats / feats.norm(dim=-1, keepdim=True)
                return feats.cpu().numpy()[0].astype('float32')
            except Exception as e:
                logger.warning(f"clip image embed failed, falling back to stub: {e}")
        if self.image_model.startswith('stub'):
            return self._stub_from_key(path)
        # fallback stub for any other unhandled model names
        return self._stub_from_key(path)

    def embed_text(self, text: str) -> np.ndarray:
        if self._clip_model is not None:
            try:
                import torch  # type: ignore
                if hasattr(self, '_clip_tokenizer'):
                    tokens = self._clip_tokenizer([text])  # type: ignore
                    with torch.no_grad():
                        feats = self._clip_model.encode_text(tokens.to(self.device))  # type: ignore
                        feats = feats / feats.norm(dim=-1, keepdim=True)
                    return feats.cpu().numpy()[0].astype('float32')
            except Exception as e:
                logger.warning(f"clip text embed failed, falling back: {e}")
        if self._text_model_impl is not None:
            try:
                vec = self._text_model_impl.encode(text)  # type: ignore
                return np.array(vec, dtype='float32')
            except Exception as e:
                logger.warning(f"SentenceTransformer encode failed, falling back to stub: {e}")
        return self._stub_from_key(text)

    # Backward compatibility methods used elsewhere
    def embed_image_stub(self, path: str) -> np.ndarray:  # deprecated
        return self.embed_image(path)
    def embed_text_stub(self, text: str) -> np.ndarray:  # deprecated
        return self.embed_text(text)
