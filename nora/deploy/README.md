# Nora Media deployment

Canonical code and deployment sources live in this fork. Runtime state, credentials,
Python/Node installations and generated media stay outside releases.

## Target topology

```text
Browser → HTTPS media.bp-flow.com → gateway Caddy
  → apps Caddy 192.168.100.70:36443 (gateway only)
    → immutable authenticated frontend
    → apps loopback 127.0.0.1:36442: API, queue, cloud and H3 controller
      → databases 192.168.100.75:5466: nora_media_prod PostgreSQL
      → apps runtime: uploads and generated files
      → OpenAI / OpenRouter directly
      → SimplePod H3 over its existing SSH/provider API
      → apps loopback 36447 → private SSH tunnel → workstation Qwen executor 36446
```

Only Qwen depends on the workstation. Its availability is checked independently;
cloud/H3 and queue/history remain usable when that executor disconnects. No model
weights or GPU inference are installed on apps. Deployment status and evidence
belong in `../../deploy/pending-prod.md`; the diagram alone is not deployment proof.

## Apps runtime

- Base: `/home/victor/apps/media-studio`.
- Immutable bundles: `releases/RELEASE_ID`; `current` selects backend source.
- Native service: `nora-media-apps-backend.service`, user `victor`, enabled with
  `loginctl enable-linger`. Native systemd preserves the existing independent H3
  budget timer without granting a container the Docker socket or host system bus.
- Python environment: `runtime/venv`; install `backend/requirements.txt`.
- Node dependencies: `runtime/tools/simplepod`; install the reviewed runtime lockfile.
- `runtime/backend.env` (0600): DATABASE_URL, public authentication and Qwen tunnel
  credentials. `runtime/.env` (0600): only the used provider keys.
- `runtime/outputs/generation-studio`: media files; PostgreSQL owns queue metadata.
- `runtime/work/simplepod/worker.json`: saved rental identity; SSH key and verified
  host keys in `runtime/ssh`. Never include these files in release bundles.

Production must not enable `--allow-loopback-local`: apps-local callers can forge a
loopback Host. The public Host and authentication guards apply on loopback too.
Sessions are Secure/HttpOnly/SameSite=Strict; static authentication runs before file
serving, and API/media require login. Backend restart requires logging in again.

## Workstation reboot and local execution

Verified 2026-11-01: these user services are enabled and active:

- `nora-comfy-photos.service`: existing local ComfyUI on loopback 8190.
- `nora-qwen-executor.service`: authenticated Qwen-only executor on loopback 36446.
- `nora-qwen-bridge.service`: outgoing SSH connection to apps, exposing only apps
  loopback 36447 → workstation loopback 36446. The bridge retries after disconnect.

Workstation `loginctl show-user victor -p Linger` reports `Linger=yes`. Services
start after boot without a desktop login or manual command. The machine must be
powered on with network connectivity; the server does not power it on remotely.
Service configuration was checked live; a physical reboot was not part of testing.

The server owns the queue and sends a bounded authenticated photo job through
this tunnel. The local executor starts the Comfy workflow and returns images to
apps. Weights load when needed, so the first inference after boot can take longer.
When disconnected, only Qwen becomes unavailable; cloud/H3 continue independently.
A restart during inference preserves interruption evidence and does not silently
resubmit the job. Inspect interrupted work before an explicit retry.

Diagnostic commands on the workstation:

```bash
systemctl --user status nora-comfy-photos.service nora-qwen-executor.service nora-qwen-bridge.service
loginctl show-user victor -p Linger
journalctl --user -u nora-qwen-executor.service -u nora-qwen-bridge.service -n 50
```

Executor unit source: `nora/backend/runtime/nora-qwen-executor.service`; tunnel
unit: `nora/deploy/nora-qwen-bridge.service`. The existing ComfyUI installation and
its unit remain workstation runtime dependencies, separate from the hosted app.

## Database

`databases/compose.yml` provisions only `pg_nora_media_prod`, its own persistent
volume, LAN port 5466 and dedicated non-superuser `nora_media`. Its pg_hba allows
application connections only from apps LAN address. Passwords are generated outside
Git. Check live container/listener bindings before allocating a port on another
installation. The initial role script runs only on an empty volume.

