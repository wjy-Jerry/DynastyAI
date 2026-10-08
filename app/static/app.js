const $ = (id) => document.getElementById(id);
let project = null;
let busy = false;

function status(message, type = "") {
  $("status").textContent = message;
  $("status").className = type;
}

function setBusy(value) {
  busy = value;
  document.body.classList.toggle("busy", value);
  $("generate").disabled = value;
  $("generate").textContent = value
    ? "Writing your storyboard…"
    : "Generate storyboard ↗";
  $("save").disabled = value || !project;
  $("import").disabled = value;
  $("refresh-prompts").disabled = value || !project;
  $("generate-all").disabled = value || !project;
  $("title").disabled = value;
  $("scenes").setAttribute("aria-busy", String(value));
}

async function api(path, body, extraHeaders = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 310000);
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...extraHeaders },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      const message = Array.isArray(data.detail)
        ? data.detail
            .map((item) => `${item.loc.slice(1).join(".")}: ${item.msg}`)
            .join("; ")
        : data.detail || "The request could not be completed.";
      throw new Error(message);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error("The request timed out. Please try again.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function summary() {
  const total = project.scenes.reduce((sum, scene) => sum + scene.duration, 0);
  $("summary").textContent =
    `${project.scenes.length} scenes · ${total}s / ${project.request.target_duration}s`;
}

function markPromptsStale() {
  markAssetsStale();
  status(
    "Scene details changed. Click Refresh prompts before generating images.",
    "warning",
  );
}

function markAssetsStale() {
  if (!project) return;
  project.scenes.forEach((scene) => {
    if (scene.image_asset) {
      const message = $(`scene-status-${scene.scene_number}`);
      if (message) {
        message.textContent =
          "This image may reflect an older prompt. Review and regenerate it.";
        message.className = "scene-status warning";
      }
    }
  });
}

function newCharacter(name) {
  return {
    id: `character-${crypto.randomUUID().replaceAll("-", "").slice(0, 20)}`,
    name,
    role: "Role unspecified; review before image generation",
    approximate_age: "Age unspecified; review before image generation",
    appearance: "Appearance unspecified; review before image generation",
    facial_features:
      "Facial features unspecified; review before image generation",
    hairstyle: "Hairstyle unspecified; review before image generation",
    costume: "Costume unspecified; review before image generation",
    accessories: "Accessories unspecified; review before image generation",
    personality_visual_impression:
      "Visual impression unspecified; review before image generation",
  };
}

function bibleField(
  labelText,
  value,
  onChange,
  { multiline = false, id = "" } = {},
) {
  const wrap = document.createElement("div");
  const label = document.createElement("label");
  const control = document.createElement(multiline ? "textarea" : "input");
  control.id = id || `bible-${++field.counter}`;
  label.htmlFor = control.id;
  label.textContent = labelText;
  control.value = value;
  control.maxLength = multiline ? 1000 : 300;
  if (multiline) control.rows = 2;
  control.addEventListener("input", () => onChange(control.value));
  wrap.append(label, control);
  return wrap;
}

