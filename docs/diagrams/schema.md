# Nora queue storage

Verified against `nora/backend/server.py` at `8b61e89`, 2026-11-01.

The external runtime SQLite database has three tables:

| Table | Key | Stored state |
| --- | --- | --- |
| `settings` | `key` | JSON settings including queue pause |
| `assets` | `id` | Private filename, MIME and contained filesystem path |
| `jobs` | `id` | Status/timestamps, payload JSON, result JSON, error, progress and cancellation flag |

Reference IDs live inside job payload JSON; there is no SQL foreign-key relation
between jobs and assets. Output registration requires files inside that job's
output directory. The database has one process owner enforced by a filesystem
lock. Restarted running work becomes interrupted and the queue returns to pause.
