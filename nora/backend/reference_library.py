"""Browse original references and compose deterministic sheets without inference.

The portable manifest uses relative ``path`` entries below NORA_REFERENCE_ROOT.
Only those originals are exposed: ``delivery`` and generated/cropped variants
are intentionally ignored. This module performs no network or workflow actions.
"""
from __future__ import annotations

import hashlib
import base64
import binascii
from contextlib import contextmanager
import copy
import fcntl
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import threading
import warnings
import zipfile
import uuid
import datetime as dt
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_PIXELS = 64_000_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ZIP_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')
FORMATS = {'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}
CATEGORIES = {'face','body','outfit','scene','lora'}
VIDEO_FORMATS = {'.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime'}
MAX_VIDEO_BYTES = 100 * 1024 * 1024


class LibraryError(ValueError):
    """Safe public error with an HTTP status for optional routing adapters."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise LibraryError(f'{name} must be an integer from {minimum} to {maximum}')
    return value


def _text(value, limit=500):
    if not isinstance(value, str):
        return ''
    # Metadata is deliberately not a back door for runtime source paths.
    if re.search(r'''(?:^|[\s"'(=])/(?!/)[^\s]+|[A-Za-z]:[\\/]|file://''',value):
        return ''
    return value[:limit]


def _result(filename, kind, data):
    return {'filename':filename,'kind':kind,'bytes':data}


def byte_range(value, size):
    """A single RFC byte range; invalid/unsatisfied input raises a safe 416."""
    if not value:return 0,size-1,200
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
    if not match or not any(match.groups()):raise LibraryError('Invalid byte range',416)
    first,last=match.groups()
    if not first:
        count=int(last)
        if count<=0:raise LibraryError('Invalid byte range',416)
        return max(0,size-count),size-1,206
    start=int(first);end=min(int(last),size-1) if last else size-1
    if start>=size or start>end:raise LibraryError('Byte range is outside the file',416)
    return start,end,206


class Library:
    def __init__(self, root=None):
        configured = root if root is not None else os.environ.get('NORA_REFERENCE_ROOT')
        if not configured:
            raise LibraryError('Reference library is not configured',503)
        self.root = Path(configured).expanduser().resolve()
        self.lock = threading.RLock()
        self._stamp = None
        self.records = {}
        self.metadata = {}
        self.refresh()

    @contextmanager
    def _mutation(self):
        """Serialize multiple Library objects/processes using the same manifest."""
        with self.lock:
            try:
                lock_path=self._path('.library.lock')
                with lock_path.open('a') as stream:
                    fcntl.flock(stream,fcntl.LOCK_EX)
                    self._stamp=None
                    self.refresh()
                    yield
            except OSError:
                raise LibraryError('Reference library could not be saved',503) from None

    def _persist(self, data):
        encoded=json.dumps(data,ensure_ascii=False,indent=2).encode()+b'\n'
        if len(encoded)>MAX_MANIFEST_BYTES:
            raise LibraryError('Reference library metadata limit reached',413)
        target=self._path('manifest.json')
        temporary=self._path('.manifest-'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,target)
            descriptor=os.open(self.root,os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
        self._stamp=None
        self.refresh()

    @staticmethod
    def _slots(category, supplied=None):
        if supplied is None:
            if category in ('face','body'):
                supplied=[{'id':f'a{angle:03d}','title':f'{angle}°','angle_degrees':angle} for angle in range(0,360,45)]
            elif category=='outfit':
                supplied=[{'id':key,'title':key.title()} for key in ('front','back','side','detail')]
            else:
                supplied=[{'id':key,'title':key.title(),'angle_degrees':angle} for key,angle in zip(('front','right','back','left'),range(0,360,90))]
        if not isinstance(supplied,list) or not 1<=len(supplied)<=16:
            raise LibraryError('A reference set needs between 1 and 16 slots')
        slots=[];seen=set()
        for value in supplied:
            if not isinstance(value,dict) or set(value)-{'id','title','angle_degrees'}:
                raise LibraryError('Invalid reference slot')
            identifier=value.get('id')
            title=value.get('title',identifier)
            if not isinstance(identifier,str) or not ID.fullmatch(identifier) or identifier in seen:
                raise LibraryError('Slot IDs must be unique letters, numbers, underscores or hyphens')
            if not isinstance(title,str) or not title.strip() or len(title)>120 or not _text(title):
                raise LibraryError('A slot needs a title of up to 120 characters')
            slot={'id':identifier,'title':title.strip(),'reference_id':None}
            if 'angle_degrees' in value:
                angle=value['angle_degrees']
                if type(angle) not in (int,float) or not math.isfinite(angle) or not 0<=angle<360:
                    raise LibraryError('Slot angle must be from 0 to less than 360 degrees')
                slot['angle_degrees']=angle
            slots.append(slot);seen.add(identifier)
        return slots

    def _collections(self):
        """Expose reusable user sets and portable read-only legacy groups."""
        collections=[]
        for source in self.metadata.get('collections',[]):
            collection={key:source[key] for key in ('id','title','category')}
            collection['read_only']=False
            collection['slots']=[{key:slot[key] for key in ('id','title','reference_id','angle_degrees') if key in slot} for slot in source['slots']]
            if source['category']=='lora':collection['items']=list(source.get('items',[]))
            collections.append(collection)
        grouped={}
        for identifier,record in self.records.items():
            if record.get('collection_id'):
                continue
            category=record.get('category','face')
            name=record.get('collection') or category
            key='legacy-'+str(name) if ID.fullmatch('legacy-'+str(name)) else 'legacy-'+hashlib.sha256(str(name).encode()).hexdigest()[:16]
            group=grouped.setdefault(key,{'id':key,'title':_text(str(name).replace('head360','Head 360°')),
                                          'category':category,'read_only':True,'slots':[]})
            slot={'id':identifier,'title':_text(record.get('title',identifier)),'reference_id':identifier}
            if name=='head360' and re.fullmatch(r'H\d{3}',identifier):
                slot['angle_degrees']=int(identifier[1:])
            group['slots'].append(slot)
        return collections+list(grouped.values())

    def create_collection(self, payload):
        if not isinstance(payload,dict) or set(payload)-{'title','category','slots'}:
            raise LibraryError('Only a title, category and optional slots are accepted')
        title=payload.get('title');category=payload.get('category')
        if not isinstance(title,str) or not title.strip() or len(title)>120 or not _text(title):
            raise LibraryError('A reference set needs a title of up to 120 characters')
        if not isinstance(category,str) or category not in CATEGORIES:
            raise LibraryError('Category must be face, body, outfit, scene or lora')
        collection={'id':'set-'+uuid.uuid4().hex,'title':title.strip(),'category':category,
                    'slots':[] if category=='lora' else self._slots(category,payload.get('slots')),'read_only':False}
        if category=='lora':
            if payload.get('slots'):raise LibraryError('LoRA datasets contain free items, not angle slots')
            collection['items']=[]
        with self._mutation():
            data=copy.deepcopy(self.metadata)
            if len(data.get('collections',[]))>=200:
                raise LibraryError('Reference set limit reached',413)
            data.setdefault('collections',[]).append(collection)
            self._persist(data)
        return {'collection':copy.deepcopy(collection)}

    def upload_reference(self, payload):
        if not isinstance(payload,dict) or set(payload)-{'collection_id','slot_id','name','mime','data','replace_id'}:
            raise LibraryError('Unsupported reference upload fields')
        name=payload.get('name');mime=payload.get('mime');encoded=payload.get('data')
        if not isinstance(name,str) or not name or len(name)>240 or '/' in name or '\\' in name or any(ord(c)<32 for c in name):
            raise LibraryError('Upload name must be a filename without a path')
        if not isinstance(mime,str) or mime not in (*FORMATS.values(),*VIDEO_FORMATS.values()):
            raise LibraryError('Upload a PNG, JPEG, WebP, MP4, WebM or MOV original')
        video=mime in VIDEO_FORMATS.values()
        maximum=MAX_VIDEO_BYTES if video else MAX_UPLOAD_BYTES
        if not isinstance(encoded,str) or not encoded or len(encoded)>4*((maximum+2)//3):
            raise LibraryError('Reference upload exceeds its '+str(maximum//1024//1024)+' MiB limit',413)
        try:
            raw=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):
            raise LibraryError('Invalid reference image encoding') from None
        if not raw or len(raw)>maximum:
            raise LibraryError('Reference upload exceeds its '+str(maximum//1024//1024)+' MiB limit',413)
        media_metadata={}
        if video:
            media_metadata=self._probe_video(raw,mime)
            size=media_metadata.pop('size')
        else:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error',Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as image:
                        expected={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}.get(image.format)
                        if expected!=mime or getattr(image,'n_frames',1)!=1:
                            raise LibraryError('MIME type must match a single original image')
                        if image.width*image.height>MAX_PIXELS:
                            raise LibraryError('Reference image exceeds the 64 megapixel limit',413)
                        size=list(image.size)
                        image.verify()
                    with Image.open(io.BytesIO(raw)) as image:
                        image.load()
                        with ImageOps.exif_transpose(image) as oriented:size=list(oriented.size)
            except LibraryError:
                raise
            except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
                raise LibraryError('Upload is not a valid bounded raster image') from None
        identifier='U'+uuid.uuid4().hex
        extension={**{v:k for k,v in FORMATS.items()},**{v:k for k,v in VIDEO_FORMATS.items()}}[mime]
        relative='uploads/'+identifier+extension
        with self._mutation():
            if len(self.metadata['records'])>=5000:
                raise LibraryError('Reference image limit reached',413)
            data=copy.deepcopy(self.metadata)
            collection=next((item for item in data.get('collections',[]) if item['id']==payload.get('collection_id')),None)
            if collection is None:
                raise LibraryError('Unknown editable reference set',404)
            if video and collection['category']!='lora':raise LibraryError('Videos can only be added to a LoRA dataset')
            if collection['category']=='lora':
                if payload.get('slot_id'):raise LibraryError('LoRA dataset uploads do not use angle slots')
                slot={'id':None,'title':name,'reference_id':None}
            else:
                slot=next((item for item in collection['slots'] if item['id']==payload.get('slot_id')),None)
                if slot is None:raise LibraryError('Unknown reference slot',404)
            previous=slot.get('reference_id')
            replacement=payload.get('replace_id')
            if replacement is not None and (not isinstance(replacement,str) or not ID.fullmatch(replacement)):
                raise LibraryError('Invalid replacement reference')
            if collection['category']=='lora':
                if replacement is not None:
                    self._owned_reference(data,replacement,collection['id'])
                    previous=replacement
            elif previous!=replacement:
                raise LibraryError('This slot changed; reload before replacing it',409)
            if previous:
                old,_=self._owned_reference(data,previous,collection['id'])
                self._archive(data,old,'replaced')
            record={'id':identifier,'path':relative,'category':collection['category'],'collection':collection['id'],
                    'collection_id':collection['id'],'slot_id':slot['id'],'title':slot['title'],'status':'user_supplied',
                    'source_kind':'individual','size':size,'sha256':hashlib.sha256(raw).hexdigest(),'original_name':name,
                    'mime':mime,'media_kind':'video' if video else 'image',**media_metadata,'tags':[],'parent_review':{'verdict':'user_supplied','user_approval':False}}
            if 'angle_degrees' in slot:record['angle_degrees']=slot['angle_degrees']
            data['records'].append(record)
            if collection['category']=='lora':
                if previous:collection['items'][collection['items'].index(previous)]=identifier
                else:collection['items'].append(identifier)
            else:slot['reference_id']=identifier
            directory=self._path('uploads');directory.mkdir(exist_ok=True)
            target=self._path(relative)
            try:
                with target.open('xb') as stream:
                    stream.write(raw);stream.flush();os.fsync(stream.fileno())
                self._persist(data)
            except BaseException:
                # Retain the new original on an uncertain fsync/manifest failure.
                # An orphan is recoverable; deleting a possibly committed asset
                # would leave a manifest pointer to a missing photograph.
                raise
            public=next(item for item in self.catalog()['records'] if item['id']==identifier)
            return {'collection':copy.deepcopy(collection),'record':public,'replaced_reference_id':previous}

    @staticmethod
    def _owned_reference(data, identifier, expected_collection=None, require_current=True):
        record=next((record for record in data['records'] if record['id']==identifier),None)
        if record is None or record.get('archived'):
            raise LibraryError('Reference changed or is no longer active; reload the library',409)
        collection=next((item for item in data.get('collections',[]) if item['id']==record.get('collection_id')),None)
        if collection is None or collection.get('read_only'):
            raise LibraryError('Legacy references cannot be replaced or removed',403)
        if expected_collection is not None and collection['id']!=expected_collection:
            raise LibraryError('Reference is not a current member of this set',409)
        if collection['category']=='lora':
            current=identifier in collection['items']
        else:
            current=any(slot.get('reference_id')==identifier and slot['id']==record.get('slot_id') for slot in collection['slots'])
        if require_current and not current:raise LibraryError('Reference is not a current member of this set',409)
        return record,collection

    @staticmethod
    def _archive(data, record, reason):
        record.update(archived=True,archived_reason=reason,archived_at=dt.datetime.now(dt.timezone.utc).isoformat())
        defaults=data.get('defaults')
        if isinstance(defaults,dict):
            data['defaults']={key:value for key,value in defaults.items() if value!=record['id']}

    def remove_reference(self, payload):
        if not isinstance(payload,dict) or set(payload)!={'id'} or not isinstance(payload['id'],str) or not ID.fullmatch(payload['id']):
            raise LibraryError('Provide the ID of one reference to remove')
        with self._mutation():
            data=copy.deepcopy(self.metadata)
            record,collection=self._owned_reference(data,payload['id'],require_current=False)
            if collection['category']=='lora':
                if record['id'] in collection['items']:collection['items'].remove(record['id'])
            else:
                for slot in collection['slots']:
                    if slot.get('reference_id')==record['id']:slot['reference_id']=None
            self._archive(data,record,'removed')
            self._persist(data)
            return {'removed_id':record['id'],'collection':copy.deepcopy(collection)}

    @staticmethod
    def _probe_video(raw, mime):
        """Probe a private local file with no network/playlist demuxers enabled."""
        suffix={value:key for key,value in VIDEO_FORMATS.items()}[mime]
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix) as source:
                source.write(raw);source.flush()
                result=subprocess.run([os.environ.get('NORA_FFPROBE_BIN','ffprobe'),'-v','error','-protocol_whitelist','file',
                    '-format_whitelist','mov,matroska,webm','-select_streams','v:0',
                    '-show_entries','format=format_name,duration:stream=codec_name,codec_type,width,height',
                    '-of','json',source.name],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12,check=False)
            if result.returncode or len(result.stdout)>65536:
                raise LibraryError('Upload is not a valid supported video')
            data=json.loads(result.stdout)
            container=data.get('format',{}).get('format_name','')
            valid=('matroska' in container or 'webm' in container) if mime=='video/webm' else 'mov' in container
            streams=data.get('streams',[])
            stream=streams[0] if streams else {}
            width,height=stream.get('width',0),stream.get('height',0)
            duration=float(data.get('format',{}).get('duration',0))
            if not valid or stream.get('codec_type')!='video' or stream.get('codec_name') in (None,'unknown'):
                raise LibraryError('Video MIME type must match its actual container and video stream')
            if type(width) is not int or type(height) is not int or not 0<width<=16384 or not 0<height<=16384 or width*height>MAX_PIXELS or not math.isfinite(duration) or not 0<duration<=86400:
                raise LibraryError('Video dimensions or duration exceed the supported budget',413)
            return {'size':[width,height],'duration_seconds':duration}
        except FileNotFoundError:
            raise LibraryError('Video uploads are unavailable: ffprobe is not installed',503) from None
        except subprocess.TimeoutExpired:
            raise LibraryError('Video validation exceeded its time limit',413) from None
        except (OSError,ValueError,KeyError,TypeError) as exc:
            if isinstance(exc,LibraryError):raise
            raise LibraryError('Video could not be validated') from None

    def original_file(self, identifier):
        """Trusted routing adapter may stream this path; never serialize it to JSON."""
        record=self._record(identifier)
        path=self._asset(record)
        if path.suffix.lower() not in VIDEO_FORMATS:
            with self._image(record):pass
        return {'path':path,'filename':identifier+path.suffix.lower(),
                'kind':{**FORMATS,**VIDEO_FORMATS}[path.suffix.lower()]}

    def _path(self, relative):
        if not isinstance(relative,str) or not relative or '\\' in relative:
            raise LibraryError('Reference manifest contains an invalid relative path',503)
        path = PurePosixPath(relative)
        if path.is_absolute() or '..' in path.parts or ':' in relative:
            raise LibraryError('Reference manifest contains an invalid relative path',503)
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root):
            raise LibraryError('Reference asset escapes its library root',503)
        return resolved

    def refresh(self):
        with self.lock:
            try:
                manifest = self._path('manifest.json')
                stat = manifest.stat()
                stamp = (stat.st_mtime_ns,stat.st_size)
                if stamp == self._stamp:
                    return
                if stat.st_size > MAX_MANIFEST_BYTES:
                    raise LibraryError('Reference manifest exceeds its size limit',503)
                data = json.loads(manifest.read_bytes())
                if not isinstance(data,dict) or not isinstance(data.get('records'),list) or len(data['records']) > 5000:
                    raise LibraryError('Reference manifest has an unsupported structure',503)
                records = {}
                for record in data['records']:
                    if not isinstance(record,dict):
                        raise LibraryError('Reference manifest has an invalid record',503)
                    identifier = record.get('id')
                    if not isinstance(identifier,str) or not ID.fullmatch(identifier) or identifier in records:
                        raise LibraryError('Reference manifest has an invalid or duplicate ID',503)
                    if 'archived' in record and type(record['archived']) is not bool:
                        raise LibraryError('Reference manifest has an invalid archive state',503)
                    if record.get('source_kind','individual') != 'individual':
                        raise LibraryError('Reference library accepts original individual photographs only',503)
                    if not isinstance(record.get('category'),str) or record['category'] not in CATEGORIES:
                        raise LibraryError('Reference manifest has an invalid category',503)
                    if record.get('collection') is not None and (not isinstance(record['collection'],str) or not ID.fullmatch(record['collection'])):
                        raise LibraryError('Reference manifest has an invalid collection name',503)
                    path = self._path(record.get('path'))
                    if path.suffix.lower() not in {**FORMATS,**VIDEO_FORMATS}:
                        raise LibraryError('Reference manifest supports raster images and video only',503)
                    if path.suffix.lower() in VIDEO_FORMATS and record['category']!='lora':raise LibraryError('Video references require a LoRA dataset',503)
                    records[identifier] = dict(record)
                collections=data.get('collections',[])
                if not isinstance(collections,list) or len(collections)>200:
                    raise LibraryError('Reference manifest has invalid collections',503)
                seen=set()
                for collection in collections:
                    if not isinstance(collection,dict) or not isinstance(collection.get('id'),str) or not ID.fullmatch(collection['id']) or collection['id'] in seen:
                        raise LibraryError('Reference manifest has an invalid collection ID',503)
                    if collection.get('category') not in CATEGORIES or not _text(collection.get('title')):
                        raise LibraryError('Reference manifest has invalid collection metadata',503)
                    slots=collection.get('slots')
                    if not isinstance(slots,list):
                        raise LibraryError('Reference manifest has invalid slots',503)
                    if collection['category']=='lora':
                        items=collection.get('items',[])
                        if slots or not isinstance(items,list) or len(items)>5000 or any(not isinstance(i,str) or i not in records or records[i].get('archived') for i in items) or len(set(items))!=len(items):
                            raise LibraryError('Invalid LoRA dataset items',503)
                        seen.add(collection['id']);continue
                    try:
                        self._slots(collection['category'],[{key:value for key,value in slot.items() if key!='reference_id'} for slot in slots])
                    except (LibraryError,AttributeError,TypeError):
                        raise LibraryError('Reference manifest has invalid slots',503) from None
                    for slot in slots:
                        if slot.get('reference_id') is not None and (slot.get('reference_id') not in records or records[slot['reference_id']].get('archived')):
                            raise LibraryError('Reference slot points to an unknown original',503)
                    seen.add(collection['id'])
                self.records = {key:value for key,value in records.items() if not value.get('archived')}
                self.metadata = data
                self._stamp = stamp
            except (OSError,ValueError,TypeError) as exc:
                if isinstance(exc,LibraryError):
                    raise
                raise LibraryError('Reference library is unavailable or its manifest is invalid',503) from None

    def _record(self, identifier):
        self.refresh()
        if not isinstance(identifier,str) or not ID.fullmatch(identifier) or identifier not in self.records:
            raise LibraryError('Unknown reference',404)
        return self.records[identifier]

    def _asset(self, record):
        path = self._path(record.get('path'))
        try:
            size = path.stat().st_size
            maximum=MAX_VIDEO_BYTES if path.suffix.lower() in VIDEO_FORMATS else MAX_FILE_BYTES
            if not path.is_file() or not 0 < size <= maximum:
                raise LibraryError('Reference file exceeds its size limit',413)
            return path
        except OSError:
            raise LibraryError('Reference image is unavailable',404) from None

    def _image(self, record):
        path = self._asset(record)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                image = Image.open(path)
                if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height > MAX_PIXELS:
                    image.close()
                    raise LibraryError('Reference image exceeds the supported image budget',413)
                image = ImageOps.exif_transpose(image)
                image.load()
                return image
        except LibraryError:
            raise
        except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise LibraryError('Reference image is invalid or exceeds its size limit',413) from None

    def catalog(self, base_url='/references'):
        self.refresh()
        base = base_url.rstrip('/')
        if not base.startswith('/') or base.startswith('//') or '?' in base or '#' in base:
            raise LibraryError('Catalog URL must be a local path')
        records = []
        with self.lock:
            for identifier, record in self.records.items():
                public = {key:_text(record[key]) for key in ('category','collection','collection_id','slot_id','title','status','original_name') if key in record}
                public['id'] = identifier
                public['source_kind'] = 'individual'
                media_kind='video' if Path(record['path']).suffix.lower() in VIDEO_FORMATS else 'image'
                public['media_kind']=media_kind
                public['mime']={**FORMATS,**VIDEO_FORMATS}[Path(record['path']).suffix.lower()]
                if media_kind=='video':
                    public['video_url']=base+'/image/'+identifier
                    duration=record.get('duration_seconds')
                    if type(duration) in (int,float) and math.isfinite(duration):public['duration_seconds']=duration
                public['tags'] = [_text(v,150) for v in record.get('tags',[])[:30]] if isinstance(record.get('tags'),list) else []
                size = record.get('size')
                if isinstance(size,list) and len(size)==2 and all(type(n) is int and 0<n<=100000 for n in size):
                    public['size'] = size
                digest=record.get('sha256')
                if isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest):
                    public['sha256']=digest
                review=record.get('parent_review')
                if isinstance(review,dict):
                    public['parent_review']={key:_text(review[key]) for key in ('verdict','note') if key in review}
                    if type(review.get('user_approval')) is bool:
                        public['parent_review']['user_approval']=review['user_approval']
                angle=record.get('angle_degrees',record.get('angle'))
                if angle is None and record.get('collection')=='head360' and re.fullmatch(r'H\d{3}',identifier):
                    angle=int(identifier[1:])
                if type(angle) in (int,float) and math.isfinite(angle) and 0<=angle<360:
                    public.update(angle_degrees=angle,angle_is_nominal=True)
                public.update(image_url=base+'/image/'+identifier,thumb_url=base+'/thumb/'+identifier,download_url=base+'/file/'+identifier)
                records.append(public)
            defaults=self.metadata.get('defaults',{})
            missing=self.metadata.get('missing',{})
            return {'character':_text(self.metadata.get('character',''),100),'records':records,
                    'defaults':{_text(k,80):v for k,v in defaults.items() if isinstance(v,str) and v in self.records} if isinstance(defaults,dict) else {},
                    'missing':{_text(k,80):[_text(v) for v in values[:30]] for k,values in missing.items() if isinstance(values,list)} if isinstance(missing,dict) else {},
                    'policy':_text(self.metadata.get('policy','')),'collections':self._collections(),
                    'supports_zip':True,'supports_uploads':True,'export_formats':['png','zip'],
                    'limits':{'max_references':16,'max_columns':8,'max_pixels':MAX_PIXELS,'max_dimension':16384,'max_upload_bytes':MAX_UPLOAD_BYTES,'max_video_bytes':MAX_VIDEO_BYTES,'max_video_upload_bytes':MAX_VIDEO_BYTES}}

    def original(self, identifier):
        record=self._record(identifier)
        video=Path(record['path']).suffix.lower() in VIDEO_FORMATS
        if not video:
            with self._image(record):pass
        path=self._asset(record)
        try:
            data=path.read_bytes()
        except OSError:
            raise LibraryError('Reference image is unavailable',404) from None
        if len(data)>(MAX_VIDEO_BYTES if video else MAX_FILE_BYTES):
            raise LibraryError('Reference file exceeds its size limit',413)
        return _result(identifier+path.suffix.lower(),{**FORMATS,**VIDEO_FORMATS}[path.suffix.lower()],data)

    def thumbnail(self, identifier, size=320):
        _integer(size,'Thumbnail size',32,1024)
        if Path(self._record(identifier)['path']).suffix.lower() in VIDEO_FORMATS:raise LibraryError('Use the video playback URL for video references',400)
        with self._image(self._record(identifier)) as original:
            image=ImageOps.contain(original.convert('RGBA'),(size,size),Image.Resampling.LANCZOS)
            canvas=Image.new('RGB',image.size,'white')
            canvas.paste(image,mask=image.getchannel('A'))
            output=io.BytesIO();canvas.save(output,format='JPEG',quality=85,optimize=False)
        return _result(identifier+'.jpg','image/jpeg',output.getvalue())

    def _selection(self, payload, allowed):
        if not isinstance(payload,dict) or set(payload)-allowed:
            raise LibraryError('Unsupported reference export fields')
        identifiers=payload.get('ids')
        if not isinstance(identifiers,list) or not 1<=len(identifiers)<=16:
            raise LibraryError('Select between 1 and 16 original references')
        records=[];seen=set()
        for identifier in identifiers:
            record=self._record(identifier)
            if identifier in seen:
                raise LibraryError('Select each reference only once')
            seen.add(identifier);records.append(record)
        return identifiers,records

    def export_sheet(self, payload):
        identifiers,records=self._selection(payload,{'ids','columns','cell_width','cell_height','labels'})
        if any(Path(record['path']).suffix.lower() in VIDEO_FORMATS for record in records):raise LibraryError('PNG sheets support photographs only; remove videos or download ZIP')
        columns=_integer(payload.get('columns',4),'Columns',1,8)
        width=_integer(payload.get('cell_width',768),'Cell width',32,16384)
        height=_integer(payload.get('cell_height',1024),'Cell height',32,16384)
        labels=payload.get('labels',False)
        if type(labels) is not bool:
            raise LibraryError('Labels must be true or false')
        rows=math.ceil(len(records)/columns)
        label_height=28 if labels else 0
        dimensions=(width*columns,(height+label_height)*rows)
        if max(dimensions)>16384 or dimensions[0]*dimensions[1]>MAX_PIXELS:
            raise LibraryError('Sheet exceeds the 16384 dimension or 64 megapixel render limit',413)
        # Budget is checked before allocating the sheet or decoding any original.
        sheet=Image.new('RGB',dimensions,'white')
        draw=ImageDraw.Draw(sheet)
        for index,record in enumerate(records):
            x=(index%columns)*width;y=(index//columns)*(height+label_height)
            with self._image(record) as original:
                fitted=ImageOps.contain(original.convert('RGBA'),(width,height),Image.Resampling.LANCZOS)
                sheet.paste(fitted,(x+(width-fitted.width)//2,y+(height-fitted.height)//2),fitted.getchannel('A'))
            if labels:
                draw.text((x+8,y+height+5),identifiers[index],fill='black',font=ImageFont.load_default())
        output=io.BytesIO();sheet.save(output,format='PNG',compress_level=6)
        fingerprint=hashlib.sha256(json.dumps({'ids':identifiers,'columns':columns,'cell_width':width,'cell_height':height,'labels':labels},sort_keys=True).encode()).hexdigest()[:12]
        return _result('references-'+fingerprint+'.png','image/png',output.getvalue())

    def export_zip(self, payload):
        identifiers,records=self._selection(payload,{'ids'})
        paths=[self._asset(record) for record in records]
        if sum(path.stat().st_size for path in paths)>MAX_ZIP_BYTES:
            raise LibraryError('Selected originals exceed the 256 MiB archive limit',413)
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
            for identifier in identifiers:
                original=self.original(identifier)
                info=zipfile.ZipInfo(original['filename'],date_time=(1980,1,1,0,0,0))
                info.external_attr=0o100644<<16
                archive.writestr(info,original['bytes'])
                if output.tell()>MAX_ZIP_BYTES:
                    raise LibraryError('Selected originals exceed the 256 MiB archive limit',413)
        fingerprint=hashlib.sha256(json.dumps(identifiers).encode()).hexdigest()[:12]
        return _result('references-'+fingerprint+'.zip','application/zip',output.getvalue())
