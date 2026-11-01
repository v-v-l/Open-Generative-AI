"""Reference exports preserve originals, framing and selection without inference."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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


if __name__=='__main__':unittest.main()