function renderBibles() {
  $("characters").replaceChildren();
  project.character_bible.forEach((character) => {
    const card = document.createElement("div");
    card.className = "character-card";
    const heading = document.createElement("h3");
    heading.textContent = `${character.name} · ${character.id}`;
    card.append(heading);
    const grid = document.createElement("div");
    grid.className = "bible-grid";
    const labels = {
      name: "Name",
      role: "Role",
      approximate_age: "Approximate age",
      appearance: "Appearance",
      facial_features: "Facial features",
      hairstyle: "Hairstyle",
      costume: "Costume",
      accessories: "Accessories",
      personality_visual_impression: "Personality / visual impression",
    };
    Object.entries(labels).forEach(([key, label]) => {
      grid.append(
        bibleField(
          `${character.id} ${label}`,
          character[key],
          (value) => {
            if (key === "name") {
              const previous = character.name;
              project.scenes.forEach((scene) => {
                scene.characters = scene.characters.map((name) =>
                  name === previous ? value : name,
                );
                const sceneNames = $(`characters-${scene.scene_number}`);
                if (sceneNames) sceneNames.value = scene.characters.join("\n");
                scene.dialogue.forEach((line, index) => {
                  if (line.character === previous) {
                    line.character = value;
                    const speaker = document.querySelector(
                      `[aria-label="Scene ${scene.scene_number} dialogue ${index + 1} speaker"]`,
                    );
                    if (speaker) speaker.value = value;
                  }
                });
              });
              heading.textContent = `${value} · ${character.id}`;
            }
            character[key] = value;
            markPromptsStale();
          },
          { multiline: !["name", "role", "approximate_age"].includes(key) },
        ),
      );
    });
    card.append(grid);
    $("characters").append(card);
  });
  $("visual-style").replaceChildren();
  const styleLabels = {
    historical_era: "Historical era / dynasty",
    visual_style: "Visual style",
    lighting: "Lighting",
    cinematography: "Cinematography",
    color_mood: "Color mood",
  };
  Object.entries(styleLabels).forEach(([key, label]) => {
    $("visual-style").append(
      bibleField(
        label,
        project.visual_style[key],
        (value) => {
          project.visual_style[key] = value;
          markPromptsStale();
        },
        { multiline: true },
      ),
    );
  });
  $("visual-style").append(
    bibleField("Aspect ratio", project.visual_style.aspect_ratio, () => {}, {
      id: "aspect-ratio",
    }),
  );
  $("aspect-ratio").readOnly = true;
}

function renderImage(scene, container) {
  container.replaceChildren();
  if (!scene.image_asset) {
    const placeholder = document.createElement("div");
    placeholder.className = "image-placeholder";
    placeholder.textContent = "9:16 scene image awaits";
    container.append(placeholder);
    return;
  }
  const image = document.createElement("img");
  image.src = scene.image_asset.url;
  image.alt = `Scene ${scene.scene_number} ${scene.image_asset.is_mock ? "mock placeholder, not AI generated" : "generated keyframe"}`;
  image.loading = "lazy";
  const caption = document.createElement("p");
  caption.className = "image-caption";
  caption.textContent = scene.image_asset.is_mock
    ? "MOCK PLACEHOLDER · NOT AI GENERATED"
    : `${scene.image_asset.model} · ${scene.image_asset.width}×${scene.image_asset.height}`;
  image.addEventListener("error", () => {
    caption.textContent = "Image file missing on this machine. Generate again.";
  });
  container.append(image, caption);
}

async function generateImage(scene) {
  const message = $(`scene-status-${scene.scene_number}`);
  message.textContent = "Generating image…";
  try {
    const result = await api(
      `/api/images/scenes/${scene.scene_number}`,
      project,
    );
    scene.image_asset = result.image_asset;
    renderImage(scene, $(`scene-image-${scene.scene_number}`));
    const button = $(`scene-generate-button-${scene.scene_number}`);
    button.textContent = "Regenerate Image";
    button.setAttribute(
      "aria-label",
      `Regenerate Image for scene ${scene.scene_number}`,
    );
    message.textContent = scene.image_asset.is_mock
      ? "Mock placeholder ready. No AI image was generated."
      : "Image generated and saved locally.";
    message.className = "scene-status";
    return true;
  } catch (error) {
    message.textContent = error.message;
    message.className = "scene-status error";
    return false;
  }
}

function field(
  labelText,
  value,
  onChange,
  {
    wide = false,
    rows = 2,
    maxLength = 4000,
    eventName = "input",
    id = "",
  } = {},
) {
  const wrap = document.createElement("div");
  if (wide) wrap.className = "wide";
  const label = document.createElement("label");
  const control = document.createElement("textarea");
  control.id = id || `field-${++field.counter}`;
  label.htmlFor = control.id;
  label.textContent = labelText;
  control.value = value;
  control.rows = rows;
  control.maxLength = maxLength;
  control.addEventListener(eventName, () => onChange(control.value));
  wrap.append(label, control);
  return wrap;
}
field.counter = 0;

