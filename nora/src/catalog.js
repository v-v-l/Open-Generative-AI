// Translate only verified backend capabilities; do not infer provider support from a product name.
export function modelFromDescriptor(m, mode) {
  const inputs = {
    prompt: { type: "string", title: "Prompt", name: "prompt" },
  };
  for (const [key, spec] of Object.entries(m.settings || {})) {
    if (key === "seed") {
      inputs.seed = {
        type: "integer",
        title: "Seed (-1 random)",
        default: -1,
        minValue: -1,
        configurable: true,
      };
      continue;
    }
    inputs[key] = {
      type:
        spec.type === "boolean"
          ? "boolean"
          : typeof spec.default === "number"
            ? "number"
            : "string",
      title: key.replaceAll("_", " "),
      name: key,
      ...(spec.values ? { enum: spec.values } : {}),
      ...(spec.default !== undefined ? { default: spec.default } : {}),
      configurable: ![
        "aspect_ratio",
        "resolution",
        "quality",
        "duration",
      ].includes(key),
    };
  }
  const local = ["local", "simplepod"].includes(m.provider);
  if (local) {
    for (const [key, defaultValue, min, max, step] of [
      ["width", m.default_width || 704, 256, 1536, 32],
      ["height", m.default_height || 960, 256, 1536, 32],
      ["steps", 25, 1, 60, 1],
      ["seed", -1, -1, 9007199254740991, 1],
      ["max_minutes", 20, 5, 90, 1],
      ["lora_strength", 0.8, 0, 1.5, 0.05],
    ])
      inputs[key] = {
        type: "number",
        title: key,
        default: defaultValue,
        minValue: min,
        maxValue: max,
        step,
        configurable: true,
      };
    inputs.lora_enabled = {
      type: "boolean",
      title: "Alice LoRA",
      default: false,
      configurable: true,
    };
    if (m.lora_names)
      inputs.lora_name = {
        type: "string",
        title: "Alice LoRA version",
        enum: m.lora_names,
        default: m.default_lora,
        configurable: true,
      };
    if (m.kind === "video") {
      inputs.frames = {
        type: "integer",
        title: "Frames (24 fps, 17k+5)",
        default: 141,
        minValue: 107,
        maxValue: 362,
        step: 17,
        configurable: true,
      };
      inputs.generated_audio = {
        type: "boolean",
        title: "Generate H3 audio",
        default: false,
        configurable: true,
      };
      inputs.video_ref_audio = {
        type: "boolean",
        title: "Use video reference audio",
        default: false,
        configurable: true,
      };
    }
  }
  inputs.max_cost_usd = {
    type: "number",
    title: "Max USD per job (optional)",
    minValue: 0.001,
    step: 0.001,
    configurable: true,
  };
  const result = {
    id: m.id,
    name: m.label,
    endpoint: m.id,
    description: local ? "Our " + m.provider : "Via " + m.provider,
    provider: m.provider,
    provider_name:
      m.provider === "openai"
        ? "OpenAI direct"
        : m.provider === "openrouter"
          ? "OpenRouter"
          : m.provider,
    inputs,
    hasPrompt: true,
    promptRequired: true,
  };
  if (m.kind === "photo" && m.roles.image) {
    result.imageField = "images_list";
    result.maxImages = m.roles.image;
    inputs.images_list = {
      type: "array",
      field: "image",
      title: "Reference images",
      items: { type: "string" },
      minItems: m.required_roles?.image || 0,
      maxItems: m.roles.image,
    };
  }
  if (m.kind === "video" && mode === "i2v") {
    if (m.roles.start) {
      result.imageField = "image_url";
      inputs.image_url = {
        type: "string",
        field: "image",
        title: "Start frame",
      };
    } else if (m.roles.image) {
      result.imageField = "images_list";
      result.maxImages = m.roles.image;
      inputs.images_list = {
        type: "array",
        field: "image",
        title: "Image references",
        items: { type: "string" },
        maxItems: m.roles.image,
      };
    }
    if (m.roles.end) {
      result.lastImageField = "last_image";
      inputs.last_image = {
        type: "string",
        field: "image",
        title: "End frame",
      };
    }
    for (const role of ["video", "audio"])
      if (m.roles[role]) {
        const field = role === "video" ? "videos_list" : "audios_list";
        result[role + "Field"] = field;
        result[role === "video" ? "maxVideos" : "maxAudios"] = m.roles[role];
        inputs[field] = {
          type: "array",
          field: role,
          title: role + " references",
          items: { type: "string" },
          maxItems: m.roles[role],
        };
      }
  }
  return result;
}
export function installCatalog(registry, descriptors) {
  const photo = descriptors.filter((m) => m.kind === "photo"),
    video = descriptors.filter((m) => m.kind === "video");
  registry.t2iModels.splice(
    0,
    registry.t2iModels.length,
    ...photo
      .filter((m) => !m.required_roles?.image)
      .map((m) => modelFromDescriptor(m, "t2i")),
  );
  registry.i2iModels.splice(
    0,
    registry.i2iModels.length,
    ...photo
      .filter((m) => m.roles.image)
      .map((m) => modelFromDescriptor(m, "i2i")),
  );
  registry.t2vModels.splice(
    0,
    registry.t2vModels.length,
    ...video.map((m) => modelFromDescriptor(m, "t2v")),
  );
  registry.i2vModels.splice(
    0,
    registry.i2vModels.length,
    ...video
      .filter((m) => m.roles.start || m.roles.image)
      .map((m) => modelFromDescriptor(m, "i2v")),
  );
  registry.v2vModels.splice(0, registry.v2vModels.length);
}
