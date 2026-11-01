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
