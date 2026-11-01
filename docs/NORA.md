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

For a backend update, pause and drain active work first. Stage a new immutable
release on apps, stop `nora-media-apps-backend.service`, switch the `current`
symlink, then restart that service and verify authentication/paused queue. Keep
the previous release for rollback; PostgreSQL and media are not rolled back with
application code. The legacy `activate-laptop.sh` is not used for this topology.

Refresh provider models/prices separately through the explicit catalog-refresh
operation after queued/running work is finished or cancelled. Refresh is blocked
while unfinished jobs exist, so their endpoint settings are not silently replaced. A catalog update must not generate media, select another model, or
change a queued job. A listed model is not proof of account access or successful
paid generation. Costs computed from token rates are not provider invoices.

## Hosting

The frontend, authentication, backend, queue, media and cloud/H3 control run on
apps; PostgreSQL runs on databases. Only local Qwen needs the workstation online.
The workstation establishes an outgoing private SSH reverse tunnel to apps. The
server sends authenticated Qwen-only HTTP jobs through it to the local executor,
which submits the maintained workflow to loopback ComfyUI. No public ComfyUI
endpoint, generic remote shell or browser-side provider key is required.

Workstation reboot/autostart and service checks are documented in
[the deployment manual](../nora/deploy/README.md#workstation-reboot-and-local-execution).

## Verified deployment

The private studio is available at https://media.bp-flow.com. Release and
verification records are in [the deployment ledger](../deploy/pending-prod.md);
[data flow](diagrams/data-flow.md), [queue schema](diagrams/schema.md) and
[user journey](diagrams/user-journey.md) describe the integration boundaries.

## Reference library

Open [/references/](https://media.bp-flow.com/references/) with the same login.
Browse/download originals and export an ordered photo set as a PNG sheet or ZIP.
No model, prompt, seed, queue or workflow controls exist in this library. See
[reference library manual](../nora/references/README.md). Source originals and
provenance stay in private versioned apps storage outside Git.

The **LoRA** library tab holds named, freely filled photo/video sets for future
dataset curation. It supports original uploads, video playback/download and mixed
ZIP exports, without training or inference. See the reference library manual for
formats and limits. Video validation needs `ffprobe`; on apps, prepare the rootless
Ubuntu dependency bundle with `nora/deploy/provision-apps-ffprobe.sh` before backend
activation. This configures nonsecret `NORA_FFPROBE_BIN` in private `backend.env`
and saves package provenance under runtime/tools/media-probe-v1. It does not
install system packages or restart the backend. Existing releases can use the
same runtime tool; source updates do not reinstall it.

The studio header keeps only the hamburger and studio tabs on desktop/mobile.
Open **Меню и очередь** for the brand link, reference library, catalog refresh,
logout and the existing queue controls/history.


## Attaching generation references

The composer commits file uploads immediately and displays attached thumbnails as
Image1/Image2 or separate Start/End/Image/Video/Audio roles supported by the selected
model. Reorder/remove files in that row; there is no hidden picker confirmation.
Submission waits for upload completion. An explicit image placeholder without its
corresponding attachment is rejected rather than silently generating from text.
Prompt wording, quality defaults and requested dimensions are not rewritten.
Price remains visible in one compact row; detailed tariffs, queue/budget behavior
and native guide caveats are under the closed “Детали” section.

For OpenRouter video models, first/last-frame controls follow each model's public
`supported_frame_images` catalog entry. Veo 3.1, Fast and Lite currently expose
both frames; some other models expose only the first. These are frame constraints,
not interchangeable subject/style references. “Generate audio” controls generated
sound, not an uploaded audio reference. The current OpenRouter adapter does not
expose arbitrary image/video/audio references or editing/continuation endpoints.
Transport and validation are tested with mocked requests; this does not certify
paid generation quality or account access for every listed model.

The reference library additionally supports named sets with empty view slots and
original uploads; these actions do not run any model. See its manual for storage
and replacement behavior. Model generation still happens only in Image/Video Studio.

### Collapsing the prompt composer

Photo and Video Studio each have a **Свернуть** control. It hides the composer body
without unmounting it; text, attached files, model parameters and in-progress uploads
remain intact. The compact bar shows the model, reference count and prompt excerpt.
Use **Развернуть** to restore the same draft on desktop or mobile; both controls work
with keyboard Enter or Space and expose their expanded state to screen readers.
Switching generation models preserves compatible references. References unsupported
by the new model are excluded with a visible notice; Veo retains Start/End frames,
while a start-only model retains only Start.

## Qualifying a newly selected model

A catalog entry establishes advertised endpoint capabilities, not successful studio
generation. Before relying on a new model, verify its provider-specific modes:

1. Check the current endpoint schema, reference roles/counts, parameter ranges and
   pricing. Native model features are exposed only when this endpoint supports them.
2. Use mocked submission tests to verify exact prompt, ordered references, file
   contents, dimensions, seed handling and the absence of unsupported parameters.
3. With an explicitly authorized generation, exercise each mode that will actually
   be used (for example prompt-only, first frame, first+last frame). Check the saved
   submission and final media for reference fidelity, framing, motion/audio and
   usable output; compare quoted and reported costs. Do not infer success of untested
   reference modes from a text-only result.
4. Keep model/version/provider and tested modes in the review evidence. Retest the
   affected modes when the endpoint, model version or studio adapter changes.

Paid checks are not automatic. A fixed seed helps repeat an experiment where the
provider supports it, but does not guarantee identical output across model updates.

### Random seeds and the queue sidebar

Models that support seeds show a compact **Seed · случайный** control by default.
Each new job asks the server for a fresh random seed, which is stored with that job.
Turn off **Новый seed для каждого задания** to enter a fixed seed; zero is a valid
fixed value. Saved manual seeds remain fixed, and retrying a job retains its saved
seed. Models without seed support, including the current OpenAI image models, do
not show a seed control or claim reproducibility from a seed.

Open the queue with the hamburger, job count and status in the header. The sidebar
contains start/pause, job history, cancel/retry and result downloads. Escape, the
close button or a desktop backdrop click closes it and returns focus to the trigger;
keyboard focus stays within the open sidebar. Supported models show their stored
actual seed on the job card. The same sidebar works on mobile without a separate
full-width queue bar.

### Parameter window

In Image/Video Studio, **Параметры** opens a screen-fitting modal with its own
scrolling field area and reachable **Применить / Отменить** buttons. Edits stay in
a draft until Apply; Cancel, Escape, close and backdrop discard them. Applying
updates the supported parameters together without changing the prompt, references
or separately selected seed. Closing returns focus to the parameter button.
