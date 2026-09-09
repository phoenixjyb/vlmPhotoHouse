# Additive legacy read schema — slice 6

Local synthetic checkpoint, 2026-09-09; follows [the ORM rehearsal](ORM_REHEARSAL.md).

Revision `a5d2e8f4b610`, after `f4c1a8d2e703`, creates the four missing legacy
read tables and adds nullable asset duration/FPS and face-label fields. It adds
missing indexes without removing existing indexes, rebuilding assets, changing
records or creating access grants. Existing compatible startup-created tables are
preserved. Incompatible types, parent links, indexes or foreign-key violations
stop the transaction for explicit review. Downgrade requires offline restoration.

The ORM declarations now match the original asset path uniqueness/index,
`ix_assets_hash` name, and nullable legacy status. NULL status remains valid;
original IDs and paths are unchanged. The HTTP entry point still performs no
migration or implicit schema creation.

## Verification

Five additional tests exercise real SQLAlchemy/Alembic against temporary SQLite:

- Fresh full-chain upgrade has zero structural metadata differences; full ORM
  asset/tag/video reads succeed, including NULL asset status.
- Compatible pre-existing tables, records and extra indexes survive the upgrade.
- Captured SQL contains no destructive table/data replacement or security grants.
- Incompatible existing tables and same-name indexes fail with complete rollback.

All **111 security tests passed in 11.944 seconds** using the isolated `.venv`.
The existing access-schema comparison includes server defaults; the full legacy
comparison is structural only. Extra historical indexes are intentionally
preserved, so structural parity is claimed for the fresh migration chain, not
for every previously startup-created database. No live schema was inspected.

Changed files: `backend/app/db.py`, the new revision,
`tests/security/test_orm_migrations.py`,
`tests/security/test_legacy_read_migration.py`, and these checkpoint documents.

Next: scoped gallery, asset detail and caption reads, using current membership
and explicit asset-to-library mappings before counts, pagination or disclosure.
Albums, vector search, writes, operational controls and voice remain closed.
Windows migration/backup, TLS/proxy integration and real client acceptance remain
unverified. No live host, real database/media, model or mobile repository was used.
