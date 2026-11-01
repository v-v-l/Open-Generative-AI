"""Validate isolated fork merges and refusal of dirty live checkouts."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('nora-update.py')
spec = importlib.util.spec_from_file_location('fork_updater', SCRIPT)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class ForkUpdateTests(unittest.TestCase):
    def test_merge_and_conflict_do_not_change_live_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / 'original'
            original.mkdir()
            def git(repo, *args):
                return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
            def configure(repo):
                git(repo, 'config', 'user.name', 'Test')
                git(repo, 'config', 'user.email', 'test@localhost')
            git(original, 'init', '-q')
            configure(original)
            (original / 'panel').write_text('base\n')
            git(original, 'add', '.')
            git(original, 'commit', '-qm', 'base')
            live = root / 'live'
            subprocess.run(['git', 'clone', str(original), str(live)], check=True, capture_output=True)
            configure(live)
            git(live, 'remote', 'add', 'upstream', str(original))
            (live / 'nora').mkdir()
            (live / 'nora/adapter').write_text('our provider adapter\n')
            git(live, 'add', '.')
            git(live, 'commit', '-qm', 'our integration')
            live_commit = git(live, 'rev-parse', 'HEAD')
            (original / 'new-feature').write_text('upstream addition\n')
            git(original, 'add', '.')
            git(original, 'commit', '-qm', 'new feature')
            target = git(original, 'rev-parse', 'HEAD')
            with patch.object(updater, 'UPSTREAM', str(original)):
                report = updater.prepare(live, target, root / 'candidate')
                self.assertEqual(git(live, 'rev-parse', 'HEAD'), live_commit)
                self.assertFalse((live / 'new-feature').exists())
                self.assertTrue((Path(report['candidate']) / 'new-feature').is_file())
                self.assertEqual((Path(report['candidate']) / 'nora/adapter').read_text(), 'our provider adapter\n')
                (live / 'panel').write_text('our change\n')
                with self.assertRaisesRegex(ValueError, 'Commit or stash'):
                    updater.prepare(live, target, root / 'dirty')
                git(live, 'add', '.')
                git(live, 'commit', '-qm', 'our panel')
                (original / 'panel').write_text('upstream conflicting change\n')
                git(original, 'add', '.')
                git(original, 'commit', '-qm', 'upstream panel')
                conflict_target = git(original, 'rev-parse', 'HEAD')
                with self.assertRaises(subprocess.CalledProcessError):
                    updater.prepare(live, conflict_target, root / 'conflict')
                self.assertEqual((live / 'panel').read_text(), 'our change\n')
                self.assertTrue((root / 'conflict/panel').is_file())


if __name__ == '__main__':
    unittest.main()
