"""Qwen-only transport and H3 cleanup contracts; every inference/provider mocked."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch, Mock
import urllib.error
import urllib.request
import uuid

from PIL import Image

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


executor = load("executor_test", BACKEND / "qwen_executor.py")
engine = load("executor_engine_test", BACKEND / "engine.py")


class ExecutorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        image = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(image, format="PNG")
        self.png = image.getvalue()
        self.calls = []
        def photo(job, folder, assets, progress, cancelled):
            self.calls.append(dict(job))
            target = folder / "output.png"
            target.write_bytes(self.png)
            return [{"path": str(target), "kind": "image"}]
        self.fake = types.SimpleNamespace(_api=lambda path: {}, validate_job=lambda job, assets: None,
                                          _lock=lambda name: contextlib.nullcontext(), _prepare=lambda assets, folder: assets,
                                          _photo=photo)
        self.service = executor.Executor(self.root, self.fake)

    def payload(self):
        return {"request_id": uuid.uuid4().hex, "job": {"kind": "photo", "model": "qwen-local", "prompt": "literal <image1>", "seed": 42, "max_minutes": 5},
                "images": [{"role": "image", "data": base64.b64encode(self.png).decode()}]}

    def finish(self, identifier):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = self.service.public(identifier)
            if state["status"] in ("completed", "failed"):
                return state
            time.sleep(.005)
        self.fail("Mock executor did not finish")

    def test_submit_is_qwen_only_idempotent_and_paths_are_private(self):
        payload = self.payload()
        self.service.submit(payload)
        state = self.finish(payload["request_id"])
        self.assertEqual(state["status"], "completed")
        self.assertEqual(self.calls[0]["prompt"], "literal <image1>")
        self.service.submit(payload)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("paths", state)
        self.assertNotIn(str(self.root), json.dumps(state))
        self.assertEqual(self.service.output(payload["request_id"], 0).read_bytes(), self.png)
        payload["job"]["prompt"] = "different"
        with self.assertRaisesRegex(ValueError, "different inputs"):
            self.service.submit(payload)

    def test_arbitrary_models_workflows_paths_and_batches_rejected(self):
        for key, value in (("kind", "video"), ("model", "h3-simplepod"), ("batch_count", 2), ("max_minutes", 31), ("workflow", {"LoadCheckpoint": "anything"}), ("output_path", "/etc/passwd")):
            payload = self.payload()
            payload["job"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.service.submit(payload)
        self.assertEqual(self.calls, [])

    def test_restart_does_not_resubmit_existing_running_job(self):
        identifier = uuid.uuid4().hex
        folder = self.root / identifier
        folder.mkdir()
        (folder / "executor-state.json").write_text(json.dumps({"id": identifier, "status": "running", "outputs": []}))
        resumed = executor.Executor(self.root, self.fake)
        self.assertEqual(resumed.public(identifier)["status"], "interrupted")
        self.assertEqual(self.calls, [])

    def test_authenticated_http_has_no_proxy_or_origin_bypass(self):
        server = executor.ThreadingHTTPServer(("127.0.0.1", 0), executor.Handler)
        server.executor = self.service
        server.executor_token = "t"*40
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"
        for headers in ({}, {"Authorization": "Bearer wrong", "X-Forwarded-For": "127.0.0.1"}, {"Authorization": "Bearer " + "t"*40, "Origin": "https://public.example"}):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(url + "/health", headers=headers))
            self.assertEqual(caught.exception.code, 401)
            caught.exception.close()
        headers = {"Authorization": "Bearer " + "t"*40}
        with urllib.request.urlopen(urllib.request.Request(url + "/health", headers=headers)) as response:
            self.assertEqual(json.load(response)["model"], "qwen-local")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(urllib.request.Request(url + "/api/prompt", headers=headers))
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_apps_client_downloads_images_without_forwarding_workflow_fields(self):
        folder = self.root / "client"
        folder.mkdir()
        calls = []
        def request(path, payload=None, **kwargs):
            calls.append((path, payload))
            if path == "/jobs":
                return {"id": payload["request_id"], "status": "completed", "outputs": [{"index": 0}]}
            return self.png
        with patch.object(executor, "health", return_value={"available": True}), patch.object(executor, "request", side_effect=request):
            outputs = executor.run_remote({"kind": "photo", "prompt": "literal", "workflow": "ignored", "seed": 7}, folder, [], lambda value: None, lambda: False)
        self.assertEqual(calls[0][1]["job"]["prompt"], "literal")
        self.assertNotIn("workflow", calls[0][1]["job"])
        self.assertEqual(Path(outputs[0]["path"]).read_bytes(), self.png)

    def test_executor_url_cannot_be_an_arbitrary_network_proxy(self):
        for url in ("http://169.254.169.254:80", "https://evil.example:443", "http://user:password@127.0.0.1:44", "http://127.0.0.1:44/arbitrary"):
            with self.subTest(url=url), patch.dict(os.environ, {"NORA_QWEN_EXECUTOR_URL": url}), self.assertRaises(ValueError):
                executor.configured_url()


class H3CleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.worker = load("portable_worker_test", BACKEND / "runtime/simplepod-worker.py")
        self.state = self.root / "worker.json"
        self.state.write_text(json.dumps({"instance_id": 10, "support_id": "disk"}))
        self.credentials = self.root / "provider.env"
        self.credentials.write_text("SIMPLEPOD_API_KEY=mock-provider-key\n")
        self.worker.STATE = self.state
        self.worker.CREDENTIALS_FILE = str(self.credentials)
        self.folder = self.root / "job"
        self.folder.mkdir()

    def provider(self, name, args=None):
        return {"sp_get_instance": {"pausedAt": "yesterday", "status": "paused"},
                "sp_get_summary": {"rentalAvailability": {"balanceRental": 10}},
                "sp_list_vps_market": [{"pricePerGpu": .5, "systemMemory": 90000, "rigRentalDatacenter": {"id": 1}, "instanceMarket": "market"}],
                "resume-vps": {"id": 11, "pricePerGpu": .5}}[name]

    def test_timer_arm_failure_still_pauses_provider_accepted_rental(self):
        pause = Mock()
        with patch.object(engine, "_worker", return_value=self.worker), patch.object(self.worker, "provider", side_effect=self.provider), patch.object(self.worker, "pause", pause), patch.object(self.worker.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["systemd-run"])) as process, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                engine._video({"max_minutes": 5}, self.folder, [], lambda value: None, lambda: False)
        pause.assert_called_once()
        self.assertTrue(any(arg.startswith("--setenv=NORA_SIMPLEPOD_CREDENTIALS_FILE=") for arg in process.call_args.args[0]))
        self.assertNotIn("mock-provider-key", " ".join(process.call_args.args[0]))

    def test_state_write_failure_after_provider_resume_still_pauses(self):
        original = self.state.read_text()
        self.worker.STATE = types.SimpleNamespace(read_text=lambda: original, write_text=Mock(side_effect=OSError("disk full")))
        pause = Mock()
        with patch.object(engine, "_worker", return_value=self.worker), patch.object(self.worker, "provider", side_effect=self.provider), patch.object(self.worker, "pause", pause), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                engine._video({"max_minutes": 5}, self.folder, [], lambda value: None, lambda: False)
        pause.assert_called_once()

    def test_timer_arm_and_pause_progress_failure_still_pauses_and_preserves_original_error(self):
        pause = Mock()
        def progress(value):
            if value.get("stage") == "pausing_gpu":
                raise OSError("private database credentials must not be logged")
        with patch.object(engine, "_worker", return_value=self.worker), patch.object(self.worker, "provider", side_effect=self.provider), patch.object(self.worker, "pause", pause), patch.object(self.worker.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["systemd-run"])), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                engine._video({"max_minutes": 5}, self.folder, [], progress, lambda: False)
        pause.assert_called_once()
        evidence = (self.folder / "rental-events.json").read_text()
        self.assertIn("pause_progress_unavailable", evidence)
        self.assertIn('"error_type": "OSError"', evidence)
        self.assertNotIn("private database credentials", evidence)

    def test_missing_timer_credentials_rejected_before_any_provider_call(self):
        self.worker.CREDENTIALS_FILE = str(self.root / "missing.env")
        with patch.object(self.worker, "provider") as provider:
            with self.assertRaisesRegex(RuntimeError, "credentials file"):
                self.worker.resume({}, [], 5)
            provider.assert_not_called()


class EngineInputValidationTest(unittest.TestCase):
    def test_lost_submission_reply_and_status_timeout_reconcile_without_second_post(self):
        with tempfile.TemporaryDirectory() as directory:
            buffer = io.BytesIO()
            Image.new('RGB', (8, 8), 'blue').save(buffer, format='PNG')
            responses = iter([TimeoutError('lost acknowledgement'),
                              urllib.error.HTTPError('http://localhost/jobs/id', 404, 'not accepted yet', {}, io.BytesIO()),
                              {'status':'running'}, TimeoutError('lost status'),
                              {'status':'completed','outputs':[{'index':0}]}, buffer.getvalue()])
            calls=[]
            def request(path, *args, **kwargs):
                calls.append(path)
                value=next(responses)
                if isinstance(value, Exception):raise value
                return value
            with patch.object(executor,'health',return_value={'available':True}), patch.object(executor,'request',side_effect=request), patch.object(executor.time,'sleep'):
                outputs=executor.run_remote({'max_minutes':5},directory,[],lambda event:None,lambda:False)
            self.assertEqual(calls.count('/jobs'),1)
            self.assertEqual(len(outputs),1)
            self.assertEqual(Path(outputs[0]['path']).read_bytes(),buffer.getvalue())
            marker=json.loads((Path(directory)/'executor-submission.json').read_text())
            self.assertFalse(marker['automatic_retries'])
            self.assertTrue(all(path.startswith('/jobs/'+marker['request_id']) for path in calls[1:]))

    def test_rejected_submission_does_not_poll_or_resubmit(self):
        with tempfile.TemporaryDirectory() as directory:
            error=urllib.error.HTTPError('http://localhost/jobs',400,'bad input',{},io.BytesIO())
            self.addCleanup(error.close)
            with patch.object(executor,'health',return_value={'available':True}), patch.object(executor,'request',side_effect=error) as request:
                with self.assertRaises(urllib.error.HTTPError):
                    executor.run_remote({'max_minutes':5},directory,[],lambda event:None,lambda:False)
            self.assertEqual(request.call_count,1)

    def test_native_validation_does_not_probe_remote_capabilities(self):
        with patch.dict(os.environ, {"NORA_QWEN_EXECUTOR_URL": "http://127.0.0.1:36447"}), patch.object(engine, "capabilities", side_effect=AssertionError("Live capability lookup is forbidden during validation")), patch.object(engine, "_qwen_executor", side_effect=AssertionError("Executor network access is forbidden during validation")):
            engine.validate_job({"kind": "photo", "model": "qwen-local", "prompt": "literal", "max_minutes": 30}, [])
            engine.validate_job({"kind": "video", "model": "h3-simplepod", "prompt": "literal", "max_minutes": 90}, [])

    def test_photo_minutes_match_executor_limit_before_enqueue(self):
        engine.validate_job({"kind": "photo", "prompt": "literal", "max_minutes": 30}, [])
        with self.assertRaisesRegex(ValueError, "max_minutes.*5 to 30"):
            engine.validate_job({"kind": "photo", "prompt": "literal", "max_minutes": 31}, [])


if __name__ == "__main__":
    unittest.main()
