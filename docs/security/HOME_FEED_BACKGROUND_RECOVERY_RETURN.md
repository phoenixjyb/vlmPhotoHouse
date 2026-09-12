# Existing home feeds recovered without Terminal

2026-09-12. The authorized recovery restored the existing v1 and v2 feeds on
Windows without changing their source, publications, TLS identity or audience.
Preparation remains stopped at its memory-pressure checkpoint: five ready,
one interrupted entry, 27,836 pending. No bulk process or preparation resume ran.

Worktree: `_worktrees/home-feed-background-recovery`; branch
`codex/home-feed-background-recovery`, based on `3674c555df6e5cab50be8640821126c6bcab54f0`.
Launcher commits: `2908f1fa6c672d9a3e6d02f2174c1ad5aec867eb` and reviewed correction
`0314ee92b2bb6e87122a424f8f7e6ff61a9d7930`. The deployed Python launcher SHA-256 is
`4c1cd3aafadbfc1dfafb515b342c5adea1e5338c34a6bacf1e8044e85f72bcc6`.
There was no push or merge.

## Change and rollback

Only the Actions of existing manual tasks `PhotoHouse-HomeFeed-Synthetic` and
`PhotoHouse-HomeCatalog-V2-Canary` changed: each now executes its existing venv's
`pythonw.exe`, with `-I -B`, through
[home_feed_background.py](../../scripts/home_feed_background.py).
The launcher imports each task's existing release and retains its configuration
validation, factory and serving options. The only server option override is
`log_config=None`, to retain the bounded diagnostics configuration. Access logging
remains disabled; proxy headers, TLS, bind address, concurrency, workers and all
other serving options remain unchanged.

Task XML comparisons confirmed that principals, interactive logon type, settings
and zero triggers were preserved. No automatic retry, startup trigger, Windows
service or global Terminal setting was added. These are still manual interactive
tasks; reboot/sign-out recovery was not established.

Diagnostics use one `server.log` per feed, a 1 MiB rotation threshold and three
backups. Formatted records are capped at 2,048 characters; stdout/stderr have no
unbounded line buffer. Log I/O failures are dropped and counted in process without
writing recursively to redirected stderr or creating another fallback log. Old
unbounded log files and old launch wrappers were preserved, not truncated.

Private task XML backups, process receipts and new logs are beneath
`%LOCALAPPDATA%\PhotoHouseAccess\home-feed-background-20260912` on Windows.
[rollback_home_feed_background.ps1](../../scripts/rollback_home_feed_background.ps1)
accepts that directory as `-Stage`. It checks task ownership, stops only these two
tasks, refuses to restore actions while their recorded processes remain present,
and restores the saved actions. It **leaves the feeds stopped**; automatically
starting the old console launchers would reintroduce Terminal dependence.
The rollback's command doubles were tested; live rollback was not rehearsed.

## Observed runtime

At 18:13:33 +08, both tasks were running with these unchanged private binds:

| Feed | Listener | Pythonw PID | Redirector PID | Publication |
| --- | --- | --- | --- | --- |
| v1 | `192.168.0.108:8444` | 16020 | 12044 | Existing synthetic revision 4 |
| v2 | `192.168.0.108:8445` | 20448 | 22808 | Existing real-media revision 1 |

Port 8443 remained absent. Both native process receipts reported
`GetConsoleWindow() == 0`. At 18:16, ancestry was
`pythonw -> pythonw -> svchost -> services -> wininit`, with no Terminal or console
ancestor; no WindowsTerminal/OpenConsole process was observed. The launcher receipt
state `starting` is a start receipt, not a health signal: separate listener, TLS
and request observations establish the service evidence.

At that snapshot, v1 used 50,032,640 bytes of working set, v2 68,288,512 bytes
(observed peak 112,783,360), and available RAM was 53,201,660 KiB, about 50.74 GiB.
This short observation does not establish long-term stability or the cause of
the earlier Terminal memory growth.

Both active logs were verified through shared file handles: **411 bytes each**,
containing the launcher's startup marker and Uvicorn startup messages. Initial
FileInfo observations showed stale zero sizes while writer handles were open;
shared-handle reads and subsequent FileInfo observations confirmed actual content.

## Validation and preservation

- Seven focused launcher tests passed on Mac and Windows (Windows: 0.180 seconds),
  including successful None-stream logging, rotation bounds, console refusal,
  option preservation and a simulated rotation permission failure without recursion.
- Direct bounded ASGI probes used synthetic JPEG/MP4 fixtures with each actual
  serving release and its own native venv: feed/catalog 200, photo HEAD 200,
  exact photo bytes, closed routes and spoofed peers 403; v2 video Range 206 with
  exact bytes and Content-Range. No application listener was started by these probes.
- Live native trusted hostname TLS 1.3 checks passed on both restored listeners.
  Nine requests from the non-allowlisted server peer returned 403, including
  feed/catalog, photo HEAD, spoofed peer, closed route and video Range cases.
  No certificate verification bypass was used.
- The Android coordinator independently reported normal native curl TLS trust
  (`ssl_verify_result=0`) and expected 403 on both feeds, preserved API/caption
  identities, no Terminal/FFmpeg, and an independent diagnostic write-failure check.
- Source trees, all existing publication files, configs, certificates/key hashes,
  preparation job/checkpoint and firewall snapshot matched before/after. API PID
  23284 and caption PID 10460 retained their September 11 start identities.

The first synthetic probe could not import TestClient because the v1 environment
lacked `httpx2`. The direct ASGI harness then passed without installing or replacing
runtime dependencies. It bounds requests to 10 seconds, 128 response messages and
512 KiB response bytes. No model, original-media or metadata-database mutation ran.

The Mac was off the home LAN. Approved peers remain exactly `192.168.0.102/32`
and `192.168.0.109/32`; actual successful access from those devices and physical
TV acceptance are still pending. A synthetic allowed-peer response and a live
denied-peer TLS response are separate evidence, not a live TV playback claim.

[Verification receipt](evidence/home-feed-background-recovery/verification.json)
contains aggregate hashes, process observations and probe outcomes.
