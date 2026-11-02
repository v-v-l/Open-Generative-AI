import React, { useId, useState } from 'react';
import { descriptor } from './runtime.js';
import { FORMATS, NATIVE_TIERS, nativeModel, nativeDimensions, ratioFor, framePresets, settingValue, allowedValues, compatiblePatch, outputConflict, sizeFormat, tierLabel } from './outputPresets.js';

function Choice({label, value, options, onChange, customLabel}) {
  const id = useId();
  if (!options.length) return null;
  const known = options.some((option) => String(option.value) === String(value));
  return <label className="nora-output-choice" htmlFor={id}><span>{label}</span><select id={id} aria-label={label} value={value ?? ''} onChange={(event) => onChange(options.find((option) => String(option.value) === event.target.value)?.value)}>
    {!known && <option value={value ?? ''}>Свой: {customLabel || value || 'не задано'}</option>}
    {options.map((option) => <option key={String(option.value)} value={option.value}>{option.label}</option>)}
  </select></label>;
}
const options = (values) => values.map((value) => ({value, label:String(value)}));
export function NoraOutputPresets({modelId, values, onChange}) {
  const model = descriptor(modelId), [notice, setNotice] = useState('');
  if (!model) return null;
  const local = nativeModel(model), settings = model.settings || {};
  const apply = (patch) => {
    const result = compatiblePatch(model, values, patch);
    setNotice(result.adjusted.length ? `Для совместимости обновлено: ${result.adjusted.join(', ')}` : '');
    onChange(result.patch);
  };
  const width = Number(values.width ?? model.default_width ?? 704), height = Number(values.height ?? model.default_height ?? 960);
  const format = ratioFor(width, height);
  const standardFormat = FORMATS.includes(format);
  const nativeOptions = (standardFormat ? NATIVE_TIERS : []).map((tier) => ({tier, ...nativeDimensions(model, format, tier)})).filter((item) => item.width);
  const currentTier = nativeOptions.find((item) => item.width === width && item.height === height)?.tier;
  const sizeValues = settings.size?.values || [], size = settingValue(model, values, 'size');
  const selectedSizeFormat = sizeFormat(size || ''), sizesForFormat = sizeValues.filter((value) => sizeFormat(value) === selectedSizeFormat);
  const changeFormat = (next) => {
    if (local) apply(nativeDimensions(model, next, currentTier || 1024));
    else if (sizeValues.length) apply({size:sizeValues.find((value) => sizeFormat(value) === next)});
    else apply({aspect_ratio:next});
  };
  const conflict = outputConflict(model, values);
  const quality = settingValue(model, values, 'quality');
  return <section className="nora-output-presets" aria-label="Формат, разрешение и длительность">
    {local ? <>
      <Choice label="Формат" value={format} options={options(FORMATS)} onChange={changeFormat}/>
      <Choice label="Разрешение" value={currentTier || `${width}×${height}`} options={nativeOptions.length ? nativeOptions.map((item) => ({value:item.tier, label:`${Math.max(item.width,item.height) === item.tier ? '' : '≈ '}${tierLabel(item.tier)} · ${item.width}×${item.height}`})) : [{value:`${width}×${height}`,label:`Свой · ${width}×${height}`}]} onChange={(tier) => apply(nativeDimensions(model, format, tier))}/>
    </> : sizeValues.length ? <>
      <Choice label="Формат" value={selectedSizeFormat} options={[...new Set(sizeValues.map(sizeFormat))].map((value) => ({value,label:value === 'auto' ? 'Авто' : value}))} onChange={changeFormat}/>
      <Choice label="Разрешение" value={size} options={sizesForFormat.map((value) => ({value,label:value === 'auto' ? 'Авто · по модели' : value.replace('x','×')}))} onChange={(value) => apply({size:value})}/>
    </> : <>
      <Choice label="Формат" value={settingValue(model, values, 'aspect_ratio')} options={options(allowedValues(model, values, 'aspect_ratio'))} onChange={changeFormat}/>
      <Choice label="Разрешение" value={settingValue(model, values, 'resolution')} options={options(allowedValues(model, values, 'resolution'))} onChange={(resolution) => apply({resolution})}/>
    </>}
    <Choice label="Качество" value={quality} options={options(allowedValues(model, values, 'quality'))} onChange={(quality) => apply({quality})}/>
    {local && model.kind === 'video' ? <Choice label="Длительность" value={values.frames ?? model.default_frames ?? 141} options={framePresets(model)} customLabel={`≈ ${(Number(values.frames ?? model.default_frames ?? 141) / (model.fps || 24)).toFixed(2)} с`} onChange={(frames) => apply({frames})}/> : <Choice label="Длительность" value={settingValue(model, values, 'duration')} options={allowedValues(model, values, 'duration').map((value) => ({value,label:`${value} с`}))} onChange={(duration) => apply({duration})}/>}
    {local && <small className="nora-output-note">{width}×{height} px</small>}
    {(conflict || notice) && <small className="nora-output-note" role="status">{conflict || notice}</small>}
  </section>;
}
export const noraHasOutputPresets = (modelId) => Boolean(descriptor(modelId));
