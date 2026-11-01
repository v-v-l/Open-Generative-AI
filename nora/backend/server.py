#!/usr/bin/env python3
"""Loopback-only persistent generation queue. No automatic paid retries."""
from __future__ import annotations
import argparse
import base64
import binascii
import importlib
import fcntl
import json
import mimetypes
import math
import os
import hashlib
import hmac
import secrets
import getpass
from http.cookies import SimpleCookie, CookieError
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, quote, parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import storage
from reference_library import LibraryError
PROJECT = Path(os.environ.get('NORA_PROJECT_ROOT', str(HERE.parents[3]))).expanduser().resolve()
MAX_BODY = 140 * 1024 * 1024
MAX_ASSET = 100 * 1024 * 1024
REFERENCE_EXPORT_LOCK = threading.BoundedSemaphore(1)
ALLOWED_MIME = {'image/png','.unused','image/jpeg','image/webp','video/mp4','video/quicktime','video/webm','audio/mpeg','audio/mp3','audio/wav','audio/x-wav','audio/flac','audio/ogg','audio/mp4'} - {'.unused'}


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def safe_error(error):
    text = str(error)
    text = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[redacted]', text)
    text = re.sub(r'(?i)(?:https?|postgres(?:ql)?)://[^\s]+', '[URL redacted]', text)
    return text[:1000]


def clean_metadata(value, depth=0):
    """Bound provider accounting data without serializing credentials or raw payloads."""
    if depth > 4: return None
    if value is None or isinstance(value, bool): return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if isinstance(value, str): return safe_error(value)
    if isinstance(value, list): return [clean_metadata(v, depth+1) for v in value[:40]]
    if isinstance(value, dict):
        return {str(k)[:80]: clean_pricing_source(v) if k == 'pricing_source' else clean_metadata(v, depth+1) for k,v in list(value.items())[:60]
                if not re.search(r'(?i)(secret|token$|api.?key|authorization|credential|base64|raw|response|request_body)', str(k))}
    return None


def clean_pricing_source(value):
    if isinstance(value,str) and value.startswith('https://'):
        parsed = urlsplit(value)
        if parsed.hostname and not parsed.username and not parsed.password:
            # Pricing citations are public documentation, not signed asset URLs.
            return 'https://' + parsed.netloc + parsed.path
    return clean_metadata(value)


def billing_metadata(value):
    if not isinstance(value, dict): return None
    allowed = ('actual_usd','currency','status','usage','source','pricing_source')
    return {key: clean_pricing_source(value[key]) if key == 'pricing_source' else clean_metadata(value[key]) for key in allowed if key in value}


def engine():
    return importlib.import_module('engine')


