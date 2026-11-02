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

## Requested OpenRouter video models

`heygen/heygen-video-1` supports prompt-only or one first frame, catalog durations
5–15 seconds, 480p/768p/2K and advertised aspect ratios. Seed is supported; no
generated-audio toggle or additional reference roles are inferred from its prose.
`minimax/hailuo-3-max` supports prompt-only or first/last frames, 5–15 seconds,
480p/768p; no seed or generated-audio control is advertised.

`heygen/avatar-iv` uses the explicit `heygen_avatar_script` adapter. One photograph
becomes an `input_references` image data URL; the literal prompt is spoken script.
`voice_id` is required, while `motion_prompt`, `expressiveness`, `fit` and
`remove_background` are typed, allowlisted settings sent under
`provider.options.heygen.parameters`. Only settings still advertised by the live
catalog are retained. There is no duration selector, seed or audio toggle.
Uploaded audio, caption/background objects and voice-settings objects are not
exposed by this first adapter. OpenRouter inline-audio transport has not been
verified; private `/media/` URLs are never sent as remotely accessible files.

`refresh_requested_videos()` performs one public catalog GET, merges only these
three model IDs atomically and preserves unrelated pinned image/provider settings.
It fails without writes if any requested model/capability is missing. Use it only
under the deployment's paused/idle preflight; the regular full catalog refresh also
recognizes Avatar IV. No POST or inference occurs during discovery.

H3 Max and text-only HeyGen Video quotes use catalog rates times duration. HeyGen
with a frame stays unknown until usage because reference-price SKUs do not establish
one unambiguous formula. Avatar IV exposes its per-second rate with unknown total
until speech duration is known. Promotions are never assumed; provider `usage.cost`
is authoritative. The model snapshots in `backend_tests/fixtures/` are public
metadata, not paid verification or an assertion of account access.

Contract sources: [OpenRouter video API](https://openrouter.ai/docs/guides/overview/multimodal/video-generation),
[official OpenRouter video skill](https://github.com/OpenRouterTeam/skills/blob/main/skills/openrouter-video/SKILL.md),
[Avatar IV model](https://openrouter.ai/heygen/avatar-iv),
[HeyGen image-to-video](https://developers.heygen.com/image-to-video).
