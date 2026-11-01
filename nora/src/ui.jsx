import { isReadOnly, availabilityReason, modelUnavailable } from "./runtime.js";
import React, { useEffect, useState } from "react";
import { runtime, publish, request, refresh, descriptor } from "./runtime.js";
import { buildJob, historyFor, hideHistory } from "./api.js";
export { NoraAttachments } from "./attachments.jsx";
export { NoraComposer } from "./composer.jsx";
export { referenceInputs as noraReferenceInputs } from "./api.js";
export function useRuntime() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const callback = () => setTick((v) => v + 1);
    runtime.listeners.add(callback);
    return () => runtime.listeners.delete(callback);
  }, []);
  return runtime.state;
}
export function NoraSummary({ params }) {
  const state = useRuntime();
  const [estimate, setEstimate] = useState(null),
    [error, setError] = useState("");
  const model = descriptor(params.model);
  const signature = JSON.stringify([
    params,
    runtime.extraAssets[params.model],
    runtime.uploads[params.model],
  ]);
  useEffect(() => {
    runtime.drafts[params.model] = params;
    if (!String(params.prompt || "").trim() || runtime.uploads[params.model]) {
      setEstimate(null);
      setError("");
      return;
    }
    let stopped = false;
    const timer = setTimeout(async () => {
      try {
        const result = await request("/api/estimate", buildJob(params));
        if (!stopped) {
          setEstimate(result);
          setError("");
        }
      } catch (e) {
        if (!stopped) {
          setEstimate(null);
          setError(e.message);
        }
      }
    }, 500);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [signature]);
  if (!model) return null;
  const unavailable = availabilityReason(model, state),
    cost = estimate?.estimated_usd,
    upper = estimate?.upper_usd;
  return (
    <div className="nora-summary nora-summary-compact">
      <div className="nora-cost-row">
        <span className="nora-cost">
          {model.id === "qwen-local"
            ? "Локально · без оплаты API"
            : typeof cost === "number"
              ? "≈ $" + cost.toFixed(4)
              : "Стоимость после генерации"}
          {typeof upper === "number" && upper !== cost
            ? " · до $" + upper.toFixed(4)
            : ""}
        </span>
        <details className="nora-advanced">
          <summary>Детали</summary>
          <div>
            <p>
              Модель: <code>{model.remote_model || model.id}</code>
            </p>
            {model.id === "h3-simplepod" && (
              <p>
                H3: Start/End — мягкие направляющие; при несовпадении пропорций
                модель обрезает их по центру. Видео/аудио по 2–15 с, суммарно до
                15 с на тип; всего до 12 файлов.
              </p>
            )}
            <p>
              Файлы до 100 МБ, без автоматического кропа и ресайза при загрузке.
              Порядок Image1, Image2 соответствует строке вложений. Промпт
              передаётся дословно.
            </p>
            <p>
              Max USD проверяет предварительную оценку. Если она неизвестна,
              задание с бюджетом отклоняется. Это не гарантия итогового
              списания. Очередь {state?.queue_paused ? "на паузе" : "запущена"}.
            </p>
            {(estimate?.uncertainty || estimate?.details) && (
              <p>{String(estimate.uncertainty || estimate.details)}</p>
            )}
            {(estimate?.timestamp || model.timestamp) && (
              <small>
                Цены: {String(estimate?.timestamp || model.timestamp)}
              </small>
            )}
            {model.pricing && (
              <>
                <h4>Тарифы провайдера</h4>
                <pre>{JSON.stringify(model.pricing, null, 2)}</pre>
                {typeof model.pricing_source === "string" &&
                  model.pricing_source.startsWith("https://") && (
                    <a
                      href={model.pricing_source}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Источник тарифов
                    </a>
                  )}
              </>
            )}
          </div>
        </details>
      </div>
      {(unavailable || error) && (
        <p className="nora-warning" role="status">
          {unavailable || error}
        </p>
      )}
    </div>
  );
}
export function Queue() {
  const state = useRuntime(),
    [open, setOpen] = useState(false),
    [error, setError] = useState("");
  if (!state) return null;
  async function act(path, body = {}) {
    try {
      await request(path, body);
      await refresh();
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  const pending = state.jobs.filter((j) =>
    ["queued", "running"].includes(j.status),
  );
  return (
    <section className="nora-queue">
      <div className="nora-queue-head">
        <button type="button" onClick={() => setOpen(!open)}>
          Очередь · {pending.length} {open ? "▴" : "▾"}
        </button>
        <span>
          {state.queue_paused
            ? "Приостановлена"
            : "Выполняется последовательно"}
        </span>
        <button
          type="button"
          disabled={isReadOnly()}
          onClick={() =>
            void act("/api/queue", { paused: !state.queue_paused })
          }
        >
          {state.queue_paused ? "▶ Запустить очередь" : "Ⅱ Приостановить"}
        </button>
      </div>
      {open && (
        <div className="nora-queue-body">
          {state.jobs.length === 0 && (
            <p>
              Добавьте задания в студии. Выполнение начнётся после «Запустить
              очередь».
            </p>
          )}
          {state.jobs.map((job) => (
            <article key={job.id}>
              <header>
                <strong>{descriptor(job.model)?.label || job.model}</strong>
                <span>{job.status}</span>
              </header>
              <p>{job.prompt}</p>
              {job.error && <p className="nora-warning">{job.error}</p>}
              {job.status === "queued" && modelUnavailable(job.model) && (
                <p className="nora-warning" role="status">
                  {availabilityReason(descriptor(job.model), state)} Выполнение
                  недоступно.
                </p>
              )}
              {job.billing && job.billing.actual_usd == null && (
                <small>Стоимость неизвестна</small>
              )}
              {job.billing?.actual_usd != null && (
                <small>
                  {job.billing.status === "calculated_list_price_not_invoice"
                    ? "По тарифам, не счёт"
                    : "Фактически"}
                  : ${job.billing.actual_usd.toFixed(5)}
                </small>
              )}
              <div>
                {["queued", "running"].includes(job.status) && (
                  <button
                    disabled={isReadOnly()}
                    onClick={() => void act("/api/jobs/" + job.id + "/cancel")}
                  >
                    Отменить
                  </button>
                )}
                {["failed", "cancelled", "canceled", "interrupted"].includes(
                  job.status,
                ) && (
                  <button
                    disabled={isReadOnly() || modelUnavailable(job.model)}
                    onClick={() => void act("/api/jobs/" + job.id + "/retry")}
                  >
                    Повторить
                  </button>
                )}
                {job.outputs?.map((o) => (
                  <a key={o.url} href={o.url} download={o.name}>
                    Скачать {o.kind}
                  </a>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
      {error && <p className="nora-warning">{error}</p>}
    </section>
  );
}
const studios = [
  ["image", "Image Studio"],
  ["video", "Video Studio"],
  ["cinema", "Cinema"],
  ["lipsync", "Lip Sync"],
  ["audio", "Audio"],
  ["other", "Другие студии"],
];
export function Shell({ ImageStudio, VideoStudio }) {
  useRuntime();
  const [tab, setTab] = useState("image"),
    [toast, setToast] = useState("");
  useEffect(() => {
    const listener = () => {
      setToast("Задание добавлено в постоянную очередь");
      setTimeout(() => setToast(""), 5000);
    };
    window.addEventListener("nora-enqueued", listener);
    return () => window.removeEventListener("nora-enqueued", listener);
  }, []);
  return (
    <div className="nora-app">
      <header className="nora-header">
        <a href="/" className="nora-brand">
          Open Generative AI <small>Alice</small>
        </a>
        <nav>
          {studios.map(([id, label]) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <a href="/references/" className="nora-reference-link">
          Референсы ↗
        </a>
        <button
          disabled={isReadOnly()}
          onClick={async () => {
            try {
              await request("/api/catalog/refresh", {});
              location.reload();
            } catch (error) {
              setToast(error.message);
            }
          }}
        >
          Обновить каталог
        </button>
        <button
          onClick={async () => {
            await request("/api/auth/logout", {});
            location.assign("/login");
          }}
        >
          Выйти
        </button>
      </header>
      {isReadOnly() && (
        <div className="nora-readonly" role="status">
          Режим просмотра · генерация, загрузка файлов и запуск очереди
          отключены.
        </div>
      )}
      <Queue />
      <main className="nora-main">
        <div className="nora-studio-page" hidden={tab !== "image"}>
          <ImageStudio
            apiKey="nora-cookie-session"
            historyItems={historyFor("photo")}
            onDeleteHistoryItem={(id) =>
              hideHistory(typeof id === "string" ? id : id.id)
            }
          />
        </div>
        <div className="nora-studio-page" hidden={tab !== "video"}>
          <VideoStudio
            apiKey="nora-cookie-session"
            historyItems={historyFor("video")}
            onDeleteHistoryItem={(id) =>
              hideHistory(typeof id === "string" ? id : id.id)
            }
          />
        </div>
        {!["image", "video"].includes(tab) && (
          <section className="nora-unavailable">
            <h1>{studios.find((s) => s[0] === tab)?.[1]}</h1>
            <p>
              Эта нативная MuAPI-студия сохранена в исходном fork, но ещё не
              подключена к нашему backend. Она не отправляет запросы через
              другого провайдера автоматически.
            </p>
            <p>
              Сейчас подключены Image Studio и Video Studio: наш Qwen/H3, OpenAI
              и модели OpenRouter из живого каталога.
            </p>
            <button onClick={() => setTab("image")}>
              Открыть Image Studio
            </button>
          </section>
        )}
      </main>
      {toast && (
        <div className="nora-toast" role="status">
          {toast}
        </div>
      )}
      <footer className="nora-footer">
        Anil-matcha / Open-Generative-AI · MIT · наш fork и backend. Ключи
        хранятся на сервере.
      </footer>
    </div>
  );
}
