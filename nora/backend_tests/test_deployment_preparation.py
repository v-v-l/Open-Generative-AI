"""Deployment preparation is local, portable and contains no runtime credentials."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

DEPLOY=Path(__file__).resolve().parents[1]/'deploy'


class DeploymentPreparation(unittest.TestCase):
    def test_activation_scripts_have_valid_shell_syntax(self):
        scripts=sorted(DEPLOY.glob('*.sh'))
        self.assertGreaterEqual(len(scripts),6)
        for script in scripts:
            subprocess.run(['bash','-n',str(script)],check=True,capture_output=True)

    def test_release_preparation_bundles_source_but_no_runtime_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime=root/'runtime';runtime.mkdir()
            (runtime/'.env').write_text('OPENAI_API_KEY=never-copy-this-fixture-secret\n')
            frontend=root/'frontend';frontend.mkdir();(frontend/'index.html').write_text('<h1>mock static frontend</h1>')
            env={**os.environ,'NORA_PROJECT_ROOT':str(runtime),'MEDIA_STUDIO_FRONTEND_DIST':str(frontend),'MEDIA_STUDIO_RELEASE_ID':'test-release'}
            subprocess.run([str(DEPLOY/'prepare-release.sh')],env=env,check=True,capture_output=True,text=True)
            bundle=runtime/'work/media-studio-deploy/releases/test-release'
            manifest=json.loads((bundle/'release.json').read_text())
            paths={f['path'] for f in manifest['files']}
            self.assertTrue({'Apps.Caddyfile','compose.yml','dist/index.html','nora-media-apps-backend.service','backend/server.py','backend/engine.py'}.issubset(paths))
            self.assertFalse(any('__pycache__' in p or p.endswith('.pyc') or p.endswith('.env') for p in paths))
            for item in manifest['files']:
                content=(bundle/item['path']).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(),item['sha256'])
                self.assertNotIn(b'never-copy-this-fixture-secret',content)
            self.assertFalse((bundle/'.env').exists())

    def test_stage_rejects_shell_metacharacters_before_any_connection(self):
        result=subprocess.run([str(DEPLOY/'stage-release.sh'),'bad;id'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Invalid release ID',result.stderr)

    def test_laptop_handover_tracks_and_restores_startup_intent(self):
        script=(DEPLOY/'activate-laptop.sh').read_text()
        self.assertIn('old_enablement=',script)
        self.assertIn('restore_enablement nora-media-backend.service "$backend_enablement"',script)
        self.assertIn('restore_enablement nora-media-bridge.service "$bridge_enablement"',script)
        self.assertIn('if [[ "$old_enablement" == transient ]]',script)
        self.assertIn('systemd-run --user --unit=nora-generation-studio --collect',script)
        self.assertLess(script.index('systemctl --user start nora-media-bridge.service'),script.index('systemctl --user enable nora-media-backend.service nora-media-bridge.service'))
        self.assertLess(script.index('check_queue\nif systemctl'),script.index('systemctl --user stop nora-generation-studio.service'))

    def test_gateway_policy_remains_private_authenticated_and_noindex(self):
        apps=(DEPLOY/'Apps.Caddyfile').read_text()
        gateway=(DEPLOY/'Gateway.Caddyfile.fragment').read_text()
        self.assertIn('bind 192.168.100.70',apps)
        self.assertIn('not remote_ip 192.168.100.10',apps)
        self.assertIn('uri /api/auth/check',apps)
        self.assertIn('X-Robots-Tag "noindex, nofollow"',gateway)
        self.assertNotIn('--allow-loopback-local',(DEPLOY/'nora-media-backend.service').read_text())


if __name__=='__main__':unittest.main()
