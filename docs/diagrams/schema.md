# Nora queue storage

Verified production `nora-v2-9215134`, 2026-11-01.

Production metadata lives in PostgreSQL `nora_media_prod` on databases:5466.
SQLite remains an isolated development option.

| Table | Key | Stored state |
| --- | --- | --- |
| `settings` | `key` | JSON settings including queue pause |
| `assets` | `id` | Private filename, MIME and contained apps filesystem path |
| `jobs` | `id` | Status/timestamps, payload/result/progress JSON, cancellation and FIFO sequence |
| `studio_imports` | `source_sha256` | Completed offline import timestamp and verified row counts |

Reference IDs remain inside payload JSON; there are no SQL foreign keys between
jobs and assets. Media files live on apps, not inside the database. A PostgreSQL
session advisory lock prevents competing controllers across machines; the local
filesystem lock also protects the runtime directory. The driver never silently
reconnects after losing ownership. Restart pauses the queue and marks running jobs
interrupted. Imports refuse nonempty targets and preserve IDs and FIFO order.
