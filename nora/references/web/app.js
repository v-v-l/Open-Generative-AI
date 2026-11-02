"use strict";
const $ = (selector) => document.querySelector(selector);
const categoryNames = {
  all: "Все наборы",
  face: "Голова / причёска",
  body: "Фигура / причёска",
  outfit: "Образы / одежда",
  scene: "Локация",
  lora: "LoRA · фото / видео",
};
const statusNames = {
  accepted: "Отобран",
  candidate: "Кандидат",
  working: "Рабочий референс",
  user_supplied: "Загружен вами",
};
const limit = 16;
let catalog = { records: [], missing: {}, collections: [] },
  selected = [],
  tab = "all",
  busy = false,
  exportURL = null;
let creating = false, uploading = false, uploadTarget = null, uploadFile = null, uploadPreviewURL = null;
let uploadFiles = [], uploadResults = [], removing = false, removeTarget = null;
const isVideo = (item) => item?.media_kind === "video";
const memberIds = (collection) => collection.category === "lora" ? (collection.items || []) : (collection.slots || []).map((slot) => slot.reference_id);
const slotLabels = {
  face: ["0° · спереди", "45° · передние ¾", "90° · профиль", "135° · задние ¾", "180° · сзади", "225° · задние ¾", "270° · профиль", "315° · передние ¾"],
  body: ["0° · спереди", "45° · передние ¾", "90° · сбоку", "135° · задние ¾", "180° · сзади", "225° · задние ¾", "270° · сбоку", "315° · передние ¾"],
  outfit: ["0° · спереди", "45° · передние ¾", "90° · сбоку", "135° · задние ¾", "180° · сзади", "225° · задние ¾", "270° · сбоку", "315° · передние ¾"],
  scene: ["Спереди · 0°", "Справа · 90°", "Сзади · 180°", "Слева · 270°"],
};
function node(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined) value.textContent = text;
  if (className) value.className = className;
  return value;
}
function button(text, action, label) {
  const value = node("button", text);
  value.type = "button";
  value.onclick = action;
  if (label) value.setAttribute("aria-label", label);
  return value;
}
function message(text, error = false) {
  $("#library-status").textContent = text;
  $("#status").textContent = text;
  $("#status").classList.toggle("error", error);
}
function setCategory(collection) { return collection.id === "head360" || collection.category === "head360" ? "face" : collection.category; }
function setRecords(collection) { return [...new Set(memberIds(collection))].map(record).filter(Boolean); }
function visibleSets() {
  const query = $("#search").value.trim().toLocaleLowerCase("ru");
  return (catalog.collections || []).filter((collection) =>
    (!collection.archived || $("#archived").checked) &&
    (tab === "all" || setCategory(collection) === tab) &&
    (!query || [collection.title, collection.description, ...setRecords(collection).flatMap((item) => [item.title, item.id, ...(item.tags || [])])].join(" ").toLocaleLowerCase("ru").includes(query))).sort((a, b) => Number(Boolean(b.curated)) - Number(Boolean(a.curated)));
}
function hashCollection() {
  try { return new URLSearchParams(location.hash.slice(1)).get("set") || ""; } catch { return ""; }
}
function navigateSet(id) {
  const next = id ? "#set=" + encodeURIComponent(id) : "#";
  if (location.hash === next || (!id && !location.hash)) applyLocation();
  else location.hash = next;
}
function applyLocation() {
  const id = hashCollection();
  $("#collection").value = collectionInfo(id) ? id : "";
  $("#search").value = "";
  render();
  if (collectionInfo()) $("#set-title").focus();
  else $('#tabs button[aria-pressed="true"]')?.focus();
}
function renderSets() {
  const current = collectionInfo();
  $("#set-detail").hidden = !current;
  $("#detail-controls").hidden = !current;
  $("#cards").hidden = !current;
  $("#set-cards").hidden = Boolean(current);
  $("#collection-note").hidden = !current;
  $("#set-cards").replaceChildren();
  if (current) {
    const items = setRecords(current), photos = items.filter((item) => !isVideo(item));
    $("#set-title").textContent = current.title;
    $("#set-description").textContent = [categoryNames[setCategory(current)], current.archived ? "Архив" : "", current.description].filter(Boolean).join(" · ");
    $("#export-set-sheet").textContent = photos.length === 8 ? "Скачать лист · 4 × 2" : "Скачать лист · 4 колонки · " + photos.length + " фото";
    $("#export-set-sheet").disabled = busy || !photos.length || photos.length > limit;
    $("#export-set-zip").disabled = busy || !items.length || items.length > limit;
    $("#set-export-note").textContent = "Только этот набор. " + photos.length + " фото" + (items.length > photos.length ? " и " + (items.length - photos.length) + " видео (только ZIP)" : "") + ". Пустые места не добавляются в PNG. Статусы оригиналов сохраняются." + (items.length > limit ? " Для экспорта выберите до 16 оригиналов в конструкторе." : "");
    return;
  }
  for (const collection of visibleSets()) {
    const items = setRecords(collection), cover = items.find((item) => !isVideo(item)), total = collection.category === "lora" ? items.length : (collection.slots || []).length;
    const card = node("article", undefined, "card set-card");
    const link = node("a", undefined, "set-link");
    link.href = "#set=" + encodeURIComponent(collection.id);
    const picture = node("div", undefined, "set-cover");
    if (cover) { const img = node("img"); img.src = mediaURL(cover, "thumb"); img.alt = ""; img.loading = "lazy"; picture.append(img); }
    else picture.append(node("span", collection.category === "lora" ? "Фото / видео" : "Пустой набор"));
    const body = node("div", undefined, "body");
    body.append(node("div", categoryNames[setCategory(collection)] || collection.category, "eyebrow"), node("h3", collection.title), node("p", collection.category === "lora" ? items.length + " оригиналов" : "Заполнено " + items.length + " / " + total + " ракурсов", "set-count"));
    if (collection.description) body.append(node("p", collection.description, "hint"));
    if (collection.curated) body.append(node("span", "Основной набор", "badge working"));
    if (collection.archived) body.append(node("span", "Архив", "badge working"));
    const candidates = items.filter((item) => item.status === "candidate").length;
    if (candidates) body.append(node("span", "Кандидаты · " + candidates, "badge candidate"));
    body.append(node("span", "Открыть набор →", "set-open"));
    link.append(picture, body); card.append(link); $("#set-cards").append(card);
  }
}
function angle(item) {
  const value = item.angle_degrees ?? item.angle;
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : item.collection === "head360" && /^H\d{3}$/.test(item.id)
      ? Number(item.id.slice(1))
      : null;
}
function byAngle(a, b) {
  return (
    (angle(a) ?? Infinity) - (angle(b) ?? Infinity) ||
    a.id.localeCompare(b.id, undefined, { numeric: true })
  );
}
function record(id) {
  return catalog.records.find((item) => item.id === id);
}
function collectionInfo(id = $("#collection").value) {
  return (catalog.collections || []).find((item) => item.id === id);
}
function collectionReadOnly(collection) {
  return Boolean(catalog.read_only || collection.read_only);
}
function slotTitle(collection, slot) {
  if (!collection.read_only && ["face", "body"].includes(collection.category) && /^\d+°$/.test(slot.title) && Number.isInteger(slot.angle_degrees / 45))
    return slotLabels[collection.category][slot.angle_degrees / 45] || slot.title;
  const defaults = {front: "Спереди", back: "Сзади", side: "Сбоку", detail: "Деталь", right: "Справа", left: "Слева"};
  if (!collection.read_only && slot.title === slot.id.charAt(0).toUpperCase() + slot.id.slice(1) && defaults[slot.id])
    return defaults[slot.id] + (collection.category === "scene" ? " · " + slot.angle_degrees + "°" : "");
  return slot.title;
}
function mediaURL(item, type) {
  return (
    item[type + "_url"] ||
    "/references/" +
      { image: "image", thumb: "thumb", download: "file" }[type] +
      "/" +
      encodeURIComponent(item.id)
  );
}
function visibleRecords() {
  const query = $("#search").value.trim().toLocaleLowerCase("ru");
  const current = collectionInfo();
  if (!current) return [];
  return setRecords(current).filter((item) => !query || [item.id, item.title, ...(item.tags || [])].join(" ").toLocaleLowerCase("ru").includes(query));
}
function resetExport() {
  if (exportURL) URL.revokeObjectURL(exportURL);
  exportURL = null;
  $("#export-preview").hidden = true;
  $("#download-sheet").hidden = true;
  $("#sheet-preview").hidden = false;
}
function saveSelection() {
  try {
    localStorage.setItem(
      "alice-reference-library-selection-v1",
      JSON.stringify(selected),
    );
  } catch {}
}
function changeSelection(next, text) {
  if (busy) return;
  selected = next;
  saveSelection();
  resetExport();
  renderCards();
  renderSelection();
  if (text) message(text);
}
function toggle(item) {
  if (selected.includes(item.id))
    changeSelection(selected.filter((id) => id !== item.id));
  else if (selected.length === limit)
    message(
      "Можно выбрать до 16 оригиналов. Уберите один из выбранных.",
      true,
    );
  else changeSelection([...selected, item.id]);
}
function showPreview(item) {
  $("#preview").dataset.referenceId = item.id;
  $("#preview-playback-error").hidden = true;
  $("#preview-video").onerror = () => { $("#preview-playback-error").hidden = false; };
  $("#preview-image").hidden = isVideo(item);
  $("#preview-video").hidden = !isVideo(item);
  if (isVideo(item)) $("#preview-video").src = item.video_url || mediaURL(item, "image");
  else $("#preview-image").src = mediaURL(item, "image");
  $("#preview-image").alt = item.title || item.id;
  $("#preview-title").textContent = item.id + " · " + (item.title || "");
  $("#preview-meta").textContent = [
    statusNames[item.status] || item.status,
    (item.size || []).join(" × "),
    ...(item.tags || []),
    angle(item) !== null ? "Целевой угол " + angle(item) + "°" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  $("#original").href = mediaURL(item, "download");
  $("#preview").showModal();
}
function renderTabs() {
  $("#tabs").replaceChildren();
  for (const [key, label] of Object.entries(categoryNames)) {
    const count = (catalog.collections || []).filter((item) => (!item.archived || $("#archived").checked) && (key === "all" || setCategory(item) === key)).length;
    const value = button(label + " · " + count, () => { tab = key; $("#search").value = ""; navigateSet(""); render(); });
    value.setAttribute("aria-pressed", String(tab === key));
    $("#tabs").append(value);
  }
}
function renderCards() {
  renderSets();
  const items = visibleRecords();
  const current = collectionInfo();
  const query = $("#search").value.trim().toLocaleLowerCase("ru");
  const matchesSlot = (collection, slot) => !query || [collection.title, slot.title, slot.angle_degrees].join(" ").toLocaleLowerCase("ru").includes(query);
  let entries = items;
  if (current?.category === "lora") {
    const shown = new Map(items.map((item) => [item.id, item]));
    entries = memberIds(current).map((id) => shown.get(id)).filter(Boolean);
  } else if (current) {
    const shown = new Set(items.map((item) => item.id));
    entries = (current.slots || []).flatMap((slot) => slot.reference_id
      ? (shown.has(slot.reference_id) ? [{...record(slot.reference_id), librarySlot: slot, libraryCollection: current}] : [])
      : (matchesSlot(current, slot) ? [{emptySlot: slot, libraryCollection: current}] : []));
  }
  $("#cards").replaceChildren();
  $("#empty").hidden = current ? entries.length > 0 : visibleSets().length > 0;
  $("#empty").textContent = current ? "В наборе пока нет оригиналов по этому запросу." : "Наборы не найдены. Измените фильтры или создайте новый набор.";
  for (const control of document.querySelectorAll("[data-create-category]")) control.disabled = busy || creating || uploading || Boolean(catalog.read_only);
  for (const item of entries) {
    if (item.emptySlot) {
      $("#cards").append(emptySlotCard(item.libraryCollection, item.emptySlot));
      continue;
    }
    const chosen = selected.includes(item.id);
    const card = node(
      "article",
      undefined,
      "card" + (chosen ? " selected" : ""),
    );
    const picture = button(
      "",
      () => showPreview(item),
      "Посмотреть " + item.id,
    );
    picture.className = "picture";
    const image = node(isVideo(item) ? "video" : "img");
    image.src = isVideo(item) ? (item.video_url || mediaURL(item, "image")) : mediaURL(item, "thumb");
    if (isVideo(item)) { image.muted = true; image.preload = "metadata"; image.playsInline = true; }
    else { image.alt = item.title || item.id; image.loading = "lazy"; }
    picture.append(image, node("span", item.id, "card-id"));
    if (isVideo(item)) picture.append(node("span", "▶ Видео", "media-kind"));
    const body = node("div", undefined, "body");
    body.append(
      node("h3", item.librarySlot ? slotTitle(item.libraryCollection, item.librarySlot) : item.title || item.id),
      node("div", (item.tags || []).join(" · "), "tags"),
      node(
        "span",
        statusNames[item.status] || item.status || "Без статуса",
        "badge " + item.status,
      ),
    );
    if (item.parent_review?.note)
      body.append(node("p", item.parent_review.note, "review-note"));
    const choose = button(
      chosen
        ? (isVideo(item) ? "✓ В ZIP · " : "✓ В листе · ") + (selected.indexOf(item.id) + 1)
        : isVideo(item) ? "Добавить в ZIP" : "Добавить в лист",
      () => toggle(item),
      (chosen ? "Убрать " : "Добавить ") +
        item.id +
        " " +
        (chosen ? "из листа" : "в лист"),
    );
    choose.className = "choose";
    choose.disabled = busy;
    choose.setAttribute("aria-pressed", String(chosen));
    const download = node("a", "Скачать оригинал", "original-link");
    download.href = mediaURL(item, "download");
    download.download = "";
    body.append(choose, download);
    const collection = item.libraryCollection || collectionInfo(item.collection_id || item.collection);
    const slot = item.librarySlot || collection?.slots?.find((value) => value.reference_id === item.id);
    if (collection && !collectionReadOnly(collection)) {
      const mutations = node("div", undefined, "reference-mutations");
      const replace = button("Заменить", () => openUpload(collection, slot, null, item), "Заменить оригинал: " + (item.original_name || item.title || item.id));
      replace.className = "replace-reference";
      replace.disabled = busy || uploading || removing;
      const remove = button("Удалить", () => openRemove(item, collection), "Удалить оригинал: " + (item.original_name || item.title || item.id));
      remove.className = "remove-reference";
      remove.disabled = busy || uploading || removing;
      if (slot || (collection.category === "lora" && memberIds(collection).includes(item.id))) mutations.append(replace);
      mutations.append(remove);
      body.append(mutations);
    }
    card.append(picture, body);
    $("#cards").append(card);
  }
  renderCollectionNote();
}
function collectionRecords() {
  const collection = $("#collection").value;
  const info = collectionInfo(collection);
  if (info) return memberIds(info).map(record).filter(Boolean);
  return (
    collection
      ? catalog.records.filter((item) => item.collection === collection)
      : visibleRecords()
  )
    .slice()
    .sort(byAngle);
}
function renderCollectionNote() {
  const items = collectionRecords();
  const info = collectionInfo();
  const append = $("#append-lora");
  append.hidden = !(info?.category === "lora" && !collectionReadOnly(info));
  append.disabled = busy || uploading;
  if (info?.category === "lora") {
    $("#collection-note").textContent = items.length + " оригиналов. Для добавления выберите или создайте набор LoRA. Фото и видео сохраняются для будущего датасета; обучение не запускается. Видео доступны для просмотра и ZIP, но не входят в PNG.";
    $("#select-collection").disabled = busy || !items.length;
    return;
  }
  if (info && !collectionReadOnly(info)) {
    const slots = info.slots || [], missing = slots.filter((slot) => !slot.reference_id);
    $("#collection-note").textContent = "Заполнено " + (slots.length - missing.length) + " из " + slots.length + " ракурсов. " +
      (missing.length ? "Можно добавить сейчас или позже: " + missing.map((slot) => slotTitle(info, slot)).join(", ") + "." : "Все места заполнены. Можно собрать лист или заменить отдельный кадр.");
    $("#select-collection").disabled = busy || items.length === 0;
    return;
  }
  let text = items.length + " фотографий в наборе.";
  const angles = items.map(angle).filter((value) => value !== null);
  if (angles.length) {
    const missing = [0, 45, 90, 135, 180, 225, 270, 315].filter(
      (value) => !angles.includes(value),
    );
    text += " Углы номинальные.";
    if (missing.length)
      text +=
        " Нет ракурсов: " +
        missing.map((value) => value + "°").join(", ") +
        ".";
    else text += " Есть все 8 целевых углов с шагом 45°.";
  }
  $("#collection-note").textContent = text;
  $("#select-collection").disabled = busy || items.length === 0;
}
function render() {
  renderTabs();
  renderCards();
  $("#section-note").textContent = collectionInfo() ? "Выберите отдельные оригиналы или скачайте весь набор. Выбор не меняет статус кандидата." : "Наборы фигуры с причёсками, головы и образов. Откройте набор, чтобы увидеть ракурсы.";
  $("#missing").replaceChildren();
  $("#missing").hidden = true;
  renderSelection();
}
function move(id, offset) {
  const index = selected.indexOf(id),
    other = index + offset;
  if (other < 0 || other >= selected.length) return;
  const next = selected.slice();
  [next[index], next[other]] = [next[other], next[index]];
  changeSelection(next);
  message(
    "Положение " + id + ": " + (other + 1) + " из " + selected.length + ".",
  );
  $("#selection")
    .querySelector(
      '[data-id="' +
        CSS.escape(id) +
        '"] .move-' +
        (offset < 0 ? "up" : "down"),
    )
    ?.focus();
}
function settings() {
  return {
    ids: selected.filter((id) => !isVideo(record(id))),
    columns: Number($("#columns").value),
    cell_width: Number($("#cell-width").value),
    cell_height: Number($("#cell-height").value),
    labels: $("#labels").checked,
  };
}
function sheetDimensions(value) {
  return [value.columns * value.cell_width, Math.ceil(value.ids.length / value.columns) * (value.cell_height + (value.labels ? 28 : 0))];
}
function settingsError(value) {
  if (!value.ids.length) return selected.length ? "Видео не входят в PNG. Добавьте фотографию или скачайте оригиналы в ZIP." : "Выберите фотографии для листа.";
  if (
    ![value.cell_width, value.cell_height].every(
      (size) => Number.isInteger(size) && size >= 128 && size <= 2048,
    )
  )
    return "Размер каждой стороны ячейки — целое число от 128 до 2048 px.";
  const [width, height] = sheetDimensions(value);
  if (width > 16384 || height > 16384 || width * height > 64000000)
    return "Лист превышает 64 мегапикселя или 16384 px по стороне. Уменьшите ячейку или измените колонки.";
  return "";
}
function renderSelection() {
  $("#selection").replaceChildren();
  $("#selection-count").textContent = selected.length + " / " + limit;
  $("#builder-count").textContent = "· " + selected.length;
  $("#selection-link").textContent = "Конструктор листа · " + selected.length;
  $("#selection-empty").hidden = selected.length > 0;
  selected.forEach((id, index) => {
    const item = record(id);
    if (!item) return;
    const row = node("li");
    row.dataset.id = id;
    const image = node(isVideo(item) ? "span" : "img");
    if (isVideo(item)) { image.textContent = "▶"; image.className = "video-icon"; }
    else { image.src = mediaURL(item, "thumb"); image.alt = ""; }
    const text = node("div");
    text.append(
      node("strong", index + 1 + ". " + id),
      node("small", item.title || ""),
    );
    const controls = node("div", undefined, "order-controls");
    for (const [offset, label] of [
      [-1, "↑"],
      [1, "↓"],
    ]) {
      const value = button(
        label,
        () => move(id, offset),
        (offset < 0 ? "Переместить выше " : "Переместить ниже ") + id,
      );
      value.className = offset < 0 ? "move-up" : "move-down";
      value.disabled = offset < 0 ? index === 0 : index === selected.length - 1;
      controls.append(value);
    }
    controls.append(
      button(
        "×",
        () => changeSelection(selected.filter((value) => value !== id)),
        "Убрать " + id + " из выбранных",
      ),
    );
    row.append(image, text, controls);
    $("#selection").append(row);
  });
  $("#clear-selection").disabled = busy || selected.length === 0;
  $("#download-zip").hidden = !(
    catalog.supports_zip || catalog.export_formats?.includes("zip")
  );
  $("#download-zip").disabled = busy || selected.length === 0;
  renderSheet();
}
function renderSheet() {
  for (const id of ["columns", "cell-width", "cell-height", "labels"])
    $("#" + id).disabled = busy;
  const value = settings(),
    error = settingsError(value);
  $("#sheet-preview").replaceChildren();
  $("#sheet-preview").style.setProperty("--columns", value.columns);
  $("#sheet-preview").style.setProperty(
    "--cell-ratio",
    value.cell_width + "/" + (value.cell_height + (value.labels ? 28 : 0)),
  );
  value.ids.forEach((id) => {
    const item = record(id);
    if (!item) return;
    const cell = node("div", undefined, "sheet-cell");
    const image = node("img");
    image.src = mediaURL(item, "thumb");
    image.alt = item.id;
    cell.append(image);
    if (value.labels) cell.append(node("small", item.id));
    $("#sheet-preview").append(cell);
  });
  $("#build-sheet").disabled = busy || Boolean(error);
  $("#preview-note").textContent =
    error ||
    (exportURL
      ? "Готовый PNG · " + value.ids.length + " фотографий."
      : "Предпросмотр расположения · " +
        sheetDimensions(value)[0] +
        " × " +
        sheetDimensions(value)[1] +
        " px." + (selected.some((id) => isVideo(record(id))) ? " Видео исключены из PNG; ZIP сохранит все выбранные оригиналы." : ""));
}
function emptySlotCard(collection, slot) {
  const card = node("article", undefined, "card empty-slot");
  card.dataset.collectionId = collection.id;
  card.dataset.slotId = slot.id;
  const picture = node("div", undefined, "slot-placeholder");
  picture.append(node("span", "＋", "slot-symbol"), node("strong", slotTitle(collection, slot)));
  if (typeof slot.angle_degrees === "number") picture.append(node("small", "Целевой угол " + slot.angle_degrees + "°"));
  const body = node("div", undefined, "body");
  body.append(node("h3", collection.title), node("p", "Фотография пока не добавлена", "hint"));
  if (!collectionReadOnly(collection)) {
    const upload = button("Загрузить фото", () => openUpload(collection, slot), "Загрузить фото: " + collection.title + " · " + slotTitle(collection, slot));
    upload.className = "choose";
    upload.disabled = busy || uploading;
    body.append(upload, node("p", "Или перетащите сюда один файл", "drop-hint"));
    card.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!busy && !uploading) card.classList.add("drag-over");
    });
    card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
    card.addEventListener("drop", (event) => {
      event.preventDefault();
      card.classList.remove("drag-over");
      if (busy || uploading) return;
      const files = event.dataTransfer.files;
      if (files.length !== 1) return message("На каждый ракурс загрузите одну фотографию.", true);
      openUpload(collection, slot, files[0]);
    });
  } else body.append(node("p", catalog.read_only ? "Режим просмотра: загрузка в этой копии отключена." : "Исходный набор. Для своих кадров создайте новый набор.", "hint"));
  card.append(picture, body);
  return card;
}
function formMessage(id, text, error = false) {
  $(id).textContent = text;
  $(id).classList.toggle("error", error);
}
function renderSlotPlan() {
  const lora = $("#create-category").value === "lora";
  $("#create-slot-plan").hidden = lora;
  $("#create-hint").textContent = lora ? "Свободный набор фотографий и видео для будущего датасета. Добавляйте оригиналы в любом порядке, без обязательных ракурсов." : "Создадим пустые места для фотографий. Их можно заполнить сейчас или вернуться позже.";
  $("#create-slots").replaceChildren();
  for (const label of slotLabels[$("#create-category").value] || []) $("#create-slots").append(node("span", label));
}
function openCreate(category) {
  if (busy || uploading || creating || catalog.read_only) return;
  $("#create-category").value = category;
  $("#create-name").value = "";
  $("#create-name").placeholder = {face: "Алиса · короткое каре", body: "Алиса · базовая фигура", outfit: "Чёрный комбинезон", scene: "Пальмовая аллея · закат", lora: "Алиса · отбор для LoRA"}[category];
  formMessage("#create-message", "");
  renderSlotPlan();
  $("#create-collection").showModal();
  $("#create-name").focus();
}
function clearUploadPreview() {
  if (uploadPreviewURL) URL.revokeObjectURL(uploadPreviewURL);
  uploadPreviewURL = null;
  $("#upload-preview").hidden = true;
  $("#upload-preview").removeAttribute("src");
  $("#upload-video-preview").pause();
  $("#upload-video-preview").removeAttribute("src");
  $("#upload-video-preview").load();
  $("#upload-video-preview").hidden = true;
}
function setUploadFiles(files) {
  clearUploadPreview();
  const lora = uploadTarget?.collection.category === "lora";
  uploadFiles = Array.from(files || []);
  uploadFile = uploadFiles[0] || null;
  uploadResults = uploadFiles.map(() => "Ожидает загрузки");
  let error = "";
  if ((!lora || uploadTarget?.replacement) && uploadFiles.length !== 1) error = "Для одного ракурса или замены выберите один файл.";
  if (uploadFiles.length > 32) error = "За один раз можно загрузить до 32 оригиналов.";
  for (const file of uploadFiles) {
    const video = ["video/mp4", "video/webm", "video/quicktime"].includes(file.type);
    const maximum = video ? (catalog.limits?.max_video_upload_bytes || 100 * 1024 * 1024) : (catalog.limits?.max_upload_bytes || 40 * 1024 * 1024);
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) && !(lora && video)) error = "Допустимы PNG, JPEG, WebP" + (lora ? ", MP4, WebM и MOV." : ".");
    if (!file.size || file.size > maximum) error = "Файл «" + file.name + "» пустой или превышает лимит " + Math.floor(maximum / 1024 / 1024) + " МБ.";
  }
  renderUploadFiles();
  $("#submit-upload").disabled = !uploadFiles.length || Boolean(error);
  if (error) { uploadFiles = []; uploadFile = null; return formMessage("#upload-message", error, true); }
  if (uploadFile) {
    uploadPreviewURL = URL.createObjectURL(uploadFile);
    const preview = uploadFile.type.startsWith("video/") ? $("#upload-video-preview") : $("#upload-preview");
    preview.src = uploadPreviewURL;
    preview.hidden = false;
  }
  formMessage("#upload-message", uploadFiles.length + " файлов готово к загрузке.");
}
function renderUploadFiles() {
  $("#upload-files").replaceChildren();
  uploadFiles.forEach((file, index) => $("#upload-files").append(node("li", file.name + " · " + (uploadResults[index] || ""))));
}
function setUploadFile(file) { setUploadFiles(file ? [file] : []); }
function openUpload(collection, slot = null, file = null, replacement = null) {
  if (busy || uploading || removing || collectionReadOnly(collection)) return;
  const lora = collection.category === "lora";
  replacement = replacement || (slot?.reference_id ? record(slot.reference_id) : null);
  uploadTarget = {collection, slot, replacement};
  uploadFile = null;
  uploadFiles = []; uploadResults = [];
  clearUploadPreview(); renderUploadFiles();
  $("#upload-input").value = "";
  $("#upload-input").multiple = lora && !replacement;
  $("#upload-input").accept = "image/png,image/jpeg,image/webp" + (lora ? ",video/mp4,video/webm,video/quicktime,.mov" : "");
  $("#upload-formats").textContent = lora ? "Фото PNG / JPEG / WebP до 40 МБ; видео MP4 / WebM / MOV до 100 МБ. " + (replacement ? "Один файл для замены." : "Можно несколько файлов.") : "PNG, JPEG или WebP · до 40 МБ";
  $("#upload-title").textContent = replacement ? "Заменить оригинал" : lora ? "Фото и видео для LoRA" : slotTitle(collection, slot);
  $("#upload-target").textContent = collection.title + (replacement ? " · замена «" + (replacement.original_name || replacement.title || replacement.id) + "» на том же месте. Прежний файл будет скрыт из библиотеки и экспорта." : lora ? " · оригиналы добавятся в конец набора" : " · пустой ракурс");
  $("#submit-upload").textContent = replacement ? "Заменить этим файлом" : lora ? "Добавить оригиналы" : "Сохранить в этот ракурс";
  $("#upload-progress").hidden = true;
  $("#upload-progress").value = 0;
  $("#submit-upload").disabled = true;
  formMessage("#upload-message", "");
  $("#upload-reference").showModal();
  if (file) setUploadFile(file);
}
function openRemove(item, collection) {
  if (busy || uploading || removing || collectionReadOnly(collection)) return;
  removeTarget = {item, collection};
  $("#remove-name").textContent = item.original_name || item.title || item.id;
  $("#remove-id").textContent = collection.title + " · " + item.id;
  formMessage("#remove-message", "");
  $("#remove-reference").showModal();
  $("#cancel-remove").focus();
}
$("#cancel-remove").onclick = () => $("#remove-reference").close();
$("#remove-reference").addEventListener("cancel", (event) => { if (removing) event.preventDefault(); });
$("#remove-reference-form").onsubmit = async (event) => {
  event.preventDefault();
  if (!removeTarget || removing || busy || uploading || collectionReadOnly(removeTarget.collection)) return;
  removing = true;
  $("#confirm-remove").disabled = true;
  $("#cancel-remove").disabled = true;
  formMessage("#remove-message", "Убираю оригинал из библиотеки…");
  try {
    await response("remove", {id: removeTarget.item.id});
    if ($("#preview").dataset.referenceId === removeTarget.item.id) $("#preview").close();
    selected = selected.filter((id) => id !== removeTarget.item.id);
    saveSelection(); resetExport();
    const loaded = await load({collectionId: removeTarget.collection.id});
    $("#remove-reference").close();
    message(loaded ? "Оригинал удалён из библиотеки, выбранных и экспорта. Его место можно заполнить заново." : "Оригинал удалён, но каталог не обновился. Нажмите «Обновить».", !loaded);
  } catch (error) {
    formMessage("#remove-message", "Не удалось удалить: " + error.message + ". Можно повторить.", true);
  } finally {
    removing = false;
    $("#confirm-remove").disabled = false;
    $("#cancel-remove").disabled = false;
    renderCards(); renderSelection();
  }
};
function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(Error("Не удалось прочитать выбранный файл."));
    reader.readAsDataURL(file);
  });
}
function uploadRequest(payload) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/references/api/uploads");
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.timeout = 120000;
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percentage = Math.round(event.loaded / event.total * 100);
      $("#upload-progress").value = Math.min(95, percentage);
      formMessage("#upload-message", percentage < 100 ? "Отправка файла · " + percentage + "%" : "Проверяю и сохраняю оригинал…");
    };
    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { return reject(Object.assign(Error("Сервер вернул неверный ответ. Обновите набор и проверьте оригинал перед повтором."), {uncertain: true})); }
      if (xhr.status === 401) {
        location.assign("/login?next=" + encodeURIComponent(location.pathname));
        return reject(Error("Требуется вход."));
      }
      if (xhr.status < 200 || xhr.status >= 300) return reject(Error(data.error?.message || data.error || "Загрузка не удалась: " + xhr.status));
      resolve(data);
    };
    xhr.onerror = () => reject(Object.assign(Error("Нет связи с сервером. Файл не удалось подтвердить; обновите набор перед повторной загрузкой."), {uncertain: true}));
    xhr.ontimeout = () => reject(Object.assign(Error("Сервер долго не отвечает. Обновите набор, чтобы проверить, сохранился ли файл."), {uncertain: true}));
    xhr.send(JSON.stringify(payload));
  });
}
async function response(path, payload) {
  const result = await fetch(
    "/references/api/" + path,
    payload
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      : {},
  );
  if (result.status === 401) {
    location.assign("/login?next=" + encodeURIComponent(location.pathname));
    throw Error("Требуется вход");
  }
  if (!result.ok) {
    const error = await result.json().catch(() => ({}));
    throw Error(
      error.error?.message || error.error || "Ошибка запроса: " + result.status,
    );
  }
  return result;
}
async function load(options = {}) {
  $("#refresh-library").disabled = true;
  $("#library-status").textContent = "Загружаю наборы…";
  try {
    const result = await (await response("catalog")).json();
    if (!Array.isArray(result.records))
      throw Error("Неверный формат библиотеки");
    catalog = result;
    $(".purpose").textContent = catalog.read_only ? "Режим просмотра · загрузка в этой копии отключена. Выбор и экспорт доступны." : "Загрузка, выбор и экспорт · без запуска генерации. Оригиналы сохраняются.";
    const retained = selected.filter((id) => record(id));
    if (retained.length !== selected.length) {
      selected = retained;
      resetExport();
      saveSelection();
      message("Недоступные фотографии исключены из выбора.");
    }
    const current = typeof options.collectionId === "string" ? options.collectionId : $("#collection").value || hashCollection();
    $("#collection").replaceChildren(new Option("Текущий раздел", ""));
    const metadata = new Map((catalog.collections || []).map((item) => [item.id, item]));
    const covered = new Set((catalog.collections || []).flatMap((item) => memberIds(item)).filter(Boolean));
    [
      ...new Set(
        [...metadata.keys(), ...catalog.records.filter((item) => !covered.has(item.id)).map((item) => item.collection)].filter(Boolean),
      ),
    ].forEach((collection) =>
      $("#collection").append(
        new Option(metadata.get(collection)?.title || categoryNames[collection] || collection, collection),
      ),
    );
    if (
      [...$("#collection").options].some((option) => option.value === current)
    )
      $("#collection").value = current;
    $("#summary").replaceChildren();
    const activeSets = (catalog.collections || []).filter((item) => !item.archived);
    const activeIds = new Set(activeSets.flatMap(memberIds).filter(Boolean));
    for (const [count, label] of [
      [activeSets.length, "активных наборов"],
      [activeIds.size, "оригиналов в наборах"],
      [(catalog.collections || []).filter((item) => item.archived).length, "наборов в архиве"],
    ]) {
      const value = node("span");
      value.append(node("b", String(count)), document.createTextNode(label));
      $("#summary").append(value);
    }
    if (typeof options.collectionId === "string" && hashCollection() !== options.collectionId) history.pushState(null, "", "#set=" + encodeURIComponent(options.collectionId));
    $("#library-status").textContent = hashCollection() && !collectionInfo(hashCollection()) ? "Набор недоступен. Выберите другой набор или обновите библиотеку." : "";
    render();
    return true;
  } catch (error) {
    $("#library-status").textContent = "Не удалось загрузить наборы: " + error.message + ". Нажмите «Обновить».";
    message("Не удалось загрузить библиотеку: " + error.message, true);
    return false;
  } finally {
    $("#refresh-library").disabled = false;
  }
}
$("#refresh-library").onclick = load;
for (const control of document.querySelectorAll("[data-create-category]")) control.onclick = () => openCreate(control.dataset.createCategory);
$("#create-category").onchange = renderSlotPlan;
$("#close-create").onclick = () => $("#create-collection").close();
$("#create-collection").addEventListener("cancel", (event) => { if (creating) event.preventDefault(); });
$("#create-collection-form").onsubmit = async (event) => {
  event.preventDefault();
  if (catalog.read_only) return formMessage("#create-message", "Создание наборов в этой копии отключено.", true);
  if (creating || !$("#create-name").value.trim()) return;
  creating = true;
  $("#submit-create").disabled = true;
  $("#close-create").disabled = true;
  formMessage("#create-message", "Создаю пустые места для ракурсов…");
  try {
    const category = $("#create-category").value;
    const payload = {title: $("#create-name").value.trim(), category};
    if (category === "outfit") payload.slots = slotLabels.outfit.map((title, index) => ({id: "a" + String(index * 45).padStart(3, "0"), title, angle_degrees: index * 45}));
    const data = await (await response("collections", payload)).json();
    const collection = data.collection || data;
    if (!collection.id) throw Error("Набор создан, но сервер не вернул его ID. Обновите библиотеку.");
    tab = collection.category;
    $("#search").value = "";
    const loaded = await load({collectionId: collection.id});
    $("#create-collection").close();
    if (loaded) message("Набор «" + collection.title + "» создан. " + (collection.category === "lora" ? "Добавьте фотографии и видео." : "Выберите ракурс и загрузите фотографию."));
  } catch (error) { formMessage("#create-message", error.message, true); }
  finally {
    creating = false;
    $("#submit-create").disabled = false;
    $("#close-create").disabled = false;
    renderCards();
  }
};
$("#upload-input").onchange = () => setUploadFiles($("#upload-input").files);
$("#append-lora").onclick = () => { const collection = collectionInfo(); if (collection?.category === "lora") openUpload(collection); };
$("#preview").addEventListener("close", () => { $("#preview-video").pause(); $("#preview-video").removeAttribute("src"); $("#preview-video").load(); });
$("#close-upload").onclick = () => $("#upload-reference").close();
$("#upload-reference").addEventListener("cancel", (event) => { if (uploading) event.preventDefault(); });
$("#upload-reference").addEventListener("close", clearUploadPreview);
$("#upload-reference-form").onsubmit = async (event) => {
  event.preventDefault();
  if (catalog.read_only) return formMessage("#upload-message", "Загрузка в этой копии отключена.", true);
  if (uploading || !uploadFile || !uploadTarget || collectionReadOnly(uploadTarget.collection)) return;
  uploading = true;
  $("#submit-upload").disabled = true;
  $("#upload-input").disabled = true;
  $("#close-upload").disabled = true;
  $("#upload-progress").hidden = false;
  formMessage("#upload-message", "Подготавливаю фотографию…");
  let failed = false;
  try {
    for (let index = 0; index < uploadFiles.length; index++) {
      if (uploadResults[index] === "Сохранён") continue;
      const file = uploadFiles[index];
      uploadResults[index] = "Загружается…"; renderUploadFiles();
      try {
        const data = await readFile(file);
        const payload = {collection_id: uploadTarget.collection.id, name: file.name, mime: file.type, data};
        if (uploadTarget.slot) payload.slot_id = uploadTarget.slot.id;
        if (uploadTarget.replacement) payload.replace_id = uploadTarget.replacement.id;
        const uploaded = await uploadRequest(payload);
        if (uploadTarget.replacement && uploaded.record?.id) {
          selected = selected.map((id) => id === uploadTarget.replacement.id ? uploaded.record.id : id);
          saveSelection();
        }
        resetExport();
        if (uploadTarget.replacement && $("#preview").dataset.referenceId === uploadTarget.replacement.id) $("#preview").close();
        uploadResults[index] = "Сохранён";
      } catch (error) {
        if (error.uncertain) uploadFile = null;
        uploadResults[index] = error.message; failed = true;
      }
      renderUploadFiles();
      if (failed) break;
    }
    $("#upload-progress").value = 100;
    tab = uploadTarget.collection.category;
    $("#search").value = "";
    const loaded = await load({collectionId: uploadTarget.collection.id});
    if (failed) formMessage("#upload-message", "Сохранено: " + uploadResults.filter((status) => status === "Сохранён").length + ". Проверьте ошибку у файла. " + (uploadFile ? "Повторная отправка пропустит сохранённые оригиналы." : "Статус отправки не подтверждён. Закройте окно и проверьте обновлённый набор перед повтором."), true);
    else if (loaded) { uploadFiles = []; uploadFile = null; $("#upload-reference").close(); message(uploadTarget.replacement ? "Оригинал заменён на том же месте в наборе. Прежний файл скрыт из библиотеки и экспорта." : "Оригиналы сохранены в набор «" + uploadTarget.collection.title + "»."); }
    else { uploadFile = null; formMessage("#upload-message", "Файлы сохранены, но каталог не обновился. Закройте окно и нажмите «Обновить».", true); }
  } finally {
    uploading = false;
    $("#upload-input").disabled = false;
    $("#close-upload").disabled = false;
    $("#submit-upload").disabled = !uploadFile;
    renderCards();
  }
};
$("#search").oninput = renderCards;
$("#archived").onchange = render;
$("#collection").onchange = () => navigateSet($("#collection").value);
$("#back-to-sets").onclick = (event) => { event.preventDefault(); tab = "all"; navigateSet(""); };
$("#selection-link").onclick = () => { $("#sheet-builder").open = true; $("#sheet-controls").focus(); $("#sheet-controls").scrollIntoView({block: "start"}); };
window.addEventListener("hashchange", applyLocation);
window.addEventListener("popstate", applyLocation);
async function exportSet(format) {
  const collection = collectionInfo();
  if (!collection || busy) return;
  const items = setRecords(collection).filter((item) => format === "zip" || !isVideo(item));
  if (!items.length || items.length > limit) return;
  busy = true; renderCards(); renderSelection();
  const status = $("#library-status"); status.textContent = "Готовлю файл набора…";
  try {
    const payload = {ids: items.map((item) => item.id)};
    if (format !== "zip") Object.assign(payload, {columns: 4, cell_width: 512, cell_height: 768, labels: false});
    const result = await response(format === "zip" ? "zip" : "export", payload);
    if (!result.headers.get("content-type")?.includes(format === "zip" ? "application/zip" : "image/png")) throw Error("Сервер вернул неверный формат файла");
    const url = URL.createObjectURL(await result.blob()), link = node("a");
    link.href = url; link.download = collection.id + (format === "zip" ? "-originals.zip" : "-4-columns.png");
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = "Файл набора готов и передан браузеру для скачивания.";
  } catch (error) { status.textContent = "Не удалось скачать набор: " + error.message + ". Повторите попытку."; }
  finally { busy = false; renderCards(); renderSelection(); }
}
$("#export-set-sheet").onclick = () => exportSet("png");
$("#export-set-zip").onclick = () => exportSet("zip");
$("#select-collection").onclick = () => {
  const items = collectionRecords();
  if (items.length > limit) {
    message(
      "В наборе " +
        items.length +
        " оригиналов. Выберите до 16 с помощью поиска или карточек.",
      true,
    );
    return;
  }
  changeSelection(
    items.map((item) => item.id),
    "Выбран набор: " + items.length + " оригиналов.",
  );
};
$("#clear-selection").onclick = () => changeSelection([], "Выбор очищен.");
for (const id of ["columns", "cell-width", "cell-height", "labels"])
  $("#" + id).oninput = () => {
    resetExport();
    renderSheet();
  };
