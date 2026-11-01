import test from "node:test";
import assert from "node:assert/strict";
import {
  emptyParameter,
  validateParameterDraft,
} from "../src/parameterDraft.js";
test("draft validation preserves defaults/types and rejects invalid numeric bounds/enums", () => {
  const inputs = [
    {
      key: "width",
      schema: { type: "number", minValue: 256, maxValue: 1536, default: 704 },
    },
    { key: "audio", schema: { type: "boolean", default: false } },
    {
      key: "quality",
      schema: { type: "string", enum: ["low", "high"], default: "low" },
    },
  ];
  assert.deepEqual(
    validateParameterDraft(inputs, {
      width: "832",
      audio: true,
      quality: "high",
    }),
    [],
  );
  assert.match(
    validateParameterDraft(inputs, {
      width: 2048,
      audio: false,
      quality: "low",
    })[0],
    /диапазон/,
  );
  assert.match(
    validateParameterDraft(inputs, {
      width: 704,
      audio: false,
      quality: "unknown",
    })[0],
    /списка/,
  );
  assert.equal(emptyParameter(inputs[0].schema), 704);
  assert.equal(emptyParameter(inputs[1].schema), false);
});
test("nested array/object constraints and required fields are checked without mutating drafts", () => {
  const inputs = [
    {
      key: "rows",
      schema: {
        type: "array",
        minItems: 1,
        maxItems: 2,
        items: {
          type: "object",
          required: ["name"],
          properties: { name: { type: "string" } },
        },
      },
    },
  ];
  const values = { rows: [{ name: "original" }] },
    before = structuredClone(values);
  assert.deepEqual(validateParameterDraft(inputs, values), []);
  assert.deepEqual(values, before);
  assert.ok(validateParameterDraft(inputs, { rows: [] }).length);
  assert.ok(validateParameterDraft(inputs, { rows: [{ name: "" }] }).length);
});
