# Secured WebUI prepared playback

The protected WebUI opens a video only after a same-origin, no-store `HEAD`
readiness check. It requires a successful `200 video/mp4` response with
`Cache-Control: no-store`, `Accept-Ranges: bytes`, no `Content-Range`, identity
encoding, a strong SHA-256 ETag and a bounded Content-Length. The browser's
native video element then requests the same protected URL for metadata and byte
ranges. WebUI JavaScript cannot attach an `If-Range` header to each native seek
request; the validated HEAD ETag is not automatically pinned across separate
native seek requests. Per-request and per-chunk source checks remain server
responsibilities, but they do not promise one representation across a service
or index replacement.

The browser journey uses only synthetic SQLite/media fixtures. It proves the
HEAD gate, native decode/play/seek within the tiny synthetic fixture when the
local prepared fixture is enabled, visible 403/404/409/429/503 handling,
malformed-success rejection, offline/retry behavior, no original fallback, and
cancellation cleanup. It does not prove long-duration range seeking, runtime
preparation, codec qualification, physical device playback, or family acceptance.
