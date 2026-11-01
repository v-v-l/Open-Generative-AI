#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 1 && $# -le 2 && "$1" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Usage: verify-private-candidate.sh REVIEWED_RELEASE_ID [PRIVATE_PORT]' >&2; exit 2; }
release_id="$1"
port="${2:-36446}"
[[ "$port" =~ ^[0-9]+$ && "$port" -ge 1024 && "$port" -le 65535 && "$port" != 36443 && "$port" != 36442 ]] || { echo 'Invalid candidate port' >&2; exit 2; }
project_root="${NORA_PROJECT_ROOT:-$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().parents[4])' "$0")}"
key="${MEDIA_STUDIO_SSH_KEY:-/home/victor/.ssh/bbright_codex_ed25519}"
apps="${MEDIA_STUDIO_SSH_TARGET:-victor@apps}"
gateway="${MEDIA_STUDIO_GATEWAY_TARGET:-root@gateway}"
run_token="$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
container="nora-media-candidate-$run_token"
container_id=""
ssh_options=(-i "$key" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes)
cleanup() {
  if [[ "$container_id" =~ ^[0-9a-f]{64}$ ]]; then
    ssh "${ssh_options[@]}" "$apps" docker rm -f "$container_id" </dev/null >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
metadata="$(ssh "${ssh_options[@]}" "$apps" python3 - "$release_id" "$port" "$run_token" <<'PY'
import hashlib,json,os,re,sys
from pathlib import Path
release_id,port,run_token=sys.argv[1:];release=Path('/home/victor/apps/media-studio/releases')/release_id
manifest=json.loads((release/'release.json').read_text())
for item in manifest['files']:
 p=(release/item['path']).resolve()
 if not p.is_relative_to(release.resolve()) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise SystemExit('Release checksum mismatch')
original=(release/'Apps.Caddyfile').read_text()
if original.count(':36443 {')!=1:raise SystemExit('Expected exactly one active listener declaration')
candidate=release.parent.parent/'candidates'/(release_id+'-'+port+'-'+run_token)
candidate.mkdir(parents=True,exist_ok=False);candidate.chmod(0o700)
config=candidate/'Apps.Caddyfile';config.write_text(original.replace(':36443 {',':'+port+' {',1));config.chmod(0o644)
if config.read_text().replace(':'+port+' {',':36443 {',1)!=original:raise SystemExit('Candidate changes more than its listener port')
override={'services':{'frontend':{'volumes':[str(config)+':/etc/caddy/Caddyfile:ro']}}}
(candidate/'override.json').write_text(json.dumps(override));(candidate/'override.json').chmod(0o600)
index=(release/'dist/index.html').read_text();match=re.search(r'<script[^>]+src="([^"]+)"',index)
if not match or not re.fullmatch(r'/assets/[A-Za-z0-9._/-]+',match[1]) or '..' in match[1]:raise SystemExit('Could not identify a real bundled JS asset')
print(json.dumps({'asset':match[1],'manifest_sha256':hashlib.sha256((release/'release.json').read_bytes()).hexdigest(),'proxy_sha256':hashlib.sha256((release/'Apps.Caddyfile').read_bytes()).hexdigest()}))
PY
)"
asset="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["asset"])' "$metadata")"
container_id="$(ssh "${ssh_options[@]}" "$apps" bash -s -- "$release_id" "$port" "$container" "$run_token" <<'REMOTE'
set -euo pipefail
release="/home/victor/apps/media-studio/releases/$1"
override="/home/victor/apps/media-studio/candidates/$1-$2-$4/override.json"
project="nora-media-candidate-$4"
docker compose -p "$project" -f "$release/compose.yml" -f "$override" config --quiet </dev/null
docker compose -p "$project" -f "$release/compose.yml" -f "$override" run --rm --no-deps --entrypoint caddy frontend validate --config /etc/caddy/Caddyfile --adapter caddyfile </dev/null >&2
docker compose -p "$project" -f "$release/compose.yml" -f "$override" run --rm -d --no-deps --name "$3" frontend </dev/null
REMOTE
)"
[[ "$container_id" =~ ^[0-9a-f]{64}$ ]] || { echo 'Candidate did not return a verifiable owned container ID' >&2; exit 1; }
checks="$(ssh "${ssh_options[@]}" "$gateway" python3 - "$port" "$asset" <<'PY'
import json,sys,time,urllib.request,urllib.error
port,asset=sys.argv[1:];base='http://192.168.100.70:'+port
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args):return None
client=urllib.request.build_opener(NoRedirect)
def get(path,host='media.bp-flow.com'):
 try:
  with client.open(urllib.request.Request(base+path,headers={'Host':host}),timeout=5) as response:return response.status,response.headers,response.read()
 except urllib.error.HTTPError as error:
  status,headers,body=error.code,error.headers,error.read();error.close();return status,headers,body
for attempt in range(12):
 try:
  status,headers,body=get('/api/auth')
  if status!=200 or json.loads(body)!={'authenticated':False,'required':True}:raise SystemExit('Candidate auth readiness failed')
  break
 except urllib.error.URLError:
  if attempt==11:raise
  time.sleep(1)
checks={}
for path in ['/api/state','/media/'+'0'*32,'/references/api/catalog','/references/file/F01','/references/app.js']:
 status,_,_=get(path)
 if status!=401:raise SystemExit('Anonymous API/media privacy gate failed')
 checks[path]=status
for path in ['/',asset]:
 status,headers,_=get(path)
 if status!=302 or headers.get('Location')!='/login':raise SystemExit('Anonymous HTML/JS privacy gate failed')
 checks[path]={'status':status,'location':headers.get('Location')}
for path in ['/api/auth','/']:
 status,_,_=get(path,host='wrong.example')
 if status!=403:raise SystemExit('Wrong-Host gateway gate failed')
 checks['wrong_host '+path]=status
print(json.dumps(checks))
PY
)"
ssh "${ssh_options[@]}" "$apps" python3 - "$port" <<'PY'
import sys,urllib.request,urllib.error
base='http://192.168.100.70:'+sys.argv[1]
for path in ['/api/auth','/']:
 try:urllib.request.urlopen(urllib.request.Request(base+path,headers={'Host':'media.bp-flow.com'}),timeout=5)
 except urllib.error.HTTPError as error:
  if error.code!=403:raise SystemExit('Wrong-peer gate failed')
  error.close()
 else:raise SystemExit('Wrong-peer unexpectedly accessed candidate')
print('Apps-local wrong-peer requests rejected with 403')
PY
mkdir -p "$project_root/work/media-studio-deploy"
python3 - "$project_root/work/media-studio-deploy/candidate-$release_id.json" "$release_id" "$port" "$metadata" "$checks" <<'PYRECEIPT'
import datetime,json,sys
from pathlib import Path
path,release,port,metadata,checks=sys.argv[1:];data=json.loads(metadata)
data.update({'passed':True,'release':release,'candidate_port':int(port),'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'gateway_checks':json.loads(checks),'wrong_peer_api':403,'wrong_peer_html':403})
Path(path).write_text(json.dumps(data,indent=2)+'\n')
PYRECEIPT
printf 'Private candidate negative runtime gate PASS for %s; only listener port differed.\n' "$release_id"
