# Security & Privacy

## Principles
- Local-first: no external transmission of image data
- User opt-in for any cloud augmentation
- Minimal PII exposure (faces, GPS) guarded

## Controls
- Config flag to strip GPS from exported metadata
- Optional encryption for metadata DB (future)
- Access token for API (simple bearer) initial

## Threat Considerations
- Local compromise: rely on OS permissions
- Data corruption: checksums + backups
- Model tampering: checksum verify on load

## Logging Policy
- Avoid storing raw paths in verbose logs (hash or relative)
- Redact person labels in error traces
