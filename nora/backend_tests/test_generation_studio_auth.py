"""Verify public gateway authentication without providers or GPU inference."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request

SPEC = importlib.util.spec_from_file_location('generation_studio_auth_server', Path(__file__).resolve().parents[1] / 'backend/server.py')
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class PublicAuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = 'unit test password 123!'
        cls.environment = {'MEDIA_STUDIO_PASSWORD_HASH':server.hash_password(cls.password), 'MEDIA_STUDIO_SESSION_SECRET':'mock-session-secret-' * 4}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        server.engine = lambda: types.SimpleNamespace(capabilities=lambda:{'test':True})
        self.studio = server.Studio(self.temp.name, database_url="")
        self.http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.http.studio = self.studio
        self.http.auth = server.Authentication('https://media.bp-flow.com',dict(self.environment))
        self.http.allow_loopback_local = False
        self.http.read_only = False
        self.thread = threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.studio.stopping.set();self.studio.wake.set()
        self.http.shutdown();self.http.server_close();self.thread.join(2)
        self.studio.worker.join(2);self.studio.db.close();self.studio.ownership.close()
        self.temp.cleanup()

    def request(self,path,data=None,cookie=None,origin='https://media.bp-flow.com',host='media.bp-flow.com',extra=None):
        headers={'Host':host,'Content-Type':'application/json',**(extra or {})}
        if origin is not None: headers['Origin']=origin
        if cookie: headers['Cookie']=cookie
        return urllib.request.urlopen(urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=headers))

    def assert_denied(self,path,status,**kwargs):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request(path,**kwargs)
        self.assertEqual(caught.exception.code,status)
        caught.exception.close()

    def login(self):
        with self.request('/api/auth/login',{'password':self.password}) as response:
            self.assertTrue(json.load(response)['authenticated'])
            return response.headers['Set-Cookie']

    def test_public_configuration_requires_real_credentials(self):
        with self.assertRaises(ValueError): server.Authentication('https://media.bp-flow.com',{})
        with self.assertRaises(ValueError): server.Authentication('http://media.bp-flow.com',self.environment)
        with self.assertRaises(ValueError): server.Authentication('https://media.bp-flow.com/path',self.environment)

    def test_private_routes_and_auth_check(self):
        with self.request('/api/auth') as response:
            self.assertEqual(json.load(response),{'authenticated':False,'required':True})
        for path in ['/api/state','/api/auth/check','/media/'+'a'*32,'/directcut/assets/private.js']:
            self.assert_denied(path,401)
        with self.request('/') as response:
            self.assertIn(b'Sign in to your private workspace',response.read())
        cookie=self.login().split(';')[0]
        with self.request('/api/auth/check',cookie=cookie) as response:
            self.assertEqual(response.status,204);self.assertEqual(response.read(),b'')

    def test_secure_cookie_tampering_and_logout_revocation(self):
        header=self.login()
        for attribute in ['HttpOnly','Secure','SameSite=Strict','Path=/','Max-Age=43200']:
            self.assertIn(attribute,header)
        cookie=header.split(';')[0]
        with self.request('/api/state',cookie=cookie) as response:
            self.assertTrue(json.load(response)['queue_paused'])
        self.assert_denied('/api/state',401,cookie=cookie+'tampered')
        with self.request('/api/auth/logout',{},cookie=cookie) as response:
            self.assertIn('Max-Age=0',response.headers['Set-Cookie'])
        self.assert_denied('/api/state',401,cookie=cookie)

    def test_csrf_and_host_not_forwarded_headers(self):
        self.assert_denied('/api/auth/login',403,data={'password':self.password},origin=None)
        self.assert_denied('/api/auth/login',403,data={'password':self.password},origin='https://attacker.example')
        self.assert_denied('/api/state',403,host=f'localhost:{self.http.server_port}')
        self.assert_denied('/api/state',401,extra={'X-Forwarded-Host':f'localhost:{self.http.server_port}','X-Forwarded-For':'127.0.0.1','X-Forwarded-Proto':'https'})

    def test_public_deployment_never_enables_local_auth_bypass(self):
        # The tunnel makes apps-local callers appear as loopback to this server.
        # Production must never enable the trusted-local development shortcut.
        unit = Path(__file__).resolve().parents[1] / 'deploy/nora-media-backend.service'
        self.assertTrue(unit.is_file(), 'Versioned production service file is required')
        self.assertNotIn('--allow-loopback-local',unit.read_text())

    def test_local_bypass_is_explicit_and_checks_actual_peer(self):
        self.http.allow_loopback_local=True
        host=f'127.0.0.1:{self.http.server_port}'
        with self.request('/api/auth',host=host,origin='http://'+host) as response:
            self.assertEqual(json.load(response),{'authenticated':True,'required':False})
        self.assert_denied('/api/state',403,host=host,origin='https://attacker.example')
        self.assert_denied('/api/state',401)
        handler=server.Handler.__new__(server.Handler)
        handler.server=self.http;handler.client_address=('192.0.2.8',1234)
        handler.headers={'Host':host,'Origin':'http://'+host};handler.command='GET'
        self.assertFalse(handler.loopback_local())
        self.assertFalse(handler.allowed())

    def test_read_only_preview_cannot_enqueue_or_start(self):
        self.http.read_only=True
        cookie=self.login().split(';')[0]
        self.assert_denied('/api/jobs',403,cookie=cookie,data={'kind':'video','prompt':'no inference'})
        self.assert_denied('/api/queue',403,cookie=cookie,data={'paused':False})
        self.assert_denied('/api/uploads',403,cookie=cookie,data={'name':'not uploaded'})
        self.assert_denied('/api/catalog/refresh',403,cookie=cookie,data={})
        with self.request('/api/state',cookie=cookie) as response:
            state=json.load(response)
            self.assertTrue(state['read_only']);self.assertTrue(state['queue_paused']);self.assertEqual(state['jobs'],[])


    def test_authenticated_frontend_root_and_spa_stay_contained(self):
        root=Path(self.temp.name)/'frontend';root.mkdir()
        (root/'index.html').write_text('<h1>Isolated selected frontend</h1>')
        self.http.web_root=root
        cookie=self.login().split(';')[0]
        for route in ['/','/projects/example']:
            with self.request(route,cookie=cookie) as response:
                self.assertEqual(response.read(),b'<h1>Isolated selected frontend</h1>')
        self.assert_denied('/../../queue.sqlite3',404,cookie=cookie)


    def test_public_link_navigation_reaches_login_but_cross_site_fetch_cannot(self):
        navigation={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'}
        with self.request('/',origin=None,extra=navigation) as response:
            self.assertIn(b'Sign in to your private workspace',response.read())
        self.assert_denied('/api/state',403,origin=None,extra={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'cors','Sec-Fetch-Dest':'empty'})
        self.assert_denied('/api/auth/login',403,data={'password':self.password},extra=navigation)


if __name__ == '__main__': unittest.main()
