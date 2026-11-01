#!/usr/bin/env bash
set -euo pipefail
# Upload a reviewed local bundle only. Activation and gateway changes are separate.
if [[ $# -ne 1 ]]; then echo 'Usage: stage-release.sh RELEASE_ID' >&2; exit 2; fi
release_id="$1"
[[ "$release_id" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Invalid release ID' >&2; exit 1; }
project_root="${NORA_PROJECT_ROOT:-$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().parents[4])' "$0")}"
bundle="$project_root/work/media-studio-deploy/releases/$release_id"
[[ -f "$bundle/release.json" && -f "$bundle/dist/index.html" ]] || { echo 'Prepared release not found' >&2; exit 1; }
# Paths below are fixed; no password, API key, model weight or private key is copied.
tar -C "$bundle" -cf - . | ssh \
  -i "${MEDIA_STUDIO_SSH_KEY:-/home/victor/.ssh/bbright_codex_ed25519}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  "${MEDIA_STUDIO_SSH_TARGET:-victor@apps}" \
  "set -eu; umask 077; mkdir -p /home/victor/apps/media-studio/releases; chmod 700 /home/victor/apps/media-studio/releases; test ! -e /home/victor/apps/media-studio/releases/$release_id; mkdir /home/victor/apps/media-studio/releases/$release_id; tar -xpf - -C /home/victor/apps/media-studio/releases/$release_id; chmod 700 /home/victor/apps/media-studio/releases/$release_id"
printf 'Staged release %s on apps; no services started and gateway unchanged.\n' "$release_id"
