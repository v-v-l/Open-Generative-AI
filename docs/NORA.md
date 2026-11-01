# Nora media integration

## Source of truth

- Original upstream: https://github.com/Anil-matcha/Open-Generative-AI
- Our fork: https://github.com/v-v-l/Open-Generative-AI
- `upstream` is the original repository; `origin` is our fork.
- `main` follows the original project. `nora` carries our integration.
- Preserve original license notices. This project is MIT licensed.

The Nora entry retains upstream image/video studio components. Its adapters live
under `nora/` so provider and queue changes do not require editing every studio.
Other MuAPI workflows are not automatically supported by an OpenRouter key.

The canonical generation backend lives in this fork at
`nora/backend` (the existing Nora workspace's `scripts/generation_studio` is a compatibility symlink): persistent queue, Qwen and H3 execution, cloud
adapters, capability discovery, billing and authentication. It is a separate
service, not a browser API key. Reference files stay private.

## Building the Nora frontend

Run from `nora/`:

```bash
npm ci --ignore-scripts --workspaces=false
npm run check
npm test
npm run build
```

The backend uses Python 3.11+ and the dependencies in
`nora/backend/requirements.txt` (Pillow and optional PostgreSQL driver). Existing ComfyUI/model installations and
SSH worker configuration are separate runtime dependencies.

Run backend tests from the repository root with
`python3 -m unittest discover -s nora/backend_tests`. Set
`NORA_PROJECT_ROOT=/home/victor/Projects/Nora` for the existing runtime; credentials,
worker state and generated media are resolved there, outside this fork.

Use the Python backend to serve the resulting static build and same-origin
`/api` and `/media` routes. Do not run the upstream MuAPI server and claim it is
using our OpenAI/OpenRouter keys. No model weights or keys belong in this fork.

## Upstream updates

Never use an unattended `git pull` on a running installation. Choose the exact
upstream commit after reading its changes, then from this repository run:

```bash
python3 scripts/nora-update.py --target FULL_UPSTREAM_COMMIT_SHA --verify
```

This requires a clean working tree. It fetches only from the original `upstream`
and merges the selected revision in a detached candidate worktree. Our checked-out
branch and deployed files do not change. Conflicts stop the update and remain in
that candidate for review. The report records both revisions and verification.

After reviewing the candidate, check the image/video forms, reference roles,
exact prompt preservation, model-specific controls, prices, queue actions and
login in a browser. Only then fast-forward the `nora` branch to its candidate
commit and build/deploy a new release. Push `nora` to our fork, never to upstream.

Production API/queue/cloud/H3 control run on apps, PostgreSQL on databases:5466.
The workstation hosts only the authenticated Qwen executor. See
`nora/deploy/README.md` and `nora/ARCHITECTURE.md` for ports, data and update contracts.

Keep the previous immutable release for rollback. PostgreSQL, references, provider
accounting and output files stay outside releases. Do not roll back this data or
resubmit jobs merely because application source was rolled back. SQLite remains
available for isolated development; production no longer uses it.

For a frontend/proxy-only update, stage a new immutable apps release, run the
private candidate access gate, then activate that release. Reuse the existing
gateway route; the gateway helper is for initial site creation and deliberately
refuses to append a duplicate site.

For a backend update, pause and drain active work first. Stop the backend before
fast-forwarding its checked-out source so one process cannot mix old Python
modules with new templates. Then restart `nora-media-backend.service`, verify
public authentication and the paused queue, and keep the SSH tunnel running.
`activate-laptop.sh` performs the initial handover and deliberately refuses an
implicit restart of an already active public backend. Backend rollback uses the
same idle-work guard, the previous source commit and a service restart; it never
rolls back the external SQLite database.

Refresh provider models/prices separately through the explicit catalog-refresh
operation after queued/running work is finished or cancelled. Refresh is blocked
while unfinished jobs exist, so their endpoint settings are not silently replaced. A catalog update must not generate media, select another model, or
change a queued job. A listed model is not proof of account access or successful
paid generation. Costs computed from token rates are not provider invoices.

## Hosting

The initial private bridge keeps backend execution on the existing Nora host and
serves the frontend on apps, routed by gateway at `media.bp-flow.com`. The studio
needs that host online; Qwen and GPU worker keys are not copied into a public web
container. No ComfyUI endpoint or reference file is exposed without studio auth.

## Verified deployment

The private studio is available at https://media.bp-flow.com. Release and
verification records are in [the deployment ledger](../deploy/pending-prod.md);
[data flow](diagrams/data-flow.md), [queue schema](diagrams/schema.md) and
[user journey](diagrams/user-journey.md) describe the integration boundaries.
