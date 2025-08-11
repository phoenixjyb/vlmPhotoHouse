# Storage Strategy

## Principles
- Originals immutable; never overwritten
- Derived artifacts reproducible; can be regenerated
- Separation of concerns: originals vs derived vs indices

## Layout (Proposal)
```
root/
  originals/... (symlinks or hardlinks from sources or copied)
  derived/
    thumbnails/{size}/{asset_id_prefix}/{asset_id}.jpg
    embeddings/{model}/{asset_id}.npy
    captions/{asset_id}.json
    faces/{asset_id}/{face_idx}.json
  indices/
    vector/faiss.index
    vector/meta.json
  db/
    metadata.sqlite
```

## NAS Integration
- Option 1: Move all originals into managed tree
- Option 2: Keep originals in place; store path references + validity checks

## Space Management
- Periodic audit: list orphan derived artifacts
- Configurable thumbnail sizes
- Compression: JPEG quality tuning; optional WebP

## Backup
- Originals: user-managed (RAID + offsite)
- Metadata & indices: periodic snapshot tarball

## Integrity
- Store SHA256 for each original; verify on access (optional)
