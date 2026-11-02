import { runtime, descriptor, publish } from "./runtime.js";

// Use the authenticated media endpoint directly: embedded browsers cannot always
// persist blob URLs, and the server knows the original filename and MIME type.
export function downloadOriginal(entry) {
  const url = new URL(entry.url, window.location.href);
  if (url.origin !== window.location.origin || !/^\/media\/[a-f0-9]{32}$/.test(url.pathname))
    throw Error("Оригинал недоступен в хранилище студии. Откройте файл для сохранения.");
  url.searchParams.set("download", "1");
  const link = document.createElement("a");
  link.href = url.pathname + url.search;
  link.download = entry.name || "";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export function recreationDraft(job) {
  if (!job) throw Error("Исходное задание не найдено. Обновите страницу.");
  const model = descriptor(job.model);
  if (!model) throw Error("Исходная модель больше не доступна в каталоге.");
  const assets = job.assets || [];
  const counts = {};
  for (const asset of assets) {
    if (asset.missing || !/^[a-f0-9]{32}$/.test(asset.id || "") || asset.url !== "/media/" + asset.id)
      throw Error("Исходный референс недоступен. Восстановление отменено: файлы не исключаются автоматически.");
    counts[asset.role] = (counts[asset.role] || 0) + 1;
    if (counts[asset.role] > (model.roles?.[asset.role] || 0))
      throw Error("Текущая модель больше не поддерживает исходный набор референсов. Восстановление отменено.");
  }
  const media = {
    imageUrls: assets.filter(a => a.role === (model.kind === "video" && model.roles.start ? "start" : "image")).map(a => a.url),
    endImageUrl: assets.find(a => a.role === "end")?.url || null,
    videoUrls: assets.filter(a => a.role === "video").map(a => a.url),
    audioUrls: assets.filter(a => a.role === "audio").map(a => a.url),
  };
  const keys = new Set(["prompt", "model", "aspect_ratio", "duration", "resolution", "quality", "seed", "max_cost_usd", ...Object.keys(model.settings || {})]);
  if (["local", "simplepod"].includes(model.provider))
    for (const key of ["width", "height", "steps", "frames", "lora_enabled", "lora_strength", "lora_name", "max_minutes", "generated_audio", "video_ref_audio"]) keys.add(key);
  const params = Object.fromEntries(Object.entries(job).filter(([key]) => keys.has(key)));
  params.seed = job.seed ?? -1;
  params.max_cost_usd = job.max_cost_usd ?? "";
  return { kind: model.kind, model: model.id, params, media, assets: assets.map(a => ({ ...a })) };
}

function ensureNoUploads() {
  if (Object.values(runtime.uploads).some(count => count > 0))
    throw Error("Дождитесь завершения загрузки файлов, затем нажмите «Пересоздать» ещё раз.");
}
export async function recreateJob(job) {
  ensureNoUploads();
  if (runtime.restoring) throw Error("Предыдущее задание ещё открывается. Подождите.");
  const draft = recreationDraft(job);
  runtime.restoring = true;
  try {
    // Validate all references before touching the current draft. A missing file
    // must not turn an image-conditioned request into a different generation.
    for (const asset of draft.assets) {
      const response = await fetch(asset.url, { credentials: "same-origin", headers: { Range: "bytes=0-0" } });
      const mime = response.headers.get("Content-Type") || "";
      await response.body?.cancel();
      if (!response.ok || !/^(image|video|audio)\//.test(mime))
        throw Error("Не удалось открыть исходный референс «" + (asset.name || asset.id) + "». Текущий промпт сохранён.");
    }
    ensureNoUploads();
    for (const asset of draft.assets) runtime.assetMetadata[asset.url] = { ...asset };
    runtime.extraAssets[draft.model] = draft.kind === "video" && descriptor(draft.model).roles.start
      ? draft.assets.filter(a => a.role === "image") : [];
    publish();
    window.dispatchEvent(new CustomEvent("nora-recreate", { detail: draft }));
    return draft;
  } finally { runtime.restoring = false; }
}
