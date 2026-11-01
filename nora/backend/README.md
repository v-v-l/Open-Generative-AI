# Nora execution wrapper

This directory is the single canonical backend source. It is independent of the upstream application's server and never starts inference merely by being imported.

Set `NORA_PROJECT_ROOT` to the external runtime workspace. Provider credentials are loaded server-side from that workspace's `.env` or the process environment; references, queues, logs and model/runtime files remain outside this fork.

```bash
NORA_PROJECT_ROOT=/home/victor/Projects/Nora python3 nora/backend/server.py \
  --port 36440 --web-root nora/dist
python3 -m unittest discover -s nora/backend_tests
```

The queue starts paused. `--read-only --root /tmp/nora-preview --port 36444` provides an isolated preview with job/queue/upload mutations disabled.

Public hosting requires `--public-origin https://media.bp-flow.com`, `MEDIA_STUDIO_PASSWORD_HASH` (generate with `--hash-password`) and a random `MEDIA_STUDIO_SESSION_SECRET` of at least 32 characters. Never enable the trusted-local development bypass in production behind an SSH tunnel: remote tunnel callers appear as loopback to the application.

Native Qwen/H3 and cloud adapter capabilities are separate. Referenced media is never published as an anonymous URL by this wrapper. Cost estimates and actual usage are recorded separately; an explicit `max_cost_usd` estimate guard rejects a job if no quote is available.

Existing workspace entry points under `scripts/generation_studio` and `tests/test_generation_studio*.py` are compatibility symlinks into this fork, not additional maintained copies.
