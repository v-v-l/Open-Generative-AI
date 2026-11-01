export const runtime = {
  state: null,
  descriptors: [],
  listeners: new Set(),
  extraAssets: {},
  drafts: {},
  hiddenJobs: new Set(),
};
export function publish() {
  runtime.listeners.forEach((fn) => fn());
}
export function descriptor(id) {
  return runtime.descriptors.find((m) => m.id === id);
}
export async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json().catch(() => ({}));
  if (response.status === 401) {
    location.assign("/login?next=" + encodeURIComponent(location.pathname));
    throw Error("Требуется вход");
  }
  if (!response.ok)
    throw Error(
      value.error?.message || value.error || `HTTP ${response.status}`,
    );
  return value;
}
export async function refresh() {
  const state = await request("/api/state");
  runtime.state = state;
  runtime.descriptors = (state.capabilities.models || []).map((m) =>
    m.id === "qwen-local"
      ? { ...state.capabilities.photo, ...m }
      : m.id === "h3-simplepod"
        ? { ...state.capabilities.video, ...m }
        : m,
  );
  publish();
  return state;
}

export function isReadOnly() {
  return Boolean(runtime.state?.read_only || runtime.state?.readonly);
}

// Availability is independent per executor; an offline workstation affects Qwen only.
export function availabilityReason(model, state = runtime.state) {
  if (!model) return "Модель отсутствует в каталоге";
  const executor =
    model.id === "qwen-local"
      ? state?.executors?.qwen || state?.capabilities?.executors?.qwen
      : null;
  if (executor?.available === false || model.available === false) {
    if (
      model.id === "qwen-local" &&
      (executor?.status === "executor_offline" ||
        model.availability === "executor_offline")
    )
      return "Рабочая станция Qwen недоступна. Подключите исполнитель и дождитесь статуса «Доступна».";
    return (
      model.availability_reason ||
      executor?.reason ||
      "Исполнитель модели недоступен"
    );
  }
  if (model.credential_configured === false)
    return "Исполнитель не настроен или API-ключ отсутствует на сервере";
  return "";
}
export function modelUnavailableReason(id) {
  return availabilityReason(descriptor(id));
}
export function modelUnavailable(id) {
  return Boolean(modelUnavailableReason(id));
}
