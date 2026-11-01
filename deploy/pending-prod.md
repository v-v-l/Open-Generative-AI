# Pending Production Deployment

Append-only ledger of deployment deltas. Applied items are checked after live
verification. Credentials and media are never included in this repository.

## Promoted — 2026-11-01

### nora-studio — Original frontend with private generation queue

Release: `nora-v1d-8b61e89` (frontend/proxy manifest source `8b61e89`).
The initial gateway backup retains the first activation ID shown below.
Date: 2026-11-01.

#### Env vars / secrets
- [x] `NORA_PROJECT_ROOT` (configuration) selects the external Nora runtime workspace.
- [x] Existing `OPENAI_API_KEY` / `OPENROUTER_API_KEY` remain on that execution host.
- [x] `MEDIA_STUDIO_PASSWORD_HASH` and `MEDIA_STUDIO_SESSION_SECRET` stay in a restricted local environment file. No values copied to apps or Git.

#### Config / infra
- [x] Version canonical backend, tests and deployment helpers in `nora/`; retain compatibility symlinks in the original workspace.
- [x] Enable authenticated backend and private reverse-tunnel user units; retire the original transient backend process.
- [x] Stage immutable static/proxy release on apps; verify checksums and mounted Caddy configuration before starting its container.
- [x] Add `media.bp-flow.com` to gateway Caddy atomically with validation and a backup, preserving other sites.
- [x] Verify public HTTPS, anonymous HTML/real-JS redirects to login, API/media 401, login, authenticated photo/video model selectors and paused/idle state.
- [x] Enforce private candidate access checks before activation, bound to the immutable release manifest and proxy checksum; reject wrong Host and wrong LAN peer.

#### Operational boundary
- The execution host must remain online. Apps serves static files and proxies to it; it does not have model weights or provider/worker credentials.
- No paid inference is used as a deployment test. Provider capabilities were read from catalogs, transport tested with mocks, and actual form payloads checked against an isolated fixture.
- Roll back by choosing a prior verified immutable release. Preserve queue data and provider accounting; never retry accepted jobs automatically as part of rollback.
- Gateway backup for this installation: `/etc/caddy/media-studio-backups/Caddyfile.before-nora-v1c-c51580d`.
- Command Center project identity has not been established for this fork; diagrams remain canonical in Git.

Live browser verification: 91 catalog models, no page errors, paused queue, no active job. No upload, enqueue or paid generation was used. Diagnostic evidence remains in the external runtime workspace, not the source fork.


## Promoted — 2026-11-01: apps backend and databases PostgreSQL

Release `nora-v2-9215134`, manifest source `9215134`. This supersedes the execution-
host dependency in the earlier ledger entry; the gateway route is unchanged.

- [x] Native enabled apps backend service on loopback 36442; user linger enabled.
- [x] Dedicated `pg_nora_media_prod` on databases LAN port 5466, persistent volume,
  non-superuser app role and apps-only network authentication rule.
- [x] Offline SQLite import: settings 1, assets 1, jobs 0; IDs preserved and copied
  asset SHA-256 matched the original through the authenticated public media route.
- [x] Provider/auth credentials transferred securely to apps runtime outside Git.
- [x] Portable H3 helper, locked Node dependencies, FFmpeg/FFprobe 8.0.1 and private
  worker SSH configuration on apps. Read-only provider check confirms GPU paused.
- [x] Independent H3 timer uses apps user systemd and explicit credential/module
  paths. Mocked timer/progress/storage failure tests confirm owned rental cleanup.
- [x] Separate authenticated Qwen executor workstation 36446 and private tunnel
  apps 36447. Disconnect/reconnect verified offline/ready without inference.
- [x] Old workstation backend/full-app tunnel stopped and disabled; source preview
  stopped. Cloud/API/history remained usable during Qwen tunnel disconnection.
- [x] Private proxy negative gate and public browser login/model selectors passed;
  91 models, 89 cloud credentials configured, queue paused, no active job/page errors.
- [x] Temporary PostgreSQL test container/tunnel removed. No paid inference used.

Validation: 53 backend tests (49 pass, four isolated PostgreSQL tests skipped in
that invocation); PostgreSQL integration cases separately passed on disposable
PostgreSQL 18, including singleton lock, FIFO, rollback and copied snapshot import.
Frontend checks, tests, build and browser availability checks passed. Real paid
cloud/H3/Qwen submission remains outside this deployment test.

Media runtime: `/home/victor/apps/media-studio/runtime`; backend `current` symlink
selects immutable source. Previous release and offline SQLite/media source retained.
Rollback must reconcile any subsequent PostgreSQL/provider writes before restoring
old SQLite; restarting the legacy topology blindly would discard newer history.
FFmpeg binaries came from `mwader/static-ffmpeg:8.0.1`, pinned image digest
`sha256:252705ff88532fa338e7065c21792756552f8fe7c212f84bc503d3c340689594`.
Evidence stays outside Git: `work/media-migration-{offline,ready}.json`,
`work/media-public-smoke.json`, and the matching private candidate receipt.
