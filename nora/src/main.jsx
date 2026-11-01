import React from "react";
import { createRoot } from "react-dom/client";
import * as registry from "../../packages/studio/src/models.js";
import { refresh, runtime } from "./runtime.js";
import { installCatalog } from "./catalog.js";
import "./studio.generated.css";
import "./style.css";
const root = createRoot(document.getElementById("root"));
async function boot() {
  try {
    root.render(<div className="nora-loading">Подключение к студии…</div>);
    await refresh();
    installCatalog(registry, runtime.descriptors);
    const [{ default: ImageStudio }, { default: VideoStudio }, { Shell }] =
      await Promise.all([
        import("../../packages/studio/src/components/ImageStudio.jsx"),
        import("../../packages/studio/src/components/VideoStudio.jsx"),
        import("./ui.jsx"),
      ]);
    root.render(<Shell ImageStudio={ImageStudio} VideoStudio={VideoStudio} />);
    setInterval(
      () =>
        refresh().catch((error) =>
          console.warn("Studio reconnect:", error.message),
        ),
      3000,
    );
  } catch (error) {
    root.render(
      <div className="nora-loading">
        <h1>Не удалось открыть студию</h1>
        <p>{error.message}</p>
        <button onClick={boot}>Повторить подключение</button>
      </div>,
    );
  }
}
void boot();
