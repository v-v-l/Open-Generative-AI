import React, { useState } from "react";
import { downloadOriginal, recreateJob } from "./gallery.js";
import { isReadOnly } from "./runtime.js";
export { downloadOriginal as noraDownloadOriginal } from "./gallery.js";

export function NoraGalleryActions({ entry, job = entry?.job }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <div className="nora-gallery-actions" onClick={event => event.stopPropagation()}>
    <button type="button" disabled={busy || isReadOnly()} onClick={async () => {
      setBusy(true); setError("");
      try { await recreateJob(job); }
      catch (e) { setError(e.message); }
      finally { setBusy(false); }
    }}>{busy ? "Открываем…" : "Пересоздать"}</button>
    {entry && <button type="button" onClick={() => {
      setError("");
      try { downloadOriginal(entry); } catch (e) { setError(e.message); }
    }}>Скачать оригинал</button>}
    {error && <p role="alert" className="nora-warning">{error}</p>}
  </div>;
}