class Authentication:
    """Single-user HTTPS sessions; no proxy headers influence the trust boundary."""
    COOKIE = '__Host-nora_session'

    def __init__(self, public_origin=None, environ=None):
        env = os.environ if environ is None else environ
        self.origin = public_origin
        self.required = bool(public_origin)
        self.sessions = {}
        self.attempts = []
        self.lock = threading.Lock()
        self.password_hash = env.get('MEDIA_STUDIO_PASSWORD_HASH', '')
        self.password = env.get('MEDIA_STUDIO_PASSWORD', '')
        self.secret = env.get('MEDIA_STUDIO_SESSION_SECRET', '')
        if not self.required: return
        parsed = urlsplit(public_origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('--public-origin must be an HTTPS origin without a path')
        self.origin = 'https://' + parsed.netloc
        self.host = parsed.netloc
        if len(self.secret) < 32:
            raise ValueError('Public hosting requires MEDIA_STUDIO_SESSION_SECRET with at least 32 characters')
        if self.password_hash:
            try:
                algorithm, rounds, salt, digest = self.password_hash.split('$')
                if algorithm != 'pbkdf2_sha256' or not 200000 <= int(rounds) <= 2000000 or len(bytes.fromhex(salt)) < 16 or len(bytes.fromhex(digest)) != 32:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('Invalid MEDIA_STUDIO_PASSWORD_HASH; use --hash-password') from None
        elif len(self.password) < 12:
            raise ValueError('Public hosting requires a password hash or MEDIA_STUDIO_PASSWORD of at least 12 characters')

    def verify(self, password):
        if not isinstance(password,str) or len(password) > 1024: return False
        if self.password_hash:
            _, rounds, salt, digest = self.password_hash.split('$')
            computed = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
            return hmac.compare_digest(computed,digest)
        return hmac.compare_digest(password.encode(),self.password.encode())

    def login(self, password):
        with self.lock:
            stamp = time.time()
            self.attempts = [n for n in self.attempts if n > stamp-60]
            if len(self.attempts) >= 8: raise ValueError('Too many login attempts; try again in one minute')
            self.attempts.append(stamp)
        if not self.verify(password): return None
        nonce = secrets.token_hex(24)
        expiry = int(time.time()) + 12*3600
        message = nonce + '.' + str(expiry)
        signature = hmac.new(self.secret.encode(),message.encode(),hashlib.sha256).hexdigest()
        with self.lock:
            self.sessions = {n:e for n,e in self.sessions.items() if e > time.time()}
            self.sessions[nonce] = expiry
        return message+'.'+signature

    def session(self, cookie):
        if not self.required: return True
        try:
            jar = SimpleCookie(); jar.load(cookie or '')
            value = jar[self.COOKIE].value
            nonce,expiry,signature = value.split('.')
            message = nonce+'.'+expiry
            expected = hmac.new(self.secret.encode(),message.encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected,signature) or int(expiry) <= time.time(): return False
            with self.lock: return self.sessions.get(nonce) == int(expiry)
        except (KeyError,ValueError,CookieError): return False

    def logout(self,cookie):
        try:
            jar = SimpleCookie();jar.load(cookie or '')
            nonce = jar[self.COOKIE].value.split('.')[0]
            with self.lock: self.sessions.pop(nonce,None)
        except (KeyError,ValueError,CookieError): pass

    def cookie(self,value,clear=False):
        return f'{self.COOKIE}={value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={0 if clear else 43200}'


def hash_password(password):
    salt = secrets.token_bytes(16)
    rounds = 600000
    digest = hashlib.pbkdf2_hmac('sha256',password.encode(),salt,rounds).hex()
    return f'pbkdf2_sha256${rounds}${salt.hex()}${digest}'


class Studio:
    def __init__(self, root, database_url=None):
        self.root = Path(root).resolve()
        if not (self.root.is_relative_to(PROJECT / 'outputs') or self.root.is_relative_to(Path('/tmp'))):
            raise ValueError('Studio root must be under project outputs or /tmp')
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'uploads').mkdir(exist_ok=True)
        (self.root / 'jobs').mkdir(exist_ok=True)
        # Own the database for the process lifetime before any restart recovery.
        self.ownership = (self.root / 'server.lock').open('a')
        try:
            fcntl.flock(self.ownership.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.ownership.close()
            raise RuntimeError('Another Studio server already owns this queue') from None
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.active = None
        try:
            self.db = storage.connect(self.root, database_url)
        except BaseException:
            self.ownership.close()
            raise
        self.db.execute("INSERT INTO settings VALUES('queue_paused','true') ON CONFLICT(key) DO NOTHING")
        self.db.execute("UPDATE jobs SET status='interrupted',error='Server restarted during generation; retry explicitly after checking remote work.',updated_at=? WHERE status='running'", (now(),))
        # Restarts require a deliberate resume, including after a clean shutdown.
        self.db.execute("UPDATE settings SET value='true' WHERE key='queue_paused'")
        self.db.commit()
        self.worker = threading.Thread(target=self.work, daemon=True)
        self.worker.start()

    def paused(self):
        return json.loads(self.db.execute("SELECT value FROM settings WHERE key='queue_paused'").fetchone()[0])

    def job(self, row):
        data = json.loads(row['payload'])
        public_assets = []
        for ref in data.get('assets', []):
            asset = self.db.execute('SELECT id,name,mime FROM assets WHERE id=?', (ref.get('id',''),)).fetchone()
            if asset:
                public = dict(asset)
                public.update({'role':ref.get('role','image'),'url':'/media/'+asset['id']})
                if 'include_audio' in ref: public['include_audio'] = ref['include_audio']
                public_assets.append(public)
        data['assets'] = public_assets
        data.update({k: row[k] for k in ('id','status','created_at','updated_at','error')})
        data['progress'] = json.loads(row['progress']) if row['progress'] else None
        data['result'] = json.loads(row['result']) if row['result'] else None
        data['outputs'] = (data['result'] or {}).get('outputs', [])
        data['billing'] = (data['result'] or {}).get('billing')
        data['provider_request_id'] = (data['result'] or {}).get('provider_request_id')
        data['cancel_requested'] = bool(row['cancel_requested'])
        return data

    def assets(self, refs):
        if not isinstance(refs, list) or len(refs) > 20:
            raise ValueError('assets must be a list of at most 20 references')
        found = []
        for ref in refs:
            if not isinstance(ref, dict): raise ValueError('Invalid asset reference')
            row = self.db.execute('SELECT * FROM assets WHERE id=?', (str(ref.get('id','')),)).fetchone()
            if row is None: raise ValueError('Unknown asset')
            asset = dict(row)
            asset['role'] = str(ref.get('role','image'))[:64]
            if 'include_audio' in ref:
                if not isinstance(ref['include_audio'], bool): raise ValueError('include_audio must be boolean')
                asset['include_audio'] = ref['include_audio']
            found.append(asset)
        return found

    def estimate(self, payload, refs=None):
        if not isinstance(payload, dict): raise ValueError('Job must be an object')
        if refs is None:
            with self.lock: refs = self.assets(payload.get('assets', []))
        estimator = getattr(engine(), 'estimate_job', None)
        if estimator is None:
            return {'available':False, 'actual_usd':None, 'uncertainty':'No estimator is available for this model'}
        try:
            estimate_payload = dict(payload)
            # Seed does not affect pricing; resolve only the validation placeholder here.
            # Enqueue independently selects and persists the actual random seed.
            if estimate_payload.get('seed') in (None, '', -1):
                estimate_payload['seed'] = 0
            result = estimator(estimate_payload, refs)
            if not isinstance(result, dict):
                return {'available':False, 'uncertainty':'Estimator returned no price'}
            return clean_metadata(result)
        except Exception as exc:
            return {'available':False, 'uncertainty':safe_error(exc)}

    def enqueue(self, payload):
        if not isinstance(payload, dict): raise ValueError('Job must be an object')
        payload = dict(payload)
        # Estimates are generated here, never accepted as authoritative client input.
        payload.pop('cost_estimate', None)
        count = payload.pop('batch_count', 1)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 20:
            raise ValueError('batch_count must be between 1 and 20')
        seed = payload.get('seed')
        if seed in (None, '', -1): seed = uuid.uuid4().int % (2**31)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63 - 20:
            raise ValueError('seed must be a nonnegative integer')
        with self.lock:
            refs = self.assets(payload.get('assets', []))
            prepared = []
            for n in range(count):
                item = dict(payload, seed=seed+n, batch_count=1)
                engine().validate_job(item, refs)
                item['cost_estimate'] = self.estimate(item, refs)
                limit = item.get('max_cost_usd')
                if limit is not None:
                    if isinstance(limit, bool) or not isinstance(limit, (int,float)) or not math.isfinite(limit) or limit <= 0:
                        raise ValueError('max_cost_usd must be a positive amount')
                    estimate = item['cost_estimate']
                    upper = next((estimate.get(key) for key in ('upper_usd','estimated_usd','estimate_usd','usd')
                                  if isinstance(estimate.get(key),(int,float)) and not isinstance(estimate.get(key),bool)), None)
                    if upper is None:
                        raise ValueError('Cannot apply max_cost_usd without a reliable cost quote; no job was queued')
                    if upper > limit:
                        raise ValueError('Estimated per-job cost exceeds max_cost_usd')
                prepared.append(item)
            added = []
            for item in prepared:
                identifier = uuid.uuid4().hex
                stamp = now()
                self.db.execute('INSERT INTO jobs(id,status,created_at,updated_at,payload) VALUES(?,?,?,?,?)', (identifier,'queued',stamp,stamp,json.dumps(item)))
                added.append(identifier)
            self.db.commit()
            self.wake.set()
            return [self.job(self.db.execute('SELECT * FROM jobs WHERE id=?',(i,)).fetchone()) for i in added]

    def progress(self, identifier, value):
        business = {}
        if isinstance(value, dict):
            bill = billing_metadata(value.get('billing'))
            if bill is not None: business['billing'] = bill
            request_id = value.get('provider_request_id')
            if isinstance(request_id,str): business['provider_request_id'] = safe_error(request_id)[:200]
        if isinstance(value, str): value = {'message': safe_error(value)}
        elif not isinstance(value, dict): value = {'message': 'Working'}
        else: value = {str(k)[:64]: safe_error(v) if isinstance(v, str) else v for k,v in value.items() if isinstance(v,(str,int,float,bool,type(None)))}
        with self.lock:
            if business:
                row = self.db.execute('SELECT result FROM jobs WHERE id=?',(identifier,)).fetchone()
                stored = json.loads(row[0]) if row and row[0] else {'outputs':[]}
                stored.update(business)
                self.db.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(stored),identifier))
            self.db.execute('UPDATE jobs SET progress=?,updated_at=? WHERE id=?', (json.dumps(value), now(), identifier))
            self.db.commit()

    def cancelled(self, identifier):
        with self.lock:
            row = self.db.execute('SELECT cancel_requested FROM jobs WHERE id=?',(identifier,)).fetchone()
            return self.stopping.is_set() or bool(row[0])

    def register_result(self, result, jobdir):
        if result is None: result = {}
        if isinstance(result, list): result = {'outputs': result}
        if not isinstance(result, dict): raise ValueError('Engine returned an invalid result')
        outputs = []
        for out in result.get('outputs', []):
            details = dict(out) if isinstance(out, dict) else {'path': str(out)}
            path = Path(details['path'])
            if not path.is_absolute(): path = jobdir / path
            path = path.resolve()
            if not path.is_relative_to(jobdir.resolve()) or not path.is_file():
                raise ValueError('Engine output is outside its job directory or missing')
            ident = uuid.uuid4().hex
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            self.db.execute('INSERT INTO assets VALUES(?,?,?,?)',(ident,path.name,mime,str(path)))
            outputs.append({'id':ident,'name':path.name,'mime':mime,'kind':mime.split('/')[0],'url':'/media/'+ident})
        # Only publish curated business accounting, never raw provider responses.
        registered = {'outputs':outputs}
        billing = billing_metadata(result.get('billing'))
        if billing is not None: registered['billing'] = billing
        request_id = result.get('provider_request_id')
        if isinstance(request_id,str): registered['provider_request_id'] = safe_error(request_id)[:200]
        return registered

    def work(self):
        while not self.stopping.is_set():
            self.wake.wait(1)
            self.wake.clear()
            with self.lock:
                if self.paused(): continue
                row = None
                readiness = getattr(engine(), 'job_readiness', None)
                for candidate in self.db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,rowid").fetchall():
                    payload = json.loads(candidate['payload'])
                    ready = readiness(payload) if readiness else {'available': True}
                    if not ready.get('available', False):
                        progress = json.dumps({'stage':'waiting_for_executor','message':safe_error(ready.get('reason','Executor unavailable'))})
                        if candidate['progress'] != progress:
                            self.db.execute('UPDATE jobs SET progress=?,updated_at=? WHERE id=?', (progress,now(),candidate['id']))
                        continue
                    row = candidate
                    break
                self.db.commit()
                if row is None: continue
                identifier = row['id']
                self.active = identifier
                self.db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?",(now(),identifier))
                self.db.commit()
                payload = json.loads(row['payload'])
                refs = self.assets(payload.get('assets', []))
            jobdir = self.root / 'jobs' / identifier
            jobdir.mkdir(exist_ok=True)
            try:
                engine().validate_job(payload, refs)
                result = engine().run_job(payload, jobdir, refs,
                    lambda value: self.progress(identifier,value), lambda: self.cancelled(identifier))
                with self.lock:
                    registered = self.register_result(result,jobdir)
                    status = 'cancelled' if self.cancelled(identifier) else 'completed'
                    self.db.execute('UPDATE jobs SET status=?,result=?,updated_at=? WHERE id=?',(status,json.dumps(registered),now(),identifier))
                    self.db.commit()
            except Exception as exc:
                with self.lock:
                    status = 'cancelled' if self.cancelled(identifier) else 'failed'
                    old = self.db.execute('SELECT result FROM jobs WHERE id=?',(identifier,)).fetchone()
                    failure = json.loads(old[0]) if old and old[0] else {'outputs':[]}
                    failure['billing'] = billing_metadata(getattr(exc,'billing',None)) or failure.get('billing') or {'actual_usd':None,'currency':'USD','status':'unknown'}
                    request_id = getattr(exc,'provider_request_id',None)
                    if isinstance(request_id,str): failure['provider_request_id'] = safe_error(request_id)[:200]
                    self.db.execute('UPDATE jobs SET status=?,error=?,result=?,updated_at=? WHERE id=?',(status,safe_error(exc),json.dumps(failure),now(),identifier))
                    # A failure requires attention; do not continue spending unattended.
                    self.db.execute("UPDATE settings SET value='true' WHERE key='queue_paused'")
                    self.db.commit()
            finally:
                with self.lock: self.active = None
                self.wake.set()


