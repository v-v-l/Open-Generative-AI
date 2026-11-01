"""Private, authenticated Qwen-only execution boundary and its Apps client.

This is not a Comfy proxy: callers can submit a bounded Qwen photo job, observe
their opaque job ID, cancel that job, and download its image outputs. No model
names, workflow JSON, commands, filesystem paths or arbitrary URLs are accepted.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
MAX_BODY = 140 * 1024 * 1024
MAX_IMAGE = 40 * 1024 * 1024
JOB_FIELDS = frozenset(("kind", "model", "prompt", "negative_prompt", "seed", "width", "height", "steps", "lora_enabled", "lora_strength", "lora_name", "max_minutes", "batch_count"))
_HEALTH = {"at": 0.0, "value": None}
_HEALTH_LOCK = threading.Lock()


def token():
    value = os.environ.get("NORA_QWEN_EXECUTOR_TOKEN", "")
    if not value and os.environ.get("NORA_QWEN_EXECUTOR_TOKEN_FILE"):
        value = Path(os.environ["NORA_QWEN_EXECUTOR_TOKEN_FILE"]).read_text().strip()
    return value


def configured_url():
    value = os.environ.get("NORA_QWEN_EXECUTOR_URL", "").rstrip("/")
    if not value:
        return None
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Qwen executor must use the private loopback HTTP tunnel")
    if not parsed.port:
        raise ValueError("Qwen executor tunnel port is required")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, payload=None, timeout=30, raw=False):
    origin = configured_url()
    secret = token()
    if not origin or len(secret) < 32:
        raise RuntimeError("Private Qwen executor is not configured")
    req = urllib.request.Request(origin + path,
                                 data=None if payload is None else json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"})
    with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as response:
        limit = MAX_IMAGE + 1 if raw else MAX_BODY + 1
        data = response.read(limit)
        if len(data) == limit:
            raise RuntimeError("Qwen executor response exceeds the size limit")
        return data if raw else json.loads(data)


def health():
    """Bounded five-second cached readiness; no inference or paid provider calls."""
    try:
        configured = bool(configured_url() and len(token()) >= 32)
    except (ValueError, OSError):
        configured = False
    if not configured:
        return {"configured": False, "available": False, "status": "not_configured", "reason": "Private Qwen executor is not configured on this server"}
    with _HEALTH_LOCK:
        stamp = time.monotonic()
        if _HEALTH["value"] is not None and stamp - _HEALTH["at"] < 5:
            return dict(_HEALTH["value"])
        try:
            data = request("/health", timeout=2)
            available = data.get("protocol") == 1 and data.get("available") is True
            value = {"configured": True, "available": available, "status": "ready" if available else "comfy_offline",
                     "reason": "Local Qwen workstation is ready" if available else "Local Qwen workstation is online, but ComfyUI is unavailable"}
        except (ValueError, OSError, urllib.error.URLError):
            value = {"configured": True, "available": False, "status": "offline", "reason": "Local Qwen workstation is offline"}
        _HEALTH.update(at=stamp, value=value)
        return dict(value)


def run_remote(job, job_dir, assets, progress, cancelled):
    if not health()["available"]:
        raise RuntimeError(health()["reason"])
    folder = Path(job_dir)
    marker = folder / "executor-submission.json"
    if marker.exists():
        raise RuntimeError("A Qwen executor submission already exists; preserve it before explicitly retrying")
    identifier = uuid.uuid4().hex
    safe_job = {key: value for key, value in job.items() if key in JOB_FIELDS}
    safe_job.update(kind="photo", model="qwen-local", batch_count=1)
    refs = []
    for asset in assets:
        data = Path(asset["path"]).read_bytes()
        if len(data) > MAX_IMAGE:
            raise ValueError("Qwen executor reference exceeds 40 MiB")
        refs.append({"role": "image", "data": base64.b64encode(data).decode()})
    payload = {"request_id": identifier, "job": safe_job, "images": refs}
    if len(json.dumps(payload).encode()) > MAX_BODY:
        raise ValueError("Qwen executor references exceed the private transport size limit")
    if cancelled():
        raise InterruptedError("Cancelled before Qwen executor submission")
    marker.write_text(json.dumps({"request_id": identifier, "job": safe_job, "automatic_retries": False}, indent=2))
    deadline = time.monotonic() + job.get("max_minutes", 20)*60 + 60
    state = None
    try:
        try:
            state = request("/jobs", payload, timeout=120)
        except urllib.error.HTTPError:
            raise
        except (OSError, urllib.error.URLError):
            # The executor may already have accepted a request whose reply was lost.
            # Reconcile its opaque ID using GET only; never repeat the POST.
            progress({"stage": "qwen_executor_reconciling", "executor_request_id": identifier})
        acknowledgement_deadline = min(deadline, time.monotonic() + 120)
        if state is not None:
            progress({"stage": "qwen_executor_accepted", "executor_request_id": identifier})
        while state is None or state.get("status") not in ("completed", "failed", "cancelled", "interrupted"):
            if cancelled():
                request("/jobs/" + identifier + "/cancel", {}, timeout=10)
                raise InterruptedError("Qwen executor job cancelled")
            if time.monotonic() > deadline:
                request("/jobs/" + identifier + "/cancel", {}, timeout=10)
                raise TimeoutError("Qwen executor monitoring deadline reached")
            if state is None and time.monotonic() > acknowledgement_deadline:
                raise TimeoutError("Qwen executor acknowledgement unavailable; saved request ID must be checked before retrying")
            progress({"stage": "qwen_executor_generating" if state else "qwen_executor_reconciling", "executor_request_id": identifier})
            time.sleep(2)
            try:
                state = request("/jobs/" + identifier, timeout=15)
            except urllib.error.HTTPError as exc:
                if exc.code != 404 or state is not None:
                    raise
                exc.close()
            except (OSError, urllib.error.URLError):
                # A lost status response is not an inference failure.
                continue
        (folder / "executor-result.json").write_text(json.dumps(state, indent=2))
        if state.get("status") != "completed":
            raise RuntimeError("Qwen executor job " + str(state.get("status")) + "; inspect the workstation job evidence before retrying")
        outputs = []
        for output in state.get("outputs", []):
            index = output.get("index")
            if not isinstance(index, int) or not 0 <= index <= 20:
                raise ValueError("Invalid Qwen executor output index")
            raw = request(f"/jobs/{identifier}/outputs/{index}", timeout=60, raw=True)
            from PIL import Image
            target = folder / f"qwen-{index+1}.png"
            with Image.open(io.BytesIO(raw)) as image:
                image.save(target, format="PNG")
            outputs.append({"path": str(target.resolve()), "kind": "image"})
        if not outputs:
            raise RuntimeError("Qwen executor completed without image outputs")
        return outputs
    except BaseException:
        # Never delete an unknown remote job or resubmit it on transport failure.
        progress({"stage": "qwen_executor_attention", "executor_request_id": identifier})
        raise


def _engine():
    spec = importlib.util.spec_from_file_location("qwen_executor_engine", HERE / "engine.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


class Executor:
    def __init__(self, root, engine=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.engine = engine or _engine()
        self.lock = threading.RLock()
        self.jobs = {}
        self.active = None
        self.cancelled = set()
        for path in self.root.glob("*/executor-state.json"):
            try:
                state = json.loads(path.read_text())
                identifier = state["id"]
                if not re.fullmatch(r"[0-9a-f]{32}", identifier):
                    continue
                if state.get("status") in ("accepted", "running"):
                    state["status"] = "interrupted"
                    state["error"] = "Executor restarted; inspect existing Comfy work before retrying"
                    path.write_text(json.dumps(state, indent=2))
                self.jobs[identifier] = state
            except (ValueError, OSError, KeyError):
                continue

    def health(self):
        try:
            self.engine._api("/system_stats")
            available = True
        except Exception:
            available = False
        return {"protocol": 1, "kind": "photo", "model": "qwen-local", "available": available, "busy": self.active is not None}

    def _save(self, state):
        (self.root / state["id"] / "executor-state.json").write_text(json.dumps(state, indent=2))

    def public(self, identifier):
        with self.lock:
            state = self.jobs.get(identifier)
            if state is None:
                return None
            return {key: state[key] for key in ("id", "status", "error", "progress", "outputs") if key in state}

    def submit(self, payload):
        from PIL import Image
        if not isinstance(payload, dict) or set(payload) - {"request_id", "job", "images"}:
            raise ValueError("Only a Qwen photo job and reference images are accepted")
        identifier = payload.get("request_id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError("Invalid executor request ID")
        job = payload.get("job")
        if not isinstance(job, dict) or set(job) - JOB_FIELDS or job.get("kind") != "photo" or job.get("model") != "qwen-local":
            raise ValueError("This executor accepts only bounded local Qwen photo jobs")
        if job.get("batch_count", 1) != 1 or job.get("max_minutes", 20) > 30:
            raise ValueError("Executor jobs must be individual photographs bounded to at most 30 minutes")
        images = payload.get("images", [])
        if not isinstance(images, list) or len(images) > 10:
            raise ValueError("At most 10 Qwen image references are supported")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if identifier in self.jobs:
                if self.jobs[identifier].get("fingerprint") != fingerprint:
                    raise ValueError("Executor request ID already belongs to different inputs")
                return self.public(identifier)
            if self.active is not None:
                raise RuntimeError("Qwen executor is busy; the Apps queue must schedule one job at a time")
            folder = self.root / identifier
            folder.mkdir(exist_ok=False)
            assets = []
            for i, image in enumerate(images):
                if not isinstance(image, dict) or set(image) - {"role", "data"} or image.get("role") != "image":
                    raise ValueError("Only image reference roles are accepted")
                raw = base64.b64decode(image.get("data", ""), validate=True)
                if not raw or len(raw) > MAX_IMAGE:
                    raise ValueError("Reference image size limit exceeded")
                with Image.open(io.BytesIO(raw)) as decoded:
                    decoded.verify()
                path = folder / f"source-{i+1}.png"
                path.write_bytes(raw)
                assets.append({"id": str(i), "path": str(path), "role": "image"})
            self.engine.validate_job(job, assets)
            state = {"id": identifier, "status": "accepted", "fingerprint": fingerprint, "outputs": []}
            self.jobs[identifier] = state
            self.active = identifier
            self._save(state)
            thread = threading.Thread(target=self._run, args=(job, assets, state), daemon=True)
            thread.start()
            return self.public(identifier)

    def _run(self, job, assets, state):
        identifier = state["id"]
        folder = self.root / identifier
        def progress(value):
            with self.lock:
                state["progress"] = {"stage": str(value.get("stage", "generating"))[:100]} if isinstance(value, dict) else {"stage": "generating"}
                self._save(state)
        try:
            with self.lock:
                state["status"] = "running"
                self._save(state)
            with self.engine._lock("local-comfy"):
                prepared = self.engine._prepare(assets, folder)
                # Call only the fixed local Qwen graph path, never the Apps dispatcher.
                outputs = self.engine._photo(job, folder, prepared, progress, lambda: identifier in self.cancelled)
            with self.lock:
                state["paths"] = [output["path"] for output in outputs]
                state["outputs"] = [{"index": i, "kind": "image"} for i in range(len(outputs))]
                state["status"] = "cancelled" if identifier in self.cancelled else "completed"
        except Exception as exc:
            with self.lock:
                state["status"] = "cancelled" if identifier in self.cancelled else "failed"
                state["error"] = type(exc).__name__ + ": inspect local executor evidence"
        finally:
            with self.lock:
                self._save(state)
                self.active = None

    def cancel(self, identifier):
        with self.lock:
            if identifier not in self.jobs:
                return None
            self.cancelled.add(identifier)
            return self.public(identifier)

    def output(self, identifier, index):
        with self.lock:
            state = self.jobs.get(identifier, {})
            if state.get("status") != "completed" or not 0 <= index < len(state.get("paths", [])):
                return None
            path = Path(state["paths"][index]).resolve()
            if not path.is_relative_to(self.root / identifier) or not path.is_file():
                return None
            return path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def authorized(self):
        if self.client_address[0] not in ("127.0.0.1", "::1") or self.headers.get("Origin"):
            return False
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.executor_token)

    def send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.authorized():
            return self.send(401, {"error": "Private executor authentication required"})
        if self.path == "/health":
            return self.send(200, self.server.executor.health())
        match = re.fullmatch(r"/jobs/([0-9a-f]{32})(?:/outputs/(\d{1,2}))?", self.path)
        if not match:
            return self.send(404, {"error": "Unknown executor operation"})
        identifier, index = match.groups()
        if index is None:
            state = self.server.executor.public(identifier)
            return self.send(200, state) if state else self.send(404, {"error": "Unknown executor job"})
        path = self.server.executor.output(identifier, int(index))
        if not path or path.stat().st_size > MAX_IMAGE:
            return self.send(404, {"error": "Unknown executor image"})
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self.authorized():
            return self.send(401, {"error": "Private executor authentication required"})
        try:
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("JSON required")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                return self.send(413, {"error": "Executor body exceeds the limit"})
            payload = json.loads(self.rfile.read(size))
            if self.path == "/jobs":
                return self.send(202, self.server.executor.submit(payload))
            match = re.fullmatch(r"/jobs/([0-9a-f]{32})/cancel", self.path)
            if match and payload == {}:
                state = self.server.executor.cancel(match.group(1))
                return self.send(200, state) if state else self.send(404, {"error": "Unknown executor job"})
            return self.send(404, {"error": "Unknown executor operation"})
        except (ValueError, TypeError, KeyError):
            return self.send(400, {"error": "Invalid bounded Qwen request"})
        except RuntimeError:
            return self.send(409, {"error": "Executor is busy or unavailable"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=36446)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    secret = token()
    if len(secret) < 32:
        raise SystemExit("NORA_QWEN_EXECUTOR_TOKEN must contain at least 32 characters")
    engine = _engine()
    root = args.root or Path(os.environ.get("NORA_QWEN_EXECUTOR_ROOT", str(engine.ROOT / "work/qwen-executor")))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.executor = Executor(root, engine)
    server.executor_token = secret
    server.serve_forever()


if __name__ == "__main__":
    main()