Both VMs currently lack a Docker Loki plugin. The DB uses bounded json-file logs;
the native backend uses journald. Installing shared observability infrastructure is
not part of this migration. Back up both the PostgreSQL database and apps media
files; neither is a substitute for the other. No new backup schedule is implied.

A direct PostgreSQL session holds a database advisory lock for the entire controller
lifetime; transaction-pooling proxies are unsupported. Another controller cannot
recover or dispatch the same queue. Lost connections never reconnect silently.
Restarts pause the queue and mark running jobs interrupted; no paid call is retried.

## Migration and cutover

1. Run backend tests (with NORA_TEST_DATABASE_URL pointing ONLY to an isolated
   disposable database for live integration tests), frontend checks/tests/build.
2. Check the existing queue is paused with no running job. Stop the old backend
   before copying an offline SQLite snapshot; preserve the original for rollback.
3. Copy the registered uploads/jobs to apps runtime and retain the offline snapshot.
4. Load DATABASE_URL without printing credentials, then run the reviewed
   `backend/import_sqlite.py --source-root SNAPSHOT --original-root OLD_STORAGE_ROOT
   --target-root NEW_STORAGE_ROOT`. Import refuses a nonempty target, validates
   copied files, preserves IDs/order, and commits counts/import marker atomically.
5. `prepare-release.sh` creates a checksum bundle of backend source, frontend and
   proxy configuration. `stage-release.sh RELEASE_ID` uploads without activating.
6. Install requirements/runtime dependencies and the apps user service. Select the
   reviewed `current` release. Stop the former full-application reverse tunnel
   before starting apps backend on the same apps loopback port 36442.
7. Verify backend Host/auth guards; run `verify-private-candidate.sh RELEASE_ID`.
   `activate-apps-release.sh RELEASE_ID` requires its matching negative-gate receipt.
   The existing gateway route does not change and must not be appended again.
8. Verify the public UI, login/logout, protected assets, migrated media, paused
   queue and model availability. Stop/disable the old workstation backend and full
   app tunnel. Exercise Qwen tunnel disconnection/reconnection without inference.

The old `activate-laptop.sh` and full-app bridge units are retained only for the
previous topology/rollback. They are not part of apps deployment. Qwen now has its
own executor and tunnel, with separate ports and credentials.

## Updates and rollback

Fetch/merge upstream through the fork's `scripts/nora-update.py`; it uses an isolated
worktree and never promotes automatically. Build/test a new immutable release.
Use `activate-apps-backend.sh RELEASE_ID` after pausing/draining the queue. It
checks hashes and PostgreSQL state before any mutation in one fail-fast SSH
transaction, switches `current`, restarts the backend, and restores previous source
on failed authentication readiness. A rejected preflight performs no restart.
Then verify and activate the frontend release. Runtime credentials, media, database
and worker state are not overwritten. Future schema changes need explicit compatible
migrations before source promotion.

Keep the previous release and pre-migration SQLite/media snapshot. Before any
rollback check for cloud submissions, remote Comfy work and the independent GPU
pause timer; stopping a web process does not cancel accepted provider work. After
new PostgreSQL writes, restoring old SQLite would discard those changes: reconcile
state explicitly rather than blindly restarting the old service.

## Proxy deployment details

Caddy uses explicit `route` ordering: deny wrong peer/Host before handlers, authenticate
before static rewrite/serving, and `redir * /login 302`. Syntax checks alone do not
prove access control. The private candidate gate checks real anonymous HTML/JS
redirects, API/media 401, wrong-Host/peer 403, then removes only its owned container ID.

The Caddy image requires NET_BIND_SERVICE in its bounding capability set even on a
high port; dropping ALL alone prevents execution. Keep other capabilities dropped
and no-new-privileges. Stage with `tar -xpf` to preserve readable mounted file modes;
releases and their parent remain 0700. Docker commands inside SSH-streamed scripts
must use `</dev/null` so they cannot consume subsequent shell commands.

Deployment validation never submits paid inference. Estimates remain estimates;
unknown charges stay unknown, and explicit max_cost_usd requires a reliable quote.

## Reference-only library

`/references/` uses the same login. Set NORA_REFERENCE_ROOT to the private versioned
reference inventory on apps. Browsing, original/ZIP downloads and deterministic
PNG sheet composition make no model or queue calls. See `../references/README.md`
for the inventory importer, export limits and optional local preview.
