import test from "node:test";
import assert from "node:assert/strict";
import { recreationDraft, recreateJob, downloadOriginal } from "../src/gallery.js";
import { runtime } from "../src/runtime.js";
import { buildJob, referenceInputs, historyFor } from "../src/api.js";
const id = character => character.repeat(32);
const asset = (character, role, rest = {}) => ({ id: id(character), url: "/media/" + id(character), role, name: character + ".png", mime: role === "video" ? "video/mp4" : "image/png", ...rest });
const model = { id: "h3-simplepod", kind: "video", provider: "simplepod", roles: { start: 1, end: 1, image: 9, video: 3, audio: 3 } };
const job = { id: "job-one", kind: "video", model: model.id, prompt: "  slow motion\n[Static shot] <image1>  ", seed: 0, width: 704, height: 960, frames: 141, lora_enabled: true, lora_strength: .8, video_ref_audio: true, assets: [asset("a", "start"), asset("b", "end"), asset("c", "video", { include_audio: false }), asset("d", "image"), asset("e", "image")] };
function reset() { runtime.descriptors = [model]; runtime.extraAssets = {}; runtime.assetMetadata = {}; runtime.uploads = {}; }
test("recreation preserves literal prompt, exact settings, original order, roles and explicit audio false", () => {
  reset();
  const draft = recreationDraft(job);
  assert.equal(draft.params.prompt, job.prompt);
  assert.equal(draft.params.seed, 0);
  assert.equal(draft.params.lora_strength, .8);
  assert.deepEqual(draft.assets, job.assets);
  assert.deepEqual(draft.media.imageUrls, [job.assets[0].url]);
  assert.deepEqual(draft.media.videoUrls, [job.assets[2].url]);
});
test("missing references, removed model, or changed capabilities fail without dropping files", () => {
  reset();
  assert.throws(() => recreationDraft({ ...job, assets: [{ ...job.assets[0], missing: true }] }), /недоступен/);
  assert.throws(() => recreationDraft({ ...job, assets: [{ ...job.assets[0], url: undefined }] }), /недоступен/);
  assert.throws(() => recreationDraft({ ...job, model: "removed" }), /модель/);
  runtime.descriptors = [{ ...model, roles: { start: 1 } }];
  assert.throws(() => recreationDraft(job), /не поддерживает/);
});
test("text-only jobs restore without adding references and random seed uses UI sentinel", () => {
  reset();
  const draft = recreationDraft({ ...job, seed: null, assets: [] });
  assert.equal(draft.params.seed, -1);
  assert.deepEqual(draft.assets, []);
  assert.deepEqual(draft.media.imageUrls, []);
});
test("unreadable original leaves existing draft attachments untouched and never enqueues", async () => {
  reset();
  runtime.extraAssets[model.id] = [{ id: "existing" }];
  const calls = [];
  const previous = globalThis.fetch;
  globalThis.fetch = async (...args) => { calls.push(args); return { ok: false, headers: new Headers({ "Content-Type": "application/json" }) }; };
  try {
    await assert.rejects(recreateJob(job), /Текущий промпт сохранён/);
    assert.deepEqual(runtime.extraAssets[model.id], [{ id: "existing" }]);
    assert.equal(calls.length, 1);
    assert.equal(calls[0][1].method, undefined);
  } finally { globalThis.fetch = previous; }
});
test("successful restore emits edit event only after all original reads; rebuilt request retains references", async () => {
  reset();
  const calls = [], events = [];
  const previous = { fetch: globalThis.fetch, window: globalThis.window, CustomEvent: globalThis.CustomEvent };
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return { ok: true, headers: new Headers({ "Content-Type": url === job.assets[2].url ? "video/mp4" : "image/png" }), body: { cancel: async () => {} } }; };
  globalThis.window = { dispatchEvent: event => events.push(event) };
  globalThis.CustomEvent = class { constructor(type, options) { this.type = type; this.detail = options.detail; } };
  try {
    const draft = await recreateJob(job);
    assert.equal(calls.length, job.assets.length);
    assert.ok(calls.every(([, options]) => !options.method));
    assert.equal(events[0].type, "nora-recreate");
    const rebuilt = buildJob({ ...draft.params, ...referenceInputs(draft.model, draft.media) });
    assert.equal(rebuilt.prompt, job.prompt);
    assert.equal(rebuilt.seed, 0);
    assert.deepEqual(rebuilt.assets, job.assets.map(({ id, role, include_audio }) => ({ id, role, ...(include_audio !== undefined ? { include_audio } : {}) })));
  } finally { Object.assign(globalThis, previous); }
});
test("gallery keeps original filename/MIME and full job for recreation", () => {
  reset();
  runtime.state = { jobs: [{ ...job, outputs: [{ kind: "video", url: "/media/" + id("f"), mime: "video/mp4", name: "original.mp4" }] }] };
  const entry = historyFor("video")[0];
  assert.equal(entry.name, "original.mp4");
  assert.equal(entry.mime, "video/mp4");
  assert.equal(entry.job.prompt, job.prompt);
});
test("download uses authenticated original endpoint, filename and no blob URL or MIME rewriting", () => {
  const oldWindow = globalThis.window, oldDocument = globalThis.document;
  const anchor = { click() { this.clicked = true; }, remove() {} };
  globalThis.window = { location: { href: "https://media.bp-flow.com/", origin: "https://media.bp-flow.com" } };
  globalThis.document = { createElement: () => anchor, body: { appendChild() {} } };
  try {
    downloadOriginal({ url: "/media/" + id("a"), name: "image-1.png", mime: "image/png" });
    assert.equal(anchor.href, "/media/" + id("a") + "?download=1");
    assert.equal(anchor.download, "image-1.png");
    assert.equal(anchor.clicked, true);
    assert.throws(() => downloadOriginal({ url: "https://external.example/image.png" }), /недоступен/);
  } finally { globalThis.window = oldWindow; globalThis.document = oldDocument; }
});
