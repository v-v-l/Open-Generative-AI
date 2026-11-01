// Isolated HTTP fixture: no engines, credentials, network or generation.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { resolve, extname } from "node:path";
import { randomBytes } from "node:crypto";
const root = resolve(import.meta.dirname, "../dist");
const models = [
  {
    id: "qwen-local",
    label: "Qwen test fixture",
    provider: "local",
    kind: "photo",
    roles: { image: 3 },
    max_assets: 3,
    settings: {},
    credential_configured: true,
    default_width: 704,
    default_height: 960,
  },
  {
    id: "openai:gpt-image-test",
    label: "OpenAI test fixture",
    provider: "openai",
    kind: "photo",
    roles: { image: 3 },
    max_assets: 3,
    settings: {
      quality: { type: "enum", values: ["low", "high"], default: "high" },
      size: {
        type: "enum",
        values: ["1024x1024", "1024x1536"],
        default: "1024x1024",
      },
    },
    credential_configured: true,
  },
  {
    id: "h3-simplepod",
    label: "H3 test fixture",
    provider: "simplepod",
    kind: "video",
    roles: { start: 1, end: 1, image: 9, video: 3, audio: 3 },
    max_assets: 12,
    settings: {},
    credential_configured: true,
    default_width: 704,
    default_height: 960,
  },
  {
    id: "openrouter:veo-lite-test",
    label: "Veo Lite test fixture",
    provider: "openrouter",
    kind: "video",
    roles: { start: 1, end: 1 },
    max_assets: 2,
    settings: {
      duration: { type: "enum", values: [4, 6, 8], default: 8 },
      resolution: { type: "enum", values: ["720p", "1080p"], default: "720p" },
      aspect_ratio: { type: "enum", values: ["16:9", "9:16"], default: "16:9" },
      generate_audio: { type: "boolean", default: true },
    },
    credential_configured: true,
  },
];
const state = {
  test_mode: true,
  read_only: false,
  jobs: [],
  queue_paused: true,
  active_job_id: null,
  capabilities: { models },
};
const captured = [];
const media = new Map();
const send = (res, data) => {
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(data));
};
http
  .createServer(async (req, res) => {
    try {
      let body = {};
      if (req.method === "POST") {
        let chunks = [];
        for await (const c of req) chunks.push(c);
        body = JSON.parse(Buffer.concat(chunks) || "{}");
      }
      const p = req.url.split("?")[0];
      if (p === "/__availability") {
        const qwen = models.find((model) => model.id === "qwen-local");
        qwen.available = body.available;
        qwen.availability = body.available
          ? "executor_ready"
          : "executor_offline";
        qwen.availability_reason = body.available
          ? ""
          : "Local Qwen workstation is offline";
        state.capabilities.executors = {
          qwen: { available: body.available, status: qwen.availability },
        };
        return send(res, { available: qwen.available });
      }
      if (p === "/api/state") return send(res, state);
      if (p === "/api/estimate")
        return send(res, {
          estimated_usd: null,
          upper_usd: null,
          reason: "Private test fixture — no billing",
        });
      if (p === "/__captured") return send(res, captured);
      if (p === "/api/uploads") {
        const id = randomBytes(16).toString("hex");
        const a = { id, name: body.name, mime: body.mime, url: "/media/" + id };
        media.set(id, { ...a, data: Buffer.from(body.data, "base64") });
        return send(res, a);
      }
      if (p === "/api/jobs") {
        captured.push(body);
        const j = {
          ...body,
          id: randomBytes(16).toString("hex"),
          status: "queued",
          outputs: [],
          assets: body.assets.map((a) => ({
            ...media.get(a.id),
            data: undefined,
            ...a,
          })),
        };
        state.jobs.push(j);
        return send(res, { jobs: [j] });
      }
      if (p === "/api/queue") {
        state.queue_paused = body.paused;
        return send(res, state);
      }
      if (p.startsWith("/media/")) {
        const a = media.get(p.split("/").pop());
        if (a) {
          res.setHeader("Content-Type", a.mime);
          return res.end(a.data);
        }
      }
      const file = resolve(root, "." + (p === "/" ? "/index.html" : p));
      if (!file.startsWith(root + "/")) throw Error("path");
      const bytes = await readFile(file);
      res.setHeader(
        "Content-Type",
        {
          ".js": "text/javascript",
          ".css": "text/css",
          ".html": "text/html",
          ".svg": "image/svg+xml",
          ".png": "image/png",
          ".jpg": "image/jpeg",
        }[extname(file)] || "application/octet-stream",
      );
      res.end(bytes);
    } catch (e) {
      res.statusCode = 404;
      send(res, { error: e.message });
    }
  })
  .listen(36445, "127.0.0.1", () =>
    console.log("PRIVATE test fixture http://127.0.0.1:36445 — no providers"),
  );
