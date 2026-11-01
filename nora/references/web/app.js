"use strict";
const $ = (selector) => document.querySelector(selector);
const categoryNames = {
  face: "Лицо / причёска",
  body: "Фигура / поза",
  outfit: "Одежда",
  scene: "Локация",
  head360: "Голова 360°",
};
const statusNames = {
  accepted: "Отобран",
  candidate: "Кандидат",
  working: "Рабочий референс",
};
const limit = 16;
let catalog = { records: [], missing: {} },
  selected = [],
  tab = "face",
  busy = false,
  exportURL = null;
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
  $("#status").textContent = text;
  $("#status").classList.toggle("error", error);
}
function inTab(item) {
  return tab === "head360"
    ? item.collection === "head360"
    : item.category === tab && item.collection !== "head360";
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
  return catalog.records.filter(
    (item) =>
      inTab(item) &&
      (tab === "head360" ||
        $("#candidates").checked ||
        item.status !== "candidate") &&
      (!query ||
        [item.id, item.title, ...(item.tags || [])]
          .join(" ")
          .toLocaleLowerCase("ru")
          .includes(query)),
  );
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
      "В одном листе может быть до 16 фотографий. Уберите одну из выбранных.",
      true,
    );
  else changeSelection([...selected, item.id]);
}
function showPreview(item) {
  $("#preview-image").src = mediaURL(item, "image");
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
    const count = catalog.records.filter((item) =>
      key === "head360"
        ? item.collection === "head360"
        : item.category === key && item.collection !== "head360",
    ).length;
    const value = button(label + " · " + count, () => {
      tab = key;
      $("#search").value = "";
      $("#collection").value = "";
      render();
    });
    value.setAttribute("aria-pressed", String(tab === key));
    $("#tabs").append(value);
  }
}
function renderCards() {
  const items = visibleRecords();
  $("#cards").replaceChildren();
  $("#empty").hidden = items.length > 0;
  for (const item of items) {
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
    const image = node("img");
    image.src = mediaURL(item, "thumb");
    image.alt = item.title || item.id;
    image.loading = "lazy";
    picture.append(image, node("span", item.id, "card-id"));
    const body = node("div", undefined, "body");
    body.append(
      node("h3", item.title || item.id),
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
        ? "✓ В листе · " + (selected.indexOf(item.id) + 1)
        : "Добавить в лист",
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
    card.append(picture, body);
    $("#cards").append(card);
  }
  renderCollectionNote();
}
function collectionRecords() {
  const collection = $("#collection").value;
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
  const notes = {
    face: "Портреты и причёски. «Отобран» и «Кандидат» показаны отдельно; выбор не меняет статус.",
    body: "Отдельные фотографии фигуры и поз. В лист попадут оригиналы целиком.",
    head360:
      "Отдельные ракурсы головы с видимой шеей. Углы номинальные; сходство и симметрия требуют проверки.",
    outfit:
      "Референсы одежды. Невидимые детали в исходной фотографии требуют проверки.",
    scene:
      "Референсы локации. Восстановленные участки не являются подтверждённой геометрией.",
  };
  $("#section-note").textContent = notes[tab];
  $("#missing").replaceChildren();
  const missing = catalog.missing?.[tab] || [];
  $("#missing").hidden = !missing.length;
  if (missing.length) {
    $("#missing").append(
      node("h3", "Недостающие или требующие проверки ракурсы"),
    );
    const list = node("ul");
    missing.forEach((text) => list.append(node("li", text)));
    $("#missing").append(list);
  }
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
    ids: selected.slice(),
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
  if (!value.ids.length) return "Выберите фотографии для листа.";
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
  $("#selection-link").textContent = "К листу · " + selected.length;
  $("#selection-empty").hidden = selected.length > 0;
  selected.forEach((id, index) => {
    const item = record(id);
    if (!item) return;
    const row = node("li");
    row.dataset.id = id;
    const image = node("img");
    image.src = mediaURL(item, "thumb");
    image.alt = "";
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
  selected.forEach((id) => {
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
        " px.");
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
async function load() {
  $("#refresh-library").disabled = true;
  try {
    const result = await (await response("catalog")).json();
    if (!Array.isArray(result.records))
      throw Error("Неверный формат библиотеки");
    catalog = result;
    const retained = selected.filter((id) => record(id));
    if (retained.length !== selected.length) {
      selected = retained;
      resetExport();
      saveSelection();
      message("Недоступные фотографии исключены из выбора.");
    }
    const current = $("#collection").value;
    $("#collection").replaceChildren(new Option("Текущий раздел", ""));
    [
      ...new Set(
        catalog.records.map((item) => item.collection).filter(Boolean),
      ),
    ].forEach((collection) =>
      $("#collection").append(
        new Option(categoryNames[collection] || collection, collection),
      ),
    );
    if (
      [...$("#collection").options].some((option) => option.value === current)
    )
      $("#collection").value = current;
    $("#summary").replaceChildren();
    for (const [count, label] of [
      [catalog.records.length, "фотографий"],
      [
        catalog.records.filter((item) => item.status === "accepted").length,
        "отобрано",
      ],
      [
        catalog.records.filter((item) => item.collection === "head360").length,
        "ракурсов головы",
      ],
    ]) {
      const value = node("span");
      value.append(node("b", String(count)), document.createTextNode(label));
      $("#summary").append(value);
    }
    render();
  } catch (error) {
    message("Не удалось загрузить библиотеку: " + error.message, true);
  } finally {
    $("#refresh-library").disabled = false;
  }
}
$("#refresh-library").onclick = load;
$("#search").oninput = renderCards;
$("#candidates").onchange = renderCards;
$("#collection").onchange = renderCollectionNote;
$("#select-collection").onclick = () => {
  const items = collectionRecords();
  if (items.length > limit) {
    message(
      "В наборе " +
        items.length +
        " фотографий. Выберите до 16 с помощью поиска или карточек.",
      true,
    );
    return;
  }
  changeSelection(
    items.map((item) => item.id),
    "Выбран набор: " + items.length + " фотографий.",
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
});
void load();
