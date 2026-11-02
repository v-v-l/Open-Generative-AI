"""Cloud transport/charging contracts, entirely mocked: no paid requests."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from PIL import Image

SPEC = importlib.util.spec_from_file_location("studio_cloud_test", Path(__file__).resolve().parents[1] / "backend/cloud.py")
cloud = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cloud)


class CloudContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = patch.object(cloud, "CACHE", self.root / "catalog.json")
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.creds = patch.object(cloud, "_credentials", return_value={"OPENAI_API_KEY": "test-secret-openai", "OPENROUTER_API_KEY": "test-secret-openrouter"})
        self.creds.start()
        self.addCleanup(self.creds.stop)
        self.buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(self.buffer, format="JPEG")
        self.source = self.root / "reference.jpg"
        self.source.write_bytes(self.buffer.getvalue())
        self.asset = {"id": "asset-1", "role": "image", "path": str(self.source)}
        self.events = []

    def image_response(self, malformed=False):
        return {"_request_id": "request-test", "data": [{"b64_json": "not base64" if malformed else base64.b64encode(self.buffer.getvalue()).decode()}],
                "usage": {"input_tokens_details": {"text_tokens": 100, "image_tokens": 1000}, "output_tokens": 2000, "cost": .123}}

    def openai_job(self):
        return {"kind": "photo", "model": "openai:gpt-image-2.5-sunburst-2026-09-08", "prompt": "literal [Push in] <image1>", "quality": "high", "size": "1024x1024"}

    def veo_job(self):
        return {"kind": "video", "model": "openrouter:google/veo-3.1-lite", "prompt": "literal [Static shot]", "duration": 4, "resolution": "720p", "aspect_ratio": "9:16", "generate_audio": False, "seed": 1}

    def test_openai_multipart_usage_and_actual_png(self):
        with patch.object(cloud, "_request", return_value=self.image_response()) as request:
            result = cloud.run_job(self.openai_job(), self.root / "openai", [self.asset], self.events.append, lambda: False)
        self.assertEqual(result["provider_request_id"], "request-test")
        self.assertAlmostEqual(result["billing"]["actual_usd"], .0685)
        self.assertEqual(result["billing"]["status"], "calculated_list_price_not_invoice")
        with Image.open(result["outputs"][0]["path"]) as image:
            self.assertEqual(image.format, "PNG")
        url, body, headers = request.call_args.args
        self.assertTrue(url.endswith("/images/edits"))
        self.assertIn(b"literal [Push in] <image1>", body)
        self.assertIn(b'name="image[]"', body)
        self.assertNotIn(b'name="seed"', body)

    def test_two_openai_references_reach_edits_in_order(self):
        second=self.root/'second.png';Image.new('RGB',(8,8),'blue').save(second)
        refs=[self.asset,{'id':'asset-2','role':'image','path':str(second)}]
        folder=self.root/'two-references'
        with patch.object(cloud,'_request',return_value=self.image_response()) as request:
            cloud.run_job(self.openai_job(),folder,refs,self.events.append,lambda:False)
        url,body,headers=request.call_args.args
        self.assertTrue(url.endswith('/images/edits'))
        self.assertEqual(body.count(b'name="image[]"'),2)
        self.assertLess(body.index(b'reference-1.png'),body.index(b'reference-2.png'))
        images=body.split(b'Content-Type: image/png\r\n\r\n')[1:]
        self.assertEqual(len(images),2)
        first=Image.open(io.BytesIO(images[0].split(b'\r\n--',1)[0]));second=Image.open(io.BytesIO(images[1].split(b'\r\n--',1)[0]))
        self.assertGreater(first.getpixel((0,0))[0],200)
        self.assertEqual(second.getpixel((0,0)),(0,0,255))
        audit=json.loads((folder/'cloud-submission.json').read_text())
        self.assertEqual(audit['references'],[{'id':'asset-1','role':'image'},{'id':'asset-2','role':'image'}])

    def test_duplicate_submission_is_not_retried(self):
        folder = self.root / "duplicate"
        folder.mkdir()
        (folder / "cloud-submission.json").write_text("{}")
        with patch.object(cloud, "_request") as request:
            with self.assertRaisesRegex(RuntimeError, "duplicate charge"):
                cloud.run_job(self.openai_job(), folder, [], self.events.append, lambda: False)
            request.assert_not_called()

    def test_known_charge_persisted_before_output_decode_failure(self):
        with patch.object(cloud, "_request", return_value=self.image_response(malformed=True)):
            with self.assertRaises(Exception) as caught:
                cloud.run_job(self.openai_job(), self.root / "bad-output", [], self.events.append, lambda: False)
        self.assertAlmostEqual(caught.exception.billing["actual_usd"], .0685)
        self.assertTrue(any(event.get("billing", {}).get("actual_usd") == .0685 for event in self.events))
        disk = json.loads((self.root / "bad-output/cloud-billing.json").read_text())
        self.assertAlmostEqual(disk["actual_usd"], .0685)

    def test_openrouter_images_pin_endpoint_and_ignore_local_options(self):
        job = {"kind": "photo", "model": "openrouter:google/gemini-3.1-flash-image", "prompt": "literal prompt", "resolution": "1K", "aspect_ratio": "9:16", "steps": 25, "quality": "high", "width": 704}
        with patch.object(cloud, "_request", return_value=self.image_response()) as request:
            result = cloud.run_job(job, self.root / "nano", [self.asset], self.events.append, lambda: False)
        url, body, headers = request.call_args.args
        self.assertTrue(url.endswith("/images"))
        self.assertEqual(body["prompt"], "literal prompt")
        self.assertEqual(body["provider"], {"only": ["google-ai-studio"], "allow_fallbacks": False})
        self.assertTrue(body["input_references"][0]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertNotIn("quality", body)
        self.assertNotIn("steps", body)
        self.assertEqual(result["billing"]["actual_usd"], .123)

    def test_veo_inline_frames_and_sku_quote(self):
        self.assertAlmostEqual(cloud.estimate(self.veo_job(), [dict(self.asset, role="start")])["estimated_usd"], .12)
        response = {"id": "gen-vid-test", "status": "completed", "usage": {"cost": .12}}
        with patch.object(cloud, "_request", return_value=response) as request, patch.object(cloud, "_download_video", return_value=[{"path": str(self.root / "video.mp4"), "kind": "video"}]):
            result = cloud.run_job(self.veo_job(), self.root / "veo", [dict(self.asset, role="start"), dict(self.asset, role="end")], self.events.append, lambda: False)
        body = request.call_args.args[1]
        self.assertEqual([frame["frame_type"] for frame in body["frame_images"]], ["first_frame", "last_frame"])
        self.assertEqual(body["prompt"], "literal [Static shot]")
        self.assertEqual(result["billing"]["actual_usd"], .12)

    def test_cached_veo_presets_publish_the_same_dependent_duration_rule_as_validation(self):
        cached = {'models':cloud._bootstrap(),'refreshed_at':'preserve-pinned-catalog'}
        self.cache_path = self.root/'catalog.json'
        self.cache_path.write_text(json.dumps(cached))
        original = self.cache_path.read_bytes()
        rows = cloud.catalog()
        for slug in cloud.VEO:
            model = next(row for row in rows if row['remote_model']==slug)
            if '4K' not in model['settings']['resolution']['values']:
                self.assertNotIn('output_constraints',model)
                continue
            self.assertEqual(model['output_constraints'],[{'when':{'resolution':'4K'},'allowed':{'duration':[8]}}])
            job = dict(self.veo_job(),model=model['id'],resolution='4K',duration=6)
            with self.assertRaisesRegex(ValueError,'8 seconds'):
                cloud.validate_job(job,[])
            cloud.validate_job(dict(job,duration=8),[])
        self.assertEqual(self.cache_path.read_bytes(),original)

    def test_cancel_after_video_acceptance_retains_provider_job_and_unknown_charge(self):
        checks = iter([False, True])
        with patch.object(cloud, "_request", return_value={"id": "gen-vid-pending", "status": "pending"}) as request:
            with self.assertRaises(InterruptedError) as caught:
                cloud.run_job(self.veo_job(), self.root / "cancel", [], self.events.append, lambda: next(checks))
        self.assertEqual(request.call_count, 1)
        self.assertEqual(caught.exception.provider_request_id, "gen-vid-pending")
        self.assertIsNone(caught.exception.billing["actual_usd"])
        self.assertTrue((self.root / "cancel/cloud-accepted.json").exists())

    def test_all_veo_variants_preserve_frame_pixels_and_reject_other_roles(self):
        second = self.root / "last.png"
        Image.new("RGB", (9, 7), "blue").save(second)
        refs = [dict(self.asset, role="start"), {"id": "last", "role": "end", "path": str(second)}]
        for index, slug in enumerate(cloud.VEO):
            with self.subTest(model=slug):
                job = dict(self.veo_job(), model="openrouter:" + slug)
                with patch.object(cloud, "_request", return_value={"id": "done", "status": "completed"}) as request, patch.object(cloud, "_download_video", return_value=[{"path": str(self.root / "video.mp4"), "kind": "video"}]):
                    cloud.run_job(job, self.root / f"veo-{index}", refs, self.events.append, lambda: False)
                body = request.call_args.args[1]
                self.assertEqual(body["model"], slug)
                self.assertEqual(body["seed"], job["seed"])
                self.assertFalse(body["generate_audio"])
                for frame, asset in zip(body["frame_images"], refs):
                    with Image.open(io.BytesIO(base64.b64decode(frame["image_url"]["url"].split(",", 1)[1]))) as sent, Image.open(asset["path"]) as original:
                        self.assertEqual(sent.size, original.size)
                        self.assertEqual(sent.convert("RGB").tobytes(), original.convert("RGB").tobytes())
                for role in ("image", "video", "audio"):
                    with self.assertRaisesRegex(ValueError, "Unsupported reference role"):
                        cloud.validate_job(job, [dict(self.asset, role=role)])
                with self.assertRaisesRegex(ValueError, "last frame requires a first"):
                    cloud.validate_job(job, [refs[1]])

    def test_frame_capabilities_control_other_video_model_validation(self):
        for frames in ([], ["first_frame"], ["first_frame", "last_frame"]):
            source = {"id": "test/video", "supported_durations": [5], "supported_resolutions": ["720p"], "supported_aspect_ratios": ["9:16"], "supported_frame_images": frames}
            model = cloud._video_descriptor(source, "test")
            job = {"model": model["id"], "kind": "video", "prompt": "literal", "duration": 5, "resolution": "720p", "aspect_ratio": "9:16"}
            with self.subTest(frames=frames), patch.object(cloud, "catalog", return_value=[model]):
                cloud.validate_job(job, [])
                for role, native in (("start", "first_frame"), ("end", "last_frame")):
                    refs = [dict(self.asset, role="start")] if role == "start" else [dict(self.asset, role="start"), dict(self.asset, role="end")]
                    if native in frames:
                        cloud.validate_job(job, refs)
                    else:
                        with self.assertRaisesRegex(ValueError, "Unsupported reference role"):
                            cloud.validate_job(job, refs)

    def test_http_error_saved_without_upstream_reference_body_or_secret(self):
        error = urllib.error.HTTPError(cloud.OPENAI + "/images/generations", 429, "rate limited", {}, io.BytesIO(b"test-secret-openai PRIVATE_REFERENCE_BASE64"))
        self.addCleanup(error.close)
        with patch.object(cloud, "_request", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                cloud.run_job(self.openai_job(), self.root / "http-error", [], self.events.append, lambda: False)
        saved = (self.root / "http-error/cloud-error.json").read_text()
        self.assertNotIn("test-secret", saved)
        self.assertNotIn("PRIVATE_REFERENCE", saved)
        self.assertEqual(json.loads(saved)["http_status"], 429)

    def test_json_http_diagnostic_retains_reason_code_and_request_id_without_reflected_secrets(self):
        job=self.openai_job()
        encoded=base64.b64encode(self.buffer.getvalue()).decode()
        body={'error':{'code':'invalid_value','type':'invalid_request_error','param':'quality',
                       'message':'Invalid value for quality. test-secret-openai '+job['prompt']+' data:image/jpeg;base64,'+encoded+' https://private.example/ref?token=secret',
                       'raw_request':{'private_reference':encoded}},'untrusted_extra':'PRIVATE_REFERENCE'}
        error=urllib.error.HTTPError(cloud.OPENAI+'/images/edits',400,'Bad Request',{'x-request-id':'req-diagnostic-123'},io.BytesIO(json.dumps(body).encode()))
        with patch.object(cloud,'_request',side_effect=error) as request:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                cloud.run_job(job,self.root/'diagnostic',[self.asset],self.events.append,lambda:False)
        request.assert_called_once()
        saved=(self.root/'diagnostic/cloud-error.json').read_text()
        data=json.loads(saved)
        self.assertEqual(data['provider_request_id'],'req-diagnostic-123')
        self.assertEqual(data['provider_error']['code'],'invalid_value')
        self.assertEqual(data['provider_error']['param'],'quality')
        self.assertIn('Invalid value for quality',str(caught.exception))
        for private in ('test-secret',job['prompt'],encoded,'private.example','PRIVATE_REFERENCE','raw_request'):
            self.assertNotIn(private,saved)
            self.assertNotIn(private,str(caught.exception))
        self.assertFalse(data['automatic_retries'])
        self.assertEqual(caught.exception.provider_request_id,'req-diagnostic-123')

    def test_transport_captures_http_diagnostic_once_without_retrying(self):
        error=urllib.error.HTTPError(cloud.OPENAI+'/images/generations',400,'Bad Request',{'x-request-id':'req-once'},io.BytesIO(b'{"error":{"message":"Invalid image size","code":"invalid_size"}}'))
        with patch.object(cloud.urllib.request,'build_opener') as build:
            build.return_value.open.side_effect=error
            with self.assertRaises(urllib.error.HTTPError):cloud._request(cloud.OPENAI+'/images/generations',{'prompt':'test'})
            build.return_value.open.assert_called_once()
        self.assertEqual(error.provider_error['code'],'invalid_size')
        self.assertEqual(error.provider_request_id,'req-once')
        self.assertIn('Invalid image size',str(error))

    def test_non_json_or_oversized_http_bodies_never_become_diagnostics(self):
        for raw in (b'<html>test-secret-openai PRIVATE_REFERENCE_BASE64</html>',b'{"error":{"message":"'+b'X'*70000+b'"}}'):
            body=io.BytesIO(raw)
            error=urllib.error.HTTPError(cloud.OPENAI+'/images/edits',400,'Bad Request',{'x-request-id':'req-bounded'},body)
            diagnostic=cloud._http_diagnostic(error)
            self.assertEqual(diagnostic,{})
            self.assertEqual(error.provider_request_id,'req-bounded')
            self.assertEqual(str(error),'HTTP Error 400: Bad Request')

    def test_catalog_exposes_booleans_not_credentials(self):
        text = json.dumps(cloud.catalog())
        self.assertNotIn("test-secret", text)
        self.assertTrue(all(row["credential_configured"] for row in cloud.catalog()))

    def test_live_video_descriptor_does_not_invent_audio_or_reference_modes(self):
        source = {"id": "runway/gen-4.5", "name": "Runway Gen-4.5", "supported_durations": [2, 3, 4], "supported_resolutions": ["720p"], "supported_aspect_ratios": ["16:9", "9:16"], "supported_frame_images": ["first_frame"], "generate_audio": False, "seed": True, "pricing_skus": {"cents_per_second_output": ".12"}}
        model = cloud._video_descriptor(source, "test-time")
        self.assertEqual(model["roles"], {"start": 1})
        self.assertNotIn("generate_audio", model["settings"])
        self.assertNotIn("image", model["roles"])
        self.assertFalse(model["generation_verified"])
        with patch.object(cloud, "catalog", return_value=[model]):
            estimate = cloud.estimate({"model": model["id"], "kind": "video", "prompt": "literal", "duration": 2, "resolution": "720p", "aspect_ratio": "9:16"}, [])
        self.assertIsNone(estimate["estimated_usd"])
        self.assertIsNone(cloud._video_descriptor({"id": "upscale", "supported_durations": None}, "test-time"))

    def test_image_endpoint_bounds_and_svg_exclusion(self):
        source = {"id": "krea/edit", "name": "Krea Edit"}
        endpoint = {"provider_tag": "provider", "supported_parameters": {"input_references": {"type": "range", "min": 1, "max": 5}, "output_format": {"type": "enum", "values": ["jpeg", "png"]}, "n": {"type": "range", "min": 1, "max": 1}}, "pricing": []}
        model = cloud._image_descriptor(source, endpoint, "test-time")
        self.assertEqual(model["roles"], {"image": 5})
        self.assertEqual(model["request_defaults"], {"output_format": "png"})
        with patch.object(cloud, "catalog", return_value=[model]):
            with self.assertRaisesRegex(ValueError, "requires at least"):
                cloud.validate_job({"model": model["id"], "kind": "photo", "prompt": "literal"}, [])
        endpoint["supported_parameters"]["output_format"]["values"] = ["svg"]
        self.assertIsNone(cloud._image_descriptor(source, endpoint, "test-time"))

    def test_download_does_not_forward_credentials_to_unknown_host(self):
        error = urllib.error.HTTPError(cloud.ORIGIN + "/content", 302, "redirect", {"Location": "https://evil.example/private"}, None)
        self.addCleanup(error.close)
        with patch.object(cloud, "_request", side_effect=error), patch.object(cloud.socket, "getaddrinfo") as dns:
            with self.assertRaisesRegex(ValueError, "Unrecognized provider"):
                cloud._download_video("job", self.root, {"Authorization": "Bearer test-secret"})
            dns.assert_not_called()


if __name__ == "__main__":
    unittest.main()
