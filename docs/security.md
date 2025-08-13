# Security Considerations

- Host shares
  - Mount photos as read-mostly; restrict write access to administrative users/devices.
  - Prefer read-only mounts for services that don’t need to write.
- Network exposure
  - `proxy` exposes port 80 on localhost; avoid publishing to WAN without auth/TLS.
  - Consider adding a reverse proxy with TLS (Caddy/Traefik) and access controls for remote access.
- Secrets/Config
  - `.env` carries DB URLs and paths. Don’t commit real secrets to VCS.
  - Move to Postgres with managed secrets for production.
- Container users
  - Consider running the app as a non-root user in production images.
- Backups
  - Verify backup/restore procedures for photos and DB; test recovery periodically.
