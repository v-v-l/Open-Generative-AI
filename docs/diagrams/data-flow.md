# Nora data flow

Verified against source `8b61e89`, 2026-11-01. Live deployment checks are recorded
in `deploy/pending-prod.md`.

```mermaid
flowchart LR
  Browser[Authenticated browser] -->|HTTPS| Gateway[Gateway Caddy]
  Gateway --> Apps[Apps private Caddy]
  Apps --> Static[Immutable upstream-derived frontend]
  Apps -->|Loopback SSH reverse tunnel| Backend[Nora Python backend on execution host]
  Backend --> Queue[(External SQLite queue and assets)]
  Backend --> Qwen[Local Qwen ComfyUI]
  Backend --> H3[Existing rented H3 worker]
  Backend --> OR[OpenRouter image/video API]
  Backend --> OpenAI[Direct OpenAI Images API]
```

Static routes use the backend authentication check. API/media routes require the
same session. The frontend receives capability and credential-presence flags;
provider keys, worker SSH credentials and reference files stay off apps storage.
H3 generation retains its independent pause timer. No generation runs on import,
page loading or catalog discovery.
