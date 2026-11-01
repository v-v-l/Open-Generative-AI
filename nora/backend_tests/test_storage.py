"""Real PostgreSQL safety tests run only against an explicitly supplied scratch DB."""
import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import types
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import storage
import server
from import_sqlite import import_queue


class SchedulerTest(unittest.TestCase):
    def test_offline_photo_does_not_block_cloud_and_keeps_exact_payload(self):
        with tempfile.TemporaryDirectory() as root:
            fake = types.ModuleType('engine')
            fake.validate_job = lambda *args: None
            fake.job_readiness = lambda job: {'available':job['kind']!='photo','reason':'Workstation offline'}
            calls=[]
            fake.run_job = lambda job,*args: calls.append(job) or {'outputs':[]}
            previous=sys.modules.get('engine');sys.modules['engine']=fake
            studio=server.Studio(root,database_url='')
            try:
                jobs=studio.enqueue({'kind':'photo','prompt':'exact [Static shot]','seed':123})
                studio.enqueue({'kind':'video','prompt':'cloud'})
                with studio.lock:
                    studio.db.execute("UPDATE settings SET value='false'");studio.db.commit()
                studio.wake.set()
                deadline=time.monotonic()+3
                while not calls and time.monotonic()<deadline: time.sleep(.02)
                with studio.lock:
                    row=studio.db.execute('SELECT * FROM jobs WHERE id=?',(jobs[0]['id'],)).fetchone()
                    self.assertEqual(row['status'],'queued')
                    self.assertEqual(json.loads(row['progress'])['stage'],'waiting_for_executor')
                    self.assertEqual(json.loads(row['payload'])['seed'],123)
                    self.assertFalse(studio.paused())
                self.assertEqual([job['kind'] for job in calls],['video'])
            finally:
                studio.stopping.set();studio.wake.set();studio.worker.join(3)
                studio.db.close();studio.ownership.close()
                if previous is None:sys.modules.pop('engine',None)
                else:sys.modules['engine']=previous

    def test_dsn_redacted(self):
        self.assertNotIn('sensitive',server.safe_error('connection to postgresql://user:sensitive@db/queue failed'))


@unittest.skipUnless(os.environ.get('NORA_TEST_DATABASE_URL'),'isolated scratch PostgreSQL not configured')
class PostgresTest(unittest.TestCase):
    def setUp(self):
        self.url=os.environ['NORA_TEST_DATABASE_URL']
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        import psycopg
        with psycopg.connect(self.url,autocommit=True) as db:
            db.execute('DROP TABLE IF EXISTS studio_imports,jobs,assets,settings')

    def tearDown(self):self.temp.cleanup()

    def test_lock_transactions_fifo_and_restart(self):
        db=storage.connect(self.root,self.url)
        try:
            with self.assertRaisesRegex(RuntimeError,'owns'):
                storage.connect(self.root/'different-local-root',self.url)
            db.execute("INSERT INTO jobs(id,status,created_at,payload) VALUES(?,?,?,?)",('one','queued','same','{}'))
            db.execute("INSERT INTO jobs(id,status,created_at,payload) VALUES(?,?,?,?)",('two','running','same','{}'))
            db.commit()
            self.assertEqual([r['id'] for r in db.execute('SELECT * FROM jobs ORDER BY created_at,rowid').fetchall()],['one','two'])
            self.assertEqual(db.connection.info.transaction_status,0)
            db.execute("UPDATE jobs SET status='cancelled'");db.rollback()
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id='one'").fetchone()[0],'queued')
        finally:db.close()
        studio=server.Studio(self.root,self.url)
        try:
            self.assertTrue(studio.paused())
            self.assertEqual(studio.db.execute("SELECT status FROM jobs WHERE id='two'").fetchone()[0],'interrupted')
        finally:
            studio.stopping.set();studio.wake.set();studio.worker.join(3);studio.db.close();studio.ownership.close()

    def test_import_counts_paths_fifo_and_refuses_second_import(self):
        source=self.root/'source';source.mkdir()
        target=self.root/'target';target.mkdir()
        (source/'uploads').mkdir();(target/'uploads').mkdir()
        (source/'uploads/a.png').write_bytes(b'reference');(target/'uploads/a.png').write_bytes(b'reference')
        db=storage.connect(source,'')
        db.execute("INSERT INTO settings VALUES('queue_paused','true')")
        db.execute('INSERT INTO assets VALUES(?,?,?,?)',('asset','a.png','image/png',str(source/'uploads/a.png')))
        for ident in ['second-lexically','first-lexically']:
            db.execute('INSERT INTO jobs(id,status,created_at,payload,result) VALUES(?,?,?,?,?)',(ident,'queued','same',json.dumps({'assets':[{'id':'asset'}]}),json.dumps({'billing':{'actual_usd':.25}})))
        db.commit();db.close()
        snapshot=self.root/'snapshot';snapshot.mkdir()
        # The source is closed and committed before copying its database.
        import shutil
        shutil.copy2(source/'queue.sqlite3',snapshot/'queue.sqlite3')
        result=import_queue(snapshot,target,self.url,original_root=source)
        self.assertEqual(result['counts'],{'settings':1,'assets':1,'jobs':2})
        with self.assertRaisesRegex(ValueError,'not empty'):import_queue(source,target,self.url)
        db=storage.connect(target,self.url)
        try:
            self.assertEqual(db.execute('SELECT path FROM assets').fetchone()[0],str(target/'uploads/a.png'))
            self.assertEqual([r[0] for r in db.execute('SELECT id FROM jobs ORDER BY rowid').fetchall()],['second-lexically','first-lexically'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM studio_imports').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],2)
        finally:db.close()

    def test_import_refuses_unpaused_and_missing_files_without_partial_rows(self):
        source=self.root/'source';source.mkdir();target=self.root/'target';target.mkdir()
        db=storage.connect(source,'');db.execute("INSERT INTO settings VALUES('queue_paused','false')");db.commit();db.close()
        with self.assertRaisesRegex(ValueError,'paused'):import_queue(source,target,self.url)
        db=storage.connect(source,'');db.execute("UPDATE settings SET value='true'")
        db.execute('INSERT INTO assets VALUES(?,?,?,?)',('a','missing','image/png',str(source/'missing.png')));db.commit();db.close()
        with self.assertRaisesRegex(ValueError,'Copy all'):import_queue(source,target,self.url)
        db=storage.connect(target,self.url)
        try:self.assertEqual(db.execute('SELECT COUNT(*) FROM settings').fetchone()[0],0)
        finally:db.close()

    def test_constraint_failure_rolls_back_entire_import(self):
        source=self.root/'source';source.mkdir();target=self.root/'target';target.mkdir()
        db=storage.connect(source,'')
        db.execute("INSERT INTO settings VALUES('queue_paused','true')")
        # SQLite permits NULL in this legacy TEXT PRIMARY KEY; PostgreSQL does not.
        db.execute("INSERT INTO jobs(id,status,payload) VALUES(NULL,'queued','{}')")
        db.commit();db.close()
        import psycopg
        with self.assertRaises(psycopg.errors.NotNullViolation):import_queue(source,target,self.url)
        db=storage.connect(target,self.url)
        try:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM settings').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM studio_imports').fetchone()[0],0)
        finally:db.close()


if __name__=='__main__':unittest.main()
