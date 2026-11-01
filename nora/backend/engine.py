"""Native Comfy adapters. Importing this module never starts GPU work.

Reference capabilities are source/schema verified; they are not quality promises.
Only the explicitly resumed SimplePod rental is paused by this adapter.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path(os.environ.get("NORA_PROJECT_ROOT", str(Path(__file__).resolve().parents[4]))).expanduser().resolve()
PHOTO_URL = "http://127.0.0.1:8190"
TEMPLATES = Path(__file__).resolve().parent / "templates"
H3_TEMPLATE = TEMPLATES / "h3-ref2va.json"
QWEN_TEMPLATE = TEMPLATES / "qwen-photo.json"
PHOTO_LORAS = ("Alice_Qwen_v1_49images.safetensors", "Alice_Qwen_v2_70images.safetensors")
REFERENCE_LIMITS = {"photo": {"image": 10}, "video": {"start": 1, "end": 1, "image": 9, "video": 3, "audio": 3}}
_CLOUD_MODULE = None
_QWEN_MODULE = None


def _cloud():
    global _CLOUD_MODULE
    if _CLOUD_MODULE is None:
        spec = importlib.util.spec_from_file_location("nora_studio_cloud", Path(__file__).with_name("cloud.py"))
        _CLOUD_MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_CLOUD_MODULE)
    return _CLOUD_MODULE


def _is_cloud(job):
    return job.get("model") not in (None, "", "qwen-local", "h3-simplepod")


def _qwen_executor():
    global _QWEN_MODULE
    if _QWEN_MODULE is None:
        spec = importlib.util.spec_from_file_location("nora_qwen_executor", Path(__file__).with_name("qwen_executor.py"))
        _QWEN_MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_QWEN_MODULE)
    return _QWEN_MODULE


def job_readiness(job):
    """Scheduler readiness; deliberately separate from pure input validation."""
    if not _is_cloud(job) and job.get("kind") == "photo" and os.environ.get("NORA_QWEN_EXECUTOR_URL"):
        value = _qwen_executor().health()
        return {"available": value["available"], "reason": value["reason"]}
    if not _is_cloud(job) and job.get("kind") == "photo":
        configured = QWEN_TEMPLATE.is_file() and Path("/home/victor/Nora/runtime/comfy-photos").is_dir()
        return {"available": configured, "reason": "Local Qwen runtime is configured" if configured else "Private Qwen executor is not configured on this server"}
    return {"available": True, "reason": "Execution backend is configured"}


def capabilities():
    result = {
        "photo": {"backend": "local-comfy", "url": PHOTO_URL,
                  "model": "Qwen Image 2.1 BF16", "roles": dict(REFERENCE_LIMITS["photo"]),
                  "text_only": True, "lora_names": list(PHOTO_LORAS),
                  "default_lora": PHOTO_LORAS[1], "default_steps": 25,
                  "default_width": 768, "default_height": 1024,
                  "dimension_step": 32, "dimension_min": 256, "dimension_max": 1536,
                  "max_minutes_max": 30,
                  "prompt_tags": "<image1> … <image10>",
                  "note": "Native node exposes 16 slots; studio caps at the model's documented 10. References and requested output size are separate; no automatic crop or prompt rewrite."},
        "video": {"backend": "simplepod", "model": "MiniMax H3 Singularity Ref2VA INT8",
                  "roles": dict(REFERENCE_LIMITS["video"]),
                  "max_assets": 12, "text_only": True, "default_steps": 25,
                  "default_width": 704, "default_height": 960,
                  "dimension_step": 32, "dimension_min": 256, "dimension_max": 1536,
                  "fps": 24, "default_frames": 141, "frame_step": 17, "frame_offset": 5,
                  "frames_min": 107, "frames_max": 362,
                  "reference_seconds_min": 2, "reference_seconds_max": 15,
                  "video_seconds_total_max": 15, "audio_seconds_total_max": 15,
                  "generated_audio": True, "video_ref_audio": True,
                  "default_lora": "alice-h3-pilot-200.safetensors",
                  "default_lora_strength": 0.8,
                  "prompt_tags": "<Picture 1>, <Video 1>, <Audio 1>",
                  "guide_warning": "Start/end frames are soft AddGuide conditioning, not hard pixel locks. Native guides resize and center-crop to the output aspect ratio; choose matching dimensions to avoid cropping.",
                  "note": "Image references and frame-0 guides tested. End guides, mixed video/audio references and native generated audio are wired from installed source but need visual/audio review. Bracket camera commands pass through verbatim; no special parser is claimed."},
    }
    photo_available = QWEN_TEMPLATE.is_file() and Path("/home/victor/Nora/runtime/comfy-photos").is_dir()
    qwen_health = None
    if os.environ.get("NORA_QWEN_EXECUTOR_URL"):
        qwen_health = _qwen_executor().health()
        photo_available = qwen_health["available"]
    worker_state = Path(os.environ.get("NORA_SIMPLEPOD_STATE", str(ROOT / "work/simplepod/worker.json")))
    video_available = H3_TEMPLATE.is_file() and worker_state.is_file()
    if video_available:
        try:
            video_available = Path(json.loads(worker_state.read_text())["ssh_identity"]).is_file()
        except (KeyError, ValueError, OSError):
            video_available = False
    result["photo"]["available"] = photo_available
    result["video"]["available"] = video_available
    photo_reason = qwen_health["reason"] if qwen_health else "Local Qwen runtime is configured" if photo_available else "Local Qwen runtime is not configured on this server"
    result["photo"]["availability_reason"] = photo_reason
    result["executors"] = {"qwen": qwen_health or {"configured": photo_available, "available": photo_available,
                                                 "status": "local_runtime" if photo_available else "not_configured", "reason": photo_reason}}
    result["models"] = [{"id": "qwen-local", "provider": "local", "kind": "photo", "label": "Qwen 2.1 · local",
                         "roles": result["photo"]["roles"], "settings": {}, "credential_configured": photo_available,
                         "available": photo_available, "availability_reason": photo_reason,
                         "availability": "executor_ready" if qwen_health and photo_available else "executor_offline" if qwen_health else "runtime_configured_not_health_checked" if photo_available else "not_configured_on_this_host"},
                        {"id": "h3-simplepod", "provider": "simplepod", "kind": "video", "label": "MiniMax H3 · SimplePod",
                         "roles": result["video"]["roles"], "settings": {}, "credential_configured": video_available,
                         "available": video_available, "availability": "worker_configured_not_health_checked" if video_available else "not_configured_on_this_host"}] + _cloud().catalog()
    return result


def estimate_job(job, assets):
    if _is_cloud(job):
        return _cloud().estimate(job, assets)
    validate_job(job, assets)
    return {"estimated_usd": None, "upper_usd": None, "status": "unknown_before_inference",
            "details": "Local Qwen has no API charge; SimplePod charges for actual rental time.",
            "pricing_source": "local/runtime", "uncertainty": "Rental startup, inference and transfer time depend on job settings."}


def refresh_cloud_catalog():
    return _cloud().refresh_catalog()


def _integer(job, key, default, lo, hi):
    value = job.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{key} must be an integer from {lo} to {hi}")
    return value


def _probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                             "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError("Media could not be decoded by ffprobe")
    data = json.loads(result.stdout)
    streams = {s.get("codec_type") for s in data.get("streams", [])}
    return float(data.get("format", {}).get("duration", 0)), "audio" in streams, "video" in streams


def validate_job(job, assets):
    if _is_cloud(job):
        return _cloud().validate_job(job, assets)
    if job.get("model") == "qwen-local" and job.get("kind") != "photo":
        raise ValueError("Local Qwen supports photo jobs only")
    if job.get("model") == "h3-simplepod" and job.get("kind") != "video":
        raise ValueError("SimplePod H3 supports video jobs only")
    kind = job.get("kind")
    if kind not in ("photo", "video"):
        raise ValueError("kind must be photo or video")
    if not isinstance(job.get("prompt"), str) or not job["prompt"].strip() or len(job["prompt"]) > 30000:
        raise ValueError("A prompt of 1–30000 characters is required")
    for key, default in (("width", 768 if kind == "photo" else 704), ("height", 1024 if kind == "photo" else 960)):
        value = _integer(job, key, default, 256, 1536)
        if value % 32:
            raise ValueError(f"{key} must be divisible by 32")
    _integer(job, "seed", 1, 0, 2**63-1)
    _integer(job, "steps", 25, 1, 60)
    _integer(job, "max_minutes", 20, 5, 30 if kind == "photo" else 90)
    _integer(job, "batch_count", 1, 1, 20)
    strength = job.get("lora_strength", 0.8)
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not 0 <= strength <= 1.5:
        raise ValueError("lora_strength must be from 0 to 1.5")
    for key in ("lora_enabled", "generated_audio", "video_ref_audio"):
        if key in job and not isinstance(job[key], bool):
            raise ValueError(f"{key} must be boolean")
    # Validation must remain pure: live capabilities can probe the private
    # workstation, while callers may validate under the persistent queue lock.
    allowed = REFERENCE_LIMITS[kind]
    counts = {role: 0 for role in allowed}
    videos = audios = 0.0
    audio_count = 0
    for asset in assets:
        role = asset.get("role")
        if "include_audio" in asset and not isinstance(asset["include_audio"], bool):
            raise ValueError("include_audio must be boolean")
        if role not in allowed:
            raise ValueError(f"{role!r} is not supported for {kind}")
        counts[role] += 1
        if counts[role] > allowed[role]:
            raise ValueError(f"At most {allowed[role]} {role} references are supported")
        path = Path(asset["path"])
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise ValueError("Asset must be an existing nonsymlink absolute file")
        if role in ("image", "start", "end"):
            from PIL import Image
            try:
                with Image.open(path) as image:
                    image.verify()
            except Exception as exc:
                raise ValueError("Invalid image reference") from exc
        else:
            duration, has_audio, has_video = _probe(path)
            if (role == "audio" and not has_audio) or (role == "video" and not has_video):
                raise ValueError(f"Reference contains no {role} stream")
            if not 2 <= duration <= 15:
                raise ValueError("Each video/audio reference must be 2–15 seconds")
            if role == "video":
                videos += duration
                if asset.get("include_audio", job.get("video_ref_audio", False)) and has_audio:
                    audios += duration
                    audio_count += 1
            else:
                audios += duration
                audio_count += 1
    if kind == "photo" and job.get("lora_name", PHOTO_LORAS[1]) not in PHOTO_LORAS:
        raise ValueError("Select a Qwen LoRA from the installed photo family")
    if kind == "video":
        frames = _integer(job, "frames", 141, 107, 362)
        if (frames - 5) % 17:
            raise ValueError("H3 frames must equal 17k+5 (107,124,141,…,362)")
        if len(assets) > 12 or audio_count > 3 or videos > 15.01 or audios > 15.01:
            raise ValueError("H3 allows at most 12 files and 15 seconds total video/audio references per modality")


@contextlib.contextmanager
def _lock(resource):
    folder = ROOT / "work/generation-studio"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (resource + ".lock")).open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another studio job owns this generation resource") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _api(path, payload=None):
    req = urllib.request.Request(PHOTO_URL + path, data=None if payload is None else json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def _worker():
    default = Path(__file__).resolve().parent / "runtime/simplepod-worker.py"
    spec = importlib.util.spec_from_file_location("studio_simplepod_worker", Path(os.environ.get("NORA_SIMPLEPOD_WORKER_MODULE", str(default))))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _remote_api(w, state, path, payload=None):
    # Only fixed-origin loopback REST is accessible; request data travels over stdin.
    script = """import json,sys,urllib.request
