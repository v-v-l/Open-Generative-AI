"""Reference exports preserve originals, framing and selection without inference."""
import io
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import concurrent.futures

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import reference_library as refs


class ReferenceLibraryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'images').mkdir()
        records=[]
        for index,(size,color) in enumerate([((40,80),'red'),((80,40),'blue')]):
            identifier=['H000','H045'][index]
            image=Image.new('RGB',size,color)
            image.putpixel((0,0),(0,255,0));image.putpixel((size[0]-1,size[1]-1),(255,255,0))
            image.save(self.root/f'images/{identifier}.png')
            records.append({'id':identifier,'path':f'images/{identifier}.png','category':'face','collection':'head360',
                            'title':f'{index*45}°','size':list(size),'status':'candidate','tags':['upright'],
                            'delivery':'/private/never-use.png','evidence':'/home/victor/private/file',
                            'parent_review':{'verdict':'candidate','note':'Review pending','user_approval':False,'internal_path':'/secret'}})
        self.manifest={'character':'Alice','records':records,'defaults':{'face':'H000'},'missing':{'head360':['90°']}}
        self.write_manifest()
        self.library=refs.Library(self.root)

    def tearDown(self):self.temp.cleanup()

    def write_manifest(self):
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))

    def test_catalog_preserves_review_and_nominal_angles_without_paths(self):
        catalog=self.library.catalog()
        encoded=json.dumps(catalog)
        for private in ('/private','/home/','/secret','internal_path','delivery','evidence'):
            self.assertNotIn(private,encoded)
        self.assertEqual([r['angle_degrees'] for r in catalog['records']],[0,45])
        self.assertEqual(catalog['records'][1]['status'],'candidate')
        self.assertFalse(catalog['records'][1]['parent_review']['user_approval'])
        self.assertTrue(catalog['records'][1]['angle_is_nominal'])
        self.assertEqual(catalog['records'][0]['image_url'],'/references/image/H000')
        self.assertEqual(catalog['missing'],{'head360':['90°']})

    def test_original_and_zip_are_byte_exact_and_archive_order_is_selected(self):
        for identifier in ('H000','H045'):
            self.assertEqual(self.library.original(identifier)['bytes'],(self.root/f'images/{identifier}.png').read_bytes())
        payload={'ids':['H045','H000']}
        result=self.library.export_zip(payload)
        self.assertEqual(result,self.library.export_zip(payload))
        with zipfile.ZipFile(io.BytesIO(result['bytes'])) as archive:
            self.assertEqual(archive.namelist(),['H045.png','H000.png'])
            self.assertEqual(archive.read('H000.png'),self.library.original('H000')['bytes'])

    def test_sheet_keeps_full_framing_and_selected_order_with_no_labels_by_default(self):
        payload={'ids':['H045','H000'],'columns':2,'cell_width':80,'cell_height':80}
        result=self.library.export_sheet(payload)
        self.assertEqual(result,self.library.export_sheet(payload))
        with Image.open(io.BytesIO(result['bytes'])) as image:
            self.assertEqual(image.size,(160,80))
            self.assertEqual(image.getpixel((40,40)),(0,0,255))
            self.assertEqual(image.getpixel((120,40)),(255,0,0))
            self.assertEqual(image.getpixel((0,0)),(255,255,255))
            # Both opposite corners survive contain, so neither photo was cropped.
            self.assertEqual(image.getpixel((0,20)),(0,255,0))
            self.assertEqual(image.getpixel((79,59)),(255,255,0))
            self.assertEqual(image.getpixel((100,0)),(0,255,0))
            self.assertEqual(image.getpixel((139,79)),(255,255,0))

    def test_labels_optional_thumbnail_contains_full_image(self):
        result=self.library.export_sheet({'ids':['H000'],'columns':1,'cell_width':80,'cell_height':80,'labels':True})
        with Image.open(io.BytesIO(result['bytes'])) as image:self.assertEqual(image.size,(80,108))
        with Image.open(io.BytesIO(self.library.thumbnail('H045',size=80)['bytes'])) as image:
            self.assertEqual(image.size,(80,40))

    def test_rejects_bad_selection_and_budget_before_allocating(self):
        for payload in ({'ids':[]},{'ids':['H000','H000']},{'ids':['../secret']},{'ids':['unknown']},
                        {'ids':['H000'],'columns':True},{'ids':['H000'],'labels':'false'},
                        {'ids':['H000'],'prompt':'not permitted'},{'ids':['H000']*17}):
            with self.assertRaises(refs.LibraryError):self.library.export_sheet(payload)
        with patch.object(refs.Image,'new',side_effect=AssertionError('must not allocate')):
            with self.assertRaises(refs.LibraryError) as error:
                self.library.export_sheet({'ids':['H000','H045'],'columns':2,'cell_width':8192,'cell_height':8192})
            self.assertEqual(error.exception.status,413)

    def test_rejects_traversal_absolute_paths_and_symlink_escape(self):
        for bad in ('../outside.png','/etc/passwd','images\\outside.png','file:///etc/passwd'):
            self.manifest['records'][0]['path']=bad;self.write_manifest()
            with self.assertRaises(refs.LibraryError):refs.Library(self.root)
        with tempfile.TemporaryDirectory() as outside:
            Image.new('RGB',(40,40)).save(Path(outside)/'secret.png')
            (self.root/'images/link.png').symlink_to(Path(outside)/'secret.png')
            self.manifest['records'][0]['path']='images/link.png';self.write_manifest()
            with self.assertRaises(refs.LibraryError):refs.Library(self.root)

    def test_rechecks_symlink_after_manifest_was_loaded(self):
        path=self.root/'images/H000.png';path.unlink();path.symlink_to('/etc/passwd')
        with self.assertRaises(refs.LibraryError):self.library.original('H000')

    def test_duplicate_manifest_ids_and_nonimage_rejected(self):
        self.manifest['records'][1]['id']='H000';self.write_manifest()
        with self.assertRaises(refs.LibraryError):refs.Library(self.root)
        self.manifest['records'][1]['id']='H045';self.write_manifest()
        (self.root/'images/H000.png').write_bytes(b'not a photo')
        with self.assertRaises(refs.LibraryError):refs.Library(self.root).original('H000')

    def test_manifest_declared_grid_cells_are_not_admitted_as_originals(self):
        self.manifest['records'][0]['source_kind']='grid_cell';self.write_manifest()
        with self.assertRaises(refs.LibraryError):refs.Library(self.root)

    def test_unconfigured_and_missing_library_return_safe_errors(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(refs.LibraryError) as error:refs.Library()
            self.assertEqual(error.exception.status,503)
        with self.assertRaises(refs.LibraryError) as error:refs.Library(self.root/'missing')
        self.assertEqual(error.exception.status,503)
        self.assertNotIn(str(self.root),str(error.exception))

    def upload(self, collection, slot='a000', **changes):
        raw=(self.root/'images/H000.png').read_bytes()
        payload={'collection_id':collection['id'],'slot_id':slot,'name':'original.png','mime':'image/png','data':base64.b64encode(raw).decode()}
        payload.update(changes)
        return self.library.upload_reference(payload)

    def test_create_sets_persists_empty_slots_and_preserves_legacy(self):
        original_records=json.loads((self.root/'manifest.json').read_text())['records']
        for category,count in [('face',8),('body',8),('outfit',4),('scene',4)]:
            collection=self.library.create_collection({'title':'My '+category,'category':category})['collection']
            self.assertEqual(len(collection['slots']),count)
            self.assertTrue(all(slot['reference_id'] is None for slot in collection['slots']))
            if category in ('face','body'):
                self.assertEqual([s['angle_degrees'] for s in collection['slots']],list(range(0,360,45)))
        reopened=refs.Library(self.root)
        self.assertEqual(len([c for c in reopened.catalog()['collections'] if not c['read_only']]),4)
        self.assertEqual(json.loads((self.root/'manifest.json').read_text())['records'],original_records)

    def test_upload_is_exact_unreviewed_and_replacement_retains_original(self):
        collection=self.library.create_collection({'title':'Alice face','category':'face'})['collection']
        raw=(self.root/'images/H000.png').read_bytes()
        first=self.upload(collection)
        record=first['record']
        self.assertEqual(record['status'],'user_supplied')
        self.assertEqual(record['source_kind'],'individual')
        self.assertFalse(record['parent_review']['user_approval'])
        self.assertEqual(record['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.library.original(record['id'])['bytes'],raw)
        self.assertIsNone(first['replaced_reference_id'])
        second=self.upload(collection)
        self.assertNotEqual(second['record']['id'],record['id'])
        self.assertEqual(second['replaced_reference_id'],record['id'])
        self.assertEqual(second['collection']['slots'][0]['reference_id'],second['record']['id'])
        self.assertEqual(self.library.original(record['id'])['bytes'],raw)
        catalog=refs.Library(self.root).catalog()
        saved=next(c for c in catalog['collections'] if c['id']==collection['id'])
        self.assertEqual(saved['slots'][0]['reference_id'],second['record']['id'])
        self.assertEqual(len(catalog['records']),4)

    def test_rejects_upload_mime_paths_bad_data_unknown_slot_and_oversize_before_decode(self):
        collection=self.library.create_collection({'title':'Alice body','category':'body'})['collection']
        for changes in ({'mime':'image/svg+xml'},{'mime':'image/jpeg'}, {'name':'../original.png'}, {'name':'C:\\image.png'},
                        {'data':'invalid base64!'}, {'slot_id':'unknown'}, {'collection_id':'legacy-head360'}):
            with self.assertRaises(refs.LibraryError):self.upload(collection,**changes)
        with patch.object(refs,'MAX_UPLOAD_BYTES',3),patch.object(refs.base64,'b64decode',side_effect=AssertionError('must not decode')):
            with self.assertRaises(refs.LibraryError) as error:self.upload(collection)
            self.assertEqual(error.exception.status,413)
        self.assertEqual(len(self.library.catalog()['records']),2)

    def test_concurrent_library_instances_do_not_lose_sets_or_uploads(self):
        first=refs.Library(self.root);second=refs.Library(self.root)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda args:args[0].create_collection({'title':args[1],'category':'face'}),[(first,'One'),(second,'Two')]))
        self.assertEqual(len([c for c in self.library.catalog()['collections'] if not c['read_only']]),2)
        collection=results[0]['collection']
        raw=(self.root/'images/H000.png').read_bytes()
        def submit(args):
            library,slot=args
            return library.upload_reference({'collection_id':collection['id'],'slot_id':slot,'name':'a.png','mime':'image/png','data':base64.b64encode(raw).decode()})
        with concurrent.futures.ThreadPoolExecutor(2) as pool:uploads=list(pool.map(submit,[(first,'a000'),(second,'a045')]))
        saved=next(c for c in self.library.catalog()['collections'] if c['id']==collection['id'])
        self.assertEqual([s['reference_id'] for s in saved['slots'][:2]],[u['record']['id'] for u in uploads])

    def test_manifest_replace_failure_preserves_prior_state_and_originals(self):
        collection=self.library.create_collection({'title':'Alice face','category':'face'})['collection']
        before=(self.root/'manifest.json').read_bytes()
        with patch.object(refs.os,'replace',side_effect=OSError('storage unavailable')):
            with self.assertRaises(refs.LibraryError) as error:self.upload(collection)
            self.assertEqual(error.exception.status,503)
        self.assertEqual((self.root/'manifest.json').read_bytes(),before)
        self.assertEqual(len(refs.Library(self.root).catalog()['records']),2)
        self.assertEqual(self.library.original('H000')['bytes'],(self.root/'images/H000.png').read_bytes())

    def test_upload_directory_symlink_escape_cannot_write_outside_root(self):
        collection=self.library.create_collection({'title':'Alice face','category':'face'})['collection']
        with tempfile.TemporaryDirectory() as outside:
            (self.root/'uploads').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(refs.LibraryError):self.upload(collection)
            self.assertEqual(list(Path(outside).iterdir()),[])

    def test_custom_outfit_slots_and_invalid_collection_inputs(self):
        result=self.library.create_collection({'title':'Dress','category':'outfit','slots':[{'id':'back','title':'Open back'},{'id':'hem','title':'Hem detail'}]})
        self.assertEqual([s['id'] for s in result['collection']['slots']],['back','hem'])
        for payload in ({'title':'Bad','category':[]},{'title':'','category':'face'},
                        {'title':'Bad','category':'face','slots':[{'id':'../x','title':'No'}]},
                        {'title':'Bad','category':'face','slots':[{'id':'same'},{'id':'same'}]}):
            with self.assertRaises(refs.LibraryError):self.library.create_collection(payload)

    def test_phone_jpeg_orientation_is_visible_but_original_bytes_unchanged(self):
        image=Image.new('RGB',(40,80),'red')
        exif=Image.Exif();exif[274]=6
        buffer=io.BytesIO();image.save(buffer,format='JPEG',exif=exif,quality=95)
        raw=buffer.getvalue()
        collection=self.library.create_collection({'title':'Phone originals','category':'body'})['collection']
        result=self.upload(collection,name='phone.jpg',mime='image/jpeg',data=base64.b64encode(raw).decode())
        identifier=result['record']['id']
        self.assertEqual(result['record']['size'],[80,40])
        self.assertEqual(self.library.original(identifier)['bytes'],raw)
        with Image.open(io.BytesIO(self.library.thumbnail(identifier,size=80)['bytes'])) as thumb:
            self.assertEqual(thumb.size,(80,40))
        sheet=self.library.export_sheet({'ids':[identifier],'columns':1,'cell_width':80,'cell_height':80})
        with Image.open(io.BytesIO(sheet['bytes'])) as composed:
            self.assertEqual(composed.getpixel((40,0)),(255,255,255))
            self.assertGreater(composed.getpixel((0,40))[0],240)
            self.assertLess(composed.getpixel((0,40))[1],10)


if __name__=='__main__':unittest.main()
