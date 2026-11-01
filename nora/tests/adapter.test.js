import test from "node:test";
import assert from "node:assert/strict";
import { runtime } from "../src/runtime.js";
import { buildJob } from "../src/api.js";
import { modelFromDescriptor, installCatalog } from "../src/catalog.js";
const image = "a".repeat(32),
  start = "b".repeat(32),
  end = "c".repeat(32),
  video = "d".repeat(32),
  audio = "e".repeat(32);
const photo = {
  id: "openai:gpt-image-test",
  kind: "photo",
  provider: "openai",
  label: "OpenAI",
  roles: { image: 3 },
  settings: {
    quality: { type: "enum", values: ["low", "high"], default: "high" },
    size: { type: "enum", values: ["1024x1536"], default: "1024x1536" },
  },
};
const h3 = {
  id: "h3-simplepod",
  kind: "video",
  provider: "simplepod",
  label: "H3",
  roles: { start: 1, end: 1, image: 9, video: 3, audio: 3 },
  settings: {},
  default_width: 704,
  default_height: 960,
};
test("cloud payload preserves literal prompt and omits unsupported native parameters", () => {
  runtime.descriptors = [photo];
  const prompt = "  Alice\n<image1>  ";
  const result = buildJob({
    model: photo.id,
    prompt,
    images_list: ["/media/" + image],
    seed: 8,
    steps: 25,
    lora_enabled: true,
    quality: "low",
    surprise: "ignored",
  });
  assert.equal(result.prompt, prompt);
  assert.equal(result.seed, 8);
  assert.equal(result.quality, "low");
  assert.equal(result.size, "1024x1536");
  assert.equal(result.steps, undefined);
  assert.equal(result.lora_enabled, undefined);
  assert.equal(result.surprise, undefined);
  assert.deepEqual(result.assets, [{ id: image, role: "image" }]);
});
test("native H3 preserves guide and multimodal roles/order", () => {
  runtime.descriptors = [h3];
  runtime.extraAssets[h3.id] = [{ id: image, role: "image" }];
  const result = buildJob({
    model: h3.id,
    prompt: "move",
    image_url: "/media/" + start,
    last_image: "/media/" + end,
    videos_list: ["/media/" + video],
    audios_list: ["/media/" + audio],
    seed: -1,
    frames: 141,
    lora_enabled: false,
  });
  assert.equal(result.seed, null);
  assert.deepEqual(result.assets, [
    { id: start, role: "start" },
    { id: end, role: "end" },
    { id: video, role: "video" },
    { id: audio, role: "audio" },
    { id: image, role: "image" },
  ]);
  assert.equal(result.frames, 141);
  runtime.extraAssets = {};
});
test("unknown MuAPI model is never silently routed", () => {
  runtime.descriptors = [photo];
  assert.throws(
    () => buildJob({ model: "unconnected-muapi-model", prompt: "x" }),
    /не подключена/,
  );
});
test("catalog retains explicit capabilities and optional model settings", () => {
  const mapped = modelFromDescriptor(h3, "i2v");
  assert.equal(mapped.imageField, "image_url");
  assert.equal(mapped.lastImageField, "last_image");
  assert.equal(mapped.maxVideos, 3);
  assert.equal(mapped.maxAudios, 3);
  assert.equal(mapped.inputs.lora_enabled.default, false);
  assert.equal(mapped.inputs.frames.step, 17);
  const cloud = modelFromDescriptor(photo, "i2i");
  assert.equal(cloud.inputs.steps, undefined);
  assert.equal(cloud.maxImages, 3);
  assert.equal(cloud.inputs.size.default, "1024x1536");
});
test("dynamic catalog does not expose edit-only models as text-only", () => {
  const edit = {
    ...photo,
    id: "openrouter:edit-only",
    required_roles: { image: 1 },
  };
  const registry = {
    t2iModels: [],
    i2iModels: [],
    t2vModels: [],
    i2vModels: [],
    v2vModels: [{ id: "unsupported" }],
  };
  installCatalog(registry, [photo, edit, h3]);
  assert.deepEqual(
    registry.t2iModels.map((m) => m.id),
    [photo.id],
  );
  assert.equal(registry.i2iModels.length, 2);
  assert.equal(registry.v2vModels.length, 0);
});
test("empty alias arrays do not mask actual photo or multimodal references", () => {
  runtime.extraAssets = {};
  assert.deepEqual(
    buildWith(photo, {
      images_list: [],
      image_urls: ["/media/" + image, "/media/" + start],
    }).assets,
    [
      { id: image, role: "image" },
      { id: start, role: "image" },
    ],
  );
  const refs = buildWith(h3, {
    videos_list: [],
    video_url: "/media/" + video,
    audios_list: [],
    audio_url: "/media/" + audio,
  }).assets;
  assert.deepEqual(refs, [
    { id: video, role: "video" },
    { id: audio, role: "audio" },
  ]);
});
function buildWith(model, params) {
  runtime.descriptors = [model];
  return buildJob({ model: model.id, prompt: "Literal prompt", ...params });
}
test("explicit image placeholders require actual committed files without rewriting prompt", () => {
  assert.throws(
    () => buildWith(photo, { prompt: "  Apply <image1>  ", images_list: [] }),
    /Image1.*фото: 0/,
  );
  assert.throws(
    () =>
      buildWith(photo, {
        prompt: "Use @Image2",
        images_list: ["/media/" + image],
      }),
    /Image2.*фото: 1/,
  );
  const prompt = "  Apply <image1> to @Image2\n unchanged  ";
  assert.equal(
    buildWith(photo, {
      prompt,
      images_list: ["/media/" + image, "/media/" + start],
    }).prompt,
    prompt,
  );
});
test("friendly OpenAI display names do not change request model IDs", () => {
  const model = {
    ...photo,
    id: "openai:gpt-image-2.5-sunburst-2026-09-08",
    remote_model: "gpt-image-2.5-sunburst-2026-09-08",
  };
  const mapped = modelFromDescriptor(model, "t2i");
  assert.equal(mapped.name, "OpenAI GPT Image 2.5 Sunburst");
  assert.equal(mapped.id, model.id);
});
