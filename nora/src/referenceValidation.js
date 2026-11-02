import { descriptor } from "./runtime.js";
import { referenceInputs, refsFor } from "./api.js";

// Validate the same committed roles that submission sends, including H3 extras.
export function noraReferenceError(modelId, media = {}) {
  const model = descriptor(modelId);
  if (!model) return "Модель не найдена. Выберите её заново.";
  try {
    const refs = refsFor(referenceInputs(modelId, media), model);
    for (const [role, minimum] of Object.entries(model.required_roles || {})) {
      if (refs.filter((asset) => asset.role === role).length < minimum)
        return `Добавьте референс ${role}: требуется ${minimum}.`;
    }
    if (model.provider === "openrouter" && refs.some((asset) => asset.role === "end") && !refs.some((asset) => asset.role === "start"))
      return "Для последнего кадра добавьте первый кадр (Start).";
    return "";
  } catch (error) {
    return error.message;
  }
}

export function pastedImages(clipboard) {
  const files = [...(clipboard?.files || [])].filter((file) => /^image\//.test(file.type));
  if (files.length) return files;
  return [...(clipboard?.items || [])]
    .filter((item) => item.kind === "file" && /^image\//.test(item.type))
    .map((item) => item.getAsFile()).filter(Boolean);
}

export function pasteImageRole(model, values, preferred) {
  const roles = ["image", "start", "end"].filter((role) => model.roles[role] > 0);
  if (roles.includes(preferred)) return preferred;
  return roles.find((role) => (values[role]?.length || 0) < model.roles[role]) || roles[0];
}
