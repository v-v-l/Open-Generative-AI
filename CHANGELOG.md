# Changelog

Nora integration changes are recorded here. Upstream project documentation is
preserved separately in the original README below the fork notice.

## [Unreleased]

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
