// Runs native studios against mock-server.mjs only; never reaches a provider.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
export async function verifyGallery(page, base = "http://127.0.0.1:36445") {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("dialog", async dialog => { errors.push(dialog.message()); await dialog.dismiss(); });
  const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aDhUAAAAASUVORK5CYII=";
  const upload = async (name, mime, role, extras = {}) => ({ ...await (await page.request.post(base + "/api/uploads", { data: { name, mime, data: png } })).json(), role, ...extras });
  const photos = [await upload("face.png", "image/png", "image"), await upload("body.png", "image/png", "image")];
  const videoAssets = [await upload("start.png", "image/png", "start"), await upload("end.png", "image/png", "end"), await upload("move.mp4", "video/mp4", "video", { include_audio: false }), await upload("voice.wav", "audio/wav", "audio"), await upload("identity.png", "image/png", "image")];
  const photoJob = { id: "photo-fixture", kind: "photo", model: "qwen-local", prompt: "  Exact photo prompt\n<image1> <image2>  ", seed: 42, steps: 30, width: 832, height: 1152, lora_enabled: true, lora_strength: .65, status: "completed", assets: photos, outputs: [{ ...photos[0], kind: "image", name: "original-source.png" }] };
  const videoJob = { id: "video-fixture", kind: "video", model: "h3-simplepod", prompt: "  [Static shot]\nVery slow move <image1>  ", seed: 123, steps: 29, width: 704, height: 960, frames: 158, lora_enabled: false, generated_audio: false, video_ref_audio: true, status: "completed", assets: videoAssets, outputs: [{ ...videoAssets[2], kind: "video" }] };
  const failed = { id: "failed-fixture", kind: "photo", model: "openai:gpt-image-test", prompt: "Cloud failed draft", seed: null, quality: "low", size: "1024x1536", status: "failed", assets: [], outputs: [] };
  await page.route("**/api/state", async route => { const response = await route.fetch(); const state = await response.json(); await route.fulfill({ json: { ...state, jobs: [photoJob, videoJob, failed] } }); });
  const captured = async () => (await (await page.request.get(base + "/__captured")).json());
  const before = (await captured()).length;
  await page.goto(base);
  await page.getByRole("button", { name: "Пересоздать", exact: true }).filter({visible:true}).click();
  await page.waitForFunction(prompt => [...document.querySelectorAll("textarea")].some(t => t.value === prompt), photoJob.prompt);
  assert.equal((await captured()).length, before, "recreate must not enqueue");
  await page.getByRole("img", { name: "Image2", exact: true }).waitFor();
  await page.getByRole("button", { name: "В очередь", exact: true }).filter({visible:true}).click();
  await page.waitForTimeout(150);
  const rebuiltPhoto = (await captured()).at(-1);
  for (const key of ["model","prompt","seed","steps","width","height","lora_enabled","lora_strength"]) assert.equal(rebuiltPhoto[key], photoJob[key], key);
  assert.deepEqual(rebuiltPhoto.assets, photos.map(({id,role}) => ({id,role})));
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать оригинал", exact:true }).filter({visible:true}).click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "original-source.png");
  assert.deepEqual(await readFile(await download.path()), Buffer.from(png,"base64"));
  await page.getByRole("button", { name: "Video Studio", exact: true }).click();
  await page.getByRole("button", { name: "Свернуть промпт · Видео", exact: true }).click();
  await page.getByRole("button", { name: "Пересоздать", exact: true }).filter({visible:true}).click();
  await page.waitForFunction(prompt => [...document.querySelectorAll("textarea")].some(t => t.value === prompt), videoJob.prompt);
  await page.getByRole("button", { name: "Свернуть промпт · Видео", exact: true }).waitFor();
  await page.getByText("Прикреплено референсов: 5", { exact:true }).filter({visible:true}).waitFor();
  await page.getByRole("button", { name: "В очередь", exact:true }).filter({visible:true}).click();
  await page.waitForTimeout(150);
  const rebuiltVideo = (await captured()).at(-1);
  for (const key of ["model","prompt","seed","steps","width","height","frames","lora_enabled","generated_audio","video_ref_audio"]) assert.equal(rebuiltVideo[key], videoJob[key], key);
  assert.deepEqual(rebuiltVideo.assets, videoAssets.map(({id,role,include_audio}) => ({id,role,...(include_audio !== undefined ? {include_audio} : {})})));
  await page.setViewportSize({width:390,height:844});
  await page.getByRole("button", {name:/Открыть меню и очередь/}).click();
  await page.locator("dialog article").filter({hasText:"Cloud failed draft"}).getByRole("button", {name:"Пересоздать",exact:true}).click();
  await page.waitForFunction(() => [...document.querySelectorAll("textarea")].some(t => t.value === "Cloud failed draft"));
  await page.getByRole("button",{name:"В очередь",exact:true}).filter({visible:true}).click();
  await page.waitForTimeout(150);
  const rebuiltCloud = (await captured()).at(-1);
  assert.equal(rebuiltCloud.model, failed.model); assert.equal(rebuiltCloud.quality,"low"); assert.equal(rebuiltCloud.size,"1024x1536"); assert.deepEqual(rebuiltCloud.assets,[]);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.deepEqual(errors,[]);
  return {checks:8, viewports:["desktop","390x844"], paidInference:false};
}
if (process.argv[1] === new URL(import.meta.url).pathname) {
  const { createRequire } = await import("node:module"); const require = createRequire(import.meta.url);
  const { chromium } = require("playwright");
  const browser = await chromium.launch({headless:true,...(process.env.NORA_TEST_CHROMIUM ? {executablePath:process.env.NORA_TEST_CHROMIUM}:{})});
  try { console.log(await verifyGallery(await browser.newPage({viewport:{width:1440,height:1000}}))); } finally { await browser.close(); }
}
