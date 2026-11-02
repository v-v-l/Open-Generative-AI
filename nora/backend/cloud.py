"""Explicit cloud image/video adapters; imports/catalog reads never generate media.

Public catalogs describe availability, not account access. Paid POSTs are never
retried. Credentials remain server-side, and saved submissions omit image bytes.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(os.environ.get("NORA_PROJECT_ROOT", str(Path(__file__).resolve().parents[4]))).expanduser().resolve()
CACHE = ROOT / "work/generation-studio/cloud-catalog.json"
STAMP = "2026-11-01"
ORIGIN = "https://openrouter.ai/api/v1"
OPENAI = "https://api.openai.com/v1"
PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"
IMAGE_SOURCE = "https://openrouter.ai/docs/guides/overview/multimodal/image-generation"
VIDEO_SOURCE = "https://openrouter.ai/api/v1/videos/models"
GOOGLE_IMAGES = ("google/gemini-2.5-flash-image", "google/gemini-3-pro-image", "google/gemini-3.1-flash-image",
                 "google/gemini-3.1-flash-lite-image", "google/gemini-nano-banana-2.1")
VEO = ("google/veo-3.1", "google/veo-3.1-fast", "google/veo-3.1-lite")
REQUESTED_VIDEOS = ("heygen/heygen-video-1", "heygen/avatar-iv", "minimax/hailuo-3-max")
OPENAI_MODELS = ("gpt-image-2.5-sunburst", "gpt-image-2.5-sunburst-2026-09-08",
                 "gpt-image-2.5-flare", "gpt-image-2.5-flare-2026-09-08", "gpt-image-2",
                 "gpt-image-1.5", "gpt-image-1-mini")


def _credentials():
    names = ("OPENAI_API_KEY", "OPENAI_PROJECT_ID", "OPENAI_ORG_ID", "OPENROUTER_API_KEY")
    values = {}
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() in names:
                value = value.strip()
                if value[:1] in ("'", '"') and value[-1:] == value[:1]:
                    value = value[1:-1]
                values[name.strip()] = value
    values.update({name: os.environ[name] for name in names if os.environ.get(name)})
    return values


def _enum(values, default):
    return {"type": "enum", "values": values, "default": default}


def _bootstrap():
    rows = []
    for slug in OPENAI_MODELS:
        newer = slug.startswith("gpt-image-2.5")
        rates = {"text_input_per_million": 5, "image_input_per_million": 8, "image_output_per_million": 30}
        if slug == "gpt-image-1.5":
            rates["image_output_per_million"] = 32
        if slug == "gpt-image-1-mini":
            rates = {"text_input_per_million": 2, "image_input_per_million": 2.5, "image_output_per_million": 8}
        rows.append({"id": "openai:" + slug, "remote_model": slug, "provider": "openai", "kind": "photo",
                     "label": "OpenAI · " + slug, "roles": {"image": 16}, "max_assets": 16,
                     "settings": {"size": _enum(["1024x1024", "1024x1536", "1536x1024"], "1024x1536"),
                                  "quality": _enum(["low", "medium", "high"] + (["xhigh", "max"] if newer else []) + ["auto"], "high")},
                     "pricing": rates, "pricing_source": PRICE_SOURCE, "timestamp": STAMP,
                     "note": "Direct Images API; no seed control. Cost is computed from returned token usage; cached discounts do not apply. Model access is not verified by this catalog."})
    ratios = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
    for slug, label, maximum, resolutions, tag, rate in (
            (GOOGLE_IMAGES[0], "Nano Banana", 3, [], "google-vertex/global", .00003),
            (GOOGLE_IMAGES[1], "Nano Banana Pro", 14, ["1K", "2K", "4K"], "google-ai-studio/global", .00012),
            (GOOGLE_IMAGES[2], "Nano Banana 2", 14, ["512", "1K", "2K", "4K"], "google-ai-studio", .00006),
            (GOOGLE_IMAGES[3], "Nano Banana 2 Lite", 14, ["1K"], "google-ai-studio", .00003),
            (GOOGLE_IMAGES[4], "Nano Banana 2.1", 14, ["1K", "2K", "4K"], "google-ai-studio", .00003)):
        settings = {"aspect_ratio": _enum(ratios if maximum == 3 or "pro" in slug else ["1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"], "9:16")}
        if resolutions:
            settings["resolution"] = _enum(resolutions, "1K")
        rows.append({"id": "openrouter:" + slug, "remote_model": slug, "provider": "openrouter", "kind": "photo",
                     "label": "OpenRouter · " + label, "roles": {"image": maximum}, "max_assets": maximum,
                     "provider_tag": tag, "settings": settings,
                     "pricing": ([{"billable": "input_image", "unit": "token", "cost_usd": .0000003 if maximum == 3 else .000002}] if maximum == 3 or "pro" in slug else []) + [{"billable": "output_image", "unit": "token", "cost_usd": rate}],
                     "pricing_source": ORIGIN + "/images/models/" + slug + "/endpoints", "timestamp": STAMP,
                     "note": "Dedicated OpenRouter Image API with inline image references. Endpoint is pinned, automatic provider fallback disabled. Token-priced output; no flat per-image quote."})
    for slug, prices in (
            (VEO[0], {"duration_seconds_with_audio": ".40", "duration_seconds_without_audio": ".20", "duration_seconds_with_audio_4k": ".60", "duration_seconds_without_audio_4k": ".40"}),
            (VEO[1], {"duration_seconds_with_audio": ".12", "duration_seconds_without_audio": ".10", "duration_seconds_with_audio_720p": ".10", "duration_seconds_without_audio_720p": ".08", "duration_seconds_with_audio_4k": ".30", "duration_seconds_without_audio_4k": ".25"}),
            (VEO[2], {"duration_seconds_with_audio": ".08", "duration_seconds_without_audio": ".05", "duration_seconds_with_audio_720p": ".05", "duration_seconds_without_audio_720p": ".03"})):
        rows.append({"id": "openrouter:" + slug, "remote_model": slug, "provider": "openrouter", "kind": "video",
                     "label": "OpenRouter · " + slug.split("/")[-1], "roles": {"start": 1, "end": 1}, "max_assets": 2,
                     "settings": {"duration": _enum([4, 6, 8], 4), "resolution": _enum(["720p", "1080p"] + ([] if "lite" in slug else ["4K"]), "720p"),
                                  "aspect_ratio": _enum(["16:9", "9:16"], "9:16"), "generate_audio": {"type": "boolean", "default": False}, "seed": {"type": "boolean", "default": True}},
                     "pricing": prices, "pricing_source": VIDEO_SOURCE, "timestamp": STAMP,
                     "note": "Async OpenRouter Videos API. Inline first/last image transport follows official string schema and existing open-source clients; not yet validated with a paid studio request. Video/audio references are not exposed for this model."})
    return rows


def catalog():
    rows = _bootstrap()
    if CACHE.is_file():
        try:
            rows = json.loads(CACHE.read_text())["models"]
        except (ValueError, KeyError):
            pass
    keys = _credentials()
    result = []
    for row in rows:
        row = dict(row)
        # Cache files predate dependent output choices. Publish the same rule
        # enforced at validation without refreshing unrelated pinned endpoints.
        if row.get('kind') == 'video' and row.get('remote_model','').startswith('google/veo-') and '4K' in row.get('settings',{}).get('resolution',{}).get('values',[]):
            row['output_constraints'] = [{'when':{'resolution':'4K'}, 'allowed':{'duration':[8]}}]
        row["credential_configured"] = bool(keys.get("OPENAI_API_KEY" if row["provider"] == "openai" else "OPENROUTER_API_KEY"))
        row["availability"] = "catalogued_not_account_verified"
        account_snapshot = ROOT / "work/provider-api-research/openai-account-image-models.json"
        if row["provider"] == "openai" and account_snapshot.is_file():
            try:
                row["account_model_listed"] = row["remote_model"] in json.loads(account_snapshot.read_text()).get("ids", [])
                row["account_model_listed_at"] = STAMP
                row["account_access_note"] = "Read-only model-list evidence; generation access and account balance have not been tested."
            except (ValueError, OSError):
                pass
        result.append(row)
    return result


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _diagnostic_text(value, sensitive=(), limit=1000):
    """Retain useful provider explanations without reflected credentials/media."""
    if not isinstance(value,str):return None
    for secret in sensitive:
        if isinstance(secret,str) and secret:value=value.replace(secret,'[redacted]')
    value=re.sub(r'(?i)data:[^\s"\']+','[inline data redacted]',value)
    value=re.sub(r'(?i)(?:https?|postgres(?:ql)?)://[^\s"\']+','[URL redacted]',value)
    value=re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+',r'\1[redacted]',value)
    value=re.sub(r'\bsk-[A-Za-z0-9_-]+','[redacted]',value)
    value=re.sub(r'[A-Za-z0-9+/_=-]{80,}','[encoded data redacted]',value)
    value=re.sub(r'(?:/home/|/tmp/|/var/|/opt/)[^\s"\']+','[path redacted]',value)
    return value[:limit]


def _http_diagnostic(error, sensitive=()):
    """Read a bounded JSON error once; never persist an upstream response body."""
    try:
        sensitive=tuple(sensitive)+tuple(_credentials().values())
        request_id=error.headers.get('x-request-id') if error.headers else None
        if isinstance(request_id,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,200}',request_id):
            error.provider_request_id=_diagnostic_text(request_id,sensitive,200)
        if not hasattr(error,'provider_error'):
            raw=error.read(65537)
            error.close()
            parsed=json.loads(raw) if len(raw)<=65536 else None
            upstream=parsed.get('error') if isinstance(parsed,dict) else None
            diagnostic={}
            if isinstance(upstream,dict):
                for key in ('code','type','param'):
                    value=upstream.get(key)
                    if type(value) is int:value=str(value)
                    if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.\[\]-]{1,150}',value):
                        diagnostic[key]=_diagnostic_text(value,sensitive,150)
                message=_diagnostic_text(upstream.get('message'),sensitive)
                if message:diagnostic['message']=message
            error.provider_error=diagnostic
        else:
            error.provider_error={key:_diagnostic_text(value,sensitive,1000 if key=='message' else 150)
                                  for key,value in error.provider_error.items() if key in ('code','type','param','message')}
        if error.provider_error.get('message'):
            # HTTPError.__str__ uses msg, keeping its original status/type intact.
            error.msg=error.provider_error['message']
        return error.provider_error
    except Exception:
        # Diagnostic parsing must never replace the original transport failure.
        error.provider_error={}
        return {}


def _request(url, payload=None, headers=None, timeout=60, raw=False):
    # API origins are fixed constants. Redirects cannot forward credentials elsewhere.
    if not (url.startswith(ORIGIN + "/") or url.startswith(OPENAI + "/")):
        raise ValueError("Unsupported API origin")
    data = payload if isinstance(payload, bytes) else None if payload is None else json.dumps(payload).encode()
    h = {"User-Agent": "NoraGenerationStudio/1.0", **(headers or {})}
    if payload is not None and not isinstance(payload, bytes):
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as response:
            data = response.read()
            if raw:
                return data
            result = json.loads(data)
            if isinstance(result, dict) and response.headers.get("x-request-id"):
                result["_request_id"] = response.headers["x-request-id"]
            return result
    except urllib.error.HTTPError as error:
        _http_diagnostic(error,[payload.get('prompt','')] if isinstance(payload,dict) else ())
        raise


def _video_descriptor(model, timestamp):
    """Use catalog shapes; speech-led Avatar IV has its own explicit contract."""
    if model['id'] == 'heygen/avatar-iv':
        if not all(model.get(key) for key in ('supported_resolutions', 'supported_aspect_ratios')) or 'voice_id' not in model.get('allowed_passthrough_parameters', []):
            return None
        row = {'id':'openrouter:'+model['id'], 'remote_model':model['id'], 'provider':'openrouter', 'kind':'video',
                'label':'HeyGen · Avatar IV', 'adapter':'heygen_avatar_script', 'roles':{'image':1}, 'required_roles':{'image':1}, 'max_assets':1,
                'settings':{'resolution':_enum(model['supported_resolutions'],model['supported_resolutions'][0]),
                            'aspect_ratio':_enum(model['supported_aspect_ratios'],'9:16' if '9:16' in model['supported_aspect_ratios'] else model['supported_aspect_ratios'][0]),
                            'voice_id':{'type':'string','required':True,'max_length':200,'title':'Голос HeyGen · Voice ID','description':'ID голоса HeyGen для озвучки текста речи.'},
                            'motion_prompt':{'type':'string','max_length':2000,'title':'Движения и жесты','description':'Не произносится; отдельная инструкция движения.'},
                            'expressiveness':_enum(['low','medium','high'],'low'), 'fit':_enum(['contain','cover'],'contain'),
                            'remove_background':{'type':'boolean','default':False}},
                'passthrough_keys':[key for key in ('voice_id','motion_prompt','expressiveness','fit','remove_background') if key in model.get('allowed_passthrough_parameters',[])],
                'prompt_label':'Текст речи', 'input_note':'Одно фото + текст речи. Укажите Voice ID HeyGen в параметрах. Аудиофайлы пока не подключены.',
                'pricing':model.get('pricing_skus',{}), 'rate_per_second':float(model.get('pricing_skus',{}).get('duration_seconds',0)) or None,
                'pricing_source':VIDEO_SOURCE,'timestamp':timestamp,'catalog_source':VIDEO_SOURCE,'generation_verified':False,
                'note':'Avatar script adapter: image input_references and prompt as speech; required voice_id in provider.options.heygen.parameters. Source: OpenRouter model page + video schema and HeyGen image-to-video docs. No fixed duration/seed/audio toggle. Uploaded audio is not exposed: inline audio transport unverified. No paid verification.'}
        optional = {'motion_prompt','expressiveness','fit','remove_background'}
        row['settings'] = {key:value for key,value in row['settings'].items() if key not in optional or key in row['passthrough_keys']}
        rate = row['rate_per_second']
        row['pricing_note'] = (f'${rate:g} за секунду результата; ' if rate else '')+'длительность определяется речью. Итог после генерации.'
        return row
    if not all(model.get(key) for key in ("supported_durations", "supported_resolutions", "supported_aspect_ratios")):
        return None
    settings = {}
    for field, source, preferred in (("duration", "supported_durations", 5), ("resolution", "supported_resolutions", "720p"), ("aspect_ratio", "supported_aspect_ratios", "9:16")):
        values = model[source]
        fallback = min(values) if field == "duration" else values[0]
        settings[field] = _enum(values, preferred if preferred in values else fallback)
    if model.get("generate_audio"):
        settings["generate_audio"] = {"type": "boolean", "default": False}
    if model.get("seed"):
        settings["seed"] = {"type": "boolean", "default": True}
    roles = {role: 1 for role, native in (("start", "first_frame"), ("end", "last_frame")) if native in (model.get("supported_frame_images") or [])}
    slug = model["id"]
    row = {"id": "openrouter:" + slug, "remote_model": slug, "provider": "openrouter", "kind": "video",
            "label": "OpenRouter · " + model.get("name", slug), "roles": roles, "max_assets": sum(roles.values()),
            "settings": settings, "pricing": model.get("pricing_skus", {}), "pricing_source": VIDEO_SOURCE,
            "timestamp": timestamp, "catalog_source": VIDEO_SOURCE, "generation_verified": False,
            "note": "Native OpenRouter video generation catalog. Only frame roles and controls advertised by that model are exposed. Arbitrary image/video/audio references, continuation, upscaling and editing need separate model-specific adapters. Inline frames follow schema/open-source clients; no paid studio verification."}
    if slug in REQUESTED_VIDEOS:
        rates = [f'{resolution}: ${float(row["pricing"]["duration_seconds_"+resolution.lower()]):g}/с'
                 for resolution in model['supported_resolutions'] if 'duration_seconds_'+resolution.lower() in row['pricing']]
        row['pricing_note'] = ' · '.join(rates)+('. С фото — стоимость после генерации. Акционные скидки не предполагаются.' if slug.startswith('heygen/') else '. По тарифам каталога; итог по usage.')
    return row


def refresh_requested_videos():
    """GET-only targeted discovery preserves all unrelated model/endpoint settings."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    source = _request(VIDEO_SOURCE)
    models = source.get('data',[]) if isinstance(source,dict) else source
    selected = {model['id']:_video_descriptor(model,timestamp) for model in models if model['id'] in REQUESTED_VIDEOS}
    if set(selected) != set(REQUESTED_VIDEOS) or not all(selected.values()):
        raise ValueError('Requested video models or required capabilities are missing; catalog unchanged')
    saved = json.loads(CACHE.read_text()) if CACHE.is_file() else {'models':_bootstrap()}
    replaced = {'openrouter:'+slug for slug in selected}
    rows = [selected[row['remote_model']] if row.get('id') in replaced else row for row in saved['models']]
    present = {row['id'] for row in rows}
    rows.extend(row for row in selected.values() if row['id'] not in present)
    saved.update(models=rows,requested_videos_refreshed_at=timestamp)
    saved['excluded_models'] = [row for row in saved.get('excluded_models',[]) if row.get('model') not in selected]
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    temporary = CACHE.with_suffix('.requested.tmp')
    temporary.write_text(json.dumps(saved,indent=2));temporary.replace(CACHE)
    return list(selected)


