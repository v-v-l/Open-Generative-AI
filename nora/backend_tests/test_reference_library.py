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
import shutil
import subprocess

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
        retained=self.root/self.library.records[record['id']]['path']
        second=self.upload(collection,replace_id=record['id'])
        self.assertNotEqual(second['record']['id'],record['id'])
        self.assertEqual(second['replaced_reference_id'],record['id'])
        self.assertEqual(second['collection']['slots'][0]['reference_id'],second['record']['id'])
        self.assertEqual(retained.read_bytes(),raw)
        with self.assertRaises(refs.LibraryError):self.library.original(record['id'])
        catalog=refs.Library(self.root).catalog()
        saved=next(c for c in catalog['collections'] if c['id']==collection['id'])
        self.assertEqual(saved['slots'][0]['reference_id'],second['record']['id'])
        self.assertEqual(len(catalog['records']),3)

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

    def video_bytes(self):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('Local media validation tools unavailable')
        target=self.root/'tiny.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=32x48:r=2','-t','1',
                        '-c:v','libx264','-pix_fmt','yuv420p','-y',str(target)],check=True,timeout=15,capture_output=True)
        return target.read_bytes()

    def test_lora_dataset_appends_images_and_verified_video_preserving_originals(self):
        collection=self.library.create_collection({'title':'Worthy samples','category':'lora'})['collection']
        self.assertEqual(collection['slots'],[]);self.assertEqual(collection['items'],[])
        first=self.upload(collection,slot_id=None)
        raw=self.video_bytes()
        second=self.upload(collection,slot_id=None,name='motion.mp4',mime='video/mp4',data=base64.b64encode(raw).decode())
        video=second['record']
        self.assertEqual(video['media_kind'],'video');self.assertEqual(video['mime'],'video/mp4')
        self.assertAlmostEqual(video['duration_seconds'],1,delta=.2)
        self.assertEqual(self.library.original(video['id'])['bytes'],raw)
        self.assertEqual(second['collection']['items'],[first['record']['id'],video['id']])
        reopened=refs.Library(self.root)
        dataset=next(c for c in reopened.catalog()['collections'] if c['id']==collection['id'])
        self.assertEqual(dataset['items'],second['collection']['items'])
        result=reopened.export_zip({'ids':dataset['items']})
        with zipfile.ZipFile(io.BytesIO(result['bytes'])) as archive:
            self.assertEqual(archive.read(video['id']+'.mp4'),raw)
        with self.assertRaisesRegex(refs.LibraryError,'photographs only'):reopened.export_sheet({'ids':dataset['items']})

    def test_video_rejects_invalid_container_mismatch_oversize_and_non_lora_slot(self):
        collection=self.library.create_collection({'title':'Samples','category':'lora'})['collection']
        with self.assertRaises(refs.LibraryError):self.upload(collection,slot_id=None,name='fake.mp4',mime='video/mp4')
        raw=self.video_bytes()
        with self.assertRaises(refs.LibraryError):self.upload(collection,slot_id=None,name='fake.webm',mime='video/webm',data=base64.b64encode(raw).decode())
        with patch.object(refs,'MAX_VIDEO_BYTES',3),patch.object(refs.base64,'b64decode',side_effect=AssertionError('must not decode')):
            with self.assertRaises(refs.LibraryError):self.upload(collection,slot_id=None,name='big.mp4',mime='video/mp4',data=base64.b64encode(raw).decode())
        face=self.library.create_collection({'title':'Face','category':'face'})['collection']
        with self.assertRaisesRegex(refs.LibraryError,'only be added'):self.upload(face,name='motion.mp4',mime='video/mp4',data=base64.b64encode(raw).decode())
        self.assertEqual(len(self.library.catalog()['records']),2)

    def test_video_probe_failure_is_safe_and_bounded(self):
        with patch.object(refs.subprocess,'run',side_effect=FileNotFoundError):
            with self.assertRaises(refs.LibraryError) as error:refs.Library._probe_video(b'anything','video/mp4')
            self.assertEqual(error.exception.status,503)
        with patch.object(refs.subprocess,'run',side_effect=subprocess.TimeoutExpired('ffprobe',12)):
            with self.assertRaises(refs.LibraryError) as error:refs.Library._probe_video(b'anything','video/mp4')
            self.assertEqual(error.exception.status,413)

    def test_byte_ranges_are_bounded_and_invalid_inputs_rejected(self):
        self.assertEqual(refs.byte_range('bytes=2-5',10),(2,5,206))
        self.assertEqual(refs.byte_range('bytes=-3',10),(7,9,206))
        self.assertEqual(refs.byte_range('bytes=4-',10),(4,9,206))
        for value in ('bytes=-','bytes=-0','bytes=15-20','bytes=4-2','bytes=0-1,3-4','garbage'):
            with self.assertRaises(refs.LibraryError) as error:refs.byte_range(value,10)
            self.assertEqual(error.exception.status,416)

    def test_remove_slot_archives_retains_bytes_and_hides_all_active_access(self):
        collection=self.library.create_collection({'title':'Body','category':'body'})['collection']
        record=self.upload(collection)['record'];identifier=record['id']
        path=self.root/self.library.records[identifier]['path'];raw=path.read_bytes()
        with self.library._mutation():
            data=json.loads(json.dumps(self.library.metadata));data['defaults']={'body':identifier};self.library._persist(data)
        result=self.library.remove_reference({'id':identifier})
        self.assertIsNone(result['collection']['slots'][0]['reference_id'])
        self.assertEqual(path.read_bytes(),raw)
        catalog=refs.Library(self.root).catalog()
        self.assertNotIn(identifier,json.dumps(catalog))
        for action in (lambda:self.library.original(identifier),lambda:self.library.original_file(identifier),
                       lambda:self.library.thumbnail(identifier),lambda:self.library.export_sheet({'ids':[identifier]}),
                       lambda:self.library.export_zip({'ids':[identifier]})):
            with self.assertRaises(refs.LibraryError) as error:action()
            self.assertEqual(error.exception.status,404)
        with self.assertRaises(refs.LibraryError) as error:self.library.remove_reference({'id':'H000'})
        self.assertEqual(error.exception.status,403)

    def test_lora_replace_same_index_image_video_and_remove_archive(self):
        collection=self.library.create_collection({'title':'Dataset','category':'lora'})['collection']
        first=self.upload(collection,slot_id=None)['record'];second=self.upload(collection,slot_id=None)['record']
        old_path=self.root/self.library.records[first['id']]['path'];old_bytes=old_path.read_bytes()
        video=self.upload(collection,slot_id=None,replace_id=first['id'],name='motion.mp4',mime='video/mp4',data=base64.b64encode(self.video_bytes()).decode())
        video_path=self.root/self.library.records[video['record']['id']]['path'];video_raw=video_path.read_bytes()
        self.assertEqual(video['collection']['items'],[video['record']['id'],second['id']])
        self.assertEqual(video['replaced_reference_id'],first['id'])
        self.assertEqual(old_path.read_bytes(),old_bytes)
        self.assertNotIn(first['id'],json.dumps(self.library.catalog()))
        replacement=self.upload(collection,slot_id=None,replace_id=video['record']['id'])
        self.assertEqual(video_path.read_bytes(),video_raw)
        with self.assertRaises(refs.LibraryError):self.library.original_file(video['record']['id'])
        self.assertEqual(replacement['record']['media_kind'],'image')
        self.assertEqual(replacement['collection']['items'],[replacement['record']['id'],second['id']])
        removed=self.library.remove_reference({'id':replacement['record']['id']})
        self.assertEqual(removed['collection']['items'],[second['id']])

    def test_stale_replacement_wrong_membership_and_failed_upload_preserve_active(self):
        collection=self.library.create_collection({'title':'Face','category':'face'})['collection']
        first=self.upload(collection)['record']
        with self.assertRaises(refs.LibraryError) as error:self.upload(collection)
        self.assertEqual(error.exception.status,409)
        with self.assertRaises(refs.LibraryError):self.upload(collection,replace_id=first['id'],mime='image/jpeg')
        self.assertIn(first['id'],self.library.records)
        with patch.object(refs.os,'replace',side_effect=OSError('storage unavailable')):
            with self.assertRaises(refs.LibraryError):self.upload(collection,replace_id=first['id'])
        self.assertIn(first['id'],refs.Library(self.root).records)
        second=self.upload(collection,replace_id=first['id'])['record']
        with self.assertRaises(refs.LibraryError) as error:self.upload(collection,replace_id=first['id'])
        self.assertEqual(error.exception.status,409)
        other=self.library.create_collection({'title':'Other','category':'lora'})['collection']
        with self.assertRaises(refs.LibraryError) as error:self.upload(other,slot_id=None,replace_id=second['id'])
        self.assertEqual(error.exception.status,409)
        self.assertIn(second['id'],self.library.records)

    def test_concurrent_replacements_only_one_can_archive_expected_current_id(self):
        collection=self.library.create_collection({'title':'Face','category':'face'})['collection']
        first=self.upload(collection)['record']
        raw=base64.b64encode((self.root/'images/H000.png').read_bytes()).decode()
        def replace(_):
            library=refs.Library(self.root)
            try:return library.upload_reference({'collection_id':collection['id'],'slot_id':'a000','replace_id':first['id'],'name':'new.png','mime':'image/png','data':raw})
            except refs.LibraryError as error:return error.status
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(replace,range(2)))
        self.assertEqual(sum(isinstance(value,dict) for value in results),1)
        self.assertIn(409,results)
        self.assertNotIn(first['id'],json.dumps(self.library.catalog()))

    def test_historical_orphan_upload_can_be_removed_without_touching_current_slot(self):
        collection=self.library.create_collection({'title':'Face','category':'face'})['collection']
        first=self.upload(collection)['record']
        second=self.upload(collection,replace_id=first['id'])['record']
        # Simulate a pre-archive-version replacement: the old record remained active.
        with self.library._mutation():
            data=json.loads(json.dumps(self.library.metadata))
            old=next(record for record in data['records'] if record['id']==first['id'])
            for key in ('archived','archived_reason','archived_at'):old.pop(key,None)
            self.library._persist(data)
        with self.assertRaises(refs.LibraryError) as error:self.upload(collection,replace_id=first['id'])
        self.assertEqual(error.exception.status,409)
        removed=self.library.remove_reference({'id':first['id']})
        self.assertEqual(removed['collection']['slots'][0]['reference_id'],second['id'])
        self.assertIn(second['id'],self.library.records)
        self.assertNotIn(first['id'],self.library.records)


if __name__=='__main__':unittest.main()
