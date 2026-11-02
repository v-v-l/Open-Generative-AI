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

## Promoted — 2026-11-01: scrolling parameter modal with Apply/Cancel

Frontend release `nora-v4f-parameter-modal`, source `7776271`.

- [x] Replaced connected photo/video PARAMS popovers with a portaled native modal and separate draft values. Apply commits the supported fields; Cancel, close, Escape and backdrop discard edits and restore focus.
- [x] Preserved schema types/defaults/enums/labels and numeric limits; added validation, internal touch scrolling, fixed header/footer and visualViewport sizing for small visible areas. Separately selected seed, prompts and references remain unchanged.
- [x] Opening parameters closes previous legacy popovers. Unconnected upstream grouped tools remain unchanged.
- [x] Frontend check/typecheck, unit tests and production build passed. Actual isolated form tests verified numeric/boolean Apply and Cancel for photo/video, invalid bounds, focus/close behavior and real CDP touch swipe (scrollTop0→192).
- [x] Short390x360 viewport fit verified: modaltop12/bottom348, footerbottom347, content scrolls inside172px region. Chromium mobile/touch emulation verified; actual iOS Safari was not tested.
- [x] Private candidate negative authentication/Host/peer gate passed; activated frontend only. Backend stays on `nora-v4e-lora-library`; no restart, queue setting or schema/env changes.
- [x] Public smoke verified both studios' Cancel and Apply, mobile scrolling, reachable footer and screen-fitting352x576 dialog at390x600. Jobs remained10 before/after; no page errors or paid calls.

Evidence outside Git: work/studio-parameters-validation.json,
work/studio-public-parameter-modal-verification.json and desktop/mobile screenshots.
User journey documents draft commit/discard behavior. No migration or infrastructure
change required.

## Promoted — 2026-11-01: transport recovery, safe cloud diagnostics and right menu

Release `nora-v4g-transport-errors`, source `dbb1b65`.

- [x] Qwen incident traced: Appsjob b4ab0fcd67f04dfebfc981d86a0b1776 submittedexecutorID76812e76ca5248aeac056d4ae49f7a3e at20:41:36UTC;45srequesttimeout occurred before local source files/acceptance at20:42:30. The existing inference finished successfully at20:44:25. No inference exception or duplicate recovery generation occurred.
- [x] Restored the existing result to its original failed job with seed52363425, verified768x1024PNG/SHA256, added a private executor-recovery.json audit retaining the former timeout, and marked the job completed. Local backup preserved under outputs/studio-recovery/b4ab0fcd67f04dfebfc981d86a0b1776/.
- [x] Qwen transfer timeout now120s; lost acknowledgements/status reads reconcile by existing opaque ID with GET only, under bounded deadlines, never a second submission. Explicit HTTP rejection is not retried. Tests cover late acceptance404, lost acknowledgement/status response and exactly one POST.
- [x] Sunburst400incident3ff38109e6774a7c9dc0979d3494d581 has no recoverable original provider error body or request ID: old handler discarded them. Three PNG references and selected quality/size do not establish a documented limit violation. No policy cause asserted and no paid reproduction attempted.
- [x] Future cloud HTTP failures capture bounded64KiBJSON-derived message/code/type/parameter/requestID, redact credentials/prompts/URLs/paths/inline or encoded data, and expose the sanitized reason. Raw upstream bodies are not saved; automatic retries remain off.
- [x] Hamburger moved to the right edge beside the right-hand drawer; desktop1440 and mobile390/320 layouts/focus checked. Frontend check/typecheck/build passed.
- [x] Full backend suite90 tests total,4 isolated PostgreSQL tests skipped. Safe paused/idle backend activation and private candidate negative auth/Host/peer gate passed; no unfinished job interrupted.
- [x] Public smoke downloaded recovered image with exact SHA256, confirmed completed status and original seed, right trigger gaps14px desktop/10px mobile, no page errors,12jobs retained, queue paused and zero paid test calls.

