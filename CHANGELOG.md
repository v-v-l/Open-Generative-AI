# Changelog

Nora integration changes are recorded here. Upstream project documentation is
preserved separately in the original README below the fork notice.

## [Unreleased]

### Added
- OpenRouter Avatar IV photo-and-script generation with required HeyGen Voice ID, separate gesture instructions and typed provider settings; explicit HeyGen Video/H3 Max capability and catalog-price checks.
- Open a prior gallery/queue job with **Пересоздать** to edit its full prompt, model, seed, settings and original reference roles before submitting; no automatic generation.
- Paste clipboard images into the photo/video composer with Ctrl/⌘V, using the supported reference roles and existing upload limits.
- Browse reference sets by hairstyle/body/look, open their individual originals and download an ordered no-crop 4×2 sheet or original ZIP; historical sets remain accessible through the archive filter.
- Replace or remove user-uploaded photo/video references while preserving set positions and private originals.
- Replace studio attachments in place without losing the current file on upload failure.
- Curate named LoRA photo/video sets with batch uploads, playback, original downloads and mixed ZIP exports; no training is launched.
- Collapse/expand the photo and video prompt panel while retaining its draft, files and settings.
- Choose random or fixed seeds explicitly for supported models; inspect the saved seed in the queue.
- Open the queue from a compact hamburger button as a desktop/mobile sidebar.

### Fixed
- Allow prompt-only photo/video requests when the selected endpoint permits them; count committed H3 image references rather than requiring a first frame.
- Download gallery originals through authenticated server attachments with the original filename and MIME type, avoiding temporary blob links and PNG-to-JPG mislabeling.
- Reconcile lost Qwen submission/status responses using the existing request ID without duplicate generation.
- Show bounded, redacted cloud provider error details instead of only generic HTTP failures.
- Align the hamburger button with the sidebar on the right edge.
- Replaced the clipped parameter popover with a scrolling modal and Apply/Cancel draft editing in photo and video studios.
- Moved branding, references, catalog refresh and logout into the shared hamburger menu on desktop and mobile.
- Random-seed drafts can obtain price estimates without allocating or changing the eventual generation seed.
- Filter video references by the selected model capabilities and explain removal of incompatible attachments after model changes.
- Added mocked transport checks for all three Veo variants and models with first-frame-only input.

## [Nora 0.4.0] - 2026-11-01

- Added user-created reference sets with empty face/body/clothing/location view slots, persistent uploads and safe replacement retaining previous originals.
- Replaced the hidden upload-confirmation flow with immediate, numbered attachment thumbnails and explicit supported video roles.
- Fixed empty-array aliases masking populated reference fields; blocked submission while uploading or missing explicitly referenced images.
- Compacted cost display and collapsed technical details; shortened display labels without changing requested models, quality, dimensions or prompt text.
- Verified ordered two-image OpenAI multipart transport with mocks and original-byte/EXIF handling for library uploads.

## [Nora 0.3.0] - 2026-11-01

- Added the private reference-only library at /references/ with shared login.
- Added ordered selection, whole-collection selection, no-crop PNG sheets, original downloads and byte-exact ZIP exports.
- Preserved candidate/review statuses and nominal angle metadata; moved 28 originals to private apps storage.
- Retired local workflow preparation from the reference site.
- Added fail-fast backend activation: rejected queue preflight cannot switch source or restart the service.

## [Nora 0.2.0] - 2026-11-01

- Moved authentication, API, queue, media storage and cloud/H3 control to apps.
- Added dedicated PostgreSQL on databases, controller ownership and atomic offline SQLite import.
- Kept only a bounded authenticated Qwen executor on the workstation, with independent availability in the UI and scheduler.
- Preserved H3 independent budget timers and strengthened cleanup when progress/storage fails.
- Verified workstation-tunnel independence, migrated media integrity and access guards without paid inference.

## [Nora 0.1.0] - 2026-11-01

### Added
- Original image/video studio forms connected to private Qwen/H3, OpenRouter and direct OpenAI adapters.
- Persistent sequential queue with pause, cancellation, explicit retry and private output downloads.
- Model-specific reference slots and settings, price estimates where available, and separately labelled provider or token-calculated costs.
- Isolated upstream update candidates with dependency checks, frontend/backend tests and a production build before review.

### Security
- Password-protected public studio and media, fixed-host proxying and private SSH transport to the execution host.
- Queues start paused; failures and restarts require attention instead of automatically repeating paid requests.