x=json.load(sys.stdin)
r=urllib.request.Request('http://127.0.0.1:8188'+x['path'],data=None if x['payload'] is None else json.dumps(x['payload']).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(r,timeout=25) as v: print(v.read().decode())
"""
    command = "python3 -c " + shlex.quote(script)
    result = w.remote(state, command, timeout=40, input_text=json.dumps({"path": path, "payload": payload}))
    if result.returncode:
        raise RuntimeError("Remote Comfy API unavailable; inspect job evidence")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def _queue_empty(api):
    q = api("/queue")
    if q.get("queue_running") or q.get("queue_pending"):
        raise RuntimeError("ComfyUI has existing work; refusing to interfere with its queue")


def _cancel_prompt(api, pid):
    queue = api("/queue")
    running = queue.get("queue_running", [])
    if running and all(row[1] == pid for row in running):
        api("/interrupt", {})
    elif any(row[1] == pid for row in queue.get("queue_pending", [])):
        api("/queue", {"delete": [pid]})


def _wait(api, pid, deadline, progress, cancelled, job_dir):
    try:
        while time.monotonic() < deadline:
            if cancelled():
                raise InterruptedError("Job cancelled")
            history = api("/history/" + pid)
            if pid in history:
                record = history[pid]
                (job_dir / "history.json").write_text(json.dumps(record, indent=2))
                if record.get("status", {}).get("status_str") != "success":
                    raise RuntimeError("Comfy inference failed; see history.json")
                return record
            progress({"stage": "generating", "prompt_id": pid})
            time.sleep(3)
        raise TimeoutError("Bounded generation time expired")
    except BaseException:
        _cancel_prompt(api, pid)
        raise


def _outputs(history):
    seen = set()
    for node in history.get("outputs", {}).values():
        for key in ("images", "gifs", "videos", "audio"):
            for item in node.get(key, []):
                if item.get("type", "output") != "output":
                    continue
                rel = PurePosixPath(item.get("subfolder", "")) / item["filename"]
                if rel.is_absolute() or ".." in rel.parts or str(rel) in seen:
                    continue
                seen.add(str(rel))
                yield item, rel


def _kind(path):
    suffix = path.suffix.lower()
    return "video" if suffix in (".mp4", ".webm", ".mov") else "audio" if suffix in (".flac", ".wav", ".mp3", ".ogg") else "image"


def _upload_image(path, name):
    boundary = "studio" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(PHOTO_URL + "/upload/image", body,
                                 {"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.load(response)
    return str(PurePosixPath(data.get("subfolder", "")) / data["name"])


def _prepare(assets, job_dir):
    folder = job_dir / "inputs"
    folder.mkdir(exist_ok=True)
    prepared = []
    for i, original in enumerate(assets):
        asset = dict(original)
        source = Path(asset["path"])
        role = asset["role"]
        name = "studio-" + uuid.uuid4().hex + f"-{i}"
        if role in ("image", "start", "end"):
            from PIL import Image, ImageOps
            dest = folder / (name + ".png")
            with Image.open(source) as image:
                # Resolve EXIF orientation so native visual conditioning matches the UI.
                ImageOps.exif_transpose(image).convert("RGB").save(dest)
        elif role == "video":
            dest = folder / (name + ".mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-vf", "fps=24,pad=ceil(iw/2)*2:ceil(ih/2)*2",
                            "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-y", str(dest)], check=True, timeout=180)
        else:
            dest = folder / (name + ".wav")
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-vn", "-ar", "32000", "-ac", "2", "-y", str(dest)], check=True, timeout=90)
        asset.update(path=str(dest), filename=dest.name,
                     source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        prepared.append(asset)
    (job_dir / "assets.json").write_text(json.dumps(prepared, indent=2))
    return prepared


def build_photo_graph(job, assets):
    graph = json.loads(QWEN_TEMPLATE.read_text())
    for key in list(graph):
        if graph[key]["class_type"] == "LoadImage":
            del graph[key]
    encode = graph["100"]["inputs"]
    for key in list(encode):
        if key.startswith("images."):
            del encode[key]
    encode.update(prompt=job["prompt"], negative_prompt=job.get("negative_prompt", ""), resolution=1024)
    for i, asset in enumerate(assets):
        key = str(300 + i)
        graph[key] = {"class_type": "LoadImage", "inputs": {"image": asset["filename"]}}
        encode[f"images.image_{i+1}"] = [key, 0]
    graph["101"]["inputs"].update(width=job.get("width", 768), height=job.get("height", 1024), batch_size=1)
    graph["102"]["inputs"].update(seed=job.get("seed", 1), steps=job.get("steps", 25))
    if job.get("lora_enabled", False):
        graph["5"]["inputs"].update(lora_name=job.get("lora_name", PHOTO_LORAS[1]), strength_model=job.get("lora_strength", .8))
    else:
        del graph["5"]
        graph["4"]["inputs"]["model"] = ["1", 0]
    graph["104"]["inputs"]["filename_prefix"] = "NoraStudio/photo-" + uuid.uuid4().hex
    return graph


def build_video_graph(job, assets):
    graph = json.loads(H3_TEMPLATE.read_text())
    del graph["10"]
    del graph["31"]
    encode = graph["20"]["inputs"]
    for key in list(encode):
        if key.startswith("ref_") and key != "ref_image_size":
            del encode[key]
    encode.update(prompt=job["prompt"], width=job.get("width", 704), height=job.get("height", 960), length=job.get("frames", 141))
    condition = ["20", 0]
    counts = {"image": 0, "video": 0, "audio": 0}
    for i, asset in enumerate(assets):
        key = str(300 + 3*i)
        role = asset["role"]
        if role in ("image", "start", "end"):
            graph[key] = {"class_type": "LoadImage", "inputs": {"image": asset["filename"]}}
            if role == "image":
                encode[f"ref_images.ref_image_{counts['image']}"] = [key, 0]
                counts["image"] += 1
            else:
                guide = str(301 + 3*i)
                graph[guide] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
                    "positive": condition, "latent": ["20", 1], "vae": ["3", 0], "image": [key, 0],
                    "frame_idx": 0 if role == "start" else -1}}
                condition = [guide, 0]
        elif role == "video":
            graph[key] = {"class_type": "LoadVideo", "inputs": {"file": asset["filename"]}}
            parts = str(301 + 3*i)
            graph[parts] = {"class_type": "GetVideoComponents", "inputs": {"video": [key, 0]}}
            encode[f"ref_videos.ref_video_{counts['video']}"] = [parts, 0]
            if asset.get("include_audio", job.get("video_ref_audio", False)) and _probe(Path(asset["path"]))[1]:
                encode[f"ref_video_audios.ref_video_audio_{counts['video']}"] = [parts, 1]
            counts["video"] += 1
        else:
            graph[key] = {"class_type": "LoadAudio", "inputs": {"audio": asset["filename"]}}
            encode[f"ref_audios.ref_audio_{counts['audio']}"] = [key, 0]
            counts["audio"] += 1
    graph["22"]["inputs"]["conditioning"] = condition
    graph["21"]["inputs"]["noise_seed"] = job.get("seed", 1)
    graph["24"]["inputs"]["steps"] = job.get("steps", 25)
    prefix = "NoraStudio/video-" + uuid.uuid4().hex
    graph["28"]["inputs"]["filename_prefix"] = prefix
    if job.get("lora_enabled", False):
        graph["40"]["inputs"]["strength_model"] = job.get("lora_strength", .8)
    else:
        del graph["40"]
        for key in ("22", "24"):
            graph[key]["inputs"]["model"] = ["1", 0]
    if job.get("generated_audio", False):
        graph["80"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["25", 0], "vae": ["4", 0]}}
        graph["81"] = {"class_type": "SaveAudio", "inputs": {"audio": ["80", 0], "filename_prefix": prefix}}
        graph["27"]["inputs"]["audio"] = ["80", 0]
    return graph


def _photo(job, job_dir, assets, progress, cancelled):
    _queue_empty(_api)
    for asset in assets:
        if cancelled():
            raise InterruptedError("Job cancelled")
        asset["filename"] = _upload_image(Path(asset["path"]), asset["filename"])
    graph = build_photo_graph(job, assets)
    (job_dir / "workflow-api.json").write_text(json.dumps(graph, indent=2))
    if cancelled():
        raise InterruptedError("Job cancelled")
    _queue_empty(_api)
    submitted = _api("/prompt", {"prompt": graph, "client_id": "nora-studio-" + uuid.uuid4().hex})
    (job_dir / "submission.json").write_text(json.dumps(submitted, indent=2))
    if submitted.get("node_errors") or not submitted.get("prompt_id"):
        raise RuntimeError("Comfy rejected the workflow; inspect submission.json")
    history = _wait(_api, submitted["prompt_id"], time.monotonic()+job.get("max_minutes", 20)*60, progress, cancelled, job_dir)
    outputs = []
    for index, (item, rel) in enumerate(_outputs(history)):
        target = job_dir / (str(index) + "-" + rel.name)
        with urllib.request.urlopen(PHOTO_URL + "/view?" + urllib.parse.urlencode(item), timeout=60) as response:
            target.write_bytes(response.read())
        outputs.append({"path": str(target), "kind": _kind(target)})
    return outputs


def _video(job, job_dir, assets, progress, cancelled):
    w = _worker()
    state = json.loads(w.STATE.read_text())
    original_instance_id = state["instance_id"]
    events = []
    resumed = False
    try:
        if cancelled():
            raise InterruptedError("Job cancelled")
        progress({"stage": "starting_gpu"})
        # resume refuses an already-running rental; it arms an independent systemd pause timer.
        w.resume(state, events, job.get("max_minutes", 20))
        resumed = True
        deadline = time.monotonic() + job.get("max_minutes", 20)*60 - 45
        w.ready(state, events)
        api = lambda path, payload=None: _remote_api(w, state, path, payload)
        _queue_empty(api)
        if cancelled():
            raise InterruptedError("Job cancelled")
        graph = build_video_graph(job, assets)
        # Refuse unsupported installed nodes before uploading or submitting inference.
        installed = api("/object_info")
        for node_type in {n["class_type"] for n in graph.values()}:
            if node_type not in installed:
                raise RuntimeError("Remote Comfy lacks required node " + node_type)
        if job.get("lora_enabled", False):
            digest = w.remote(state, "sha256sum /opt/nora-comfy/ComfyUI/models/loras/alice-h3-pilot-200.safetensors", timeout=25)
            if digest.returncode or digest.stdout.split()[0] != "de504eb2b76f6608126368f7cdc60e378b879049e718005d49908fbda96adfdc":
                raise RuntimeError("Remote Alice LoRA identity differs from reviewed adapter")
        if assets:
            host = state["ssh_user"] + "@" + state["ssh_host"]
            subprocess.run(["scp", *w.ssh_args(state), *[a["path"] for a in assets], host+":/opt/nora-comfy/ComfyUI/input/"],
                           check=True, timeout=180)
        (job_dir / "workflow-api.json").write_text(json.dumps(graph, indent=2))
        if cancelled():
            raise InterruptedError("Job cancelled")
        _queue_empty(api)
        submitted = api("/prompt", {"prompt": graph, "client_id": "nora-studio-" + uuid.uuid4().hex})
        (job_dir / "submission.json").write_text(json.dumps(submitted, indent=2))
        if submitted.get("node_errors") or not submitted.get("prompt_id"):
            raise RuntimeError("Remote Comfy rejected workflow; inspect submission.json")
        history = _wait(api, submitted["prompt_id"], deadline, progress, cancelled, job_dir)
        outputs = []
        for index, (item, rel) in enumerate(_outputs(history)):
            target = job_dir / (str(index) + "-" + rel.name)
            host = state["ssh_user"] + "@" + state["ssh_host"]
            subprocess.run(["scp", *w.ssh_args(state), host+":/opt/nora-comfy/ComfyUI/output/"+str(rel), str(target)], check=True, timeout=120)
            outputs.append({"path": str(target), "kind": _kind(target)})
        return outputs
    finally:
        # resume can fail after provider acceptance while arming the timer.
        owned = resumed or any(e["event"] == "resume_accepted" for e in events)
        try:
            if owned:
                # Accounting/UI availability cannot veto rental cleanup. Preserve
                # its failure in local evidence without replacing the original
                # inference/startup error or leaking a database error message.
                try:
                    progress({"stage": "pausing_gpu"})
                except Exception as exc:
                    events.append({"event": "pause_progress_unavailable", "error_type": type(exc).__name__})
                try:
                    current = json.loads(w.STATE.read_text())
                except (OSError, ValueError):
                    current = None
                if current and current["instance_id"] not in (original_instance_id, state["instance_id"]):
                    raise RuntimeError("Worker ownership changed; refusing to pause another rental")
                w.pause(state, events)
        finally:
            (job_dir / "rental-events.json").write_text(json.dumps(events, indent=2))


def run_job(job, job_dir, assets, progress, cancelled):
    validate_job(job, assets)
    if _is_cloud(job):
        return _cloud().run_job(job, job_dir, assets, progress, cancelled)
    job_dir = Path(job_dir).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    if (job_dir / "submission.json").exists():
        raise RuntimeError("Existing submission preserved; refusing duplicate inference")
    with _lock("simplepod" if job["kind"] == "video" else "local-comfy"):
        if cancelled():
            raise InterruptedError("Job cancelled")
        progress({"stage": "preparing"})
        prepared = _prepare(assets, job_dir)
        if job["kind"] == "photo" and os.environ.get("NORA_QWEN_EXECUTOR_URL"):
            results = _qwen_executor().run_remote(job, job_dir, prepared, progress, cancelled)
        else:
            results = (_video if job["kind"] == "video" else _photo)(job, job_dir, prepared, progress, cancelled)
        if not results:
            raise RuntimeError("Comfy completed without downloadable outputs")
        return results
