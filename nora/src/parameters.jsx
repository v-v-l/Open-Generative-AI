import React, { useId, useRef, useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { emptyParameter, validateParameterDraft } from "./parameterDraft.js";

function Field({ schema, value, onChange, label }) {
  const id = useId(),
    current = value ?? emptyParameter(schema);
  if (schema.type === "object")
    return (
      <fieldset className="nora-param-object">
        <legend>{label}</legend>
        {Object.entries(schema.properties || {}).map(([key, child]) => (
          <Field
            key={key}
            schema={child}
            value={current[key]}
            onChange={(next) => onChange({ ...current, [key]: next })}
            label={child.title || key.replaceAll("_", " ")}
          />
        ))}
      </fieldset>
    );
  if (schema.type === "array")
    return (
      <fieldset className="nora-param-array">
        <legend>{label}</legend>
        {schema.description && <small>{schema.description}</small>}
        {(Array.isArray(current) ? current : []).map((item, index) => (
          <div key={index}>
            <Field
              schema={schema.items || { type: "string" }}
              value={item}
              label={label + " " + (index + 1)}
              onChange={(next) =>
                onChange(
                  current.map((value, i) => (i === index ? next : value)),
                )
              }
            />
            <button
              type="button"
              onClick={() => onChange(current.filter((_, i) => i !== index))}
              aria-label={"Удалить " + label + " " + (index + 1)}
            >
              Удалить
            </button>
          </div>
        ))}
        {current.length < (schema.maxItems ?? schema.max_items ?? Infinity) && (
          <button
            type="button"
            onClick={() => onChange([...current, emptyParameter(schema.items)])}
          >
            Добавить {label}
          </button>
        )}
      </fieldset>
    );
  const numeric = ["number", "integer", "int"].includes(schema.type);
  return (
    <div
      className={
        "nora-param-field" +
        (schema.type === "boolean" ? " nora-param-boolean" : "")
      }
    >
      <label htmlFor={id}>{label}</label>
      {schema.enum ? (
        <select
          id={id}
          value={current}
          required={schema.required === true}
          aria-describedby={schema.description ? id + "-help" : undefined}
          onChange={(event) =>
            onChange(
              schema.enum.find(
                (option) => String(option) === event.target.value,
              ),
            )
          }
        >
          {schema.emptyLabel && schema.default === undefined && (
            <option value="">{schema.emptyLabel}</option>
          )}
          {schema.enum.map((option) => (
            <option key={String(option)} value={String(option)}>
              {schema.optionLabels?.[option] || String(option)}
            </option>
          ))}
        </select>
      ) : schema.type === "boolean" ? (
        <input
          id={id}
          type="checkbox"
          checked={Boolean(current)}
          onChange={(event) => onChange(event.target.checked)}
        />
      ) : (
        <input
          id={id}
          type={numeric ? "number" : "text"}
          value={current}
          min={schema.minValue ?? schema.minimum}
          max={schema.maxValue ?? schema.maximum}
          step={schema.step ?? (schema.type === "number" ? "any" : 1)}
          required={schema.required === true}
          placeholder={
            ["string", "number"].includes(typeof schema.examples?.[0])
              ? String(schema.examples[0])
              : undefined
          }
          aria-describedby={schema.description ? id + "-help" : undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {schema.description && (
        <small id={id + "-help"}>{schema.description}</small>
      )}
    </div>
  );
}
export function NoraParameterControls({
  inputs,
  values,
  onApply,
  onOpen,
  title = "Параметры модели",
}) {
  const filtered = inputs.filter((input) => input.key !== "seed");
  const dialog = useRef(null),
    trigger = useRef(null),
    form = useRef(null),
    titleId = useId();
  const [draft, setDraft] = useState({}),
    [error, setError] = useState(""),
    [viewport, setViewport] = useState({ height: window.innerHeight, top: 0 });
  useEffect(() => {
    const view = window.visualViewport;
    const update = () =>
      setViewport({
        height: view?.height || window.innerHeight,
        top: view?.offsetTop || 0,
      });
    update();
    view?.addEventListener("resize", update);
    view?.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    return () => {
      view?.removeEventListener("resize", update);
      view?.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);
  if (!filtered.length) return null;
  const cancel = () => dialog.current?.close();
  const apply = (event) => {
    event.preventDefault();
    const errors = validateParameterDraft(filtered, draft);
    if (errors.length) {
      setError(errors[0]);
      return;
    }
    if (!form.current.reportValidity()) return;
    const patch = Object.fromEntries(
      filtered.map(({ key, schema }) => [
        key,
        draft[key] ?? emptyParameter(schema),
      ]),
    );
    onApply(patch);
    dialog.current.close();
  };
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="nora-params-trigger"
        aria-haspopup="dialog"
        aria-label={"Параметры модели · " + filtered.length}
        onClick={(event) => {
          event.stopPropagation();
          onOpen?.();
          setDraft(structuredClone(values));
          setError("");
          dialog.current.showModal();
        }}
      >
        Параметры <span>{filtered.length}</span>⌄
      </button>
      {createPortal(
        <dialog
          ref={dialog}
          className="nora-params-dialog"
          aria-labelledby={titleId}
          style={{
            top: viewport.top + 12,
            maxHeight: Math.max(140, viewport.height - 24),
          }}
          onClose={() => trigger.current?.focus()}
          onClick={(event) => {
            event.stopPropagation();
            if (event.target !== event.currentTarget) return;
            const rect = event.currentTarget.getBoundingClientRect();
            if (
              event.clientX < rect.left ||
              event.clientX > rect.right ||
              event.clientY < rect.top ||
              event.clientY > rect.bottom
            )
              cancel();
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") event.stopPropagation();
            if (event.key !== "Tab") return;
            const items = [
              ...event.currentTarget.querySelectorAll(
                "button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href]",
              ),
            ].filter((node) => node.getClientRects().length);
            const first = items[0],
              last = items.at(-1);
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first?.focus();
            }
          }}
        >
          <form ref={form} onSubmit={apply} noValidate>
            <header>
              <h2 id={titleId}>{title}</h2>
              <button
                type="button"
                autoFocus
                onClick={cancel}
                aria-label="Закрыть параметры без изменений"
              >
                ×
              </button>
            </header>
            <div
              className="nora-params-scroll"
              role="region"
              aria-label="Поля параметров"
              tabIndex="0"
            >
              {filtered.map(({ key, schema }) => (
                <Field
                  key={key}
                  schema={schema}
                  value={draft[key]}
                  label={schema.title || key.replaceAll("_", " ")}
                  onChange={(value) =>
                    setDraft((current) => ({ ...current, [key]: value }))
                  }
                />
              ))}
            </div>
            <footer>
              {error && <p role="alert">{error}</p>}
              <div>
                <button type="button" onClick={cancel}>
                  Отменить
                </button>
                <button type="submit" className="nora-params-apply">
                  Применить
                </button>
              </div>
            </footer>
          </form>
        </dialog>,
        document.body,
      )}
    </>
  );
}
