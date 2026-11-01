#!/usr/bin/env bash
set -euo pipefail
# A failed preflight must end this single SSH transaction before any restart.
[[ $# -eq 1 && "$1" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Usage: activate-apps-backend.sh STAGED_RELEASE_ID' >&2; exit 2; }
ssh -i "${MEDIA_STUDIO_SSH_KEY:-/home/victor/.ssh/bbright_codex_ed25519}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  "${MEDIA_STUDIO_SSH_TARGET:-victor@apps}" \
  /home/victor/apps/media-studio/runtime/venv/bin/python - "$1" <<'PY'
import hashlib,json,os,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
import psycopg
base=Path('/home/victor/apps/media-studio');release=base/'releases'/sys.argv[1]
manifest=json.loads((release/'release.json').read_text())
for entry in manifest['files']:
 p=(release/entry['path']).resolve()
 if not p.is_relative_to(release.resolve()) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:
  raise SystemExit('Release checksum mismatch; nothing changed')
if not (release/'backend/server.py').is_file():raise SystemExit('Backend source missing; nothing changed')
lines=(base/'runtime/backend.env').read_text().splitlines()
url=next((line.split('=',1)[1] for line in lines if line.startswith('DATABASE_URL=')),None)
if not url:raise SystemExit('Database configuration missing; nothing changed')
try:
 with psycopg.connect(url,connect_timeout=8) as db:
  paused=db.execute("SELECT value FROM settings WHERE key='queue_paused'").fetchone()
  unfinished=db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('running','queued')").fetchone()[0]
except Exception:raise SystemExit('Database preflight unavailable; nothing changed') from None
if not paused or paused[0]!='true' or unfinished:
 raise SystemExit('Pause and drain the queue before deployment; nothing changed')
current=base/'current';previous=os.readlink(current)
if not current.resolve().is_relative_to(base/'releases'):raise SystemExit('Unexpected current release; nothing changed')
def select(target):
 temporary=base/'current.deploy-next'
 if temporary.exists() or temporary.is_symlink():raise RuntimeError('Another release switch may be in progress')
 temporary.symlink_to(target);temporary.replace(current)
def check_ready():
 for attempt in range(30):
  try:
   req=urllib.request.Request('http://127.0.0.1:36442/api/auth',headers={'Host':'media.bp-flow.com'})
   with urllib.request.urlopen(req,timeout=2) as response:
    if json.load(response)=={'authenticated':False,'required':True}:return
  except (OSError,ValueError):pass
  time.sleep(.2)
 raise RuntimeError('Backend authentication readiness failed')
try:
 select('releases/'+sys.argv[1])
 subprocess.run(['systemctl','--user','restart','nora-media-apps-backend.service'],check=True)
 check_ready()
except BaseException:
 try:
  select(previous);subprocess.run(['systemctl','--user','restart','nora-media-apps-backend.service'],check=True)
 except BaseException:raise SystemExit('Activation failed and rollback needs operator attention') from None
 raise SystemExit('Activation failed; previous source restored. Check service status.') from None
print('Apps backend activated with paused queue; frontend/proxy activation is separate')
PY
