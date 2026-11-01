"""Reference browsing/export uses studio auth without touching model execution."""
import importlib.util
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
import urllib.request
import urllib.error
import shutil
import subprocess
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
    def request(self,path,payload=None,cookie=None,origin='https://media.bp-flow.com',extra_headers=None):
        headers={'Host':'media.bp-flow.com','Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        if cookie:headers['Cookie']=cookie
        if extra_headers:headers.update(extra_headers)
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
    def test_authenticated_upload_slots_persist_and_never_queue_generation(self):
        self.denied('/references/api/collections',401,payload={'title':'My face','category':'face'})
        cookie=self.login()
        with self.request('/references/api/collections',{'title':'My face','category':'face'},cookie) as r:
            self.assertEqual(r.status,201);collection=json.load(r)['collection']
        self.assertEqual(len(collection['slots']),8)
        raw=(Path(self.tmp.name)/'red.png').read_bytes()
        payload={'collection_id':collection['id'],'slot_id':'a000','name':'new-face.png','mime':'image/png','data':base64.b64encode(raw).decode()}
        self.denied('/references/api/uploads',403,payload=payload,cookie=cookie,origin='https://example.com')
        with self.request('/references/api/uploads',payload,cookie) as r:
            self.assertEqual(r.status,201);uploaded=json.load(r)
        self.assertEqual(uploaded['record']['status'],'user_supplied')
        with self.request(uploaded['record']['download_url'],cookie=cookie) as r:self.assertEqual(r.read(),raw)
        self.http.reference_library=Library(self.tmp.name)
        with self.request('/references/api/catalog',cookie=cookie) as r:
            catalog=json.load(r);persisted=next(c for c in catalog['collections'] if c['id']==collection['id'])
        self.assertEqual(sum(slot['reference_id'] is None for slot in persisted['slots']),7)
        self.assertTrue(any(r['id']=='H000' for r in catalog['records']))
        self.http.read_only=True
        self.denied('/references/api/uploads',403,payload=payload,cookie=cookie)
        self.assertEqual(self.studio.db.execute('select count(*) from jobs').fetchone()[0],0)

    def test_export_csrf_budget_and_private_inventory(self):
        cookie=self.login()
        self.denied('/references/api/export',403,payload={'ids':['H000']},cookie=cookie,origin='https://example.com')
        self.denied('/references/source-inventory.json',404,cookie=cookie)
        self.denied('/references/api/export',400,payload={'ids':['H000','H000']},cookie=cookie)
        self.denied('/references/api/export',400,payload={'ids':['H000'],'cell_width':99999},cookie=cookie)

    def test_lora_upload_video_inline_ranges_download_and_readonly(self):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('media tools unavailable')
        target=Path(self.tmp.name)/'tiny.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=32x48:r=2','-t','1','-c:v','libx264','-pix_fmt','yuv420p','-y',str(target)],check=True,timeout=15,capture_output=True)
        raw=target.read_bytes();cookie=self.login()
        with self.request('/references/api/collections',{'title':'LoRA samples','category':'lora'},cookie) as response:collection=json.load(response)['collection']
        payload={'collection_id':collection['id'],'name':'tiny.mp4','mime':'video/mp4','data':base64.b64encode(raw).decode()}
        self.denied('/references/api/uploads',401,payload=payload)
        self.denied('/references/api/uploads',403,payload=payload,cookie=cookie,origin='https://evil.example')
        with self.request('/references/api/uploads',payload,cookie) as response:record=json.load(response)['record']
        self.denied(record['video_url'],401)
        with self.request(record['video_url'],cookie=cookie,extra_headers={'Range':'bytes=4-23'}) as response:
            self.assertEqual(response.status,206);self.assertEqual(response.headers['Content-Type'],'video/mp4')
            self.assertEqual(response.headers['Content-Range'],f'bytes 4-23/{len(raw)}');self.assertEqual(response.read(),raw[4:24])
        with self.request(record['video_url'],cookie=cookie,extra_headers={'Range':'bytes=-8'}) as response:self.assertEqual(response.read(),raw[-8:])
        self.denied(record['video_url'],416,cookie=cookie,extra_headers={'Range':'bytes=999999-'})
        with self.request(record['download_url'],cookie=cookie) as response:
            self.assertIn('attachment',response.headers['Content-Disposition']);self.assertEqual(response.read(),raw)
        self.http.read_only=True
        self.denied('/references/api/uploads',403,payload=payload,cookie=cookie)
        self.denied('/references/api/collections',403,payload={'title':'No write','category':'lora'},cookie=cookie)
        retained=self.http.reference_library.original_file(record['id'])['path']
        self.http.read_only=False
        with self.request('/references/api/remove',{'id':record['id']},cookie) as response:self.assertEqual(json.load(response)['removed_id'],record['id'])
        self.assertEqual(retained.read_bytes(),raw)
        self.denied(record['video_url'],404,cookie=cookie)
        self.assertEqual(self.studio.db.execute('select count(*) from jobs').fetchone()[0],0)

    def test_remove_and_replace_routes_require_auth_origin_and_active_membership(self):
        cookie=self.login()
        with self.request('/references/api/collections',{'title':'My face','category':'face'},cookie) as response:collection=json.load(response)['collection']
        payload={'collection_id':collection['id'],'slot_id':'a000','name':'face.png','mime':'image/png','data':base64.b64encode((Path(self.tmp.name)/'red.png').read_bytes()).decode()}
        with self.request('/references/api/uploads',payload,cookie) as response:first=json.load(response)['record']
        self.denied('/references/api/remove',401,payload={'id':first['id']})
        self.denied('/references/api/remove',403,payload={'id':first['id']},cookie=cookie,origin='https://evil.example')
        self.denied('/references/api/remove',403,payload={'id':'H000'},cookie=cookie)
        self.denied('/references/api/uploads',409,payload=payload,cookie=cookie)
        payload['replace_id']=first['id']
        with self.request('/references/api/uploads',payload,cookie) as response:second=json.load(response)['record']
        self.denied(first['download_url'],404,cookie=cookie)
        self.denied('/references/api/uploads',409,payload=payload,cookie=cookie)
        self.http.read_only=True
        self.denied('/references/api/remove',403,payload={'id':second['id']},cookie=cookie)
        self.http.read_only=False
        with self.request('/references/api/remove',{'id':second['id']},cookie) as response:self.assertEqual(json.load(response)['removed_id'],second['id'])
        self.denied(second['image_url'],404,cookie=cookie)
        self.denied(second['download_url'],404,cookie=cookie)
        self.denied('/references/api/zip',404,payload={'ids':[second['id']]},cookie=cookie)
        self.assertEqual(self.studio.db.execute('select count(*) from jobs').fetchone()[0],0)

if __name__=='__main__':unittest.main()
