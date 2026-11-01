import React, { useState, useEffect, useRef } from "react";
import {
  descriptor,
  runtime,
  publish,
  isReadOnly,
  isUploading,
} from "./runtime.js";
import { uploadFile } from "./api.js";

// Files commit directly to the same arrays used by submission; no hidden picker draft.
export function NoraAttachments({
  modelId,
  imageUrls = [],
  endImageUrl = null,
  videoUrls = [],
  audioUrls = [],
  onChange,
}) {
  const [error, setError] = useState("");
  const m = descriptor(modelId);
  const uploadContext = useRef({ modelId, epoch: 0, mounted: true });
  if (uploadContext.current.modelId !== modelId) {
    uploadContext.current.modelId = modelId;
    uploadContext.current.epoch++;
  }
  useEffect(() => {
    uploadContext.current.mounted = true;
    return () => {
      uploadContext.current.mounted = false;
      uploadContext.current.epoch++;
    };
  }, []);
  const previousModel = useRef(modelId);
  useEffect(() => {
    if (!m) return;
    const removed = [];
    if (
      previousModel.current !== modelId &&
      (runtime.extraAssets[previousModel.current] || []).length
    )
      removed.push("Image");
    previousModel.current = modelId;
    const imageLimit = m.roles.start || m.roles.image || 0;
    if (imageUrls.length > imageLimit) {
      onChange(
        m.roles.start ? "start" : "image",
        imageUrls.slice(0, imageLimit),
      );
      removed.push("Image");
    }
    if (endImageUrl && !m.roles.end) {
      onChange("end", []);
      removed.push("End");
    }
    for (const [role, urls] of [
      ["video", videoUrls],
      ["audio", audioUrls],
    ]) {
      const max = m.roles[role] || 0;
      if (urls.length > max) {
        onChange(role, urls.slice(0, max));
        removed.push(role === "video" ? "Video" : "Audio");
      }
    }
    setError(
      removed.length
        ? "При смене модели несовместимые вложения исключены: " +
            removed.join(", ")
        : "",
    );
  }, [modelId]);
  if (!m) return null;
  const extra = (runtime.extraAssets[modelId] || []).filter(
    (asset) => asset.role === "image",
  );
  const values = {
    image:
      m.kind === "video" && m.roles.start
        ? extra.map((asset) => asset.url)
        : imageUrls,
    start: imageUrls,
    end: endImageUrl ? [endImageUrl] : [],
    video: videoUrls,
    audio: audioUrls,
  };
  const roles =
    m.kind === "photo"
      ? ["image"]
      : ["start", "end", "image", "video", "audio"];
  const enabled = roles.filter((role) => m.roles[role] > 0);
  const total = enabled.reduce((sum, role) => sum + values[role].length, 0);
  const busy = isUploading(modelId);
  const title = (role, index) =>
    ({
      start: "Start",
      end: "End",
      image: "Image",
      video: "Video",
      audio: "Audio",
    })[role] + (["start", "end"].includes(role) ? "" : index + 1);
  function commit(role, urls) {
    if (m.kind === "video" && role === "image" && m.roles.start) {
      runtime.extraAssets[modelId] = urls.map((url) => ({
        id: url.split("/").pop(),
        url,
        role: "image",
        name: runtime.assetMetadata[url]?.name || "Image",
      }));
      publish();
    } else onChange(role, urls);
  }
  const accept = (role) => role === "video" ? "video/*" : role === "audio" ? "audio/*" : "image/png,image/jpeg,image/webp";
  const activeUpload = (epoch) => uploadContext.current.mounted && uploadContext.current.epoch === epoch && uploadContext.current.modelId === modelId;
  async function replace(role, index, file) {
    if (!file || isUploading(modelId) || isReadOnly()) return;
    const epoch = uploadContext.current.epoch;
    runtime.uploads[modelId] = (runtime.uploads[modelId] || 0) + 1;
    setError("");
    publish();
    try {
      const url = await uploadFile(null, file);
      if (!activeUpload(epoch)) return;
      const next = values[role].slice();
      next[index] = url;
      commit(role, next);
    } catch (e) {
      if (activeUpload(epoch)) setError(e.message);
    } finally {
      runtime.uploads[modelId]--;
      publish();
    }
  }
  async function attach(role, files) {
    if (!files.length || isUploading(modelId) || isReadOnly()) return;
    const epoch = uploadContext.current.epoch;
    if (values[role].length + files.length > m.roles[role]) {
      setError(`Лимит ${role}: ${m.roles[role]}.`);
      return;
    }
    if (m.max_assets && total + files.length > m.max_assets) {
      setError(`Всего можно прикрепить до ${m.max_assets} файлов.`);
      return;
    }
    runtime.uploads[modelId] = (runtime.uploads[modelId] || 0) + 1;
    setError("");
    publish();
    const next = values[role].slice();
    try {
      for (const file of files) {
        const url = await uploadFile(null, file);
        if (!activeUpload(epoch)) return;
        next.push(url);
        commit(role, next.slice());
      }
    } catch (e) {
      if (activeUpload(epoch)) setError(e.message);
    } finally {
      runtime.uploads[modelId]--;
      publish();
    }
  }
  function move(role, index, offset) {
    const next = values[role].slice(),
      other = index + offset;
    [next[index], next[other]] = [next[other], next[index]];
    commit(role, next);
  }
  return (
    <div className="nora-attachments" aria-label="Прикреплённые референсы">
      <div className="nora-attachment-row">
        {enabled.map((role) => (
          <React.Fragment key={role}>
            {values[role].map((url, index) => (
              <div
                className={"nora-attachment nora-attachment-" + role}
                key={url}
              >
                <span className="nora-attachment-label">
                  {title(role, index)}
                </span>
                {["image", "start", "end"].includes(role) ? (
                  <img src={url} alt={title(role, index)} />
                ) : role === "video" ? (
                  <video
                    src={url}
                    muted
                    playsInline
                    preload="metadata"
                    aria-label={title(role, index)}
                  />
                ) : (
                  <audio
                    src={url}
                    controls
                    preload="metadata"
                    aria-label={title(role, index)}
                  />
                )}
                <small title={runtime.assetMetadata[url]?.name}>
                  {runtime.assetMetadata[url]?.name || title(role, index)}
                </small>
                <label className={"nora-attachment-replace" + (busy || isReadOnly() ? " disabled" : "")}>
                  Заменить
                  <input
                    type="file"
                    aria-label={"Заменить " + title(role, index)}
                    accept={accept(role)}
                    disabled={busy || isReadOnly()}
                    onChange={(event) => {
                      void replace(role, index, event.target.files[0]);
                      event.target.value = "";
                    }}
                  />
                </label>
                <div className="nora-attachment-actions">
                  {m.roles[role] > 1 && (
                    <>
                      <button
                        type="button"
                        disabled={busy || index === 0}
                        aria-label={
                          "Передвинуть " + title(role, index) + " влево"
                        }
                        onClick={() => move(role, index, -1)}
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        disabled={busy || index === values[role].length - 1}
                        aria-label={
                          "Передвинуть " + title(role, index) + " вправо"
                        }
                        onClick={() => move(role, index, 1)}
                      >
                        →
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={"Удалить " + title(role, index)}
                    onClick={() =>
                      commit(
                        role,
                        values[role].filter((_, i) => i !== index),
                      )
                    }
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
            {values[role].length < m.roles[role] && (
              <label
                className={
                  "nora-attachment-add" +
                  (busy || isReadOnly() ? " disabled" : "")
                }
              >
                <span>＋</span>
                <span>
                  {role === "image"
                    ? "Image"
                    : role[0].toUpperCase() + role.slice(1)}
                </span>
                <input
                  type="file"
                  data-role={role}
                  aria-label={
                    "Добавить " +
                    (role === "image"
                      ? "Image"
                      : role[0].toUpperCase() + role.slice(1))
                  }
                  accept={accept(role)}
                  multiple={m.roles[role] - values[role].length > 1}
                  disabled={busy || isReadOnly()}
                  onChange={(event) => {
                    void attach(role, [...event.target.files]);
                    event.target.value = "";
                  }}
                />
              </label>
            )}
          </React.Fragment>
        ))}
      </div>
      <div className="nora-attachment-status" role="status">
        {busy
          ? "Загрузка… Отправка станет доступна после завершения."
          : total
            ? `Прикреплено референсов: ${total}`
            : enabled.length
              ? "Прикрепите референсы или опишите новый кадр"
              : "Эта модель создаёт кадр по описанию"}
        {error && <span className="nora-warning"> · {error}</span>}
      </div>
    </div>
  );
}