function renderDialogue(scene, container) {
  container.replaceChildren();
  scene.dialogue.forEach((line, index) => {
    const row = document.createElement("div");
    row.className = "dialogue-line";
    const name = document.createElement("input");
    name.value = line.character;
    name.maxLength = 100;
    name.setAttribute(
      "aria-label",
      `Scene ${scene.scene_number} dialogue ${index + 1} speaker`,
    );
    name.addEventListener("input", () => {
      line.character = name.value;
    });
    const words = document.createElement("textarea");
    words.value = line.line;
    words.rows = 1;
    words.maxLength = 2000;
    words.setAttribute(
      "aria-label",
      `Scene ${scene.scene_number} dialogue ${index + 1} line`,
    );
    words.addEventListener("input", () => {
      line.line = words.value;
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-line";
    remove.textContent = "×";
    remove.setAttribute(
      "aria-label",
      `Remove dialogue ${index + 1} from scene ${scene.scene_number}`,
    );
    remove.addEventListener("click", () => {
      scene.dialogue.splice(index, 1);
      renderDialogue(scene, container);
    });
    row.append(name, words, remove);
    container.append(row);
  });
  const add = document.createElement("button");
  add.type = "button";
  add.className = "add-line";
  add.textContent = "+ Add dialogue";
  add.disabled = scene.dialogue.length >= 30;
  add.addEventListener("click", () => {
    scene.dialogue.push({ character: scene.characters[0] || "", line: "" });
    renderDialogue(scene, container);
  });
  container.append(add);
}

function render() {
  $("empty").hidden = true;
  $("project").hidden = false;
  $("title").value = project.title;
  renderBibles();
  $("scenes").replaceChildren();
  project.scenes.forEach((scene) => {
    const article = document.createElement("article");
    article.className = "scene";
    article.setAttribute("aria-label", `Scene ${scene.scene_number}`);
    const header = document.createElement("div");
    header.className = "scene-head";
    const heading = document.createElement("h3");
    heading.textContent = `SCENE ${String(scene.scene_number).padStart(2, "0")}`;
    const timing = document.createElement("div");
    timing.className = "seconds";
    const durationLabel = document.createElement("label");
    durationLabel.textContent = "Duration (s)";
    const duration = document.createElement("input");
    duration.type = "number";
    duration.min = 1;
    duration.max = 180;
    duration.step = 1;
    duration.required = true;
    duration.value = scene.duration;
    duration.id = `duration-${scene.scene_number}`;
    durationLabel.htmlFor = duration.id;
    duration.addEventListener("input", () => {
      scene.duration = Number(duration.value);
      summary();
    });
    timing.append(durationLabel, duration);
    header.append(heading, timing);
    const grid = document.createElement("div");
    grid.className = "scene-grid";
    grid.append(
      field(
        `Scene ${scene.scene_number} narration`,
        scene.narration,
        (v) => {
          scene.narration = v;
        },
        { maxLength: 3000 },
      ),
      field(
        `Scene ${scene.scene_number} characters (one per line)`,
        scene.characters.join("\n"),
        (v) => {
          scene.characters = v
            .split("\n")
            .map((name) => name.trim())
            .filter(Boolean);
          scene.character_ids = scene.characters.map((name) => {
            let entry = project.character_bible.find(
              (character) => character.name === name,
            );
            if (!entry) {
              entry = newCharacter(name);
              project.character_bible.push(entry);
              renderBibles();
            }
            return entry.id;
          });
          markPromptsStale();
        },
        { eventName: "change", id: `characters-${scene.scene_number}` },
      ),
    );
    const dialogue = document.createElement("div");
    dialogue.className = "wide";
    const dialogueHeading = document.createElement("label");
    dialogueHeading.textContent = "DIALOGUE";
    const dialogueRows = document.createElement("div");
    renderDialogue(scene, dialogueRows);
    dialogue.append(dialogueHeading, dialogueRows);
    grid.append(
      dialogue,
      field(
        `Scene ${scene.scene_number} visual prompt`,
        scene.visual_prompt,
        (v) => {
          scene.visual_prompt = v;
          markPromptsStale();
        },
        { wide: true },
      ),
      field(
        `Scene ${scene.scene_number} camera description`,
        scene.camera_description,
        (v) => {
          scene.camera_description = v;
          markPromptsStale();
        },
        { wide: true, maxLength: 2000 },
      ),
    );
    grid.append(
      field(
        `Scene ${scene.scene_number} final image prompt (sent verbatim)`,
        scene.final_image_prompt,
        (value) => {
          scene.final_image_prompt = value;
          markAssetsStale();
        },
        { wide: true, rows: 8, maxLength: 16000 },
      ),
    );
    const imageArea = document.createElement("div");
    imageArea.className = "scene-image-area";
    const preview = document.createElement("div");
    preview.className = "image-preview";
    preview.id = `scene-image-${scene.scene_number}`;
    renderImage(scene, preview);
    const controls = document.createElement("div");
    controls.className = "image-controls";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.id = `scene-generate-button-${scene.scene_number}`;
    button.textContent = scene.image_asset
      ? "Regenerate Image"
      : "Generate Image";
    button.setAttribute(
      "aria-label",
      `${button.textContent} for scene ${scene.scene_number}`,
    );
    button.addEventListener("click", async () => {
      if (busy) return;
      setBusy(true);
      try {
        if (await generateImage(scene)) {
          button.textContent = "Regenerate Image";
          button.setAttribute(
            "aria-label",
            `Regenerate Image for scene ${scene.scene_number}`,
          );
        }
      } finally {
        setBusy(false);
      }
    });
    const imageStatus = document.createElement("p");
    imageStatus.className = "scene-status";
    imageStatus.id = `scene-status-${scene.scene_number}`;
    controls.append(button, imageStatus);
    imageArea.append(preview, controls);
    article.append(header, grid, imageArea);
    $("scenes").append(article);
  });
  summary();
  $("save").disabled = false;
  $("refresh-prompts").disabled = false;
  $("generate-all").disabled = false;
}

$("title").addEventListener("input", () => {
  if (project) project.title = $("title").value;
});

$("refresh-prompts").addEventListener("click", async () => {
  if (!project || busy) return;
  if (
    !window.confirm(
      "Refresh all final prompts? This replaces manual edits to those prompts.",
    )
  )
    return;
  setBusy(true);
  try {
    project = await api("/api/projects/prompts/refresh", project);
    render();
    markAssetsStale();
    status(
      "Final prompts refreshed. Review them and regenerate existing images if needed.",
    );
  } catch (error) {
    status(`Cannot refresh prompts: ${error.message}`, "error");
  } finally {
    setBusy(false);
  }
});

$("generate-all").addEventListener("click", async () => {
  if (!project || busy) return;
  setBusy(true);
  let completed = 0;
  try {
    for (const scene of project.scenes) {
      if (await generateImage(scene)) completed += 1;
    }
    status(
      `${completed} of ${project.scenes.length} scene images ready. Save JSON to preserve their asset references.`,
      completed === project.scenes.length ? "" : "warning",
    );
  } finally {
    setBusy(false);
  }
});
$("story-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  if (
    project &&
    !window.confirm(
      "Generate a new storyboard? Save JSON first to keep your current edits.",
    )
  )
    return;
  const request = {
    story_idea: $("idea").value.trim(),
    genre: $("genre").value,
    target_duration: Number($("duration").value),
    output_language: $("language").value,
  };
  setBusy(true);
  status("Building your scenes. This may take a moment…");
  try {
    const next = await api("/api/storyboards", request, {
      "X-DynastyAI-Version": "2",
    });
    project = next;
    render();
    status(
      next.generation_mode === "demo"
        ? "Demo template loaded. This is a fixed sample, not a story generated from your idea."
        : "Your storyboard is ready. Edit any scene, then save your project as JSON.",
      next.generation_mode === "demo" ? "warning" : "",
    );
  } catch (error) {
    status(error.message, "error");
  } finally {
    setBusy(false);
  }
});