def _image_descriptor(model, endpoint, timestamp):
    params = endpoint.get("supported_parameters", {})
    formats = params.get("output_format", {}).get("values", [])
    if "vector" in model["id"] or formats and not any(x in formats for x in ("png", "jpeg", "webp")):
        return None
    if not endpoint.get("provider_tag"):
        return None
    if params.get("n", {}).get("min", 1) > 1:
        return None
    settings = {}
    for key in ("resolution", "aspect_ratio", "quality", "seed"):
        desc = params.get(key)
        if not desc:
            continue
        if desc.get("type") == "enum" and desc.get("values"):
            values = desc["values"]
            preference = {"resolution": "1K", "aspect_ratio": "9:16", "quality": "high"}.get(key)
            settings[key] = {**desc, "default": preference if preference in values else values[0]}
        elif key == "seed" and desc.get("type") in ("range", "boolean"):
            settings[key] = {**desc, "default": True}
    count = params.get("input_references", {})
    maximum = min(16, int(count.get("max", 0)))
    minimum = int(count.get("min", 0))
    if minimum > maximum:
        return None
    slug = model["id"]
    output_format = next((value for value in ("png", "jpeg", "webp") if value in formats), None)
    return {"id": "openrouter:" + slug, "remote_model": slug, "provider": "openrouter", "kind": "photo",
            "label": "OpenRouter · " + model.get("name", slug), "roles": {"image": maximum} if maximum else {},
            "required_roles": {"image": minimum} if minimum else {}, "max_assets": maximum,
            "provider_tag": endpoint["provider_tag"], "settings": settings, "pricing": endpoint.get("pricing", []),
            "request_defaults": {"output_format": output_format} if output_format else {},
            "pricing_source": ORIGIN + "/images/models/" + slug + "/endpoints", "timestamp": timestamp,
            "catalog_source": ORIGIN + "/images/models", "generation_verified": False,
            "note": "Dedicated OpenRouter Image API; settings and reference limits come from the pinned endpoint. Provider fallback disabled. Studio caps references at 16 and preserves raster output as PNG. No paid studio verification."}


