// Output choices are derived from each executor's advertised contract.
export const FORMATS = ['1:1', '3:4', '4:3', '9:16', '16:9', '2:3', '3:2'];
export const NATIVE_TIERS = [512, 1024, 1536];
export const nativeModel = (model) => ['local', 'simplepod'].includes(model?.provider);
const gcd = (a, b) => b ? gcd(b, a % b) : a;
export function ratioFor(width, height) {
  const divisor = gcd(Number(width), Number(height));
  return divisor > 0 ? `${width / divisor}:${height / divisor}` : '';
}
export function nativeDimensions(model, format, tier) {
  const [x, y] = format.split(':').map(Number), step = model.dimension_step || 32;
  const minimum = model.dimension_min || 256, maximum = model.dimension_max || 1536;
  const low = Math.ceil(minimum / (Math.min(x, y) * step));
  const high = Math.floor(maximum / (Math.max(x, y) * step));
  if (!x || !y || low > high) return null;
  const scale = Math.min(high, Math.max(low, Math.round(tier / (Math.max(x, y) * step))));
  return { width: x * step * scale, height: y * step * scale };
}
export function framePresets(model) {
  const fps = model.fps || 24, step = model.frame_step || 17, offset = model.frame_offset ?? 5;
  const minimum = model.frames_min || 107, maximum = model.frames_max || 362;
  const values = [5, 6, 8, 10, 12, 15].map((seconds) => Math.max(minimum, Math.min(maximum, Math.round((seconds * fps - offset) / step) * step + offset)));
  return [...new Set(values)].map((frames) => ({value: frames, label: `≈ ${(frames / fps).toFixed(2)} с`}));
}
export function settingValue(model, values, key) {
  const spec = model.settings?.[key];
  return values[key] != null && values[key] !== '' ? values[key] : spec?.default ?? spec?.values?.[0];
}
export function allowedValues(model, values, key) {
  let options = model.settings?.[key]?.values || [];
  for (const rule of model.output_constraints || []) {
    if (Object.entries(rule.when).every(([field, value]) => settingValue(model, values, field) === value) && rule.allowed[key]) {
      options = options.filter((value) => rule.allowed[key].includes(value));
    }
  }
  return options;
}
export function compatiblePatch(model, values, patch) {
  const next = {...values, ...patch}, result = {...patch}, adjusted = [];
  for (const rule of model.output_constraints || []) {
    if (!Object.entries(rule.when).every(([key, value]) => settingValue(model, next, key) === value)) continue;
    for (const [key, options] of Object.entries(rule.allowed)) {
      if (!options.includes(settingValue(model, next, key))) {
        next[key] = result[key] = options[0];
        const label = {duration:'длительность', resolution:'разрешение', aspect_ratio:'формат', quality:'качество'}[key] || key;
        adjusted.push(`${label}: ${options[0]}${key === 'duration' ? ' с' : ''}`);
      }
    }
  }
  return {patch: result, adjusted};
}
export function outputConflict(model, values) {
  for (const rule of model.output_constraints || []) {
    if (Object.entries(rule.when).every(([key, value]) => settingValue(model, values, key) === value)) {
      for (const [key, options] of Object.entries(rule.allowed)) {
        if (!options.includes(settingValue(model, values, key))) return `Для ${Object.values(rule.when).join(' / ')}: ${{duration:'длительность', resolution:'разрешение', aspect_ratio:'формат', quality:'качество'}[key] || key} — ${options.join(', ')}${key === 'duration' ? ' с' : ''}. Выберите совместимый вариант.`;
      }
    }
  }
  return '';
}
export function sizeFormat(size) {
  const match = /^(\d+)x(\d+)$/.exec(size);
  if (!match) return size;
  const [width, height] = match.slice(1).map(Number);
  return ratioFor(width, height);
}
export function tierLabel(tier) {
  return tier === 1024 ? '1K' : tier === 1536 ? '1.5K' : String(tier);
}
