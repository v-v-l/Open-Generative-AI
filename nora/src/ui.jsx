import { isReadOnly, availabilityReason, modelUnavailable } from "./runtime.js";
import React, { useEffect, useState } from "react";
import { runtime, publish, request, refresh, descriptor } from "./runtime.js";
import { buildJob, uploadFile, historyFor, hideHistory } from "./api.js";
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
  const state = useRuntime(),
    [estimate, setEstimate] = useState(null),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const model = descriptor(params.model),
    signature = JSON.stringify(params),
    [extraVersion, setExtraVersion] = useState(0);
  useEffect(() => {
    runtime.drafts[params.model] = params;
    if (!String(params.prompt || "").trim()) {
      setEstimate(null);
      setMessage("Добавьте промпт для расчёта");
      return;
    }
    let stopped = false;
    const timer = setTimeout(async () => {
      try {
        const result = await request("/api/estimate", buildJob(params));
        if (!stopped) {
          setEstimate(result);
          setMessage("");
        }
      } catch (error) {
        if (!stopped) {
          setEstimate(null);
          setMessage(error.message);
        }
      }
    }, 500);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [signature, extraVersion]);
  if (!model) return null;
  const unavailable = availabilityReason(model, state);
  const extras = runtime.extraAssets[model.id] || [];
  async function attach(files) {
    setBusy(true);
    try {
      for (const file of files) {
        if (extras.length >= (model.roles.image || 0))
          throw Error("Превышен лимит фото-референсов");
        const url = await uploadFile(null, file);
        extras.push({
          id: url.split("/").pop(),
          url,
          name: file.name,
          role: "image",
        });
      }
      runtime.extraAssets[model.id] = extras;
      setExtraVersion((v) => v + 1);
      publish();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }
  const cost = estimate?.estimated_usd,
    upper = estimate?.upper_usd;
  return (
    <div className="nora-summary">
      {unavailable ? (
        <p className="nora-warning" role="status">
          {unavailable}
        </p>
      ) : model.id === "qwen-local" &&
        model.available === true &&
        model.availability === "executor_ready" ? (
        <p role="status">Qwen · Доступна</p>
      ) : null}
      {model.id === "h3-simplepod" && (
        <>
          <details>
            <summary>Дополнительные image refs H3 ({extras.length})</summary>
            <p>
              Первый/последний кадр задаются выше. Эти фото — отдельные
              референсы внешности/одежды, по порядку Picture N.
            </p>
            <div className="nora-ref-tray">
              {extras.map((a, i) => (
                <div key={a.id}>
                  <img src={a.url} alt={a.name} />
                  <span>Picture {i + 1}</span>
                  <button
                    type="button"
                    aria-label="Удалить референс"
                    onClick={() => {
                      runtime.extraAssets[model.id] = extras.filter(
                        (x) => x !== a,
                      );
                      setExtraVersion((v) => v + 1);
                      publish();
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
              <label>
                + Фото
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  disabled={busy}
                  onChange={(e) => {
                    void attach([...e.target.files]);
                    e.target.value = "";
                  }}
                />
              </label>
            </div>
          </details>
          <p>
            H3: первый/последний кадр — мягкие направляющие. Если пропорции
            отличаются от выхода, направляющая обрезается по центру. Видео/аудио
            по 2–15 с, суммарно до 15 с на тип; всего до 12 файлов.
          </p>
        </>
      )}
      {model.pricing && (
        <details className="nora-rates">
          <summary>Тарифы провайдера</summary>
          <pre>{JSON.stringify(model.pricing, null, 2)}</pre>
          {typeof model.pricing_source === "string" &&
            model.pricing_source.startsWith("https://") && (
              <a href={model.pricing_source} target="_blank" rel="noreferrer">
                Источник тарифов
              </a>
            )}
          {model.timestamp && <small>Обновлено: {model.timestamp}</small>}
        </details>
      )}
      <div className="nora-estimate">
        <strong>
          Оценка за одно задание:{" "}
          {typeof cost === "number"
            ? "≈ $" + cost.toFixed(4)
            : "заранее неизвестна"}
        </strong>
        {typeof upper === "number" && upper !== cost && (
          <span> · до ${upper.toFixed(4)}</span>
        )}
        <small>
          {message ||
            String(
              estimate?.uncertainty ||
                estimate?.details ||
                "Фактическая стоимость определяется временем GPU или ответом провайдера.",
            )}
        </small>
        {(estimate?.timestamp || model.timestamp) && (
          <small>Цены: {String(estimate?.timestamp || model.timestamp)}</small>
        )}
      </div>
      <details>
        <summary>Об очереди и бюджете</summary>
        <p>
          Бюджет Max USD проверяет предварительную оценку; если она неизвестна,
          запуск с бюджетом отклоняется. Это не гарантия итогового списания.
          Промпт отправляется дословно. Файлы до 100 МБ без автоматического
          кропа и ресайза. Очередь{" "}
          {state?.queue_paused ? "на паузе — аренда не начинается" : "запущена"}
          .
        </p>
      </details>
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
