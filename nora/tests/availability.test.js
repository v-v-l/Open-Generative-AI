import test from "node:test";
import assert from "node:assert/strict";
import {
  availabilityReason,
  modelUnavailable,
  runtime,
} from "../src/runtime.js";
import { generateImage } from "../src/api.js";
const qwen = {
  id: "qwen-local",
  kind: "photo",
  provider: "local",
  roles: { image: 3 },
  available: false,
  availability: "executor_offline",
  availability_reason: "Local Qwen workstation is offline",
  credential_configured: true,
};
test("offline Qwen does not disable cloud or H3 and blocks enqueue before any request", async () => {
  runtime.state = { read_only: false };
  runtime.descriptors = [
    qwen,
    { id: "openai:photo", available: true, credential_configured: true },
    { id: "h3-simplepod", available: true, credential_configured: true },
  ];
  assert.equal(modelUnavailable("qwen-local"), true);
  assert.equal(modelUnavailable("openai:photo"), false);
  assert.equal(modelUnavailable("h3-simplepod"), false);
  await assert.rejects(
    generateImage(null, {
      model: "qwen-local",
      prompt: "literal",
      images_list: [],
    }),
    /Рабочая станция Qwen недоступна/,
  );
  runtime.descriptors[0] = {
    ...qwen,
    available: true,
    availability: "executor_ready",
  };
  assert.equal(modelUnavailable("qwen-local"), false);
});
test("live executor offline state takes precedence over stale descriptor, while missing credentials stay explicit", () => {
  assert.match(
    availabilityReason(
      { ...qwen, available: true, availability: "executor_ready" },
      {
        capabilities: {
          executors: { qwen: { available: false, status: "executor_offline" } },
        },
      },
    ),
    /Qwen недоступна/,
  );
  assert.match(
    availabilityReason({ id: "openrouter:test", credential_configured: false }),
    /API-ключ/,
  );
  assert.equal(
    availabilityReason({
      id: "h3-simplepod",
      available: true,
      availability: "worker_configured_not_health_checked",
    }),
    "",
  );
});
test("pending uploads block enqueue before a network request", async () => {
  runtime.state = { read_only: false };
  runtime.uploads = { "qwen-local": 1 };
  await assert.rejects(
    generateImage(null, { model: "qwen-local", prompt: "x" }),
    /завершения загрузки/,
  );
  runtime.uploads = {};
});
