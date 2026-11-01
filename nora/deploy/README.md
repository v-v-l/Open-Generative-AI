# Selected Open Generative AI frontend + private Nora backend

Canonical deployment sources live once in this fork at `nora/deploy`. The workspace path `deploy/media-studio/open-generative-ai` and old bridge launcher are compatibility symlinks. Set `NORA_PROJECT_ROOT` when using this fork against a different external runtime workspace.

This is the current deployment candidate for the selected `Anil-matcha/Open-Generative-AI` fork. Earlier `../open-higgsfield/` and standalone Directcut candidates are superseded and were never deployed.

## Concrete topology

```text
Browser HTTPS media.bp-flow.com
  → gateway Caddy (192.168.100.10; public TLS and noindex)
  → apps Caddy (192.168.100.70:36443; accepts gateway only)
      → static frontend /srv/open-generative-ai
      → authenticated API/media via apps 127.0.0.1:36442
          → private SSH reverse tunnel
          → laptop 127.0.0.1:36440 canonical Nora backend
              → local Qwen or existing SimplePod H3 worker/cloud adapters
```

The built frontend lives on apps. All model execution, references, queue data, provider credentials and worker credentials remain on the laptop. Apps stores only the frontend build and proxy configuration. There is no public ComfyUI endpoint and no GPU/model installation on apps.

**The laptop must be online and the tunnel connected.** If it sleeps or disconnects, authentication and API/media requests fail closed. This design does not provide an independent cloud execution worker while the laptop is offline.

## Files and verified paths

- Frontend build: `/home/victor/Projects/Nora/apps/open-generative-ai/nora/dist` (confirm successful build before activation).
- Canonical backend: `scripts/generation_studio/server.py`, same persistent queue `outputs/generation-studio`.
- Local public-auth environment: `work/generation-studio/public-auth.env`, mode 0600.
- Initial password: `work/media-studio-login.txt`, mode 0600. Never copy it to apps or print its contents in tool output.
- Tunnel launcher: `scripts/start-media-studio-bridge.sh`; apps reverse listener is loopback-only, port 36442.
- Apps private frontend listener: 192.168.100.70:36443; previously checked free.
- Gateway candidate: `Gateway.Caddyfile.fragment`; merge into the existing configuration after review rather than replacing other sites.

The backend authenticates every public-host request, including media. Apps verifies static access through `/api/auth/check`; anonymous static requests redirect to the backend login page. Session cookies are Secure, HttpOnly, SameSite=Strict, signed, revocable, and expire after 12 hours. Apps forwards the fixed public Host. The backend ignores forwarded host/protocol/client-IP headers.

**Production does not enable `--allow-loopback-local`.** An apps-local process could otherwise send a forged loopback Host through the SSH tunnel. Public production accepts only the configured public Host and requires authentication. Use the public HTTPS domain, or a separate read-only local preview with its own temp queue.

Canonical backend source is versioned once at `apps/open-generative-ai/nora/backend`; `scripts/generation_studio` is a compatibility symlink. Set `NORA_PROJECT_ROOT=/home/victor/Projects/Nora` so runtime settings, credentials, outputs and caches stay outside the fork. The service and local launcher set this explicitly. Canonical Python tests live in `nora/backend_tests`; old root test paths are compatibility symlinks.

## Preparation and review sequence

1. Build the selected fork's isolated `nora` frontend with root base URLs. The upstream MuAPI provider routes are not deployed.
2. Run `python3 tests/test_generation_studio.py` and `python3 tests/test_generation_studio_auth.py`. These use fake engines and never generate media.
3. Run `deploy/media-studio/open-generative-ai/prepare-release.sh` to make a local immutable bundle under `work/media-studio-deploy/releases/`. The bundle contains only static build/proxy files and a checksum manifest.
4. Review the bundle and Caddy candidates. `caddy adapt --config ... --adapter caddyfile` validates syntax without starting a listener.
5. Inspect canonical `/api/state`: `queue_paused` must be true, `active_job_id` null, and no running generation before any backend restart. Do not start another server against the same DB; the ownership lock rejects it.
6. After parent review, stage the chosen release with `stage-release.sh RELEASE_ID`. This uploads only; it does not start Docker or change the gateway.
7. Activate the reviewed laptop backend and reverse-tunnel user units, preserving the existing queue, worker tooling and independent GPU pause timer. Do not enable two backend units on the same port/DB.
8. On apps, use the staged release's Compose file with a stable project name (`docker compose -p nora-media -f .../compose.yml up -d`) only after review. This Caddy container uses host networking and binds only the chosen LAN address/port.
9. Merge and validate the gateway site fragment, then reload Caddy only after parent review.
10. Verify anonymous API/media protection, login/logout, frontend loading, model flags, paused queue, and a read-only provider catalog refresh. No paid inference is part of deployment validation.

For an isolated local source preview, use a separate temp queue and port with `--read-only --web-root .../nora/dist --root /tmp/nora-source-preview --port 36444`. This cannot enqueue jobs or start/pause the real queue.

## Rollback and resource behavior

Keep the previous frontend release and original gateway file backup. Roll back apps by selecting its previous immutable release; restore only the added gateway site block if necessary. Stopping the tunnel removes its reverse listener. Queue restart marks in-flight jobs interrupted and pauses the queue; it never automatically repeats a paid call.

Stopping a tunnel does not cancel an inference already owned by the laptop backend. Check the canonical queue and the existing worker's independent pause timer before shutting down the backend. The deployment does not alter GPU pause rules, model choices, seed settings or inference prompts.

Provider pricing estimates remain estimates. An explicit `max_cost_usd` guard rejects submission when no reliable cost quote exists. Unknown charges stay unknown; cancellation after acceptance does not imply a free request. No new daily spending limit is claimed.

## Reviewed activation scripts

These scripts are prepared, not automatically executed by build or staging:

- `activate-laptop.sh`: refuses an active/unpaused queue, installs the reviewed user units, changes the idle canonical backend once, and starts the application-only SSH tunnel. On startup failure it requests restoration of the original backend unit. It never submits a model job.
- `activate-apps-release.sh RELEASE_ID`: verifies the staged checksum manifest, checks that the public backend requires login and rejects forged loopback Hosts through the tunnel, then starts the reviewed static Caddy release. It does not alter gateway configuration.
- `activate-gateway.sh --apply RELEASE_ID`: verifies apps authentication first, locks gateway changes, backs up the existing complete Caddyfile, appends only the media site block, validates a candidate, checks no concurrent configuration change occurred, atomically replaces the file and reloads Caddy. A reload failure restores the original file.

Activation order after parent review is laptop → apps release → gateway. Apps Docker permission, Compose availability, gateway Caddy's reload action and the private listener ports were checked read-only. The initial password is never passed to apps; gateway and apps do not receive provider keys.

Startup intent is recorded before laptop activation. The original backend was verified as a transient systemd-run unit, so it currently has no persistent reboot enablement. Successful activation enables the new backend and bridge user units; a failure restores previous enablement and can recreate the original collected transient launch. No enablement is changed merely by preparing these scripts.

Manual catalog refresh returns 409 while jobs are queued or running. Finish or cancel those jobs first; this prevents changing the endpoint/pricing catalog underneath an already queued job.
