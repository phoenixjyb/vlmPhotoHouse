# Home TV selected LAN feed — v1

The user selected **no approval: share selected photos with any device reaching
the LAN feed**. No personal login, pairing, device grant, account password, bearer
or renewal credential is required. This is deliberate sharing of selected content;
a LAN address is not a person's identity. There is no per-device revocation.

This slice implements a separate app factory, `app.home_feed.create_home_feed`, and
an explicit launcher, `scripts/home_feed_app.py`. It does not alter or mount routes
in the protected `app.main` phone/web API. No TV service was deployed or real content
selected by this slice. The existing synthetic Windows protected service remains a
separate previously deployed artifact; it cannot serve this new contract.

## Contract and content selection

The machine-readable contract is [home-feed-contract-v1.json](home-feed-contract-v1.json).
It has its own version and source pin; never substitute this for the frozen phone
API pin. There is no SQLite schema change. The owner publishes a private manifest
with an explicit ordered set of at most 2,000 asset IDs and prepared previews.
There is no whole-library discovery, database connection, directory enumeration,
original path, invitation/account route, face crop, search, album or job endpoint.

| Method and path | Meaning |
| --- | --- |
| `GET /home/v1/feed?page=1&page_size=50` | Bounded page of the selected feed; inline literal caption and preview metadata/relative URLs |
| `GET /home/v1/assets/{asset_id}/preview?variant=grid&revision=1` | Exact selected cached JPEG; `variant=display` selects the display derivative |
| `HEAD` on that preview path | Same policy and integrity checks, same content length, no body |

The feed result includes version, revision, feed ID/title, page/page_size, total,
has_more and items. Each item has ID, caption, `originals_allowed=false`, and grid/
display preview metadata. Each preview has width, height, bytes, SHA-256 and a
relative URL bound to the manifest revision. There are no arbitrary URLs or paths.
No original-mode control belongs in this adapter. Query keys/duplicates are strict.

The on-disk manifest has exactly version, enabled, revision, feed_id, title and
assets; each asset has exactly id, caption and previews. Preview entries have exactly
width, height, bytes and sha256. The [synthetic manifest](home-feed-manifest.example.json)
is parseable and binds the retained test JPEGs; it is not a real content selection.
Manifest maximum is 2 MiB; caption maximum 1,024 UTF-8 bytes; title maximum 256.
Pages are 1–2,000 and page sizes 1–100; JSON responses are limited to 512 KiB.

The manifest is outside the prepared media root. The only file paths are
`<media_root>/grid/<id>.jpg` and `<media_root>/display/<id>.jpg`. Every request reads
current manifest state. Files must be direct regular files with stable identities;
symlink aliases, mismatched dimensions, changed bytes/hash, excessive size and
attached JPEG metadata fail closed. No missing-file fallback, decoding, generation,
model import, original open or media write occurs in the server.

## Quality and derivative preparation

- Grid: at most 512 pixels per edge, 262,144 pixels and 2 MiB compressed.
- Display: at most 4,096 pixels per edge, 8,847,360 pixels and 12 MiB compressed.
  An existing 3840x2160 frame fits without reduction; portrait images fit within the
  same edge/pixel constraints. Actual projector rendering resolution remains unverified.
- Format: normalized baseline, 8-bit RGB/grayscale JPEG, JFIF APP0 only; no EXIF,
  ICC, comments, attached thumbnail or trailing payload. The server checks framing,
  dimensions and exact bytes/hash without decoding. The TV must still validate and
  bound its real decode, as it already does for untrusted images.
- Offline preparation must apply orientation, convert colors to sRGB, strip all
  source metadata, preserve aspect ratio, avoid upscaling and resize to both limits.
  Start with high-quality JPEG encoding (proposed quality 92, no chroma subsampling)
  and lower quality/size if the compressed budget is exceeded. These encoding choices
  are a proposed real-media preparation plan, not a deployed processing pipeline.
- Stage JPEGs in new directories, validate a full decode/dimensions and hashes offline,
  then publish the complete manifest atomically. Increment revision on every selection
  or derivative change. Do not replace files for a live revision in place. A missing
  or changed derivative is unavailable until corrected; it never exposes an original.

