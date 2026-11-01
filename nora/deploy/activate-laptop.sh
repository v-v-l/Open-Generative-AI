#!/usr/bin/env bash
set -Eeuo pipefail
project_root="${NORA_PROJECT_ROOT:-$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().parents[4])' "$0")}"
export NORA_PROJECT_ROOT="$project_root"
cd "$project_root"
[[ -f apps/open-generative-ai/nora/dist/index.html ]] || { echo 'Selected frontend build missing' >&2; exit 1; }
[[ -f work/generation-studio/public-auth.env ]] || { echo 'Public authentication environment missing' >&2; exit 1; }
# Inspect only queue safety fields. Never print credentials or session cookies.
check_queue() {
python3 - "$project_root" <<'PY'
import json,sys,urllib.request,urllib.error
from pathlib import Path
root=Path(sys.argv[1]);base='http://127.0.0.1:36440'
def request(path,body=None,cookie=None,public=False):
 headers={'Content-Type':'application/json'}
 if public:headers.update(Host='media.bp-flow.com',Origin='https://media.bp-flow.com')
 if cookie:headers['Cookie']=cookie
 return urllib.request.urlopen(urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=15)
try:
 with request('/api/state') as r:state=json.load(r)
except urllib.error.HTTPError as error:
 if error.code not in (401,403):raise
 error.close()
 text=(root/'work/media-studio-login.txt').read_text()
 password=next(line.partition(': ')[2] for line in text.splitlines() if line.startswith('Password: '))
 with request('/api/auth/login',{'password':password},public=True) as r:cookie=r.headers['Set-Cookie'].split(';')[0];r.read()
 with request('/api/state',cookie=cookie,public=True) as r:state=json.load(r)
if not state['queue_paused'] or state['active_job_id'] or any(j['status']=='running' for j in state['jobs']):
 raise SystemExit('Refusing activation: canonical queue must be paused and idle')
print('Canonical queue is paused and idle')
PY
}
check_queue
if systemctl --user is-active --quiet nora-media-backend.service; then
  echo 'Public backend is already active; refusing an implicit restart'
  exit 0
fi
systemctl --user is-active --quiet nora-generation-studio.service || { echo 'Expected original backend unit is not active; inspect port ownership manually' >&2; exit 1; }
# Save startup intent before installing or enabling persistent public units.
old_enablement="$(systemctl --user is-enabled nora-generation-studio.service 2>/dev/null || true)"
backend_enablement="$(systemctl --user is-enabled nora-media-backend.service 2>/dev/null || true)"
bridge_enablement="$(systemctl --user is-enabled nora-media-bridge.service 2>/dev/null || true)"
for state in "$backend_enablement" "$bridge_enablement"; do
  [[ "$state" != masked* ]] || { echo 'Refusing to replace a masked backend/bridge unit' >&2; exit 1; }
done
restore_enablement() {
  local unit="$1" previous="$2"
  systemctl --user disable "$unit" >/dev/null 2>&1 || true
  case "$previous" in
    enabled) systemctl --user enable "$unit" >/dev/null ;;
    enabled-runtime) systemctl --user enable --runtime "$unit" >/dev/null ;;
  esac
}
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
install -m 644 apps/open-generative-ai/nora/deploy/nora-media-backend.service "$unit_dir/"
install -m 644 apps/open-generative-ai/nora/deploy/nora-media-bridge.service "$unit_dir/"
systemctl --user daemon-reload
rollback() {
  systemctl --user stop nora-media-bridge.service nora-media-backend.service || true
  restore_enablement nora-media-backend.service "$backend_enablement" || true
  restore_enablement nora-media-bridge.service "$bridge_enablement" || true
  case "$old_enablement" in
    enabled) systemctl --user enable nora-generation-studio.service >/dev/null || true ;;
    enabled-runtime) systemctl --user enable --runtime nora-generation-studio.service >/dev/null || true ;;
  esac
  if ! systemctl --user start nora-generation-studio.service; then
    # The original unit was verified as a collected systemd-run transient.
    # Recreate that same on-demand launch without adding reboot enablement.
    if [[ "$old_enablement" == transient ]]; then
      systemd-run --user --unit=nora-generation-studio --collect \
        --property="WorkingDirectory=$project_root" --setenv="NORA_PROJECT_ROOT=$project_root" \
        /usr/bin/python -u "$project_root/scripts/generation_studio/server.py" --port 36440 || true
    fi
  fi
  echo 'Activation failed; original backend and startup intent restoration requested. Inspect services before retrying.' >&2
}
trap rollback ERR
systemctl --user stop nora-generation-studio.service
systemctl --user start nora-media-backend.service
for attempt in {1..20}; do
  if curl --silent --fail -H 'Host: media.bp-flow.com' http://127.0.0.1:36440/api/auth >/dev/null; then break; fi
  sleep 1
done
check_queue
systemctl --user start nora-media-bridge.service
# Only a successful handover changes reboot behavior.
case "$old_enablement" in
  enabled) systemctl --user disable nora-generation-studio.service ;;
  enabled-runtime) systemctl --user disable --runtime nora-generation-studio.service ;;
  *) echo 'Original transient/static unit has no persistent startup link to disable' ;;
esac
systemctl --user enable nora-media-backend.service nora-media-bridge.service
trap - ERR
echo 'Public backend and private tunnel started; no GPU/model jobs submitted'