def refresh_catalog():
    """Explicit public GET-only refresh, never generation or state polling."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = [row for row in _bootstrap() if row["provider"] == "openai"]
    failures = []
    video_data = _request(ORIGIN + "/videos/models")
    videos = video_data.get("data", []) if isinstance(video_data, dict) else video_data
    for model in videos:
        row = _video_descriptor(model, timestamp)
        if row:
            rows.append(row)
        else:
            failures.append({"model": model["id"], "reason": "Requires editing/upscale/avatar or has no explicit generation duration/shape metadata"})
    image_data = _request(ORIGIN + "/images/models")
    images = image_data.get("data", []) if isinstance(image_data, dict) else image_data
    preferred = {row["remote_model"]: row["provider_tag"] for row in _bootstrap() if row["provider"] == "openrouter" and row["kind"] == "photo"}

    def discover(model):
        try:
            endpoints = _request(ORIGIN + "/images/models/" + model["id"] + "/endpoints")["endpoints"]
            candidates = [endpoint for endpoint in endpoints if endpoint.get("provider_tag")]
            chosen = next((e for e in candidates if e["provider_tag"] == preferred.get(model["id"])), None)
            chosen = chosen or (candidates[0] if candidates else None)
            row = _image_descriptor(model, chosen, timestamp) if chosen else None
            return row, None if row else {"model": model["id"], "reason": "No pinnable raster endpoint with supported reference bounds"}
        except (urllib.error.URLError, ValueError, KeyError) as exc:
            return None, {"model": model["id"], "reason": "Public endpoint metadata unavailable: " + type(exc).__name__}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for row, failure in pool.map(discover, images):
            if row:
                rows.append(row)
            if failure:
                failures.append(failure)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"models": rows, "refreshed_at": timestamp, "excluded_models": failures}, indent=2))
    temporary.replace(CACHE)
    return catalog()


def _model(job):
    ident = job.get("model")
    return next((row for row in catalog() if row["id"] == ident), None)


def _settings(job, model):
    result = {}
    for key, spec in model["settings"].items():
        if key == "seed":
            if key in job:
                result[key] = job[key]
            continue
        value = job.get(key, spec.get("default"))
        if spec.get('required') and (not isinstance(value,str) or not value.strip()):
            raise ValueError(spec.get('title',key)+': required for the selected model')
        if spec['type'] == 'string':
            if value is None or value == '':
                continue
            if not isinstance(value,str) or len(value) > spec.get('max_length',30000):
                raise ValueError(f'Invalid {key} for selected cloud model')
        if spec["type"] == "enum" and value not in spec["values"]:
            raise ValueError(f"Unsupported {key} for selected cloud model")
        if spec["type"] == "boolean" and not isinstance(value, bool):
            raise ValueError(f"{key} must be boolean")
        result[key] = value
    return result


def validate_job(job, assets):
    model = _model(job)
    if not model:
        raise ValueError("Unknown cloud model")
    if job.get("kind") != model["kind"]:
        raise ValueError("Model does not support this media kind")
    if not isinstance(job.get("prompt"), str) or not job["prompt"].strip() or len(job["prompt"]) > 30000:
        raise ValueError("A prompt of 1–30000 characters is required")
    if job.get("lora_enabled"):
        raise ValueError("Local Alice LoRA cannot be attached to a cloud model")
    if "seed" in model["settings"] and (isinstance(job.get("seed", 0), bool) or not isinstance(job.get("seed", 0), int) or not 0 <= job.get("seed", 0) <= 2**32-1):
        raise ValueError("Cloud seed must be an integer from 0 to 4294967295")
    _settings(job, model)
    counts = {}
    from PIL import Image
    for asset in assets:
        role = asset.get("role")
        counts[role] = counts.get(role, 0) + 1
        if role not in model["roles"] or counts[role] > model["roles"][role]:
            raise ValueError("Unsupported reference role/count for selected cloud model")
        path = Path(asset["path"])
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise ValueError("Cloud reference must be an existing absolute nonsymlink file")
        if path.stat().st_size > 40*1024*1024:
            raise ValueError("Cloud reference exceeds the studio's 40 MiB limit")
        with Image.open(path) as image:
            image.verify()
    if len(assets) > model["max_assets"]:
        raise ValueError("Too many cloud reference images")
    for role, minimum in model.get("required_roles", {}).items():
        if counts.get(role, 0) < minimum:
            raise ValueError(f"This model requires at least {minimum} {role} reference(s)")
    if model["kind"] == "video":
        settings = _settings(job, model)
        if model["remote_model"].startswith("google/veo-") and settings.get("resolution") == "4K" and settings.get("duration") != 8:
            raise ValueError("Use 8 seconds for Veo 4K output")
        if any(a["role"] == "end" for a in assets) and not any(a["role"] == "start" for a in assets):
            raise ValueError("A last frame requires a first frame in this adapter")


def estimate(job, assets):
    validate_job(job, assets)
    model = _model(job)
    settings = _settings(job, model)
    result = {"estimated_usd": None, "estimate_usd": None, "upper_usd": None, "status": "unknown_before_usage",
              "details": model["pricing"], "pricing_source": model["pricing_source"],
              "timestamp": model["timestamp"], "currency": "USD",
              "uncertainty": "Image tokens depend on input images, output resolution and generated content; not a flat per-image price."}
    if model["kind"] == "video" and model["remote_model"] in VEO:
        key = "duration_seconds_" + ("with_audio" if settings.get("generate_audio", False) else "without_audio")
        suffix = {"720p": "_720p", "4K": "_4k"}.get(settings["resolution"], "")
        price = float(model["pricing"].get(key + suffix, model["pricing"][key])) * settings["duration"]
        result.update(estimated_usd=price, estimate_usd=price, upper_usd=price, status="catalog_estimate",
                      uncertainty="Catalog SKU estimate, not a settled charge; provider usage after completion is authoritative.")
    elif model['remote_model'] in ('minimax/hailuo-3-max','heygen/heygen-video-1') and not (model['remote_model']=='heygen/heygen-video-1' and assets):
        key = 'duration_seconds_'+settings['resolution'].lower()
        raw = model['pricing'].get(key,model['pricing'].get('duration_seconds'))
        if raw is not None:
            price = float(raw)*settings['duration']
            result.update(estimated_usd=price,estimate_usd=price,upper_usd=price,status='catalog_estimate',
                          uncertainty='Published catalog rate times requested seconds. Promotions/discounts are not assumed; returned usage.cost is authoritative.')
    elif model.get('adapter') == 'heygen_avatar_script':
        result['uncertainty'] = 'Avatar IV is billed per output second. Speech duration is unknown before generation; no word-count duration or total price is invented.'
    elif model["kind"] == "video":
        result["uncertainty"] = "This model uses a different duration/token/input pricing formula. Raw catalog SKUs are shown; no unsupported per-video quote is invented. Returned usage.cost is authoritative."
    return result


def _data_image(asset):
    from PIL import Image, ImageOps
    import io
    with Image.open(asset["path"]) as image:
        buffer = io.BytesIO()
        ImageOps.exif_transpose(image).convert("RGB").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _video_payload(job, assets, model):
    settings = _settings(job,model)
    if model.get('adapter') == 'heygen_avatar_script':
        keys = set(model['passthrough_keys'])
        return {'model':model['remote_model'],'prompt':job['prompt'],
                **{key:value for key,value in settings.items() if key not in keys},
                'input_references':[{'type':'image_url','image_url':{'url':_data_image(asset)}} for asset in assets],
                'provider':{'options':{'heygen':{'parameters':{key:value for key,value in settings.items() if key in keys}}}}}
    payload = {'model':model['remote_model'],'prompt':job['prompt'],**settings}
    if assets:
        payload['frame_images'] = [{'type':'image_url','image_url':{'url':_data_image(asset)},
                                    'frame_type':'first_frame' if asset['role']=='start' else 'last_frame'} for asset in assets]
    return payload


def _save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _headers(provider):
    keys = _credentials()
    name = "OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_API_KEY"
    if not keys.get(name):
        raise ValueError(name + " is not configured")
    headers = {"Authorization": "Bearer " + keys[name]}
    if provider == "openai":
        for field, header in (("OPENAI_PROJECT_ID", "OpenAI-Project"), ("OPENAI_ORG_ID", "OpenAI-Organization")):
            if keys.get(field):
                headers[header] = keys[field]
    return headers


def _unknown_billing(source):
    return {"actual_usd": None, "currency": "USD", "status": "unknown", "usage": {}, "source": source}


def _billing(model, usage):
    result = _unknown_billing(model["pricing_source"])
    result["usage"] = usage
    if model["provider"] == "openrouter":
        cost = usage.get("cost")
        if isinstance(cost, (int, float)):
            result.update(actual_usd=cost, status="provider_reported")
    else:
        details = usage.get("input_tokens_details", {})
        if all(k in details for k in ("text_tokens", "image_tokens")) and "output_tokens" in usage:
            rates = model["pricing"]
            cost = (details["text_tokens"]*rates["text_input_per_million"] + details["image_tokens"]*rates["image_input_per_million"] + usage["output_tokens"]*rates["image_output_per_million"])/1e6
            result.update(actual_usd=cost, status="calculated_list_price_not_invoice")
    return result


def _images(data, folder):
    from PIL import Image
    import io
    outputs = []
    for i, item in enumerate(data):
        value = item.get("b64_json")
        if not value:
            raise ValueError("Cloud image response contained no inline image bytes")
        target = folder / f"cloud-image-{i+1}.png"
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) > 100*1024*1024:
            raise ValueError("Cloud image exceeds output size limit")
        with Image.open(io.BytesIO(decoded)) as image:
            image.save(target, format="PNG")
        outputs.append({"path": str(target), "kind": "image"})
    return outputs


def _openai(job, assets, model, folder, headers):
    fields = {"model": model["remote_model"], "prompt": job["prompt"], "n": 1, "output_format": "png", **_settings(job, model)}
    if not assets:
        return _request(OPENAI + "/images/generations", fields, headers, timeout=600)
    boundary = "nora-studio-" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for i, asset in enumerate(assets):
        value = _data_image(asset).split(",", 1)[1]
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="reference-{i+1}.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + base64.b64decode(value) + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return _request(OPENAI + "/images/edits", b"".join(chunks), {**headers, "Content-Type": "multipart/form-data; boundary=" + boundary}, timeout=600)


def _download_video(ident, folder, headers):
    # Use the fixed provider content endpoint rather than trusting output URLs.
    url = ORIGIN + "/videos/" + urllib.parse.quote(ident, safe="") + "/content?index=0"
    try:
        data = _request(url, headers=headers, timeout=120, raw=True)
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise
        target = exc.headers.get("Location", "")
        exc.close()
        parsed = urllib.parse.urlsplit(target)
        host = parsed.hostname or ""
        allowed = ("openrouter.ai", "storage.googleapis.com", "blob.core.windows.net", "r2.cloudflarestorage.com")
        if parsed.scheme != "https" or parsed.port not in (None, 443) or parsed.username or parsed.password or not any(host == root or host.endswith("."+root) for root in allowed):
            raise ValueError("Unrecognized provider download host; automatic download refused")
        for entry in socket.getaddrinfo(host, 443):
            if not ipaddress.ip_address(entry[4][0]).is_global:
                raise ValueError("Provider download resolved to a nonpublic address")
        request = urllib.request.Request(target, headers=headers if host == "openrouter.ai" else {})
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=120) as response:
            data = response.read(256*1024*1024+1)
    if len(data) > 256*1024*1024:
        raise ValueError("Video output exceeds download limit")
    path = folder / "cloud-video.mp4"
    path.write_bytes(data)
    return [{"path": str(path), "kind": "video"}]


def run_job(job, job_dir, assets, progress, cancelled):
    validate_job(job, assets)
    folder = Path(job_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "cloud-submission.json").exists():
        raise RuntimeError("A prior cloud submission exists; refusing an automatic duplicate charge")
    model = _model(job)
    headers = _headers(model["provider"])
    if cancelled():
        raise InterruptedError("Cancelled before cloud submission")
    billing = _unknown_billing(model["pricing_source"])
    ident = None
    _save(folder / "cloud-submission.json", {"model": model["id"], "prompt": job["prompt"], "settings": _settings(job, model),
                                           "references": [{"id": a.get("id"), "role": a["role"]} for a in assets],
                                           "submitted_at": dt.datetime.now(dt.timezone.utc).isoformat(), "automatic_retries": False})
    try:
        progress({"stage": "cloud_submitting", "billing": billing})
        if model["provider"] == "openai":
            result = _openai(job, assets, model, folder, headers)
        elif model["kind"] == "photo":
            payload = {"model": model["remote_model"], "prompt": job["prompt"], "n": 1, **model.get("request_defaults", {}), **_settings(job, model),
                       "provider": {"only": [model["provider_tag"]], "allow_fallbacks": False}}
            if assets:
                payload["input_references"] = [{"type": "image_url", "image_url": {"url": _data_image(a)}} for a in assets]
            result = _request(ORIGIN + "/images", payload, headers, timeout=600)
        else:
            payload = _video_payload(job, assets, model)
            result = _request(ORIGIN + "/videos", payload, headers, timeout=90)
        ident = result.get("id") or result.get("_request_id")
        if model["kind"] == "photo":
            billing = _billing(model, result.get("usage", {}))
        progress({"stage": "cloud_accepted", "provider_request_id": ident, "billing": billing})
        if model["kind"] == "video":
            if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", ident):
                raise ValueError("Video provider returned an invalid job ID")
            _save(folder / "cloud-accepted.json", result)
            deadline = time.monotonic() + min(90, max(5, job.get("max_minutes", 20)))*60
            while result.get("status") not in ("completed", "failed", "cancelled", "expired"):
                if cancelled():
                    raise InterruptedError("Local monitoring cancelled; provider generation may continue and incur a charge")
                if time.monotonic() > deadline:
                    raise TimeoutError("Cloud video monitoring timed out; provider job may still finish and incur a charge")
                progress({"stage": "cloud_generating", "provider_request_id": ident})
                time.sleep(5)
                result = _request(ORIGIN + "/videos/" + urllib.parse.quote(ident, safe=""), headers=headers)
                _save(folder / "cloud-status.json", result)
            billing = _billing(model, result.get("usage", {}))
            _save(folder / "cloud-billing.json", billing)
            progress({"stage": "cloud_downloading", "provider_request_id": ident, "billing": billing})
            if result.get("status") != "completed":
                raise RuntimeError("Cloud video ended with status " + str(result.get("status")))
            outputs = _download_video(ident, folder, headers)
        else:
            _save(folder / "cloud-billing.json", billing)
            progress({"stage": "cloud_downloading", "provider_request_id": ident, "billing": billing})
            metadata = {key: value for key, value in result.items() if key != "data"}
            _save(folder / "cloud-response.json", metadata)
            outputs = _images(result.get("data", []), folder)
        _save(folder / "cloud-billing.json", billing)
        if cancelled():
            raise InterruptedError("Cancelled locally after provider response; completed output and billing were preserved")
        if not outputs:
            raise ValueError("Provider returned no usable output")
        return {"outputs": outputs, "billing": billing, "provider_request_id": ident}
    except BaseException as exc:
        diagnostic=_http_diagnostic(exc,(job.get('prompt',''),)) if isinstance(exc,urllib.error.HTTPError) else None
        ident=ident or getattr(exc,'provider_request_id',None)
        exc.billing = billing
        exc.provider_request_id = ident
        _save(folder / "cloud-billing.json", billing)
        # Do not persist raw HTTP bodies: upstream text could echo submitted references.
        _save(folder / "cloud-error.json", {"type": type(exc).__name__, "http_status": getattr(exc, "code", None),
                                          "provider_request_id": ident, "provider_error":diagnostic,
                                          "automatic_retries": False, "billing": billing})
        raise
