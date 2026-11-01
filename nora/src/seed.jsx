import React from "react";
import { descriptor } from "./runtime.js";
import { supportsSeed } from "./catalog.js";

export function NoraSeedControl({ modelId, value, onChange }) {
  const model = descriptor(modelId);
  if (!supportsSeed(model)) return null;
  const random =
    value == null || value === "" || value === "random" || Number(value) < 0;
  return (
    <details className="nora-seed-control">
      <summary>{random ? "Seed · случайный" : "Seed · " + value}</summary>
      <div>
        <label>
          <input
            type="checkbox"
            aria-label="Случайный seed"
            checked={random}
            onChange={(event) => onChange(event.target.checked ? -1 : 0)}
          />
          Новый seed для каждого задания
        </label>
        {!random && (
          <label className="nora-fixed-seed">
            Фиксированный seed
            <input
              type="number"
              aria-label="Фиксированный seed"
              min="0"
              max={
                model.provider === "openrouter" ? 4294967295 : 9007199254740991
              }
              step="1"
              value={value}
              onChange={(event) => onChange(event.target.value)}
            />
          </label>
        )}
        <small>
          Фактический seed сохраняется в истории. Повтор задания использует
          сохранённый seed.
        </small>
      </div>
    </details>
  );
}