class Handler(BaseHTTPRequestHandler):
    server_version = 'NoraStudio/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(90)
    def log_message(self, *args): pass

    def auth(self):
        return getattr(self.server, 'auth', None)

    def loopback_local(self):
        if not getattr(self.server, 'allow_loopback_local', False): return False
        port = self.server.server_port
        return self.client_address[0] in ('127.0.0.1','::1') and self.headers.get('Host','') in {f'127.0.0.1:{port}',f'localhost:{port}',f'[::1]:{port}'}

    def allowed(self):
        try:
            auth = self.auth()
            host_value = self.headers.get('Host','')
            if auth and auth.required and not self.loopback_local():
                if host_value != auth.host: return False
                origin = self.headers.get('Origin')
                if origin and origin != auth.origin: return False
                if self.command == 'POST' and origin != auth.origin: return False
            else:
                port = self.server.server_port
                if host_value not in {f'127.0.0.1:{port}',f'localhost:{port}',f'[::1]:{port}'}: return False
                origin = self.headers.get('Origin')
                if origin and origin != 'http://' + host_value: return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                # A link into the public app must reach its login page. This
                # exception allows only document navigation, never fetch/POST.
                return bool(auth and auth.required and not self.loopback_local()
                            and self.command == 'GET'
                            and self.headers.get('Sec-Fetch-Mode') == 'navigate'
                            and self.headers.get('Sec-Fetch-Dest') == 'document')
            return True
        except ValueError: return False

    def authenticated(self):
        auth = self.auth()
        return self.loopback_local() or not auth or auth.session(self.headers.get('Cookie'))

    def login_page(self, target='/'):
        target = target if target.startswith('/') and not target.startswith('//') else '/'
        # Keep user-controlled paths out of executable inline markup.
        target_json = json.dumps(target).replace('<', r'\u003c')
        markup = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Media Studio · Sign in</title><style>body{font:16px system-ui;background:#101014;color:#f5f5f5;display:grid;place-items:center;min-height:95vh}form{width:min(340px,85vw);padding:32px;background:#1c1c24;border:1px solid #353540;border-radius:20px}input,button{box-sizing:border-box;width:100%;padding:13px;margin-top:14px;border-radius:9px;border:1px solid #555;background:#292934;color:inherit}button{background:#8171ee;cursor:pointer}p{color:#bdbacb}#error{color:#ffb6b6}</style></head><body><form><h1>Media Studio</h1><p>Sign in to your private workspace.</p><input type="password" name="password" autocomplete="current-password" aria-label="Password" placeholder="Password" required><button>Sign in</button><p id="error" role="alert"></p></form><script>const target=TARGET;document.querySelector('form').onsubmit=async(e)=>{e.preventDefault();const form=e.target;const button=form.querySelector('button');button.disabled=true;try{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({password:form.password.value})});const data=await response.json();if(!response.ok)throw Error(data.error||'Sign in failed');location.assign(target)}catch(error){document.querySelector('#error').textContent=error.message}finally{button.disabled=false}};</script></body></html>""".replace('TARGET',target_json)
        encoded = markup.encode()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(encoded)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.end_headers();self.wfile.write(encoded)

    def send(self, code, data, cookie=None):
        encoded = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(encoded)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(encoded)

    def file(self, path, mime):
        size = path.stat().st_size
        start, end, status = 0, size-1, 200
        value = self.headers.get('Range')
        if value:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
            if not match: return self.send(416, {'error':'Invalid range'})
            a,b = match.groups()
            if not a and b: start = max(0,size-int(b))
            elif a: start = int(a); end = min(int(b),end) if b else end
            if start > end or start >= size: return self.send(416, {'error':'Invalid range'})
            status = 206
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','private, no-store')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('X-Content-Type-Options','nosniff')
        if status == 206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    chunk = stream.read(min(1024*1024,remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError): pass

    def references(self):
        library = getattr(self.server, 'reference_library', None)
        if library is None:
            import reference_library
            library = reference_library.Library()
            self.server.reference_library = library
        return library

    def reference_binary(self, result, download=False):
        data = result['bytes']
        self.send_response(200)
        self.send_header('Content-Type', result['kind'])
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'private, no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        if download:
            filename = result['filename']
            fallback = re.sub(r'[^A-Za-z0-9._-]', '_', filename)[:120]
            self.send_header('Content-Disposition', 'attachment; filename="'+fallback+'"; filename*=UTF-8\'\''+quote(filename,safe=''))
        self.end_headers()
        self.wfile.write(data)

    def reference_get(self, route):
        try:
            if route == '/references/api/catalog':
                return self.send(200, {**self.references().catalog('/references'), 'read_only':bool(getattr(self.server,'read_only',False))})
            for prefix, operation in (('/references/image/', 'original'), ('/references/file/', 'original'), ('/references/thumb/', 'thumbnail')):
                if route.startswith(prefix):
                    ident = route[len(prefix):]
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', ident):
                        return self.send(404, {'error':'Reference not found'})
                    result = getattr(self.references(), operation)(ident)
                    return self.reference_binary(result, download=prefix=='/references/file/')
            relative = route[len('/references/'):]
            if relative not in ('', 'index.html', 'app.js', 'app.css'):
                return self.send(404, {'error':'Reference route not found'})
            path = HERE.parent/'references/web'/(relative or 'index.html')
            if not path.is_file(): return self.send(404, {'error':'Library page not found'})
            return self.file(path, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        except LibraryError as exc:
            return self.send(exc.status, {'error':safe_error(exc)})
        except (ValueError, KeyError, FileNotFoundError):
            return self.send(404, {'error':'Reference not found'})
        except (RuntimeError, OSError):
            return self.send(503, {'error':'Reference library is unavailable'})

    def do_GET(self):
        if not self.allowed(): return self.send(403,{'error':'Allowed host and same origin required'})
        route = urlsplit(self.path).path
        studio = self.server.studio
        if route == '/api/auth':
            auth = self.auth()
            return self.send(200,{'authenticated':self.authenticated(),'required':bool(auth and auth.required and not self.loopback_local())})
        if route == '/api/auth/check':
            if not self.authenticated(): return self.send(401,{'error':'Authentication required'})
            self.send_response(204);self.send_header('Cache-Control','no-store');self.end_headers();return
        if route == '/login':
            target = parse_qs(urlsplit(self.path).query).get('next',['/'])[0]
            return self.login_page('/references/' if target in ('/references','/references/') else '/')
        if not self.authenticated():
            if route in ('/','/directcut','/directcut/') or 'text/html' in self.headers.get('Accept',''):
                return self.login_page(route)
            return self.send(401,{'error':'Authentication required'})
        if route == '/references':
            self.send_response(302);self.send_header('Location','/references/');self.end_headers();return
        if route.startswith('/references/'):
            return self.reference_get(route)
        if route == '/api/state':
            try: caps = engine().capabilities()
            except Exception as exc: caps = {'available':False,'error':safe_error(exc)}
            with studio.lock:
                rows = studio.db.execute('SELECT * FROM jobs ORDER BY created_at DESC,rowid DESC LIMIT 200').fetchall()
                return self.send(200,{'jobs':[studio.job(row) for row in rows], 'queue_paused':studio.paused(),'capabilities':caps,'active_job_id':studio.active,'read_only':bool(getattr(self.server,'read_only',False))})
        if route.startswith('/media/'):
            ident = route[len('/media/'):]
            if not re.fullmatch('[0-9a-f]{32}',ident): return self.send(404,{'error':'Not found'})
            with studio.lock: row = studio.db.execute('SELECT * FROM assets WHERE id=?',(ident,)).fetchone()
            if not row: return self.send(404,{'error':'Not found'})
            path = Path(row['path']).resolve()
            if not path.is_relative_to(studio.root) or not path.is_file(): return self.send(404,{'error':'Not found'})
            return self.file(path,row['mime'])
        if route.startswith('/api/'): return self.send(404,{'error':'Not found'})
        if route == '/directcut':
            self.send_response(302);self.send_header('Location','/directcut/');self.end_headers();return
        if route.startswith('/directcut/'):
            webroot = (PROJECT / 'apps/directcut/web/dist').resolve()
            relative = route[len('/directcut/'):]
        else:
            webroot = getattr(self.server, 'web_root', HERE / 'web').resolve()
            relative = route.lstrip('/')
        path = (webroot / (relative or 'index.html')).resolve()
        if not path.is_relative_to(webroot): return self.send(404,{'error':'Not found'})
        if not path.is_file() and not Path(relative).suffix: path = webroot/'index.html'
        if not path.is_file(): return self.send(404,{'error':'Not found'})
        return self.file(path,mimetypes.guess_type(path.name)[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.allowed(): return self.send(403,{'error':'Allowed host and same origin required'})
        route = urlsplit(self.path).path
        if getattr(self.server, 'read_only', False) and route not in ('/api/auth/login','/api/auth/logout','/api/estimate','/references/api/export','/references/api/zip'):
            return self.send(403,{'error':'This isolated preview is read-only; generation is disabled'})
        if route not in ('/api/auth/login',) and not self.authenticated():
            return self.send(401,{'error':'Authentication required'})
        try:
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json': raise ValueError('application/json required')
            length = int(self.headers.get('Content-Length','0'))
            body_limit = 4096 if route.startswith('/api/auth/') else MAX_BODY if route == '/api/uploads' else 57 * 1024 * 1024 if route == '/references/api/uploads' else 1024 * 1024
            if not 0 < length <= body_limit: return self.send(413,{'error':'Request too large or empty'})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise ValueError('JSON object required')
            studio = self.server.studio
            route = urlsplit(self.path).path
            if route == '/api/auth/login':
                auth = self.auth()
                if not auth or not auth.required: return self.send(200,{'authenticated':True})
                try: token = auth.login(payload.get('password'))
                except ValueError as exc: return self.send(429,{'error':str(exc)})
                if not token: return self.send(401,{'error':'Invalid password'})
                return self.send(200,{'authenticated':True},cookie=auth.cookie(token))
            if route == '/api/auth/logout':
                auth = self.auth()
                if auth: auth.logout(self.headers.get('Cookie'))
                return self.send(200,{'authenticated':False},cookie=auth.cookie('',clear=True) if auth and auth.required else None)
            if route == '/references/api/collections':
                return self.send(201, self.references().create_collection(payload))
            if route == '/references/api/uploads':
                return self.send(201, self.references().upload_reference(payload))
            if route in ('/references/api/export', '/references/api/zip'):
                if not REFERENCE_EXPORT_LOCK.acquire(blocking=False):
                    return self.send(429, {'error':'An export is already running; try again shortly'})
                try:
                    library = self.references()
                    result = library.export_sheet(payload) if route.endswith('/export') else library.export_zip(payload)
                    return self.reference_binary(result, download=True)
                finally:
                    REFERENCE_EXPORT_LOCK.release()
            if route.startswith('/references/'):
                return self.send(404, {'error':'Reference operation not found'})
            if route == '/api/uploads':
                mime = str(payload.get('mime','')).lower()
                if mime not in ALLOWED_MIME: raise ValueError('Unsupported media type')
                raw = base64.b64decode(payload.get('data',''),validate=True)
                if not raw or len(raw) > MAX_ASSET: raise ValueError('Empty asset or asset exceeds 100 MiB')
                signatures = {'image/png':raw.startswith(b'\x89PNG\r\n\x1a\n'),'image/jpeg':raw.startswith(b'\xff\xd8\xff'),'image/webp':raw[:4]==b'RIFF' and raw[8:12]==b'WEBP'}
                if mime in signatures and not signatures[mime]: raise ValueError('Image content does not match MIME type')
                if mime.startswith('video/') and not (raw[4:8]==b'ftyp' or raw.startswith(b'\x1aE\xdf\xa3')): raise ValueError('Invalid video container')
                audio_valid = {
                    'audio/mpeg': raw.startswith(b'ID3') or raw[:1] == b'\xff',
                    'audio/mp3': raw.startswith(b'ID3') or raw[:1] == b'\xff',
                    'audio/wav': raw[:4] == b'RIFF' and raw[8:12] == b'WAVE',
                    'audio/x-wav': raw[:4] == b'RIFF' and raw[8:12] == b'WAVE',
                    'audio/flac': raw.startswith(b'fLaC'),
                    'audio/ogg': raw.startswith(b'OggS'),
                    'audio/mp4': raw[4:8] == b'ftyp',
                }
                if mime in audio_valid and not audio_valid[mime]: raise ValueError('Invalid audio container')
                ident = uuid.uuid4().hex
                name = re.sub(r'[^\w. -]','_',Path(str(payload.get('name','upload'))).name)[:120] or 'upload'
                extension = {'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','video/mp4':'.mp4','video/quicktime':'.mov','video/webm':'.webm','audio/mpeg':'.mp3','audio/mp3':'.mp3','audio/wav':'.wav','audio/x-wav':'.wav','audio/flac':'.flac','audio/ogg':'.ogg','audio/mp4':'.m4a'}[mime]
                path = studio.root/'uploads'/(ident+extension)
                path.write_bytes(raw)
                with studio.lock:
                    studio.db.execute('INSERT INTO assets VALUES(?,?,?,?)',(ident,name,mime,str(path))); studio.db.commit()
                return self.send(201,{'id':ident,'name':name,'mime':mime,'url':'/media/'+ident})
            if route == '/api/catalog/refresh':
                refresh = getattr(engine(), 'refresh_cloud_catalog', None)
                if not callable(refresh):
                    return self.send(503,{'error':'Cloud catalog refresh is unavailable'})
                with studio.lock:
                    unfinished = studio.db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
                    if unfinished or studio.active:
                        return self.send(409,{'error':'Finish or cancel queued/running jobs before refreshing the model catalog'})
                    try:
                        # Keep enqueue/start serialized with refresh: queued jobs
                        # must not silently change endpoint or pricing underneath.
                        models = refresh()
                        if not isinstance(models,list): raise ValueError('Invalid model catalog response')
                    except Exception as exc:
                        # Do not read or forward upstream HTTP error bodies.
                        return self.send(502,{'error':safe_error(exc)})
                return self.send(200,{'models':models,'refreshed_at':now()})
            if route == '/api/estimate': return self.send(200,studio.estimate(payload))
            if route == '/api/jobs': return self.send(201,{'jobs':studio.enqueue(payload)})
            if route == '/api/queue':
                if not isinstance(payload.get('paused'),bool): raise ValueError('paused must be boolean')
                with studio.lock:
                    studio.db.execute("UPDATE settings SET value=? WHERE key='queue_paused'",(json.dumps(payload['paused']),)); studio.db.commit()
                studio.wake.set()
                return self.send(200,{'queue_paused':payload['paused']})
            match = re.fullmatch(r'/api/jobs/([0-9a-f]{32})/(cancel|retry)',route)
            if match:
                ident,action = match.groups()
                with studio.lock:
                    row = studio.db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
                    if not row: return self.send(404,{'error':'Unknown job'})
                    if action == 'retry':
                        if row['status'] in ('queued','running'): raise ValueError('Cannot retry an active or queued job')
                        return self.send(201,{'jobs':studio.enqueue(json.loads(row['payload']))})
                    if row['status'] not in ('queued','running'): raise ValueError('Job is not cancellable')
                    status = 'cancelled' if row['status']=='queued' else 'running'
                    studio.db.execute('UPDATE jobs SET status=?,cancel_requested=1,updated_at=? WHERE id=?',(status,now(),ident)); studio.db.commit()
                return self.send(200,{'id':ident,'status':status,'cancel_requested':True})
            return self.send(404,{'error':'Not found'})
        except LibraryError as exc: return self.send(exc.status,{'error':safe_error(exc)})
        except (ValueError,TypeError,KeyError,binascii.Error) as exc: return self.send(400,{'error':safe_error(exc)})
        except Exception as exc: return self.send(503,{'error':safe_error(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=36440)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--public-origin')
    parser.add_argument('--allow-loopback-local',action='store_true',help='Keep trusted local UI access without public login; only actual loopback peers with a loopback Host')
    parser.add_argument('--read-only',action='store_true',help='Disable queue/upload/catalog mutations for an isolated source preview')
    parser.add_argument('--web-root',type=Path)
    parser.add_argument('--hash-password',action='store_true')
    parser.add_argument('--root',type=Path,default=PROJECT/'outputs/generation-studio')
    args = parser.parse_args()
    if args.hash_password:
        password = getpass.getpass('New Media Studio password: ')
        if len(password) < 12: parser.error('Use at least 12 characters')
        print(hash_password(password));return
    if args.host not in ('127.0.0.1','localhost') and not args.public_origin:
        parser.error('Non-loopback binding requires --public-origin and authentication')
    auth = Authentication(args.public_origin)
    server = ThreadingHTTPServer((args.host,args.port),Handler)
    server.auth = auth
    server.allow_loopback_local = args.allow_loopback_local
    server.read_only = args.read_only
    server.web_root = args.web_root.resolve() if args.web_root else HERE/'web'
    server.studio = Studio(args.root)
    print(f'Nora Generation Studio: http://127.0.0.1:{server.server_port}/ (queue paused)',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.studio.stopping.set()
        server.studio.wake.set()
        server.server_close()

if __name__ == '__main__': main()
