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


## Promoted — 2026-11-01: reference-only library

Release `nora-v3-4ed9267`, source `4ed9267`. Runtime backend and private proxy
activated; gateway route unchanged.

- [x] `/references/` shares the studio session; navigation link added to main studio.
- [x] NORA_REFERENCE_ROOT points to apps runtime/reference-library/v1, outside Git.
- [x] Imported28 individual originals with source hash checks, including8 nominal
  head angles. No former delivery crops, automatic approval or new generation.
- [x] Protected catalog/images/static/downloads; private provenance returns404.
- [x] Ordered PNG sheet4x2/2048x1536 and ZIP8 tested through authenticated public
  browser. Every ZIP original matches its source hash. No crop or AI operation.
- [x] Existing6 completed jobs preserved; reference browser actions added0 jobs.
- [x] Local workflow-preparation server retired; optional launcher now serves only
  the reference-only preview. Source images and historical outputs retained.

Validation:65 backend tests (four PostgreSQL-only tests skipped), frontend checks/
tests/build, actual reference browser exports, mobile layout and expanded private
proxy negative gate passed. Additional activation-preflight regression and five
deployment preparation tests passed after adding the fail-fast backend helper.

Operational correction: the first manual activation command incorrectly continued
past a failed paused-queue guard. The backend restarted with no running/queued job;
all6 jobs were completed, none interrupted. The queue remains paused after update.
The new `activate-apps-backend.sh` uses one fail-fast SSH transaction; tests prove
an unpaused or unfinished queue neither switches source nor restarts a service.

Evidence outside Git: work/reference-public-verification.json,
work/reference-gallery-validation.json, work/reference-library-public.png,
and the matching private candidate receipt. Example public exports are in the
Nora workspace outputs/reference-library/. No paid inference was performed by
library implementation or verification.


## Promoted — 2026-11-01: reference uploads and explicit attachments

Release `nora-v4-19fa4b7`, source `19fa4b7`.

- [x] Backend activation used fail-fast paused/idle preflight; existing jobs preserved.
- [x] Reference manifest snapshot saved privately before enabling collection writes.
- [x] Added authenticated named sets and slot uploads, empty placeholders, original
  retention on replacement, cross-process file lock and atomic manifest updates.
- [x] Face/body defaults8 nominal45-degree slots; clothing/location4 slots. Read-only
  previews and legacy collections disallow modification; uploaded status is explicit.
- [x] Composer commits file uploads immediately with numbered thumbnails/removal/
  reorder and supported Start/End/Image/Video/Audio roles. Empty aliases no longer
  hide populated arrays. Upload-in-progress and missing-placeholder guards added.
- [x] Cost remains compact and visible; tariffs/budget/native caveats closed under
  Details. Full model ID remains available without taking the primary row.
- [x] Requested model IDs, low-quality default, dimensions and literal prompt kept.
- [x] Expanded private candidate authentication/Host/peer gate passed.

Incident evidence: all6 recent completed production jobs had assets=[]; the OpenAI
submission audit also had references=[]. No service traceback was present. The old
picker required a hidden confirmation after choosing files, and empty array alias
fallback could discard populated reference fields before enqueue. Existing results
were preserved; no paid inference was repeated for this investigation.

Validation:76 backend tests passed with4 PostgreSQL-only cases skipped. Actual
original-form browser tests verified2 Qwen refs,2 OpenAI refs and5 distinct H3 roles,
exact prompts, reorder and pending-upload guards. OpenAI mocked multipart regression
verified two ordered image[] parts on /images/edits. Isolated reference browser tests
verified create/upload/reload/replace/error/PNG/ZIP/mobile and read-only behavior.
Live-public verification is recorded in the external runtime evidence file
work/studio-public-attachments-verification.json; queue remained paused.


Frontend-only follow-up `nora-v4b-picker`, source `5f2b050`: pinned OpenAI snapshot
versions are distinguished in the picker secondary label while the primary label
stays compact. Backend remains on `nora-v4-19fa4b7`; its files match the follow-up
bundle. No extra backend restart or session reset was needed for this label fix.
Live public check uploaded two real photo assets, captured ordered2-reference
OpenAI enqueue payload before production job submission, and preserved the exact
prompt. Production job count stayed6; no library test sets or paid calls created.
Reference create dialogs exposed8 face slots and4 clothing slots, and upload support
was reported available. Private candidate gate repeated successfully for the
frontend-only follow-up; final auth/model-selector smoke evidence is external.

## Promoted — 2026-11-01: collapsible composers and model-aware references

Frontend release `nora-v4c-composer`, source `e61adca`.

