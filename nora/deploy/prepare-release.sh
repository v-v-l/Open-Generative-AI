#!/usr/bin/env bash
set -euo pipefail
# Prepare an immutable local bundle. This command never connects to a server.
project_root="${NORA_PROJECT_ROOT:-$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().parents[4])' "$0")}"
script_dir="$(dirname "$(readlink -f "$0")")"
frontend_dist="${MEDIA_STUDIO_FRONTEND_DIST:-$(dirname "$script_dir")/dist}"
release_id="${MEDIA_STUDIO_RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "$release_id" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Invalid release ID' >&2; exit 1; }
[[ -f "$frontend_dist/index.html" ]] || { echo "Build the selected frontend first: $frontend_dist/index.html is missing" >&2; exit 1; }
bundle="$project_root/work/media-studio-deploy/releases/$release_id"
[[ ! -e "$bundle" ]] || { echo 'Release already exists; choose a new release ID' >&2; exit 1; }
mkdir -p "$bundle/dist"
cp -a "$frontend_dist/." "$bundle/dist/"
cp "$script_dir/Apps.Caddyfile" "$bundle/"
cp "$script_dir/compose.yml" "$bundle/"
python3 - "$bundle" "$release_id" "$project_root" <<'PY'
import hashlib,json,sys,subprocess
from pathlib import Path
root=Path(sys.argv[1]);files=[]
source=Path(sys.argv[3])/'apps/open-generative-ai'
revision=subprocess.run(['git','-C',str(source),'rev-parse','HEAD'],capture_output=True,text=True)
source_revision=revision.stdout.strip() if revision.returncode == 0 else None
for p in sorted(root.rglob('*')):
 if p.is_symlink(): raise SystemExit('Symlinks are not allowed in deployment bundles')
 if p.is_file():files.append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
(root/'release.json').write_text(json.dumps({'release':sys.argv[2],'source_revision':source_revision,'frontend':'Anil-matcha/Open-Generative-AI + Nora overlay','files':files},indent=2)+'\n')
PY
printf 'Prepared local bundle: %s\n' "$bundle"
printf 'No remote files or services were changed.\n'
