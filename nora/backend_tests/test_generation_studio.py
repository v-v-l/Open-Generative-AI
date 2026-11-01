"""Exercise persistent queue safety without contacting either inference backend."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request

SERVER = Path(__file__).resolve().parents[1] / 'backend/server.py'
spec = importlib.util.spec_from_file_location('generation_studio_server', SERVER)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.previous = sys.modules.get('engine')
        fake = types.ModuleType('engine')
        fake.capabilities = lambda: {'test': True}
        fake.validate_job = lambda job, assets: None
        def run(job, directory, assets, progress, cancelled):
            self.calls.append(job)
            target = directory / 'result.txt'
            target.write_text('test output')
            return [{'path': str(target), 'kind': 'image'}]
        fake.run_job = run
        sys.modules['engine'] = fake
        self.studio = server.Studio(self.temp.name)

    def tearDown(self):
        self.studio.stopping.set()
        self.studio.wake.set()
        self.studio.worker.join(3)
        self.studio.db.close()
        self.studio.ownership.close()
        if self.previous is None: sys.modules.pop('engine', None)
        else: sys.modules['engine'] = self.previous
        self.temp.cleanup()

    def test_enqueue_does_not_start_rental(self):
        jobs = self.studio.enqueue({'kind':'video','prompt':'Verbatim [Static shot]','seed':123,'batch_count':3})
        self.assertEqual([j['seed'] for j in jobs], [123,124,125])
        self.assertTrue(self.studio.paused())
        self.assertEqual(self.calls, [])
        self.assertTrue(all(j['prompt']=='Verbatim [Static shot]' for j in jobs))

    def test_worker_registers_results_once(self):
        job = self.studio.enqueue({'kind':'photo','prompt':'test'})[0]
        with self.studio.lock:
            self.studio.db.execute("UPDATE settings SET value='false' WHERE key='queue_paused'")
            self.studio.db.commit()
        self.studio.wake.set()
        deadline = time.monotonic()+3
        while time.monotonic()<deadline:
            with self.studio.lock:
                row=self.studio.db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone()
                done=self.studio.job(row)
            if done['status']=='completed': break
            time.sleep(.02)
        self.assertEqual(done['status'],'completed')
        self.assertEqual(len(self.calls),1)
        self.assertTrue(done['outputs'][0]['url'].startswith('/media/'))

    def test_result_outside_job_directory_rejected(self):
        outside=Path(self.temp.name)/'outside.txt';outside.write_text('private')
        jobdir=Path(self.temp.name)/'jobs/x';jobdir.mkdir()
        with self.assertRaises(ValueError):
            self.studio.register_result([{'path':str(outside)}],jobdir)

    def test_bad_seed_or_batch_rejected(self):
        for payload in [{'batch_count':0},{'batch_count':True},{'seed':True},{'seed':-2}]:
            with self.assertRaises(ValueError): self.studio.enqueue(payload)

    def test_explicit_unknown_cost_limit_rejected(self):
        sys.modules['engine'].estimate_job = lambda job, assets: {'estimated_usd':None,'upper_usd':None,'status':'unknown'}
        with self.assertRaisesRegex(ValueError,'cost quote'):
            self.studio.enqueue({'kind':'photo','prompt':'unknown quote','max_cost_usd':1})
        self.assertEqual(self.studio.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)

    def test_catalog_refresh_rejects_unfinished_jobs_without_calling_provider(self):
        calls=[]
        sys.modules['engine'].refresh_cloud_catalog=lambda: calls.append('refresh') or [{'id':'mock-model'}]
        job=self.studio.enqueue({'kind':'photo','prompt':'queued snapshot'})[0]
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);http.studio=self.studio
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        def post(path,payload):
            return urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}))
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:post('/api/catalog/refresh',{})
            self.assertEqual(error.exception.code,409);error.exception.close()
            self.assertEqual(calls,[])
            self.assertEqual(self.studio.db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'queued')
            with post('/api/jobs/'+job['id']+'/cancel',{}) as response:response.read()
            with post('/api/catalog/refresh',{}) as response:self.assertEqual(json.load(response)['models'][0]['id'],'mock-model')
            self.assertEqual(calls,['refresh'])
        finally:
            http.shutdown();http.server_close();thread.join(2)

    def test_origin_and_host_guard(self):
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        http.studio=self.studio
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{http.server_port}/api/state'
        try:
            with urllib.request.urlopen(url) as response:
                self.assertTrue(json.load(response)['queue_paused'])
            for headers in [{'Origin':'https://unrelated.example'},{'Host':'unrelated.example'}]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url,headers=headers))
                self.assertEqual(error.exception.code,403)
                error.exception.close()
        finally:
            http.shutdown();http.server_close();thread.join(2)



class GraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('studio_native_engine', SERVER.parent / 'engine.py')
        cls.engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.engine)

    def test_literal_prompt_and_lora_toggle(self):
        for builder in [self.engine.build_photo_graph, self.engine.build_video_graph]:
            for enabled in [False, True]:
                graph = builder({'prompt':'[Static shot] Exact words <image1>', 'seed':456, 'lora_enabled':enabled}, [])
                self.assertTrue(any(n['inputs'].get('prompt')=='[Static shot] Exact words <image1>' for n in graph.values()))
                self.assertEqual(any(n['class_type']=='LoraLoaderModelOnly' for n in graph.values()),enabled)
                for node in graph.values():
                    for value in node['inputs'].values():
                        if isinstance(value,list) and len(value)==2 and isinstance(value[0],str):
                            self.assertIn(value[0],graph)

    def test_start_end_guides_and_audio_are_connected(self):
        graph=self.engine.build_video_graph({'prompt':'test','generated_audio':True},[
            {'role':'start','filename':'start.png'}, {'role':'end','filename':'end.png'}])
        guides={key:node for key,node in graph.items() if node['class_type']=='MiniMaxH3AddGuide'}
        self.assertEqual([n['inputs']['frame_idx'] for n in guides.values()],[0,-1])
        self.assertEqual(graph['304']['inputs']['positive'],['301',0])
        self.assertEqual(graph['22']['inputs']['conditioning'],['304',0])
        self.assertEqual(graph['27']['inputs']['audio'],['80',0])

    def test_invalid_frame_grid_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.validate_job({'kind':'video','prompt':'test','frames':140},[])
        self.engine.validate_job({'kind':'video','prompt':'test','frames':141},[])


if __name__ == '__main__': unittest.main()
