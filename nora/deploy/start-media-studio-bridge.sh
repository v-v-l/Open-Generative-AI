#!/usr/bin/env bash
set -euo pipefail
# This forwards only the authenticated application backend, never ComfyUI or SSH.
exec ssh -N -T \
  -i "${MEDIA_STUDIO_SSH_KEY:-/home/victor/.ssh/bbright_codex_ed25519}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -R "127.0.0.1:${MEDIA_STUDIO_REMOTE_PORT:-36442}:127.0.0.1:${MEDIA_STUDIO_LOCAL_PORT:-36440}" \
  "${MEDIA_STUDIO_SSH_TARGET:-victor@apps}"