The retained synthetic 3840x2160 color-bar JPEG was generated and decoded locally
with Pillow 12.1.1 (test-fixture preparation only). Its 523,448 bytes have SHA-256
`c610ec0406005683fc6acf9ee48b5fd1bcb37e2bb23667c46e1fd01dc9979434`.
Pillow was not added to the CPU server lock. This proves the supplied synthetic
4K file, not real-library image quality, source orientation/color handling or JMGO output.

## Startup, reconnect and disable semantics for Android

1. The configured TV origin is a private build/operator input. Cold start calls
   the feed directly, without account, invitation, cookie or Authorization header.
   Maintain a separate TV home-feed adapter/state; do not fabricate a personal session.
2. Fetch the first page, show the selected feed, and use only its revision-bound
   preview URLs. Page changes use the same endpoint and update the displayed revision.
   On 409 `feed_changed`, clear stale page/media and fetch fresh feed metadata.
3. On background, disconnect, network loss or denial, stop the slideshow and cover/
   clear content according to the existing privacy lifecycle. Foreground fetches the
   feed again before exposing previous content. Discard responses from earlier
   connection generations. Do not persist media or a synthetic account session.
4. A 404 `preview_unavailable` is a placeholder for that exact preview. This contract
   does not promise thumbnail fallback. A 400 indicates invalid request/contract;
   stop that request. A 403 `feed_disabled` or `access_denied` clears content; there
   is no login screen to show. A 503 `feed_unavailable` covers content and allows retry.
5. Recommended reconnect policy: explicit retry immediately; unattended retries
   after 2, 5, 15, 30 then 60 seconds, bounded at 60 seconds with jitter. Honor 429
   `busy` with `Retry-After: 2` and never retry earlier. Recheck feed metadata at least
   every 60 seconds while visible. Stop background requests and concurrent decode.
   This client policy is a handoff requirement, not code in the backend.
6. Owner disables sharing by publishing `enabled=false`, or removes selected IDs
   and increments revision. The next admitted request reflects that change. Requests
   already admitted may finish; this is not push revocation and cannot erase images
   already downloaded by an unauthenticated reader. Re-enable resumes direct browsing.

## LAN and deployment boundary

Configuration requires canonical DNS HTTPS origin, one explicit RFC1918 IPv4 bind
address/port, and one to eight explicit RFC1918 peer CIDRs, each /24 or narrower.
There is no wildcard, loopback or IPv6 exception. Peer checks use the actual ASGI
client address, never forwarded headers. Direct Host/HTTPS, cross-site and handler
checks apply before storage. Original/account cookies and Authorization headers are
rejected to prevent accidental reuse of the personal API adapter. All responses use
no-store and same-origin CORP; no CORS, redirects, WebSockets, docs or openapi routes.
Four file/manifest operations may run concurrently; additional requests receive 429.

This cannot distinguish a remote client hidden behind a trusted LAN reverse proxy
or SNAT device. Deployment must have its own listener/firewall policy, no public
NAT/port forwarding, no DMZ/UPnP mapping or proxy into this feed, and no route through
the public protected origin. Verify from allowed LAN, disallowed LAN/guest and an
outside route. Application source-peer tests do not prove the router/firewall state.
Do not widen the existing protected listener to serve these anonymous routes.

Launch syntax is explicit:

```sh
"$PHOTOHOUSE_PYTHON" scripts/home_feed_app.py --config "$HOME_FEED_CONFIG" --check-config
```

The config fields are version=1, manifest, media_root, origin, allowed_networks,
bind_host, port, tls_certificate and tls_private_key. Paths are explicit native
absolute local paths. Config/manifest/certificate/key must be distinct and outside
prepared media. Syntax validation opens only that config file. `--serve` is the
separate action which constructs the app and starts direct TLS. One Uvicorn worker,
no reload, proxy trust, access log, model processes or ambient database config.

A reviewed source-only package and synthetic host deployment are the next operational
slice; the existing protected-package allowlist intentionally does not bundle this
new service yet. Select a private origin/address, actual allowed subnet(s), task,
operator and synthetic publish directory first. Verify file/key ACLs, normal TLS,
source hashes, start/stop, disable/re-enable and network isolation before real content.
The later real-library exporter requires an explicit audience/asset selection and
approval to read real media; no such permission is inferred from this implementation.
