# Nora data flow

Verified reference-library addition against `7818f67` and live production, 2026-11-02;
base generation topology remains `nora-v2-9215134`. See `deploy/pending-prod.md`.

```mermaid
flowchart LR
  Browser[Authenticated browser] -->|HTTPS| Gateway[Gateway Caddy]
  Gateway --> Apps[Apps private Caddy]
  Apps --> Static[Immutable upstream-derived frontend]
  Apps --> Backend[API and queue on apps]
  Backend --> DB[(PostgreSQL on databases:5466)]
  Backend --> Files[Private media files on apps]
  Backend --> Reference[Reference-only set browser and authenticated export routes]
  Reference --> Library[Private originals and portable collection manifest on apps]
  Backend -->|Authenticated Qwen-only reverse tunnel| Qwen[Workstation Qwen executor]
  Backend --> H3[Existing rented H3 worker]
  Backend --> OR[OpenRouter image/video API]
  Backend --> OpenAI[Direct OpenAI Images API]
```

Credentials remain server-side. Static access authenticates before file serving;
API and media use the same protected session. H3 retains an independent apps user
systemd pause timer. Workstation disconnection affects Qwen only. No generation
runs on import, page loading, catalog discovery or availability polling.