$("#build-sheet").onclick = async () => {
  if (busy) return;
  const value = settings(),
    error = settingsError(value);
  if (error) {
    message(error, true);
    return;
  }
  busy = true;
  renderCards();
  renderSelection();
  message("Собираю лист из выбранных оригиналов…");
  try {
    const result = await response("export", value);
    if (!result.headers.get("content-type")?.includes("image/png"))
      throw Error("Сервер вернул неверный формат листа");
    resetExport();
    exportURL = URL.createObjectURL(await result.blob());
    $("#export-preview").src = exportURL;
    $("#export-preview").hidden = false;
    $("#sheet-preview").hidden = true;
    $("#download-sheet").href = exportURL;
    $("#download-sheet").hidden = false;
    message("PNG готов. Проверьте лист и скачайте файл.");
  } catch (error) {
    message(error.message, true);
  } finally {
    busy = false;
    renderCards();
    renderSelection();
  }
};
$("#download-zip").onclick = async () => {
  if (busy || !selected.length) return;
  busy = true;
  renderCards();
  renderSelection();
  message("Готовлю выбранные оригиналы…");
  try {
    const result = await response("zip", { ids: selected.slice() });
    if (!result.headers.get("content-type")?.includes("application/zip"))
      throw Error("Сервер вернул неверный формат архива");
    const url = URL.createObjectURL(await result.blob()),
      link = node("a");
    link.href = url;
    link.download = "alice-reference-originals.zip";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message("Архив оригиналов скачан.");
  } catch (error) {
    message(error.message, true);
  } finally {
    busy = false;
    renderCards();
    renderSelection();
  }
};
$("#close-preview").onclick = () => $("#preview").close();
$("#preview").onclick = (event) => {
  if (event.target === $("#preview")) $("#preview").close();
};
try {
  // Each fresh visit starts with all sets; the URL owns set navigation.
  const saved = JSON.parse(
    localStorage.getItem("alice-reference-library-selection-v1") || "[]",
  );
  if (Array.isArray(saved))
    selected = [...new Set(saved.filter((id) => typeof id === "string"))].slice(
      0,
      limit,
    );
} catch {}
window.addEventListener("beforeunload", () => {
  if (exportURL) URL.revokeObjectURL(exportURL);
  if (uploadPreviewURL) URL.revokeObjectURL(uploadPreviewURL);
});
void load();
