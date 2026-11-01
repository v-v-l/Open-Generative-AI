#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 2 && "$1" == '--apply' && "$2" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Usage: activate-gateway.sh --apply REVIEWED_RELEASE_ID' >&2; exit 2; }
release_id="$2"
script_dir="$(dirname "$(readlink -f "$0")")"
fragment="$(base64 -w0 "$script_dir/Gateway.Caddyfile.fragment")"
ssh -i "${MEDIA_STUDIO_SSH_KEY:-/home/victor/.ssh/bbright_codex_ed25519}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  "${MEDIA_STUDIO_GATEWAY_TARGET:-root@gateway}" bash -s -- "$release_id" "$fragment" <<'REMOTE'
set -euo pipefail
umask 077
release_id="$1"
fragment="$2"
exec 9>/run/lock/nora-media-caddy.lock
flock -n 9 || { echo 'Another media gateway update owns the lock' >&2; exit 1; }
python3 - <<'PY'
import urllib.request,urllib.error,json
base='http://192.168.100.70:36443'
with urllib.request.urlopen(urllib.request.Request(base+'/api/auth',headers={'Host':'media.bp-flow.com'}),timeout=15) as r:auth=json.load(r)
if auth != {'authenticated':False,'required':True}:raise SystemExit('Apps auth readiness check failed')
try:urllib.request.urlopen(urllib.request.Request(base+'/api/state',headers={'Host':'media.bp-flow.com'}),timeout=15)
except urllib.error.HTTPError as e:
 if e.code!=401:raise SystemExit('Apps API is not protected as expected')
 e.close()
else:raise SystemExit('Apps API unexpectedly allows anonymous access')
PY
if grep -Eq '^[[:space:]]*media[.]bp-flow[.]com([[:space:]]|[{])' /etc/caddy/Caddyfile; then
  echo 'Media site already exists; inspect it instead of blindly appending another block' >&2
  exit 1
fi
original_hash="$(sha256sum /etc/caddy/Caddyfile | cut -d' ' -f1)"
backup_dir=/etc/caddy/media-studio-backups
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
backup="$backup_dir/Caddyfile.before-$release_id"
[[ ! -e "$backup" ]] || { echo 'Backup ID already exists' >&2; exit 1; }
cp -p /etc/caddy/Caddyfile "$backup"
candidate="$(mktemp /etc/caddy/.Caddyfile.media.XXXXXX)"
trap 'rm -f "$candidate"' EXIT
cp -p /etc/caddy/Caddyfile "$candidate"
printf '\n' >> "$candidate"
printf '%s' "$fragment" | base64 -d >> "$candidate"
validation_log="/tmp/nora-media-caddy-validation-$release_id.log"
if ! python3 - "$candidate" "$validation_log" <<'PYVALIDATE'
import os,re,shlex,subprocess,sys
from pathlib import Path
env=os.environ.copy()
# Match the existing caddy.service EnvironmentFile without shell evaluation.
for line in Path('/etc/caddy/cloudflare.env').read_text().splitlines():
 line=line.strip()
 if not line or line.startswith('#'):continue
 name,separator,value=line.partition('=')
 if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name):raise SystemExit('Unsupported gateway environment format')
 parts=shlex.split(value,comments=False,posix=True)
 if len(parts)!=1:raise SystemExit('Unsupported gateway environment value format')
 env[name]=parts[0]
with open(sys.argv[2],'w') as log:
 result=subprocess.run(['caddy','validate','--config',sys.argv[1],'--adapter','caddyfile'],env=env,stdout=log,stderr=log)
raise SystemExit(result.returncode)
PYVALIDATE
then
  echo "Candidate failed validation; live gateway unchanged. Inspect $validation_log on gateway." >&2
  exit 1
fi
[[ "$(sha256sum /etc/caddy/Caddyfile | cut -d' ' -f1)" == "$original_hash" ]] || { echo 'Gateway configuration changed during validation; aborting' >&2; exit 1; }
mv "$candidate" /etc/caddy/Caddyfile
if ! systemctl reload caddy; then
  rollback="$(mktemp /etc/caddy/.Caddyfile.rollback.XXXXXX)"
  cp -p "$backup" "$rollback"
  mv "$rollback" /etc/caddy/Caddyfile
  systemctl reload caddy || true
  echo 'Gateway reload failed; original configuration restored' >&2
  exit 1
fi
printf 'Gateway media site activated; other sites preserved. Backup: %s\n' "$backup"
REMOTE
