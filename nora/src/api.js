import { isReadOnly, modelUnavailableReason, isUploading } from "./runtime.js";
import { runtime, descriptor, request, refresh, publish } from "./runtime.js";
const imageExtensions = /\.(png|jpe?g|webp)$/i;
const firstNonEmpty = (...values) =>
  values.find((value) =>
    Array.isArray(value) ? value.some(Boolean) : Boolean(value),
  );
export function referenceInputs(modelId, media) {
  const m = descriptor(modelId);
  if (m?.kind === "photo")
    return { images_list: m.roles.image ? media.imageUrls || [] : [] };
  return {
    ...(m?.roles.start
      ? { image_url: media.imageUrls?.[0] }
      : { images_list: m?.roles.image ? media.imageUrls || [] : [] }),
    ...(m?.roles.end ? { last_image: media.endImageUrl || undefined } : {}),
    ...(m?.roles.video ? { videos_list: media.videoUrls || [] } : {}),
    ...(m?.roles.audio ? { audios_list: media.audioUrls || [] } : {}),
  };
}
export function refsFor(params, m) {
  const refs = [];
  const append = (urls, role) => {
    for (const url of (Array.isArray(urls) ? urls : [urls]).filter(Boolean)) {
      if (!m.roles[role])
        throw Error(
          `Модель не поддерживает референсы ${role}. Уберите несовместимые вложения.`,
        );
      const id = url.split("/").pop();
      if (!/^[a-f0-9]{32}$/.test(id))
        throw Error(
          "Прикрепите файл заново: нужен референс, загруженный в нашу студию",
        );
      if (!refs.some((a) => a.id === id && a.role === role))
        refs.push({ id, role, ...(role === "video" && runtime.assetMetadata[url]?.include_audio !== undefined ? {include_audio: runtime.assetMetadata[url].include_audio} : {}) });
    }
  };
  if (m.kind === "photo")
    append(
      firstNonEmpty(
        params.images_list,
        params.image_urls,
        params.imageUrls,
        params.image_url,
      ),
      "image",
    );
  else {
    if (params.image_url)
      append(params.image_url, m.roles.start ? "start" : "image");
    append(
      firstNonEmpty(
        params.last_image,
        params.last_image_url,
        params.end_image_url,
      ),
      "end",
    );
    append(firstNonEmpty(params.images_list, params.image_urls), "image");
    append(firstNonEmpty(params.videos_list, params.video_url), "video");
    append(firstNonEmpty(params.audios_list, params.audio_url), "audio");
  }
  for (const a of runtime.extraAssets[m.id] || []) {
    if (!m.roles[a.role])
      throw Error(
        `Модель не поддерживает референсы ${a.role}. Уберите несовместимые вложения.`,
      );
    refs.push({
      id: a.id,
      role: a.role,
      ...(a.include_audio !== undefined
        ? { include_audio: a.include_audio }
        : {}),
    });
  }
  return refs;
}
export function buildJob(params) {
  const m = descriptor(params.model);
  if (!m)
    throw Error(
      "Эта MuAPI-модель не подключена к нашему backend. Выберите модель из нашего каталога.",
    );
  const job = {
    kind: m.kind,
    model: m.id,
    prompt: params.prompt ?? "",
    seed:
      params.seed == null ||
      params.seed === "" ||
      params.seed === "random" ||
      Number(params.seed) < 0
        ? null
        : Number(params.seed),
    batch_count: 1,
    assets: refsFor(params, m),
  };
  if (params.max_cost_usd) job.max_cost_usd = Number(params.max_cost_usd);
  if (["openai", "openrouter"].includes(m.provider)) {
    for (const [key, spec] of Object.entries(m.settings || {}))
      if (key !== "seed")
        job[key] = params[key] ?? spec.default ?? spec.values?.[0];
  } else {
    for (const key of [
      "width",
      "height",
      "steps",
      "frames",
      "lora_enabled",
      "lora_strength",
      "lora_name",
      "max_minutes",
      "generated_audio",
      "video_ref_audio",
    ])
      if (params[key] !== undefined && params[key] !== "")
        job[key] = params[key];
  }
  const imageCount = job.assets.filter((asset) =>
    ["image", "start", "end"].includes(asset.role),
  ).length;
  const mentioned = [
    ...String(job.prompt).matchAll(/<image_?(\d+)>|@Image\s*(\d+)/gi),
  ].map((match) => Number(match[1] || match[2]));
  const highest = Math.max(0, ...mentioned);
  if (highest > imageCount)
    throw Error(
      `В промпте указан Image${highest}, но прикреплено фото: ${imageCount}. Добавьте референсы в строку вложений.`,
    );
  return job;
}
async function enqueue(_key, params) {
  if (isReadOnly()) throw Error("Режим просмотра: генерация отключена");
  if (isUploading(params.model))
    throw Error("Дождитесь завершения загрузки референсов");
  const job = buildJob(params);
  const unavailable = modelUnavailableReason(params.model);
  if (unavailable) throw Error(unavailable);
  const response = await request("/api/jobs", job);
  await refresh();
  window.dispatchEvent(
    new CustomEvent("nora-enqueued", { detail: response.jobs }),
  );
  return { queued: true, request_id: response.jobs[0]?.id };
}
export const generateImage = enqueue,
  generateI2I = enqueue,
  generateVideo = enqueue,
  generateI2V = enqueue,
  processV2V = enqueue;
export async function uploadFile(_key, file, onProgress) {
  if (isReadOnly()) throw Error("Режим просмотра: загрузка отключена");
  if (file.size > 100 * 1024 * 1024)
    throw Error("Максимальный размер — 100 МБ");
  onProgress?.(0);
  const data = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  const asset = await request("/api/uploads", {
    name: file.name,
    mime: file.type,
    data,
  });
  onProgress?.(100);
  runtime.assetMetadata[asset.url] = { name: file.name, mime: file.type };
  return asset.url;
}
export async function getUserBalance() {
  return null;
}
export function historyFor(kind) {
  return (runtime.state?.jobs || [])
    .filter((j) => j.kind === kind && !runtime.hiddenJobs.has(j.id))
    .flatMap((j) =>
      (j.outputs || [])
        .filter((o) => o.kind === (kind === "photo" ? "image" : "video"))
        .map((o) => ({
          id: j.id,
          url: o.url,
          prompt: j.prompt,
          model: j.model,
          aspect_ratio: j.aspect_ratio || "",
          timestamp: j.updated_at || j.created_at,
          type: kind === "photo" ? "image" : "video",
          name: o.name,
          mime: o.mime,
          job: j,
        })),
    );
}
export function hideHistory(id) {
  runtime.hiddenJobs.add(id);
  publish();
}
