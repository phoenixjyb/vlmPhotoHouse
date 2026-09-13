# Shared PhotoHouse web icon

Base: `9ebcec3ef30ba887c3582420725b81aead80b9fb`, the family web UI branch.
Branch: `codex/web-shared-brand-icon`. The supplied 1254 × 1254 artwork is unchanged:
SHA-256 `c8fc559e39c5c4d0b9902cafca47e15ac4e6cfa2cbc18d81a40d956e8a8f8909`. The exact branding PNG is intentionally tracked despite the generic
PNG ignore rule; it is not a family media asset.

Header artwork at desktop/mobile widths, PNG favicon and browser home-screen icon
share `/ui/photohouse-icon.png`. The CSS cache key was updated. Preview and synthetic
browser harness use the same explicit file mapping.

Route delta: one GET `/ui/photohouse-icon.png`, serving only the fixed `ICON_FILE`
with image/png and existing no-store UI headers. No caller-controlled file path,
broad static mount or media access. An isolated in-process FastAPI router check passed:
200/MIME/SHA/no-store, caller path query cannot change bytes, unknown asset 404,
POST 405. No application runtime, model or database was loaded.

The existing synthetic Chromium browser suite passed, including viewer/navigation,
people picker/pagination, bilingual layouts and new logo decode/favicon checks.
Desktop1440 and mobile390 screenshots were visually inspected. No real media used.

This is the family UI source, not protected-app deployment. Importing into the
protected backend still requires its route inventory/policy to explicitly admit this
non-sensitive fixed branding asset. No security inventory, runtime, discovery candidate,
preparation job, captions, live website, push or merge changed. Local commit only.
