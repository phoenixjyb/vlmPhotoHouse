from pathlib import Path
from glob import glob
import sys, os
import numpy as np

# Ensure 'app' package is importable regardless of current working directory
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import get_settings
from app import tasks as tasks_mod

def main():
    settings = get_settings()
    # Ensure index singletons
    if getattr(tasks_mod, 'VIDEO_INDEX_SINGLETON', None) is None:
        tasks_mod.VIDEO_INDEX_SINGLETON = tasks_mod.InMemoryVectorIndex(tasks_mod.EMBED_DIM)
    if getattr(tasks_mod, 'VIDEO_SEG_INDEX_SINGLETON', None) is None:
        tasks_mod.VIDEO_SEG_INDEX_SINGLETON = tasks_mod.InMemoryVectorIndex(tasks_mod.EMBED_DIM)
    tasks_mod.VIDEO_INDEX_SINGLETON.clear()
    tasks_mod.VIDEO_SEG_INDEX_SINGLETON.clear()
    base = Path(settings.derived_path) / 'video_embeddings'
    # Video-level
    vid_ids, vid_vecs = [], []
    for fp in glob(str(base / '*.npy')):
        p = Path(fp)
        if p.stem.startswith('seg_'):
            continue
        try:
            vid_ids.append(int(p.stem))
            vid_vecs.append(np.load(fp).astype('float32'))
        except Exception:
            continue
    if vid_ids:
        tasks_mod.VIDEO_INDEX_SINGLETON.add(vid_ids, np.stack(vid_vecs))
    # Segment-level
    seg_ids, seg_vecs = [], []
    for fp in glob(str(base / 'seg_*.npy')):
        p = Path(fp)
        try:
            seg_ids.append(int(p.stem.split('_',1)[1]))
            seg_vecs.append(np.load(fp).astype('float32'))
        except Exception:
            continue
    if seg_ids:
        tasks_mod.VIDEO_SEG_INDEX_SINGLETON.add(seg_ids, np.stack(seg_vecs))
    print(f"video_index loaded={len(vid_ids)}; segment_index loaded={len(seg_ids)}")

if __name__ == '__main__':
    main()
