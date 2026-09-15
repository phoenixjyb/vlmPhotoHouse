# Historical P1 branch reconciliation — 14 September 2026

The owner requested integration of all outstanding PhotoHouse source. The final
remote-branch audit found `feature/p1-single-machine`, containing two commits from
August 2025 that were never joined to the default branch history:

- `b6775d56bfcc07b4702640ad99b42a3e6a9fe5e0`: early README and P1 Docker examples.
- `2b51896b4b927d8911315bd0b55a66a1a8180147`: ignore local Compose data volumes.

Reconciliation starts at `d25290f1b074ceb93acaf29f377c5d2e8e716097` and records
both original commits as merge ancestors. It retains the current README and the
current empty `deploy/compose.p1.yml` / `deploy/.env.p1.sample` byte-for-byte.
Those current files supersede the historical quickstart; the old profile installed
unpinned dependencies at startup and advertised a legacy launch configuration.
This history merge does not restore it as a supported deployment path.

The useful `deploy/data/` ignore rules are retained to keep local original/derived
media volumes out of Git. The only changes relative to the current default branch
are these ignore rules and this record. Application, tests, lockfiles, launchers,
configuration and Android producer-pinned files remain byte-identical.

Validation: exact retained-file byte comparisons, allowed-path diff check,
`git check-ignore` for representative original/derived paths, whitespace check and
outgoing-history secret scan. No application rebuild or runtime test is needed for
this documentation/ignore-only resolution. No deployment, restart or data changes.