- [x] Staged immutable bundle and passed private candidate authentication/Host/peer negative gate.
- [x] Activated frontend only; backend service, database, queue and executor unchanged.
- [x] Photo/video prompt panels collapse to a compact restore bar without unmounting drafts, files, settings or upload controls.
- [x] Replaced legacy model-switch reference clearing with verified capability reconciliation; compatible frames survive and excluded references have a visible notice.
- [x] Mocked transport checks cover all three Veo variants, exact frame pixels/dimensions/order, unsupported roles and first-frame-only model validation.
- [x] Frontend check/typecheck/unit/build and actual isolated browser regressions passed, including pending upload, seed/width, keyboard and mobile preservation.
- [x] Public smoke verified both panels shrink from350px to56.5px, drafts survive, Veo exposes Start/End only, mobile has no overflow and restore is visible. Production jobs remained9 before/after; no page errors or paid calls.

Evidence outside Git: work/studio-video-capability-review.json,
work/studio-collapse-validation.json, work/studio-collapse-payloads.json,
work/studio-public-composer-verification.json and matching screenshots.
No migrations, secrets, infrastructure or route changes. Existing diagrams remain
valid: this update changes composer presentation and attachment reconciliation,
not the service topology, queue schema or generation journey.

## Promoted — 2026-11-01: random seed controls and queue sidebar

Release `nora-v4d-seed-queue`, source `3d0ffb9`.

- [x] Added explicit random/fixed seed controls only for supported models; fixed zero and persisted manual seeds remain valid. The queue shows supported saved seeds and retry retains them.
- [x] Moved queue controls/history into a hamburger-triggered modal sidebar with Escape, backdrop, close/focus restoration and keyboard focus containment.
- [x] Price estimates normalize random seed placeholders in a separate copy without selecting or altering the eventual stored seed.
- [x] Documented endpoint-specific model qualification: catalog/schema, mocked transport, then explicitly authorized paid checks of the actual modes needed. No automatic paid verification added.
- [x] Full backend suite:80 tests,4 PostgreSQL-only skipped. Frontend check/typecheck/unit/build and isolated actual-form browser tests passed.
- [x] Waited for existing production generation to finish. Paused only after no unfinished jobs remained, then safe backend activation rechecked the queue before restart. Existing10 jobs preserved; queue remains paused.
- [x] Private candidate negative authentication/Host/peer gate passed and frontend activated.
- [x] Public smoke confirmed random default, fixed zero selection, sidebar Escape/focus restoration, mobile no-overflow, no page errors, jobs10 before/after and zero paid test calls.

Evidence outside Git: work/studio-seed-sidebar-validation.json,
work/studio-seed-sidebar-payloads.json, work/studio-public-queue-seed-verification.json
and corresponding desktop/mobile screenshots. No migration, secret or new service
required. Updated generation journey for the sidebar and saved-seed behavior;
service topology and data schema are unchanged.

## Promoted — 2026-11-01: LoRA media selection and compact main menu

Release `nora-v4e-lora-library`, source `29809f2`.

- [x] Added free-append named LoRA collections in the reference library, mixed photo/video batch uploads, previews, original downloads and bounded mixed ZIP export. Video selection is explicitly excluded from PNG sheets. No training or inference actions added.
- [x] Preserved existing reference sets, original bytes, review statuses and photo-slot behavior. Private manifest snapshot saved before backend activation.
- [x] Moved branding, references, catalog refresh and logout into the existing menu/queue hamburger on desktop/mobile; main header retains studio tabs.
- [x] Added nonsecret `NORA_FFPROBE_BIN` pointing to runtime/bin/nora-ffprobe. `provision-apps-ffprobe.sh` prepares signed Ubuntu packages by rootless download/extraction under runtime/tools/media-probe-v1, saves package SHA256 provenance, and configures the isolated wrapper. No system packages installed or new service required.
- [x] Verified actual apps probe on synthetic1s96x128MP4. The temporary sample was removed; no synthetic records added to the user's library.
- [x] Video originals stream authenticated206byte ranges; MIME/container/stream/budget validation is bounded. Upload caps: images40MiB, video100MiB; JSON reference body137MiB stays behind the existing140MB proxy limit.
- [x] Full backend suite85 tests,4 PostgreSQL-only skipped; frontend check/typecheck/unit/build passed. Isolated library browser tests cover mixed uploads, reload, playback, exact MP4 SHA256 download, ZIP, partial failure/retry, read-only, mobile390 and existing8face slots.
- [x] Menu browser tests cover one-row<=62px header, focus/Escape/backdrop, moved actions, queue behavior and mobile overflow.
- [x] Queue was idle/paused at activation; safe backend helper and private candidate negative auth/Host/peer gate passed. Production public smoke confirmed compact menu, LoRA tab and free set dialog, no page errors; jobs10 and reference records28 unchanged. Queue remains paused. No paid checks performed.

Evidence outside Git: work/studio-mainmenu-validation.json,
work/reference-library-lora-desktop.png, work/reference-library-lora-mobile.png,
work/studio-public-lora-menu-verification.json and matching public screenshots.
No database migrations; existing portable manifest format extended for LoRA items
and media metadata. User journey updated; service topology remains unchanged.