Evidence outside Git: work/studio-public-transport-recovery-verification.json,
work/studio-header-right-browser.js and desktop/mobile screenshots. Private runtime
audit remains beside the recovered job. No migrations, new secrets or new services;
transport topology and data schema are unchanged.

## Promoted — 2026-11-01: reference replace/remove actions

Release `nora-v4h-reference-actions`, source `8d25784`.

- [x] Library user-upload cards offer Replace/Delete for photographs and videos. Replacement keeps LoRA/slot/selection position; confirmed deletion clears active membership/selection/export and restores empty angle slots.
- [x] Soft archive retains original bytes privately while archived IDs disappear from catalog/defaults and reject original/thumbnail/download/export access. Legacy read-only groups and global read-only mode remain protected. Historical active orphan uploads can be removed without modifying their current replacement slot.
- [x] Added authenticated same-origin POST /references/api/remove {id}; occupied-slot and LoRA replacement use replace_id with stale409 protection. Failed validation/persistence preserves the existing active item.
- [x] Studio attachment cards replace each supported role in place only after successful upload; errors retain the old file, queue submission is blocked while uploading, and existing removal controls remain. Late completions cannot leak across model changes/unmounts.
- [x] Full backend suite96 tests total,4 PostgreSQL-only skipped; final reference suite32 tests passed. Frontend check/typecheck/build and isolated actual-form browser tests passed for photo, all H3 roles, failures/retry, order and mobile390.
- [x] Library browser tests passed photo↔video LoRA replacement, selected index preservation, slot replacement/delete/reupload, reload, failures/retry, orphan controls, confirmation, read-only and mobile.
- [x] Saved a private manifest snapshot, verified paused/idle queue, safely activated backend, passed candidate negative authentication/Host/peer gate and activated frontend.
- [x] Public smoke verified deployed studio/library action code and confirmation, rejected malformed remove with400 before any mutation, retained37 active references and14 jobs before/after, no page errors and zero paid test calls.

Evidence outside Git: work/studio-public-reference-actions-verification.json,
work/studio-replace-browser.js, work/studio-replace-photo-mobile.png,
work/studio-replace-video-mobile.png and library mutations/delete-confirm screenshots.
No new dependencies, secrets, services or database migrations. Portable manifest
records gain optional archive metadata on mutation; retain archive-aware backend
versions on rollback so archived items do not reappear. User journey/manual updated.

## Promoted — 2026-11-02: curated reference sets

Backend release `nora-v4i-reference-sets`, implementation source `7818f67`.

- [x] Saved a full private library backup before mutation; verified all61 previous originals remain byte-exact after curation.
- [x] Safely activated backend with paused/idle preflight and passed private candidate authentication/Host/peer negative gate. Reference HTML/JS is backend-served; studio frontend/proxy unchanged.
- [x] Reused three existing selected sets and imported the accepted white tennis/bun set: four active sets with32 selected originals, eight angles each. No new inference or image alteration.
- [x] Archived the user-rejected old ponytail and historical working groups: six archived sets; original downloads remain available through the archive filter. No physical deletions.
- [x] Verified all32 original download hashes and all four ordered2048x1536/no-crop PNG sheets and byte-exact8-original ZIP files through authenticated production APIs.
- [x] Live desktop/mobile browser verified four active sets, archive access, eight-member details, navigation and actual sheet download without overflow. Fixture browser checks and35 Python reference tests passed.
- [x] Restored the originally unpaused queue only after confirming no queued/running job; retained all26 job records. No paid verification calls.

No new dependencies, services, secrets or SQL migrations. Collection manifest
metadata gains optional archived/curated flags and legacy-group overrides. Rollback
must retain archive-aware readers or restore the complete pre-curation manifest;
never remove newly imported originals while rolling back source.

