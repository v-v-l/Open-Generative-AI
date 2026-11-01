"""Reference browsing/export uses studio auth without touching model execution."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
import urllib.request
import urllib.error
from PIL import Image

SPEC=importlib.util.spec_from_file_location('reference_route_server',Path(__file__).resolve().parents[1]/'backend/server.py')
server=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(server)
from reference_library import Library

class ReferenceRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        Image.new('RGB',(80,120),'red').save(root/'red.png')
        (root/'manifest.json').write_text(json.dumps({'records':[{'id':'H000','path':'red.png','category':'face','title':'Front'}]}))
        def forbidden(): raise AssertionError('Reference request touched generation engine')
        server.engine=forbidden
        self.studio=server.Studio(root,database_url='')
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.http.studio=self.studio;self.http.reference_library=Library(root)
        self.http.auth=server.Authentication('https://media.bp-flow.com',{'MEDIA_STUDIO_PASSWORD':'fixture password 123','MEDIA_STUDIO_SESSION_SECRET':'test-secret-'*6})
        self.http.allow_loopback_local=False;self.http.read_only=False
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'
    def tearDown(self):
        self.studio.stopping.set();self.studio.wake.set();self.http.shutdown();self.http.server_close();self.thread.join(2);self.studio.worker.join(2)
        self.studio.db.close();self.studio.ownership.close();self.tmp.cleanup()
    def request(self,path,payload=None,cookie=None,origin='https://media.bp-flow.com'):
        headers={'Host':'media.bp-flow.com','Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        if cookie:headers['Cookie']=cookie
        req=urllib.request.Request(self.base+path,data=None if payload is None else json.dumps(payload).encode(),headers=headers)
        return urllib.request.urlopen(req)
    def denied(self,path,status,**kwargs):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request(path,**kwargs)
        self.assertEqual(error.exception.code,status);error.exception.close()
    def login(self):
        with self.request('/api/auth/login',{'password':'fixture password 123'}) as r:return r.headers['Set-Cookie']
    def test_auth_original_export_and_no_generation_routes(self):
        with self.request('/login?next=%2Freferences%2F') as r:self.assertIn(b'const target="/references/"',r.read())
        self.denied('/references/api/catalog',401)
        self.denied('/references/file/H000',401)
        cookie=self.login()
        with self.request('/references/api/catalog',cookie=cookie) as r:self.assertEqual(json.load(r)['records'][0]['id'],'H000')
        with self.request('/references/file/H000',cookie=cookie) as r:
            self.assertEqual(r.read(),(Path(self.tmp.name)/'red.png').read_bytes());self.assertIn('attachment',r.headers['Content-Disposition'])
        with self.request('/references/api/export',{'ids':['H000'],'columns':1,'cell_width':256,'cell_height':256},cookie) as r:
            image=Image.open(io.BytesIO(r.read()));self.assertEqual(image.size,(256,256))
        self.denied('/references/api/prepare',404,payload={},cookie=cookie)
        self.denied('/references/api/jobs',404,payload={},cookie=cookie)
        self.assertEqual(self.studio.db.execute('select count(*) from jobs').fetchone()[0],0)
    def test_export_csrf_budget_and_private_inventory(self):
        cookie=self.login()
        self.denied('/references/api/export',403,payload={'ids':['H000']},cookie=cookie,origin='https://example.com')
        self.denied('/references/source-inventory.json',404,cookie=cookie)
        self.denied('/references/api/export',400,payload={'ids':['H000','H000']},cookie=cookie)
        self.denied('/references/api/export',400,payload={'ids':['H000'],'cell_width':99999},cookie=cookie)

if __name__=='__main__':unittest.main()
