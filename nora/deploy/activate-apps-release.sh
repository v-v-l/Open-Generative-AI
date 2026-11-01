#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 1 && "$1" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Usage: activate-apps-release.sh REVIEWED_RELEASE_ID' >&2; exit 2; }
release_id="$1"
ssh -i "${MEDIA_STUDIO_SSH_KEY:-/home/victor/.ssh/bbright_codex_ed25519}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  "${MEDIA_STUDIO_SSH_TARGET:-victor@apps}" bash -s -- "$release_id" <<'REMOTE'
set -euo pipefail
release="/home/victor/apps/media-studio/releases/$1"
[[ -f "$release/release.json" && -f "$release/dist/index.html" ]] || { echo 'Reviewed release not staged' >&2; exit 1; }
python3 - "$release" <<'PY'
import hashlib,json,sys,urllib.request,urllib.error
from pathlib import Path
root=Path(sys.argv[1]).resolve();manifest=json.loads((root/'release.json').read_text())
for item in manifest['files']:
 p=(root/item['path']).resolve()
 if not p.is_relative_to(root) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise SystemExit('Release checksum mismatch')
req=urllib.request.Request('http://127.0.0.1:36442/api/auth',headers={'Host':'media.bp-flow.com'})
with urllib.request.urlopen(req,timeout=15) as r:auth=json.load(r)
if auth != {'authenticated':False,'required':True}:raise SystemExit('Tunnel backend does not require public authentication')
# Apps-local callers can forge any Host; the public service must reject loopback.
req=urllib.request.Request('http://127.0.0.1:36442/api/state',headers={'Host':'127.0.0.1:36440'})
try:urllib.request.urlopen(req,timeout=15)
except urllib.error.HTTPError as e:
 if e.code!=403:raise SystemExit('Unexpected tunnel Host guard response')
 e.close()
else:raise SystemExit('Unsafe public backend: loopback Host bypass remains enabled')
print('Release checksum and tunnel authentication guards verified')
PY
docker compose -p nora-media -f "$release/compose.yml" config --quiet
docker compose -p nora-media -f "$release/compose.yml" up -d
printf 'Apps frontend activated from reviewed release %s; gateway unchanged.\n' "$1"
REMOTE