Evidence outside Git: work/reference-housekeeping-v1/import-report.json,
live-verification.json and desktop/mobile screenshots. A conservative local cleanup
inventory was prepared; selected/archive sources and training/LoRA/FIBO folders
are protected, and no local generation files were deleted.

## Promoted — 2026-11-02: studio references, recreation and original downloads

Release `nora-v4j-studio-usability`, implementation source `6dfc50a`.

- [x] Fixed upstream form guards using actual endpoint role requirements: optional text-only photo/video requests stay valid, H3 Image-only inputs count, and text-capable video variants expose their supported input fields. Cloud last-frame-only rejection and H3 independent guide semantics remain consistent with the backend.
- [x] Clipboard images upload through the composer attachment pipeline with role selection, format/count/size/read-only/upload guards; ordinary text paste is unchanged.
- [x] Gallery and queue **Пересоздать** restore literal prompt, model, saved seed/settings and original references for editing without enqueueing. Missing originals, changed role support and concurrent uploads fail before draft mutation. Reference existence checks use bounded ranged GETs; per-video include_audio:false is preserved.
- [x] Gallery downloads now use authenticated original URLs with download=1; backend supplies original MIME and RFC5987 attachment filename, retaining inline playback and byte ranges without exposing storage paths. Missing job references remain represented rather than silently disappearing.
- [x] Full backend101 tests:97 passed,4 disposable-PostgreSQL cases skipped. Frontend check/typecheck, six test files, build and diff whitespace checks passed. Native-studio fixture browser checks cover13 flows including Qwen/OpenAI text-only, H3 clipboard image, Veo Start, exact recreation payloads and PNG bytes at desktop/mobile sizes.
- [x] Paused/drained queue, safely activated backend and frontend, passed private candidate auth/Host/peer gate, and restored original queue state after live verification. All26 jobs retained; library data unchanged.
- [x] Public browser verified original prompt/files restored without submission, real PNG download/name, captured Qwen text-only and H3 clipboard submissions, mobile layout and zero page errors. Test generation/upload requests were intercepted; no real uploads or paid calls.

No new dependencies, secrets, services or SQL migrations. Backend and frontend must
be promoted together for the server download filename contract. Previous immutable
release retained for rollback; no generation or dataset data migration required.
Evidence outside Git: work/studio-usability-v1/{backend-tests.log,frontend-check.log,
frontend-tests.log,frontend-build.log,live-verification.json,live-download.json,
live-browser.log,live-mobile-viewport.png}. Test browser state was removed privately.

## Promoted — 2026-11-02: requested OpenRouter video models and Avatar IV

Release `nora-v4k-openrouter-avatars`, implementation source `48d7a14`.

- [x] Verified live OpenRouter catalog/OpenAPI, official video skill and HeyGen upstream semantics. HeyGen Video and H3 Max were already discovered; refreshed those two and added Avatar IV with an explicit script adapter.
- [x] Avatar exposes one required image, spoken script and required Voice ID; typed optional motion/expressiveness/fit/remove-background options go under provider.options.heygen.parameters. No fixed duration, seed or audio toggle; uploaded audio and complex unimplemented options stay hidden. Complete Avatar-specific OpenRouter POST has not been paid-tested.
- [x] H3 Max supports first/last frames,480p/768p,5–15s with no seed/audio toggle. HeyGen Video supports text/first frame,480p/768p/2K,5–15s and seed. Catalog rates are shown; no screenshot promotion is assumed.
- [x] H3 Max and text-only HeyGen estimates use exact catalog rate×seconds. Avatar speech duration and HeyGen frame pricing totals remain unknown until usage; budget guards do not invent totals.
- [x] Full backend107 tests:103 pass,4 disposable-PostgreSQL cases skipped. Frontend check/typecheck, seven test files, build and diff whitespace gate passed. Native Avatar fixture browser passed10 desktop/mobile checks with mocked transport; backend tests assert one POST and exact model-specific reference/options payloads.
- [x] Preserved the complete prior cloud catalog at apps runtime/work/generation-studio/cloud-catalog.before-v4k.json, SHA256 b9e9a18a7e8df655ca8d59de3ae99323f1f701b8c2f1f67ea13260a28075b2ac. GET-only targeted refresh retained unrelated rows/pinned endpoints byte-for-byte; cloud models89→90, total91→92. No full image-catalog refresh.
- [x] Safely promoted backend/frontend with paused/idle preflight and private candidate auth/Host/peer gate. Live API verified three models and estimates; public browser verified exact Avatar photo/script/Voice-ID payload through interception, supported fields, tariff note, mobile layout and no page errors.
- [x] Restored original queue state after confirming zero pending/running jobs. History31→32 includes one concurrent, already cancelled H3 user job; it was preserved. Test submissions/uploads were intercepted; no paid test calls or real test uploads. Owned mock/browser sessions stopped and private browser-state file removed.

