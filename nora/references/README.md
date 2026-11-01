# Reference library

The private library lives at `/references/` under the studio's existing login.
Its routes organize/upload originals, generate display thumbnails, and export selected
photos as one PNG sheet or a ZIP of original files. It has no generation,
ComfyUI upload, workflow preparation, queue, seed, model or provider actions.

## Using the library

### LoRA selection

The **LoRA · фото / видео** tab stores photographs and videos selected for a future
dataset. Create a named LoRA set, then upload one or several originals. These sets
append freely without angle slots. Uploads persist across devices and reloads, stay
marked as user supplied, and never launch training or generation.

Supported originals: PNG/JPEG/WebP up to40 MiB; MP4/WebM/MOV up to100 MiB each.
Video files are checked for a supported local container, video stream, dimensions
and duration before storage. Playback uses authenticated byte-range requests;
browser playback depends on the uploaded codec. Original downloads retain exact
bytes. Mixed photo/video selections can be downloaded as ZIP (up to16 items and
256 MiB). PNG sheets include photographs only, with videos explicitly excluded.
If a multi-file upload fails, retry skips files already saved successfully.

### Photo reference sets

Choose Face, Head 360°, Body, Clothes or Location. Review status stays visible;
selecting or exporting a candidate does not approve it or add it to training.
Each card opens the original and offers a direct download. Candidate head angles
are nominal targets, not measured camera calibration.

Use “Добавить референсы лица/фигуры”, “Добавить одежду” or “Добавить локацию”
to create a named reusable set. Face/body sets start with eight nominal 45-degree
slots; clothing uses front/back/side/detail; locations use four directions. Empty
slots stay visible and can be filled later through a file picker or drag/drop.
Uploads are PNG/JPEG/WebP up to40 MiB and preserve the original bytes. They are
marked “Загружен вами”, not automatically approved or added to training. A slot
replacement keeps the previous original in the library. Legacy accepted/candidate
sets remain protected; create a new set for your own photos.

Server-side sets and filled slots persist across devices/reloads. Only the temporary
export selection is browser-local. Uploaded JPEG orientation is honored in previews
and sheets while original downloads remain byte-exact. Manifest changes use a
cross-process file lock and atomic replacement; uploads never enqueue inference.

Choose individual cards or a named collection. The selected list defines export
order left-to-right, then top-to-bottom. Reorder/remove items with its buttons.
The head collection currently contains eight separate photos at nominal
0/45/90/135/180/225/270/315 degrees. Body currently has only the existing three
originals; missing directions are shown rather than generated or duplicated.

Set column count and cell dimensions, inspect the preview, then download PNG.
Labels default off. The full image is fitted inside each cell with white padding;
there is no crop or generative alteration. ZIP/individual download preserves the
original file bytes. Only the temporary export selection is saved in browser local storage; named
reference sets and uploaded slot photographs persist on the server.

Limits: 1–16 unique photos, 1–8 columns, longest sheet dimension 16384 and at most
64 megapixels. One server export runs at a time. PNG rendering changes resolution
according to the chosen cells; choose original downloads for untouched pixels.

## Inventory and updates

`NORA_REFERENCE_ROOT` points to a private, versioned data directory outside Git.
It contains `manifest.json` and relative original image paths. Private provenance
may be kept in `source-inventory.json`, which is never exposed by HTTP routes.
The API allowlists metadata and never returns filesystem paths. Declared sheet
cells are rejected as originals; this does not infer visual provenance itself.

Import an explicitly reviewed legacy inventory without inference:

```bash
python nora/references/import_catalog.py LEGACY_MANIFEST NEW_LIBRARY_DIRECTORY
```

The importer verifies recorded source hashes, copies only original `path` files,
ignores former `delivery` crops, preserves IDs/statuses, and refuses an existing
destination. Stage a new data version on apps, set NORA_REFERENCE_ROOT, then
restart the idle backend. Keep older data versions for rollback. Source photos,
passwords, provider keys and generated exports never belong in Git.

For an optional local reference-only preview:

```bash
python nora/references/serve.py --root PORTABLE_LIBRARY_DIRECTORY --port 36430
```

The historical Nora `scripts/serve-alice-model-page.py` is a compatibility launcher
for this reference-only preview. The former workflow preparation server is retired.

## API

- `GET /references/api/catalog`
- `GET /references/image/ID`, `/thumb/ID`, `/file/ID`
- `POST /references/api/collections`: `{title,category,slots?}`
- `POST /references/api/uploads`: `{collection_id,slot_id,name,mime,data}`
- `POST /references/api/export`: `{ids,columns,cell_width,cell_height,labels}`
- `POST /references/api/zip`: `{ids}`

Only listed IDs and contained relative files are accepted. Hosted requests share
the studio's authentication, fixed Host and Origin checks; export errors do not
mutate the generation queue. Static files are allowlisted. No automatic GPU/API
call occurs when opening a page or exporting a sheet.
