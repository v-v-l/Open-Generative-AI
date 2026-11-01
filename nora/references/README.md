# Reference library

The private library lives at `/references/` under the studio's existing login.
Its routes browse originals, generate display thumbnails, and export selected
photos as one PNG sheet or a ZIP of original files. It has no generation,
ComfyUI upload, workflow preparation, queue, seed, model or provider actions.

## Using the library

Choose Face, Head 360°, Body, Clothes or Location. Review status stays visible;
selecting or exporting a candidate does not approve it or add it to training.
Each card opens the original and offers a direct download. Candidate head angles
are nominal targets, not measured camera calibration.

Choose individual cards or a named collection. The selected list defines export
order left-to-right, then top-to-bottom. Reorder/remove items with its buttons.
The head collection currently contains eight separate photos at nominal
0/45/90/135/180/225/270/315 degrees. Body currently has only the existing three
originals; missing directions are shown rather than generated or duplicated.

Set column count and cell dimensions, inspect the preview, then download PNG.
Labels default off. The full image is fitted inside each cell with white padding;
there is no crop or generative alteration. ZIP/individual download preserves the
original file bytes. The selection is saved in browser local storage; it is not
a shared server-side collection editor.

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
- `POST /references/api/export`: `{ids,columns,cell_width,cell_height,labels}`
- `POST /references/api/zip`: `{ids}`

Only listed IDs and contained relative files are accepted. Hosted requests share
the studio's authentication, fixed Host and Origin checks; export errors do not
mutate the generation queue. Static files are allowlisted. No automatic GPU/API
call occurs when opening a page or exporting a sheet.
