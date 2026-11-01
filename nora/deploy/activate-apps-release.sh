#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 1 && "$1" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Usage: activate-apps-release.sh REVIEWED_RELEASE_ID' >&2; exit 2; }
release_id="$1"
project_root="${NORA_PROJECT_ROOT:-$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().parents[4])' "$0")}"
script_dir="$(dirname "$(readlink -f "$0")")"
receipt="$project_root/work/media-studio-deploy/candidate-$release_id.json"
receipt_valid() {
python3 - "$receipt" "$project_root/work/media-studio-deploy/releases/$release_id" "$release_id" <<'PYGATE'
import hashlib,json,sys
from pathlib import Path
try:
 receipt=json.loads(Path(sys.argv[1]).read_text());bundle=Path(sys.argv[2]);release=sys.argv[3]
 assert receipt.get('passed') is True and receipt.get('release')==release
 assert receipt.get('manifest_sha256')==hashlib.sha256((bundle/'release.json').read_bytes()).hexdigest()
 assert receipt.get('proxy_sha256')==hashlib.sha256((bundle/'Apps.Caddyfile').read_bytes()).hexdigest()
except (OSError,ValueError,AssertionError):raise SystemExit(1)
PYGATE
}
if ! receipt_valid; then
  echo 'No matching successful private candidate receipt; running required negative gate first'
  "$script_dir/verify-private-candidate.sh" "$release_id"
  receipt_valid || { echo 'Private candidate receipt verification failed' >&2; exit 1; }
fi
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
docker compose -p nora-media -f "$release/compose.yml" config --quiet </dev/null
# Validate the actual mounted files with exactly the service identity/capabilities.
# Docker must not consume the remaining SSH-streamed shell commands on stdin.
docker compose -p nora-media -f "$release/compose.yml" run --rm --no-deps --entrypoint caddy frontend validate --config /etc/caddy/Caddyfile --adapter caddyfile </dev/null
docker compose -p nora-media -f "$release/compose.yml" up -d </dev/null
printf 'Apps frontend activated from reviewed release %s; gateway unchanged.\n' "$1"
REMOTE