No dependencies, SQL migrations, services or secrets added. Source and targeted
catalog update belong together. To roll back to a version without the Avatar
adapter, restore the preserved catalog snapshot as well; keep newer user jobs and
media intact, with no automatic retries. Reference library data was unchanged.

Evidence outside Git: work/openrouter-heygen-h3-v1/{video-models.json,openapi.txt,
backend-tests.log,frontend-check.log,frontend-tests.log,frontend-build.log,
live-catalog.json,live-verification.json,live-browser.log,live-mobile.png}.

## Promoted — 2026-11-02: compatible output presets

Release `nora-v4l-output-presets`, implementation source `af473c0`.

- [x] Shared format/resolution/duration controls use existing model descriptors in both studios. Literal cloud resolution tiers/durations are retained; OpenAI fixed sizes map to actual aspect ratios with separate generation quality. Duplicate primary controls are hidden.
- [x] Native Qwen/H3 presets derive exact formats and dimensions from32-pixel executor constraints, capped at1536px per dimension. Actual dimensions and approximate tiers are visible; no unsupported2K option. H3 duration choices encode valid17k+5 frame counts and display actual approximate seconds.
- [x] Recreated custom dimensions/frame counts remain untouched and clearly labelled until explicit selection. Standard-format selection enables compatible native resolution tiers. Existing advanced native controls and parameter Apply/Cancel semantics remain.
- [x] Published Veo4K→8s constraint metadata from catalog reads without modifying or refreshing cache rows. The UI reconciles duration with visible feedback and filters incompatible options; backend validation remains authoritative.
- [x] Full backend108 tests:104 passed,4 disposable-PostgreSQL cases skipped. Agent verified all8 frontend test files, typecheck/check, production build,12 native-studio preset browser flows and18 gallery/Avatar regression checks with isolated fixtures. Parent reviewed the diff and mobile render; whitespace gate passed.
- [x] Safely promoted backend/frontend with paused/idle queue and private candidate authentication/Host/peer gate. Live browser checked8 preset behaviors: exact Qwen/H3 dimensions and frame payloads, retained custom H3 defaults, Veo constraint metadata/4K8s request, mobile fit and zero page errors.
- [x] Preserved all34 original job IDs; no new jobs/uploads or paid tests. Three test submissions were intercepted in the browser. Restored original queue state after confirming no unfinished jobs; removed private browser-state file and stopped owned test browser/mock server.

No dependencies, SQL migrations, services, credentials or catalog-cache mutations.
Previous immutable release retained for rollback; reference files and generation
history are unchanged. Model tiers are not claims of paid output/performance tests.

Evidence outside Git: work/studio-output-presets-v1/{state-before.json,
queue-before-deploy.json,backend-tests.log,live-verification.json,live-browser.log,
live-mobile.png}. Fixture regression source lives in nora/tests/outputPresets.*;
its mobile screenshot is /tmp/nora-output-presets-mobile.png.
