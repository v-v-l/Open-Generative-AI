"""A rejected deployment preflight must never switch source or restart a service."""
from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock,patch

SCRIPT=Path(__file__).resolve().parents[1]/'deploy/activate-apps-backend.sh'

class ActivationGuard(unittest.TestCase):
    def test_unpaused_or_unfinished_queue_changes_nothing(self):
        remote=SCRIPT.read_text().split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
        for paused,unfinished in [('false',0),('true',1)]:
            with self.subTest(paused=paused,unfinished=unfinished),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);candidate=base/'releases/candidate';(candidate/'backend').mkdir(parents=True)
                (candidate/'release.json').write_text(json.dumps({'files':[]}));(candidate/'backend/server.py').write_text('')
                (base/'runtime').mkdir();(base/'runtime/backend.env').write_text('DATABASE_URL=postgresql://fixture\n')
                (base/'current').symlink_to('releases/previous')
                db=MagicMock();db.execute.side_effect=[types.SimpleNamespace(fetchone=lambda:(paused,)),types.SimpleNamespace(fetchone=lambda:(unfinished,))]
                driver=MagicMock();driver.connect.return_value.__enter__.return_value=db
                def local_path(value,*args):
                    return base if value=='/home/victor/apps/media-studio' else Path(value,*args)
                with patch.dict(sys.modules,{'psycopg':driver}),patch('pathlib.Path',side_effect=local_path),patch.object(sys,'argv',['activate','candidate']),patch('subprocess.run') as run:
                    with self.assertRaisesRegex(SystemExit,'Pause and drain'):
                        exec(compile(remote,str(SCRIPT),'exec'),{})
                    run.assert_not_called()
                self.assertEqual((base/'current').readlink(),Path('releases/previous'))
                self.assertFalse((base/'current.deploy-next').exists())

if __name__=='__main__':unittest.main()
