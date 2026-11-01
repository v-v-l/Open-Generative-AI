#!/usr/bin/env bash
set -euo pipefail
# Rootless Ubuntu dependency preparation; never installs system packages or restarts services.
ssh -i "${MEDIA_STUDIO_SSH_KEY:-/home/victor/.ssh/bbright_codex_ed25519}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  "${MEDIA_STUDIO_SSH_TARGET:-victor@apps}" bash -s <<'REMOTE'
set -euo pipefail
runtime=/home/victor/apps/media-studio/runtime
probe_root="$runtime/tools/media-probe-v1"
mkdir -p "$probe_root/lists/partial" "$probe_root/archives/partial" "$probe_root/root" "$runtime/bin"
apt_options=(-o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources -o Dir::Etc::sourceparts=- -o "Dir::State::Lists=$probe_root/lists" -o "Dir::Cache=$probe_root/cache" -o "Dir::Cache::Archives=$probe_root/archives" -o Debug::NoLocking=1)
if [[ ! -x "$probe_root/root/usr/bin/ffprobe" ]]; then
  apt-get "${apt_options[@]}" update > "$probe_root/update.log" 2>&1
  apt-get "${apt_options[@]}" --download-only --no-install-recommends -y install ffmpeg > "$probe_root/download.log" 2>&1
  for package in "$probe_root"/archives/*.deb; do dpkg-deb --extract "$package" "$probe_root/root"; done
fi
probe_libs="$probe_root/root/usr/lib/x86_64-linux-gnu:$probe_root/root/lib/x86_64-linux-gnu:$probe_root/root/usr/lib/x86_64-linux-gnu/pulseaudio:$probe_root/root/usr/lib/x86_64-linux-gnu/blas:$probe_root/root/usr/lib/x86_64-linux-gnu/lapack"
LD_LIBRARY_PATH="$probe_libs" "$probe_root/root/usr/bin/ffprobe" -version > "$probe_root/version.txt"
python3 - "$runtime" "$probe_root" "$probe_libs" <<'PY'
import hashlib,json,os,shlex,subprocess,sys
from pathlib import Path
runtime,root=map(Path,sys.argv[1:3]);libs=sys.argv[3]
packages=[]
for path in sorted((root/'archives').glob('*.deb')):
 info=subprocess.check_output(['dpkg-deb','--show','--showformat=${Package} ${Version}',str(path)],text=True)
 packages.append({'package':info,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(root/'provenance.json').write_text(json.dumps({'source':'Ubuntu signed APT repositories; download-only, rootless extraction','packages':packages},indent=2)+'\n')
wrapper=runtime/'bin/nora-ffprobe';temporary=wrapper.with_suffix('.next')
temporary.write_text('#!/bin/sh\nexport LD_LIBRARY_PATH='+shlex.quote(libs)+'\nexec '+shlex.quote(str(root/'root/usr/bin/ffprobe'))+' "$@"\n')
temporary.chmod(0o700);os.replace(temporary,wrapper)
env=runtime/'backend.env';lines=[line for line in env.read_text().splitlines() if not line.startswith('NORA_FFPROBE_BIN=')]
lines.append('NORA_FFPROBE_BIN='+str(wrapper))
temporary=env.with_suffix('.env.next');temporary.write_text('\n'.join(lines)+'\n');temporary.chmod(0o600);os.replace(temporary,env)
print('ffprobe wrapper configured; dependency provenance saved; backend restart remains separate')
PY
"$runtime/bin/nora-ffprobe" -version | head -1
REMOTE
