"""Requested OpenRouter model contracts; no credentials, providers or inference."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

SPEC = importlib.util.spec_from_file_location('requested_video_cloud', Path(__file__).resolve().parents[1]/'backend/cloud.py')
cloud = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cloud)


class RequestedVideoContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = json.loads((Path(__file__).parent/'fixtures/openrouter-requested-videos.json').read_text())
        self.models = {model['id']:cloud._video_descriptor(model,'fixture') for model in self.source['data']}
        self.cache = self.root/'catalog.json'
        self.cache.write_text(json.dumps({'models':list(self.models.values())}))
        self.patches = [patch.object(cloud,'CACHE',self.cache), patch.object(cloud,'_credentials',return_value={'OPENROUTER_API_KEY':'test-only'})]
        for change in self.patches:
            change.start();self.addCleanup(change.stop)
        self.image = self.root/'photo.png';Image.new('RGB',(8,12),'red').save(self.image)

    def job(self, slug, **values):
        return {'model':'openrouter:'+slug,'kind':'video','prompt':' Literal script\n[Static shot] ','seed':123,**values}

    def asset(self, role):
        return {'id':'a'*32,'path':str(self.image),'role':role}

    def test_avatar_capabilities_and_exact_passthrough_transport(self):
        model = self.models['heygen/avatar-iv']
        self.assertEqual(model['roles'],{'image':1})
        self.assertEqual(model['required_roles'],{'image':1})
        for field in ('duration','seed','generate_audio','caption','voice_settings'):
            self.assertNotIn(field,model['settings'])
        job = self.job('heygen/avatar-iv',voice_id='voice-original',motion_prompt='Gentle gesture',remove_background=False)
        cloud.validate_job(job,[self.asset('image')])
        payload = cloud._video_payload(job,[self.asset('image')],model)
        self.assertEqual(payload['prompt'],job['prompt'])
        self.assertEqual(payload['provider']['options']['heygen']['parameters'],{
            'voice_id':'voice-original','motion_prompt':'Gentle gesture','expressiveness':'low','fit':'contain','remove_background':False})
        self.assertEqual(payload['input_references'][0]['type'],'image_url')
        self.assertTrue(payload['input_references'][0]['image_url']['url'].startswith('data:image/png;base64,'))
        for field in ('frame_images','duration','seed','generate_audio','voice_id','motion_prompt'):
            self.assertNotIn(field,payload)

    def test_avatar_rejects_missing_voice_photo_and_unconnected_audio(self):
        job = self.job('heygen/avatar-iv',voice_id='voice')
        with self.assertRaisesRegex(ValueError,'requires at least'):
            cloud.validate_job(job,[])
        for voice in ('',None,42):
            with self.assertRaisesRegex(ValueError,'required'):
                cloud.validate_job(dict(job,voice_id=voice),[self.asset('image')])
        for refs in ([self.asset('start')],[self.asset('image')]*2,[self.asset('image'),self.asset('audio')]):
            with self.assertRaisesRegex(ValueError,'role/count'):
                cloud.validate_job(job,refs)
        with self.assertRaisesRegex(ValueError,'Unsupported resolution'):
            cloud.validate_job(dict(job,resolution='4K'),[self.asset('image')])

    def test_avatar_omits_removed_passthrough_fields(self):
        source = next(model for model in self.source['data'] if model['id']=='heygen/avatar-iv')
        model = cloud._video_descriptor(dict(source,allowed_passthrough_parameters=['voice_id']),'fixture')
        payload = cloud._video_payload(self.job('heygen/avatar-iv',voice_id='voice'),[self.asset('image')],model)
        self.assertEqual(payload['provider']['options']['heygen']['parameters'],{'voice_id':'voice'})
        self.assertNotIn('expressiveness',payload)

    def test_catalog_quotes_only_known_duration_tariffs(self):
        for resolution, expected in [('480p',.25),('768p',.4)]:
            for refs in ([],[self.asset('start'),self.asset('end')]):
                quote = cloud.estimate(self.job('minimax/hailuo-3-max',duration=5,resolution=resolution),refs)
                self.assertAlmostEqual(quote['estimated_usd'],expected)
                self.assertEqual(quote['estimated_usd'],quote['upper_usd'])
        for resolution, expected in [('480p',.1),('768p',.18),('2K',.5)]:
            job = self.job('heygen/heygen-video-1',duration=5,resolution=resolution)
            self.assertAlmostEqual(cloud.estimate(job,[])['estimated_usd'],expected)
            self.assertIsNone(cloud.estimate(job,[self.asset('start')])['estimated_usd'])
        avatar = cloud.estimate(self.job('heygen/avatar-iv',voice_id='voice'),[self.asset('image')])
        self.assertIsNone(avatar['estimated_usd'])
        self.assertIn('Speech duration is unknown',avatar['uncertainty'])

    def test_all_requested_models_submit_once_with_expected_reference_modes(self):
        cases = [('heygen/heygen-video-1',{},[],None),
                 ('heygen/heygen-video-1',{},[self.asset('start')],'frame_images'),
                 ('minimax/hailuo-3-max',{},[self.asset('start'),self.asset('end')],'frame_images'),
                 ('heygen/avatar-iv',{'voice_id':'voice'},[self.asset('image')],'input_references')]
        for index,(slug,settings,refs,field) in enumerate(cases):
            with self.subTest(slug=slug,field=field):
                with patch.object(cloud,'_request',return_value={'id':'mock-job','status':'completed'}) as request, patch.object(cloud,'_download_video',return_value=[{'kind':'video','path':str(self.root/'unused.mp4')}]):
                    cloud.run_job(self.job(slug,**settings),self.root/str(index),refs,lambda event:None,lambda:False)
                self.assertEqual(request.call_count,1)
                url,payload,headers = request.call_args.args
                self.assertEqual(url,cloud.ORIGIN+'/videos')
                self.assertEqual(payload['model'],slug)
                if field:self.assertEqual(len(payload[field]),len(refs))
                if slug=='minimax/hailuo-3-max':
                    self.assertNotIn('seed',payload);self.assertNotIn('generate_audio',payload)
                self.assertNotIn('/media/',json.dumps(payload))

    def test_targeted_refresh_preserves_unrelated_endpoints_and_fails_atomically(self):
        unrelated = {'id':'openrouter:unrelated','remote_model':'unrelated','settings':{'quality':{'default':'low'}},'provider_tag':'pinned/original'}
        self.cache.write_text(json.dumps({'models':[unrelated],'excluded_models':[{'model':'heygen/avatar-iv','reason':'old filter'}],'refreshed_at':'keep'}))
        with patch.object(cloud,'_request',return_value=self.source) as request:
            cloud.refresh_requested_videos()
        request.assert_called_once_with(cloud.VIDEO_SOURCE)
        saved = json.loads(self.cache.read_text())
        self.assertEqual(saved['models'][0],unrelated)
        self.assertEqual(saved['refreshed_at'],'keep')
        self.assertEqual(len(saved['models']),4);self.assertEqual(saved['excluded_models'],[])
        original = self.cache.read_bytes()
        with patch.object(cloud,'_request',return_value={'data':self.source['data'][:1]}):
            with self.assertRaisesRegex(ValueError,'unchanged'):cloud.refresh_requested_videos()
        self.assertEqual(self.cache.read_bytes(),original)
