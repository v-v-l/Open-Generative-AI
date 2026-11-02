#!/usr/bin/env python3
"""Optional loopback-only reference library; uploads/exports, no model execution."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import sys
import threading
from urllib.parse import quote,urlsplit

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'backend'))
from reference_library import Library,LibraryError,byte_range
EXPORT_LOCK=threading.BoundedSemaphore(1)

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(30)
    def log_message(self,*args):pass
    def allowed(self):
        host=self.headers.get('Host','');origin=self.headers.get('Origin')
        return (host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
                and origin in (None,'http://'+host)
                and self.headers.get('Sec-Fetch-Site')!='cross-site')
    def binary(self,data,kind,filename=None,status=200):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        if filename:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(filename,safe=''))
        self.end_headers();self.wfile.write(data)
    def json(self,value,status=200):self.binary(json.dumps(value,ensure_ascii=False).encode(),'application/json; charset=utf-8',status=status)
    def media(self,result,download=False):
        path=result['path'];size=path.stat().st_size
        try:start,end,status=byte_range(self.headers.get('Range'),size)
        except LibraryError:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
        self.send_response(status);self.send_header('Content-Type',result['kind']);self.send_header('Content-Length',str(end-start+1))
        self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(result['filename'],safe=''))
        self.end_headers()
        try:
            with path.open('rb') as stream:
                stream.seek(start);remaining=end-start+1
                while remaining:
                    chunk=stream.read(min(1024*1024,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        if not self.allowed():return self.json({'error':'Same-origin loopback access required'},403)
        route=urlsplit(self.path).path;library=self.server.library
        try:
            if route in ('/','/references'):
                self.send_response(302);self.send_header('Location','/references/');self.end_headers();return
            if route=='/references/api/catalog':return self.json(library.catalog())
            for prefix,operation in (('/references/image/','original'),('/references/file/','original'),('/references/thumb/','thumbnail')):
                if route.startswith(prefix):
                    if operation=='original':return self.media(library.original_file(route[len(prefix):]),prefix.endswith('/file/'))
                    result=getattr(library,operation)(route[len(prefix):]);return self.binary(result['bytes'],result['kind'],result['filename'] if prefix.endswith('/file/') else None)
            name=route.removeprefix('/references/')
            if not route.startswith('/references/') or name not in ('','index.html','app.js','app.css'):return self.json({'error':'Not found'},404)
            p=HERE/'web'/(name or 'index.html');return self.binary(p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
        except LibraryError as error:return self.json({'error':str(error)},error.status)
    def do_POST(self):
        if not self.allowed():return self.json({'error':'Same-origin loopback access required'},403)
        route=urlsplit(self.path).path
        if getattr(self.server,'read_only',False) and route in ('/references/api/collections','/references/api/collections/update','/references/api/uploads','/references/api/remove'):return self.json({'error':'Reference preview is read-only'},403)
        if route not in ('/references/api/export','/references/api/zip','/references/api/collections','/references/api/collections/update','/references/api/uploads','/references/api/remove'):return self.json({'error':'No generation operations exist in this library'},404)
        if not EXPORT_LOCK.acquire(blocking=False):return self.json({'error':'Another export is running'},429)
        try:
            length=int(self.headers.get('Content-Length','0'))
            limit=137*1024*1024 if route=='/references/api/uploads' else 16384
            if self.headers.get('Content-Type','').split(';')[0]!='application/json' or not 0<length<=limit:return self.json({'error':'Bounded JSON request required'},400)
            payload=json.loads(self.rfile.read(length));library=self.server.library
            if route.endswith('/collections'):return self.json(library.create_collection(payload),201)
            if route=='/references/api/collections/update':return self.json(library.update_collection(payload))
            if route.endswith('/uploads'):return self.json(library.upload_reference(payload),201)
            if route.endswith('/remove'):return self.json(library.remove_reference(payload))
            result=library.export_sheet(payload) if route.endswith('/export') else library.export_zip(payload)
            return self.binary(result['bytes'],result['kind'],result['filename'])
        except LibraryError as error:return self.json({'error':str(error)},error.status)
        except (ValueError,TypeError):return self.json({'error':'Invalid request'},400)
        finally:EXPORT_LOCK.release()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,default=36430)
    args=p.parse_args();http=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);http.library=Library(args.root)
    print(f'Reference-only preview: http://127.0.0.1:{http.server_port}/references/',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:http.server_close()

if __name__=='__main__':main()