$("save").addEventListener("click", async () => {
  if (!project || busy) return;
  setBusy(true);
  try {
    const validated = await api("/api/projects/validate", project);
    const blob = new Blob([JSON.stringify(validated, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const filename =
      validated.title.replace(/[^\p{L}\p{N}_-]+/gu, "-").slice(0, 80) ||
      "dynastyai";
    link.download = `${filename}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status("JSON export prepared. Check your browser downloads.");
  } catch (error) {
    status(`Cannot save: ${error.message}`, "error");
  } finally {
    setBusy(false);
  }
});

$("import").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", async () => {
  const file = $("file").files[0];
  $("file").value = "";
  if (!file || busy) return;
  if (
    project &&
    !window.confirm(
      "Open another project? Save JSON first to keep your current edits.",
    )
  )
    return;
  setBusy(true);
  try {
    if (file.size > 1024 * 1024)
      throw new Error("Please choose a JSON file smaller than 1 MB.");
    const original = JSON.parse(await file.text());
    const validated = await api("/api/projects/validate", original);
    project =
      validated.schema_version === "1.0"
        ? await api("/api/projects/migrate", validated)
        : validated;
    $("idea").value = project.request.story_idea;
    $("genre").value = project.request.genre;
    $("language").value = project.request.output_language;
    const durationSelect = $("duration");
    if (
      ![...durationSelect.options].some(
        (o) => Number(o.value) === project.request.target_duration,
      )
    ) {
      durationSelect.add(
        new Option(
          `${project.request.target_duration} seconds`,
          project.request.target_duration,
        ),
      );
    }
    durationSelect.value = project.request.target_duration;
    render();
    status(
      project.migrated_from === "1.0"
        ? "Phase 1 project migrated to v2. Review unspecified Character Bible details before image generation."
        : project.generation_mode === "demo"
          ? "Demo template project opened."
          : "Project opened. Your edits are ready.",
      project.migrated_from === "1.0" ? "warning" : "",
    );
  } catch (error) {
    status(`Cannot open project: ${error.message}`, "error");
  } finally {
    setBusy(false);
  }
});

window.addEventListener("beforeunload", (event) => {
  if (project) {
    event.preventDefault();
    event.returnValue = "";
  }
});

fetch("/api/health")
  .then((r) => {
    if (!r.ok) throw new Error();
    return r.json();
  })
  .then((data) => {
    $("mode").textContent =
      data.mode === "demo"
        ? "DEMO MODE"
        : data.configured
          ? "LLM CONFIGURED"
          : "SETUP REQUIRED";
    $("config-note").textContent =
      data.mode === "demo"
        ? "Demo mode uses a fixed sample storyboard. Enable an LLM to generate from your own idea."
        : data.configured
          ? "Your story is sent to the configured LLM provider when you generate."
          : "Add an LLM_API_KEY to the backend .env to generate, or enable DEMO_MODE=true to explore.";
  })
  .catch(() => {
    $("mode").textContent = "OFFLINE";
    $("config-note").textContent =
      "Cannot reach the backend. Start the server and reload this page.";
  });

fetch("/api/image-health")
  .then((response) => {
    if (!response.ok) throw new Error();
    return response.json();
  })
  .then((data) => {
    $("image-mode").textContent =
      data.provider === "mock"
        ? "MOCK MODE · Images are labeled placeholders, not AI generated."
        : data.provider === "alibaba"
          ? data.configured
            ? "QWEN IMAGES CONFIGURED · Generating an image may incur provider charges."
            : "QWEN IMAGES NEEDS IMAGE_API_KEY · Set it in the backend .env, or use IMAGE_PROVIDER=mock."
          : data.configured
            ? "OPENAI IMAGES CONFIGURED · Generating an image may incur provider charges."
            : "OPENAI IMAGES NEEDS IMAGE_API_KEY · Set it in the backend .env, or use IMAGE_PROVIDER=mock.";
  })
  .catch(() => {
    $("image-mode").textContent = "Image provider status unavailable.";
  });
