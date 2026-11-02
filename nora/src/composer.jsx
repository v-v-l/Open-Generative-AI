import React, { useId, useState, useEffect } from "react";
import { PromptComposer } from "../../packages/studio/src/components/prompt/PromptComposer.jsx";
import { descriptor, isUploading } from "./runtime.js";
import { referenceInputs, refsFor } from "./api.js";
import { pastedImages } from "./referenceValidation.js";
import { modelDisplayName } from "./catalog.js";

// Hide, rather than unmount, so draft text, upload controls and settings survive.
export function NoraComposer({
  kind,
  modelId,
  prompt = "",
  references = {},
  children,
}) {
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    const expand = (event) => { if (event.detail?.kind === kind) setCollapsed(false); };
    window.addEventListener("nora-recreate", expand);
    return () => window.removeEventListener("nora-recreate", expand);
  }, [kind]);
  const id = useId(),
    model = descriptor(modelId);
  let count = 0;
  if (model) {
    try {
      count = refsFor(referenceInputs(modelId, references), model).length;
    } catch {}
  }
  const label = kind === "photo" ? "Фото" : "Видео";
  return (
    <PromptComposer
      panelClassName={
        "nora-composer-panel" + (collapsed ? " nora-composer-collapsed" : "")
      }
    >
      <div className="nora-composer-head">
        <div className="nora-composer-brief" hidden={!collapsed}>
          <strong>
            {label}
            {model ? " · " + modelDisplayName(model) : ""}
          </strong>
          <span>
            {isUploading(modelId) ? "Загрузка…" : count + " референсов"}
            {prompt.trim() ? " · " + prompt.trim() : ""}
          </span>
        </div>
        <button
          type="button"
          className="nora-composer-toggle"
          aria-expanded={!collapsed}
          aria-controls={id}
          aria-label={
            (collapsed ? "Развернуть промпт · " : "Свернуть промпт · ") + label
          }
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? "Развернуть ↑" : "Свернуть ↓"}
        </button>
      </div>
      <div id={id} className="nora-composer-body" hidden={collapsed}
        onPaste={(event) => {
          const files = pastedImages(event.clipboardData);
          if (!files.length) return;
          event.preventDefault();
          window.dispatchEvent(new CustomEvent("nora-paste-images", {detail: {modelId, files}}));
        }}>
        {children}
      </div>
    </PromptComposer>
  );
}
