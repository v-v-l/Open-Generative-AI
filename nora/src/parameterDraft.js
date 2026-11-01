export function emptyParameter(schema = {}) {
  if (schema.default !== undefined) return structuredClone(schema.default);
  if (schema.type === "boolean") return false;
  if (schema.type === "array") return [];
  if (schema.type === "object")
    return Object.fromEntries(
      Object.entries(schema.properties || {}).map(([key, value]) => [
        key,
        emptyParameter(value),
      ]),
    );
  return "";
}
export function validateParameterDraft(inputs, values) {
  const errors = [];
  function visit(schema, value, label) {
    if (value === "" || value == null) {
      if (schema.required === true) errors.push(label + ": заполните поле");
      return;
    }
    if (schema.enum && !schema.enum.some((option) => option === value))
      errors.push(label + ": выберите значение из списка");
    if (["number", "integer", "int"].includes(schema.type)) {
      const number = Number(value),
        min = schema.minValue ?? schema.minimum,
        max = schema.maxValue ?? schema.maximum;
      if (
        !Number.isFinite(number) ||
        (["integer", "int"].includes(schema.type) && !Number.isInteger(number))
      )
        errors.push(
          label +
            ": требуется число" +
            (schema.type === "number" ? "" : " без дробной части"),
        );
      else if ((min != null && number < min) || (max != null && number > max))
        errors.push(
          label + ": допустимый диапазон " + (min ?? "−∞") + "…" + (max ?? "∞"),
        );
    }
    if (schema.type === "array") {
      if (!Array.isArray(value)) {
        errors.push(label + ": требуется список");
        return;
      }
      if (
        value.length < (schema.minItems ?? schema.min_items ?? 0) ||
        value.length > (schema.maxItems ?? schema.max_items ?? Infinity)
      )
        errors.push(label + ": неверное количество элементов");
      value.forEach((item, index) =>
        visit(schema.items || {}, item, label + " " + (index + 1)),
      );
    }
    if (schema.type === "object")
      for (const [key, child] of Object.entries(schema.properties || {}))
        visit(
          {
            ...child,
            required:
              child.required === true ||
              (schema.required || []).includes?.(key),
          },
          value?.[key],
          label + " / " + (child.title || key),
        );
  }
  for (const { key, schema } of inputs)
    visit(schema, values[key] ?? emptyParameter(schema), schema.title || key);
  return errors;
}
