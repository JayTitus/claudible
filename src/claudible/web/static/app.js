/* Claudible Config UI */

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function esc(s) {
  if (s == null) return "";
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch("/api" + path, opts);
  if (!resp.ok) {
    const err = await resp.text();
    try { const j = JSON.parse(err); throw new Error(j.detail || err); }
    catch (e) { if (e instanceof SyntaxError) throw new Error(err); throw e; }
  }
  return resp.json();
}

function toast(msg, ok = true) {
  const el = document.createElement("div");
  el.className = "toast " + (ok ? "toast-ok" : "toast-err");
  el.textContent = msg;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function badge(val, type) {
  if (type === "bool") {
    return val
      ? '<span class="badge badge-yes">Yes</span>'
      : '<span class="badge badge-no">No</span>';
  }
  return `<span class="badge badge-num">${val}</span>`;
}

/* ── Tab switching ──────────────────────────────────────────────────────── */

const navItems = document.querySelectorAll(".nav-item");
const tabs = document.querySelectorAll(".tab");

navItems.forEach(item => {
  item.addEventListener("click", e => {
    e.preventDefault();
    const target = item.dataset.tab;
    navItems.forEach(n => n.classList.remove("active"));
    tabs.forEach(t => t.classList.remove("active"));
    item.classList.add("active");
    document.getElementById("tab-" + target).classList.add("active");
    // Load tab data
    loaders[target]?.();
  });
});

/* ── Data cache ─────────────────────────────────────────────────────────── */

let cfg = null;
let statusData = null;

async function loadConfig() {
  cfg = await api("GET", "/config");
  return cfg;
}

async function loadStatus() {
  statusData = await api("GET", "/status");
  return statusData;
}

/* ── Dashboard ──────────────────────────────────────────────────────────── */

async function loadDashboard() {
  try {
    const [c, s] = await Promise.all([loadConfig(), loadStatus()]);
    document.getElementById("dash-model").innerHTML = badge(s.model_loaded, "bool");
    document.getElementById("dash-hook").innerHTML = badge(s.hook_installed, "bool");
    document.getElementById("dash-voices").innerHTML = badge(s.voice_count);
    document.getElementById("dash-active-voice").textContent = c.tts.voice;
    document.getElementById("dash-rephrase").innerHTML = badge(c.rephrase.enabled, "bool");
    document.getElementById("dash-persona").textContent = c.rephrase.persona;
    document.getElementById("dash-rephrase-model").textContent = c.rephrase.model;
    document.getElementById("dash-completion").textContent = c.completion?.mode || "none";
    document.getElementById("dash-hook-mode").textContent = c.hook?.mode || "full";
    document.getElementById("dash-input").innerHTML = badge(s.input_group, "bool");
    document.getElementById("dash-rnnoise").innerHTML = badge(s.rnnoise_active, "bool");
    document.getElementById("dash-correction").innerHTML = badge(c.correction?.enabled, "bool");
    // Container status on dashboard
    try {
      const ctr = await api("GET", "/container");
      document.getElementById("dash-container").innerHTML = ctr.running
        ? '<span class="badge badge-yes">Running</span>'
        : '<span class="badge badge-no">Off</span>';
    } catch (e) {
      document.getElementById("dash-container").innerHTML = '<span class="badge badge-no">N/A</span>';
    }

    // Missing deps banner
    const banner = document.getElementById("dash-deps-banner");
    if (s.missing_deps && s.missing_deps.length > 0) {
      const aptPkgs = s.missing_deps.filter(d => !d.includes("see README"));
      const other = s.missing_deps.filter(d => d.includes("see README"));
      let html = "<strong>Missing dependencies:</strong> " + s.missing_deps.join(", ");
      if (aptPkgs.length > 0) {
        html += "<br>Run: <code>sudo apt install " + aptPkgs.join(" ") + "</code>";
      }
      if (other.length > 0) {
        html += "<br>Also needed: " + other.join(", ");
      }
      html += "<br>Or run <code>claudible install</code> to set up everything.";
      banner.innerHTML = html;
      banner.style.display = "";
    } else {
      banner.style.display = "none";
    }
  } catch (e) {
    console.error("Dashboard load failed:", e);
  }
}

/* ── Voice ──────────────────────────────────────────────────────────────── */

let voicesData = [];

async function loadVoice() {
  await loadConfig();
  try {
    voicesData = await api("GET", "/voices");
  } catch (e) { voicesData = []; }

  // Show active voice and persona
  document.getElementById("voice-active-name").textContent = cfg.tts.voice;
  document.getElementById("voice-active-persona").textContent = cfg.rephrase.persona;

  // Populate test voice dropdown with all voices
  const sel = document.getElementById("voice-select");
  sel.innerHTML = "";
  voicesData.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v.name;
    opt.textContent = v.name;
    if (v.name === cfg.tts.voice) opt.selected = true;
    sel.appendChild(opt);
  });
  showVoiceInfo(cfg.tts.voice);

  document.getElementById("voice-speed").value = cfg.tts.speed;
  document.getElementById("voice-language").value = cfg.tts.language;
  document.getElementById("voice-lead-in").value = cfg.tts.audio_lead_in_ms ?? 150;
  document.getElementById("voice-dir").value = cfg.tts.voices_dir;
}

function showVoiceInfo(name) {
  const v = voicesData.find(v => v.name === name);
  const el = document.getElementById("voice-info");
  if (!v || v.error) {
    el.textContent = v ? "Error loading voice info" : "";
    return;
  }
  el.textContent = `Duration: ${v.duration}s | Rate: ${v.sample_rate} Hz | Channels: ${v.channels} | Size: ${v.file_size_kb} KB`;
}

document.getElementById("voice-select").addEventListener("change", e => showVoiceInfo(e.target.value));

document.getElementById("voice-test-btn").addEventListener("click", async () => {
  const name = document.getElementById("voice-select").value;
  try {
    await api("POST", `/voices/${encodeURIComponent(name)}/test`);
    toast("Playing test...");
  } catch (e) { toast("Test failed: " + e.message, false); }
});

document.getElementById("voice-save").addEventListener("click", async () => {
  try {
    await api("PATCH", "/config/tts", {
      speed: parseFloat(document.getElementById("voice-speed").value),
      language: document.getElementById("voice-language").value,
      audio_lead_in_ms: parseInt(document.getElementById("voice-lead-in").value) || 150,
      voices_dir: document.getElementById("voice-dir").value,
    });
    cfg = null;
    toast("Voice settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
});

/* ── Voice Studio ──────────────────────────────────────────────────────── */

let studioStaged = [];
let studioInstalledNames = new Set();

async function loadStudio() {
  const name = document.getElementById("studio-name").value.trim();
  if (name) {
    await loadStagedFiles(name);
  }
  await loadStudioVoices();
  updateStudioCreateBtn();
}

async function loadStagedFiles(name) {
  try {
    studioStaged = await api("GET", `/voice-studio/staging/${encodeURIComponent(name)}`);
  } catch (e) { studioStaged = []; }
  renderStagedFiles();
}

function renderStagedFiles() {
  const container = document.getElementById("studio-staged-list");
  const section = document.getElementById("studio-staged");
  const createBtn = document.getElementById("studio-create-btn");
  const clearBtn = document.getElementById("studio-clear-btn");

  if (studioStaged.length === 0) {
    section.style.display = "none";
    createBtn.disabled = true;
    clearBtn.style.display = "none";
    return;
  }

  section.style.display = "";
  clearBtn.style.display = "";
  container.innerHTML = "";

  let totalDuration = 0;
  studioStaged.forEach(f => {
    totalDuration += f.duration;
    const row = document.createElement("div");
    row.className = "staged-file";
    row.innerHTML =
      `<span class="staged-file-name">${esc(f.name)}</span>` +
      `<span class="staged-file-info">${f.duration}s</span>` +
      `<span class="staged-file-info">${f.size_kb} KB</span>`;

    const delBtn = document.createElement("button");
    delBtn.className = "btn btn-danger btn-sm";
    delBtn.textContent = "X";
    delBtn.addEventListener("click", async () => {
      const name = document.getElementById("studio-name").value.trim();
      try {
        await api("DELETE", `/voice-studio/staging/${encodeURIComponent(name)}/${encodeURIComponent(f.name)}`);
        await loadStagedFiles(name);
      } catch (e) { toast("Remove failed: " + e.message, false); }
    });
    row.appendChild(delBtn);
    container.appendChild(row);
  });

  // Update total duration display
  const totalEl = document.getElementById("studio-total-duration");
  totalEl.textContent = totalDuration.toFixed(1) + "s";

  const fill = document.getElementById("studio-duration-fill");
  const pct = Math.min(totalDuration / 15, 1) * 100;
  fill.style.width = pct + "%";
  fill.className = "duration-bar-fill " + (totalDuration >= 6 ? "duration-ok" : "duration-short");

  createBtn.disabled = totalDuration < 6;
}

function updateStudioCreateBtn() {
  const name = document.getElementById("studio-name").value.trim();
  const btn = document.getElementById("studio-create-btn");
  const isReplace = name && studioInstalledNames.has(name);
  btn.textContent = isReplace ? "Replace Voice" : "Create Voice";
}

async function loadStudioVoices() {
  const container = document.getElementById("studio-voices-list");
  try {
    const voices = await api("GET", "/voices");
    studioInstalledNames = new Set(voices.map(v => v.name));
    if (voices.length === 0) {
      container.innerHTML = '<p style="color:var(--text-muted); font-size:0.85rem;">No voices installed.</p>';
      return;
    }
    container.innerHTML = "";
    voices.forEach(v => {
      const row = document.createElement("div");
      row.className = "staged-file";
      row.innerHTML =
        `<span class="staged-file-name">${esc(v.name)}</span>` +
        `<span class="staged-file-info">${v.duration || "?"}s</span>`;

      const testBtn = document.createElement("button");
      testBtn.className = "btn btn-secondary btn-sm";
      testBtn.textContent = "Test";
      testBtn.addEventListener("click", async () => {
        testBtn.disabled = true;
        testBtn.textContent = "Playing...";
        try {
          await api("POST", `/voices/${encodeURIComponent(v.name)}/test`);
          toast("Playing " + v.name + "...");
        } catch (e) { toast("Test failed: " + e.message, false); }
        testBtn.disabled = false;
        testBtn.textContent = "Test";
      });
      row.appendChild(testBtn);

      const replaceBtn = document.createElement("button");
      replaceBtn.className = "btn btn-secondary btn-sm";
      replaceBtn.textContent = "Replace";
      replaceBtn.addEventListener("click", () => {
        document.getElementById("studio-name").value = v.name;
        updateStudioCreateBtn();
        document.getElementById("studio-upload-zone").scrollIntoView({ behavior: "smooth" });
      });
      row.appendChild(replaceBtn);

      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-danger btn-sm";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", async () => {
        if (!confirm('Delete voice "' + v.name + '"?')) return;
        try {
          await api("DELETE", `/voices/${encodeURIComponent(v.name)}`);
          toast("Voice deleted");
          loadStudioVoices();
          updateStudioCreateBtn();
        } catch (e) { toast("Delete failed: " + e.message, false); }
      });
      row.appendChild(delBtn);

      container.appendChild(row);
    });
  } catch (e) {
    container.innerHTML = '<p style="color:var(--text-muted);">Failed to load voices.</p>';
  }
}

// Upload handling
const studioZone = document.getElementById("studio-upload-zone");
const studioFileInput = document.getElementById("studio-file-input");

document.getElementById("studio-name").addEventListener("input", () => {
  updateStudioCreateBtn();
});

document.getElementById("studio-name").addEventListener("change", async () => {
  const name = document.getElementById("studio-name").value.trim();
  if (name) await loadStagedFiles(name);
  updateStudioCreateBtn();
});

document.getElementById("studio-browse-link").addEventListener("click", e => {
  e.preventDefault();
  studioFileInput.click();
});

studioFileInput.addEventListener("change", () => {
  if (studioFileInput.files.length > 0) uploadStudioFiles(studioFileInput.files);
});

studioZone.addEventListener("dragover", e => {
  e.preventDefault();
  studioZone.classList.add("upload-zone-active");
});

studioZone.addEventListener("dragleave", () => {
  studioZone.classList.remove("upload-zone-active");
});

studioZone.addEventListener("drop", e => {
  e.preventDefault();
  studioZone.classList.remove("upload-zone-active");
  if (e.dataTransfer.files.length > 0) uploadStudioFiles(e.dataTransfer.files);
});

async function uploadStudioFiles(fileList) {
  const name = document.getElementById("studio-name").value.trim();
  if (!name) { toast("Enter a voice name first", false); return; }

  const formData = new FormData();
  for (const f of fileList) formData.append("files", f);

  try {
    const resp = await fetch(`/api/voice-studio/upload/${encodeURIComponent(name)}`, {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || resp.statusText);
    }
    const result = await resp.json();
    toast(`Uploaded ${result.length} file(s)`);
    studioFileInput.value = "";
    await loadStagedFiles(name);
  } catch (e) { toast("Upload failed: " + e.message, false); }
}

// Create voice
document.getElementById("studio-create-btn").addEventListener("click", async () => {
  const name = document.getElementById("studio-name").value.trim();
  if (!name) { toast("Enter a voice name first", false); return; }

  const isReplace = studioInstalledNames.has(name);
  if (isReplace && !confirm(`Voice "${name}" already exists. Replace it?`)) return;

  const btn = document.getElementById("studio-create-btn");
  const status = document.getElementById("studio-status");
  btn.disabled = true;
  btn.textContent = isReplace ? "Replacing..." : "Creating...";
  status.style.display = "";
  status.textContent = "Processing audio and " + (isReplace ? "replacing" : "creating") + " voice...";

  try {
    const info = await api("POST", `/voice-studio/create/${encodeURIComponent(name)}`);
    status.textContent = `Voice "${info.name}" ${isReplace ? "replaced" : "created"} (${info.duration || "?"}s)`;
    toast(isReplace ? "Voice replaced!" : "Voice created!");
    studioStaged = [];
    renderStagedFiles();
    loadStudioVoices();
  } catch (e) {
    status.textContent = "Error: " + e.message;
    toast("Failed: " + e.message, false);
  }
  btn.disabled = false;
  updateStudioCreateBtn();
});

// Clear staging
document.getElementById("studio-clear-btn").addEventListener("click", async () => {
  const name = document.getElementById("studio-name").value.trim();
  if (!name) return;
  try {
    await api("DELETE", `/voice-studio/staging/${encodeURIComponent(name)}`);
    studioStaged = [];
    renderStagedFiles();
    toast("Staging cleared");
  } catch (e) { toast("Clear failed: " + e.message, false); }
});

/* ── Rephrase ──────────────────────────────────────────────────────────── */

async function loadRephrase() {
  await loadConfig();
  document.getElementById("rephrase-enabled").checked = cfg.rephrase.enabled;
  document.getElementById("rephrase-url").value = cfg.rephrase.api_url;
  document.getElementById("rephrase-key").value = cfg.rephrase.api_key;
  document.getElementById("rephrase-model").value = cfg.rephrase.model;

  // Load personas for selector
  try {
    const personas = await api("GET", "/personas");
    const sel = document.getElementById("rephrase-persona");
    sel.innerHTML = "";
    personas.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.name;
      opt.textContent = p.name + (p.custom ? " (custom)" : "");
      if (p.name === cfg.rephrase.persona) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch (e) { console.error("Failed to load personas for rephrase:", e); }

  // Fetch models into datalist
  await fetchModels(false);

  // Completion settings
  document.getElementById("completion-mode").value = cfg.completion?.mode || "none";
  document.getElementById("completion-phrase").value = cfg.completion?.simple_phrase || "Done.";
  document.getElementById("completion-prefix").value = cfg.completion?.persona_prefix || "";
  document.getElementById("completion-temperature").value = cfg.completion?.temperature ?? 0.9;
}

async function fetchModels(showToast = true) {
  const datalist = document.getElementById("rephrase-model-list");
  try {
    const models = await api("GET", "/models");
    datalist.innerHTML = "";
    models.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      datalist.appendChild(opt);
    });
    if (showToast) toast(`Found ${models.length} models`);
  } catch (e) {
    datalist.innerHTML = "";
    if (showToast) toast("Failed to fetch models: " + e.message, false);
  }
}

document.getElementById("rephrase-fetch-models").addEventListener("click", () => fetchModels(true));

document.getElementById("rephrase-save").addEventListener("click", async () => {
  try {
    await api("PATCH", "/config/rephrase", {
      enabled: document.getElementById("rephrase-enabled").checked,
      api_url: document.getElementById("rephrase-url").value,
      api_key: document.getElementById("rephrase-key").value,
      model: document.getElementById("rephrase-model").value,
      persona: document.getElementById("rephrase-persona").value,
    });
    cfg = null;
    toast("Rephrase settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
});

document.getElementById("rephrase-test-btn").addEventListener("click", async () => {
  const text = document.getElementById("rephrase-test-input").value.trim();
  if (!text) return;
  const out = document.getElementById("rephrase-test-output");
  out.textContent = "Rephrasing...";
  try {
    const res = await api("POST", "/rephrase/test", {
      text,
      persona: document.getElementById("rephrase-persona").value,
    });
    out.textContent = res.result;
  } catch (e) {
    out.textContent = "Error: " + e.message;
  }
});

/* ── Completion ────────────────────────────────────────────────────────── */

document.getElementById("completion-save").addEventListener("click", async () => {
  try {
    await api("PATCH", "/config/completion", {
      mode: document.getElementById("completion-mode").value,
      simple_phrase: document.getElementById("completion-phrase").value,
      persona_prefix: document.getElementById("completion-prefix").value,
      temperature: parseFloat(document.getElementById("completion-temperature").value),
    });
    cfg = null;
    toast("Completion settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
});

document.getElementById("completion-test-btn").addEventListener("click", async () => {
  const out = document.getElementById("completion-test-output");
  out.textContent = "Generating quip...";
  try {
    const res = await api("POST", "/completion/test");
    out.textContent = res.result;
  } catch (e) {
    out.textContent = "Error: " + e.message;
  }
});

/* ── Personas ──────────────────────────────────────────────────────────── */

async function loadPersonas() {
  const container = document.getElementById("personas-list");
  try {
    const [personas, voices] = await Promise.all([
      api("GET", "/personas"),
      api("GET", "/voices").catch(() => []),
    ]);
    await loadConfig();
    const activePersona = cfg.rephrase.persona;
    const activeVoice = cfg.tts.voice;

    container.innerHTML = "";
    personas.forEach(p => {
      const isActive = p.name === activePersona;
      const card = document.createElement("div");
      card.className = "persona-card" + (isActive ? " persona-active" : "");

      // Header: name + badges
      const header = document.createElement("div");
      header.className = "persona-header";
      const nameSpan = document.createElement("span");
      nameSpan.className = "persona-name";
      nameSpan.textContent = p.name;
      header.appendChild(nameSpan);
      const badgeWrap = document.createElement("span");
      if (isActive) {
        const ab = document.createElement("span");
        ab.className = "persona-badge persona-badge-active";
        ab.textContent = "active";
        badgeWrap.appendChild(ab);
      }
      const tb = document.createElement("span");
      tb.className = "persona-badge " + (p.custom ? "persona-badge-custom" : "persona-badge-builtin");
      tb.textContent = p.custom ? "custom" : "built-in";
      badgeWrap.appendChild(tb);
      header.appendChild(badgeWrap);
      card.appendChild(header);

      // Prompt preview
      const promptEl = document.createElement("div");
      promptEl.className = "persona-prompt";
      promptEl.textContent = p.prompt || "(no prompt)";
      promptEl.addEventListener("click", () => promptEl.classList.toggle("expanded"));
      card.appendChild(promptEl);

      // Voice row: label + dropdown + Test + Use
      const voiceLabel = document.createElement("label");
      voiceLabel.textContent = "Voice";
      voiceLabel.style.cssText = "display:block; font-size:0.8rem; color:var(--text-muted); margin:0.5rem 0 0.25rem;";
      card.appendChild(voiceLabel);

      const row = document.createElement("div");
      row.className = "input-row";

      const voiceSel = document.createElement("select");
      voiceSel.style.flex = "1";
      // Determine which voice to pre-select: saved persona voice, or active voice, or first
      const savedVoice = p.voice || (isActive ? activeVoice : "") || (voices[0]?.name || "");
      voices.forEach(v => {
        const opt = document.createElement("option");
        opt.value = v.name;
        opt.textContent = v.name;
        if (v.name === savedVoice) opt.selected = true;
        voiceSel.appendChild(opt);
      });
      row.appendChild(voiceSel);

      const testBtn = document.createElement("button");
      testBtn.className = "btn btn-secondary btn-sm";
      testBtn.textContent = "Test";
      testBtn.addEventListener("click", async () => {
        const voice = voiceSel.value;
        if (!voice) { toast("Select a voice first", false); return; }
        testBtn.disabled = true;
        testBtn.textContent = "Playing...";
        try {
          await api("POST", `/voices/${encodeURIComponent(voice)}/test`);
          toast("Playing " + voice + "...");
        } catch (e) { toast("Test failed: " + e.message, false); }
        testBtn.disabled = false;
        testBtn.textContent = "Test";
      });
      row.appendChild(testBtn);

      const useBtn = document.createElement("button");
      useBtn.className = isActive ? "btn btn-secondary btn-sm" : "btn btn-primary btn-sm";
      useBtn.textContent = isActive ? "Active" : "Use";
      useBtn.addEventListener("click", async () => {
        const voice = voiceSel.value;
        try {
          await api("POST", `/personas/${encodeURIComponent(p.name)}/activate`, { voice });
          cfg = null;
          toast("Switched to " + p.name + (voice ? " with " + voice : ""));
          loadPersonas();
        } catch (e) { toast("Failed: " + e.message, false); }
      });
      row.appendChild(useBtn);
      card.appendChild(row);

      // Edit/Delete for custom
      if (p.custom) {
        const actions = document.createElement("div");
        actions.className = "persona-actions";

        const editBtn = document.createElement("button");
        editBtn.className = "btn btn-secondary btn-sm";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", () => toggleEdit(card, p));

        const delBtn = document.createElement("button");
        delBtn.className = "btn btn-danger btn-sm";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", () => deletePersona(p.name));

        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
        card.appendChild(actions);
      }

      container.appendChild(card);
    });
  } catch (e) {
    console.error("Personas load failed:", e);
    container.innerHTML = '<div class="card">Failed to load personas: ' + esc(e.message) + '</div>';
  }
}

function toggleEdit(card, persona) {
  let area = card.querySelector(".persona-edit-area");
  if (area) { area.remove(); return; }
  area = document.createElement("div");
  area.className = "persona-edit-area";

  const ta = document.createElement("textarea");
  ta.rows = 5;
  ta.value = persona.prompt || "";
  area.appendChild(ta);

  const saveBtn = document.createElement("button");
  saveBtn.className = "btn btn-primary btn-sm";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    try {
      await api("PUT", `/personas/${encodeURIComponent(persona.name)}`, {
        prompt: ta.value,
        trigger_word: "",
        trigger_mode: "always",
      });
      toast("Persona updated");
      loadPersonas();
    } catch (e) { toast("Save failed: " + e.message, false); }
  });
  area.appendChild(saveBtn);
  card.appendChild(area);
}

async function deletePersona(name) {
  if (!confirm('Delete persona "' + name + '"?')) return;
  try {
    await api("DELETE", `/personas/${encodeURIComponent(name)}`);
    toast("Persona deleted");
    loadPersonas();
  } catch (e) { toast("Delete failed: " + e.message, false); }
}

document.getElementById("persona-create-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("persona-new-name").value.trim();
  const prompt = document.getElementById("persona-new-prompt").value.trim();
  if (!name || !prompt) { toast("Name and prompt required", false); return; }
  try {
    await api("PUT", `/personas/${encodeURIComponent(name)}`, {
      prompt,
      trigger_word: "",
      trigger_mode: "always",
    });
    document.getElementById("persona-create-form").reset();
    toast("Persona created");
    loadPersonas();
  } catch (e) { toast("Create failed: " + e.message, false); }
});

/* ── STT ────────────────────────────────────────────────────────────────── */

async function loadSTT() {
  await loadConfig();
  const [s, n, voskModels] = await Promise.all([
    loadStatus(),
    api("GET", "/noise"),
    api("GET", "/vosk-models").catch(() => []),
  ]);

  document.getElementById("stt-ptt-key").value = cfg.stt.push_to_talk_key;
  document.getElementById("stt-toggle-key").value = cfg.stt.toggle_key;
  document.getElementById("stt-hold-mode").checked = cfg.stt.hold_mode;
  document.getElementById("stt-wakeword-enabled").checked = cfg.stt.wakeword_enabled || false;
  document.getElementById("stt-wakeword-timeout").value = cfg.stt.wakeword_timeout ?? 15;
  document.getElementById("stt-window-lock-enabled").checked = cfg.stt.window_lock_enabled ?? true;
  document.getElementById("stt-watched-processes").value = (cfg.stt.watched_processes || ["claude", "codex", "gemini"]).join(", ");
  document.getElementById("stt-watch-interval").value = cfg.stt.process_watch_interval ?? 2.0;
  document.getElementById("stt-rnnoise-vad").value = cfg.stt.rnnoise_vad_threshold ?? 70;
  document.getElementById("stt-rnnoise-grace").value = cfg.stt.rnnoise_vad_grace_ms ?? 200;
  document.getElementById("stt-rnnoise-retro").value = cfg.stt.rnnoise_retroactive_ms ?? 100;
  document.getElementById("stt-echo-cancel").checked = cfg.stt.echo_cancellation ?? false;

  // Correction settings
  document.getElementById("stt-correction-enabled").checked = cfg.correction?.enabled ?? false;
  document.getElementById("stt-correction-model").value = cfg.correction?.model ?? "llama3.2:1b";
  document.getElementById("stt-correction-timeout").value = cfg.correction?.timeout_ms ?? 1500;
  document.getElementById("stt-correction-log").checked = cfg.correction?.log_enabled ?? true;

  // Load window slots
  await loadWindowSlots();

  // Poll wake word state
  try {
    const ws = await api("GET", "/wakeword/state");
    const badge = document.getElementById("stt-wakeword-status");
    if (ws.state === "awake") {
      badge.className = "badge badge-yes";
      badge.textContent = "Awake";
    } else {
      badge.className = "badge badge-no";
      badge.textContent = "Sleeping";
    }
  } catch (e) {
    document.getElementById("stt-wakeword-status").textContent = "--";
  }
  // Populate VOSK model dropdown
  const voskSel = document.getElementById("stt-vosk-model");
  const voskInfo = document.getElementById("stt-vosk-info");
  const voskDlBtn = document.getElementById("stt-vosk-download");
  const voskDlStatus = document.getElementById("stt-vosk-download-status");
  _voskModels = voskModels;
  voskSel.innerHTML = "";
  voskModels.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.name;
    opt.textContent = m.name + (m.installed ? " (installed)" : "");
    if (m.name === cfg.stt.vosk_model) opt.selected = true;
    voskSel.appendChild(opt);
  });
  updateVoskInfo();

  // Trigger word for active persona
  const persona = cfg.rephrase.persona || "default";
  const tw = (cfg.rephrase.trigger_words || {})[persona] || "";
  const tm = (cfg.rephrase.trigger_modes || {})[persona] || "always";
  document.getElementById("stt-trigger-word").value = tw;
  document.getElementById("stt-trigger-mode").value = tm;

  renderKeywords(cfg.dictation?.keywords || {});

  document.getElementById("stt-input-group").innerHTML = badge(s.input_group, "bool");
  document.getElementById("stt-rnnoise-installed").innerHTML = badge(n.installed, "bool");
  document.getElementById("stt-rnnoise-active").innerHTML = badge(n.active, "bool");

  // Show install button when not installed, hide enable/disable
  document.getElementById("stt-noise-install").style.display = n.installed ? "none" : "";
  document.getElementById("stt-noise-enable").style.display = n.installed ? "" : "none";
  document.getElementById("stt-noise-disable").style.display = n.installed ? "" : "none";
}

let _voskModels = [];

function updateVoskInfo() {
  const voskSel = document.getElementById("stt-vosk-model");
  const voskInfo = document.getElementById("stt-vosk-info");
  const voskDlBtn = document.getElementById("stt-vosk-download");
  const sel = voskSel.value;
  const m = _voskModels.find(v => v.name === sel);
  if (m) {
    voskInfo.textContent = `WER: ${m.wer} | Size: ${m.size}` + (m.installed ? " | Installed" : " | Not downloaded");
    voskDlBtn.style.display = m.installed ? "none" : "";
  } else {
    voskInfo.textContent = "";
    voskDlBtn.style.display = "none";
  }
}

document.getElementById("stt-vosk-model").addEventListener("change", updateVoskInfo);

document.getElementById("stt-vosk-download").addEventListener("click", async () => {
  const name = document.getElementById("stt-vosk-model").value;
  const btn = document.getElementById("stt-vosk-download");
  const status = document.getElementById("stt-vosk-download-status");
  btn.disabled = true;
  btn.textContent = "Downloading...";
  status.style.display = "";
  status.textContent = "Downloading " + name + " model (this may take a while for large models)...";
  try {
    const res = await api("POST", `/vosk-models/${encodeURIComponent(name)}/download`);
    status.textContent = res.message;
    toast("Model downloaded");
    // Refresh the dropdown
    btn.textContent = "Download";
    btn.disabled = false;
    loadSTT();
  } catch (e) {
    status.textContent = "Download failed: " + e.message;
    toast("Download failed", false);
    btn.textContent = "Download";
    btn.disabled = false;
  }
});

let currentKeywords = {};

function renderKeywords(kw) {
  currentKeywords = { ...kw };
  const container = document.getElementById("stt-keywords-list");
  container.innerHTML = "";
  for (const [word, key] of Object.entries(currentKeywords)) {
    const row = document.createElement("div");
    row.className = "input-row";
    row.style.marginBottom = "0.35rem";

    const wordInput = document.createElement("input");
    wordInput.type = "text";
    wordInput.value = word;
    wordInput.readOnly = true;
    wordInput.style.flex = "1";

    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.value = key;
    keyInput.readOnly = true;
    keyInput.style.flex = "1";

    const delBtn = document.createElement("button");
    delBtn.className = "btn btn-danger btn-sm";
    delBtn.textContent = "X";
    delBtn.addEventListener("click", () => {
      delete currentKeywords[word];
      renderKeywords(currentKeywords);
    });

    row.appendChild(wordInput);
    row.appendChild(keyInput);
    row.appendChild(delBtn);
    container.appendChild(row);
  }
}

document.getElementById("stt-kw-add").addEventListener("click", () => {
  const wordEl = document.getElementById("stt-kw-new-word");
  const keyEl = document.getElementById("stt-kw-new-key");
  const word = wordEl.value.trim().toLowerCase();
  const key = keyEl.value.trim();
  if (!word || !key) { toast("Both keyword and keystroke required", false); return; }
  currentKeywords[word] = key;
  renderKeywords(currentKeywords);
  wordEl.value = "";
  keyEl.value = "";
});

document.getElementById("stt-noise-install").addEventListener("click", async () => {
  const btn = document.getElementById("stt-noise-install");
  const status = document.getElementById("stt-noise-install-status");
  btn.disabled = true;
  btn.textContent = "Building...";
  status.style.display = "";
  status.textContent = "Building RNNoise from source (this may take a minute)...";
  try {
    const res = await api("POST", "/noise/install");
    status.textContent = res.message;
    toast("RNNoise installed");
    loadSTT();
  } catch (e) {
    status.textContent = "Build failed: " + e.message;
    toast("RNNoise install failed", false);
    btn.disabled = false;
    btn.textContent = "Install RNNoise";
  }
});

document.getElementById("stt-noise-enable").addEventListener("click", async () => {
  try {
    await api("POST", "/noise/enable");
    toast("RNNoise enabled");
    loadSTT();
  } catch (e) { toast("Failed: " + e.message, false); }
});

document.getElementById("stt-noise-disable").addEventListener("click", async () => {
  try {
    await api("POST", "/noise/disable");
    toast("RNNoise disabled");
    loadSTT();
  } catch (e) { toast("Failed: " + e.message, false); }
});

document.getElementById("stt-save").addEventListener("click", async () => {
  try {
    // Save trigger word for active persona
    const persona = cfg?.rephrase?.persona || "default";
    const triggerWord = document.getElementById("stt-trigger-word").value.trim();
    const triggerMode = document.getElementById("stt-trigger-mode").value;
    await api("PATCH", `/personas/${encodeURIComponent(persona)}/trigger`, {
      trigger_word: triggerWord,
      trigger_mode: triggerMode,
    });

    await Promise.all([
      api("PATCH", "/config/stt", {
        push_to_talk_key: document.getElementById("stt-ptt-key").value,
        toggle_key: document.getElementById("stt-toggle-key").value,
        hold_mode: document.getElementById("stt-hold-mode").checked,
        vosk_model: document.getElementById("stt-vosk-model").value,
        wakeword_enabled: document.getElementById("stt-wakeword-enabled").checked,
        wakeword_timeout: parseFloat(document.getElementById("stt-wakeword-timeout").value) || 15,
        window_lock_enabled: document.getElementById("stt-window-lock-enabled").checked,
        watched_processes: document.getElementById("stt-watched-processes").value.split(",").map(s => s.trim()).filter(Boolean),
        process_watch_interval: parseFloat(document.getElementById("stt-watch-interval").value) || 2.0,
        rnnoise_vad_threshold: parseInt(document.getElementById("stt-rnnoise-vad").value) || 70,
        rnnoise_vad_grace_ms: parseInt(document.getElementById("stt-rnnoise-grace").value) || 200,
        rnnoise_retroactive_ms: parseInt(document.getElementById("stt-rnnoise-retro").value) || 100,
        echo_cancellation: document.getElementById("stt-echo-cancel").checked,
      }),
      api("PATCH", "/config/dictation", {
        keywords: currentKeywords,
      }),
      api("PATCH", "/config/correction", {
        enabled: document.getElementById("stt-correction-enabled").checked,
        model: document.getElementById("stt-correction-model").value.trim() || "llama3.2:1b",
        timeout_ms: parseInt(document.getElementById("stt-correction-timeout").value) || 1500,
        log_enabled: document.getElementById("stt-correction-log").checked,
      }),
    ]);
    cfg = null;

    // Update RNNoise filter config if active
    try {
      const noise = await api("GET", "/noise");
      if (noise.active) {
        await api("POST", "/noise/enable");  // re-deploys with new thresholds
      }
    } catch (e) { /* ignore */ }

    // Toggle AEC based on checkbox
    try {
      const aecEnabled = document.getElementById("stt-echo-cancel").checked;
      const noise = await api("GET", "/noise");
      if (aecEnabled && !noise.aec_active) {
        await api("POST", "/noise/aec/enable");
      } else if (!aecEnabled && noise.aec_active) {
        await api("POST", "/noise/aec/disable");
      }
    } catch (e) { /* ignore */ }

    // Restart STT key listener to pick up new settings
    try {
      await api("POST", "/stt/restart");
      toast("STT settings saved & listener restarted");
    } catch (e) {
      toast("STT settings saved (restart listener manually)", true);
    }
  } catch (e) { toast("Save failed: " + e.message, false); }
});

/* ── Window Lock ───────────────────────────────────────────────────────── */

async function loadWindowSlots() {
  const container = document.getElementById("stt-window-list");
  try {
    const windows = await api("GET", "/windows");
    if (windows.length === 0) {
      container.innerHTML = '<span style="font-size:0.85rem; color:var(--text-muted);">No windows registered.</span>';
      return;
    }
    container.innerHTML = "";
    windows.forEach(w => {
      const row = document.createElement("div");
      row.className = "input-row";
      row.style.marginBottom = "0.35rem";
      const aliveClass = w.alive ? "badge-yes" : "badge-no";
      const aliveText = w.alive ? "alive" : "gone";
      const processInfo = w.process ? `<span class="badge badge-num" style="font-size:0.7rem; margin-left:0.25rem;">${esc(w.process)}</span>` : "";
      row.innerHTML =
        `<span style="font-weight:600; min-width:3rem;">Slot ${esc(w.slot)}</span>` +
        `<span style="flex:1; font-size:0.85rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${esc(w.title)}">${esc(w.title)}</span>` +
        processInfo +
        `<span class="badge ${aliveClass}" style="font-size:0.75rem;">${aliveText}</span>`;
      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-danger btn-sm";
      delBtn.textContent = "X";
      delBtn.addEventListener("click", async () => {
        try {
          await api("DELETE", `/windows/${encodeURIComponent(w.slot)}`);
          toast("Window slot removed");
          loadWindowSlots();
        } catch (e) { toast("Failed: " + e.message, false); }
      });
      row.appendChild(delBtn);
      container.appendChild(row);
    });
  } catch (e) {
    container.innerHTML = '<span style="font-size:0.85rem; color:var(--text-muted);">Failed to load windows.</span>';
  }
}

document.getElementById("stt-window-register").addEventListener("click", async () => {
  const slot = document.getElementById("stt-window-slot").value.trim() || "1";
  const btn = document.getElementById("stt-window-register");
  const status = document.getElementById("stt-window-status");

  btn.disabled = true;
  status.style.display = "";

  // 3-second countdown for focus switch
  for (let i = 3; i > 0; i--) {
    status.textContent = `Focus target window... ${i}...`;
    await new Promise(r => setTimeout(r, 1000));
  }

  status.textContent = "Capturing...";
  try {
    const res = await api("POST", "/windows/register", { slot });
    status.textContent = `Registered slot ${slot}: ${res.title || "window " + res.window_id}`;
    toast("Window registered to slot " + slot);
    loadWindowSlots();
  } catch (e) {
    status.textContent = "Failed: " + e.message;
    toast("Registration failed: " + e.message, false);
  }
  btn.disabled = false;
});

document.getElementById("stt-window-clear").addEventListener("click", async () => {
  try {
    await api("DELETE", "/windows");
    toast("All windows cleared");
    loadWindowSlots();
  } catch (e) { toast("Failed: " + e.message, false); }
});

/* ── Container ──────────────────────────────────────────────────────────── */

async function loadContainer() {
  const [info, c] = await Promise.all([
    api("GET", "/container").catch(() => ({ running: false, status: "error", healthy: false, port: 11435, managed: false, models: [] })),
    loadConfig(),
  ]);

  document.getElementById("container-status").innerHTML = info.running
    ? '<span class="badge badge-yes">Running</span>'
    : '<span class="badge badge-no">' + esc(info.status) + '</span>';
  document.getElementById("container-healthy").innerHTML = badge(info.healthy, "bool");
  document.getElementById("container-port").textContent = info.port;

  document.getElementById("container-managed").checked = cfg.container?.managed ?? false;
  document.getElementById("container-gpu").checked = cfg.container?.gpu ?? true;
  document.getElementById("container-correction-model").value = cfg.container?.correction_model ?? "llama3.2:1b";
  document.getElementById("container-rephrase-model").value = cfg.container?.rephrase_model ?? "llama3.2:3b";
  document.getElementById("container-port-input").value = cfg.container?.port ?? 11435;

  // Models list
  const modelsList = document.getElementById("container-models-list");
  if (info.models && info.models.length > 0) {
    modelsList.innerHTML = info.models.map(m =>
      `<div class="status-row"><span>${esc(m.name)}</span></div>`
    ).join("");
  } else {
    modelsList.innerHTML = '<span style="font-size:0.85rem; color:var(--text-muted);">No models loaded.</span>';
  }

  // Accuracy stats
  await loadAccuracy();
}

async function loadAccuracy() {
  try {
    const [stats, recent] = await Promise.all([
      api("GET", "/accuracy/stats"),
      api("GET", "/accuracy/recent?limit=20"),
    ]);
    document.getElementById("accuracy-total").textContent = stats.total;
    document.getElementById("accuracy-changed").textContent = stats.changed;
    document.getElementById("accuracy-rate").textContent = stats.change_rate + "%";
    document.getElementById("accuracy-avg").textContent = stats.avg_latency_ms + "ms";
    document.getElementById("accuracy-p50").textContent = stats.p50_latency_ms + "ms";
    document.getElementById("accuracy-p95").textContent = stats.p95_latency_ms + "ms";

    const recentEl = document.getElementById("accuracy-recent");
    if (recent.length === 0) {
      recentEl.textContent = "No corrections logged yet.";
    } else {
      recentEl.textContent = recent.map(e => {
        const marker = e.was_changed ? "*" : " ";
        return `${marker} ${JSON.stringify(e.raw)} → ${JSON.stringify(e.corrected)}  (${e.latency_ms}ms)`;
      }).join("\n");
    }
  } catch (e) {
    document.getElementById("accuracy-total").textContent = "--";
  }
}

document.getElementById("container-start-btn").addEventListener("click", async () => {
  const btn = document.getElementById("container-start-btn");
  const status = document.getElementById("container-action-status");
  btn.disabled = true;
  btn.textContent = "Starting...";
  status.style.display = "";
  status.textContent = "Starting Ollama container...";
  try {
    const res = await api("POST", "/container/start");
    status.textContent = res.ready ? "Container started and ready." : "Container started (warming up).";
    toast("Container started");
    loadContainer();
  } catch (e) {
    status.textContent = "Failed: " + e.message;
    toast("Start failed", false);
  }
  btn.disabled = false;
  btn.textContent = "Start";
});

document.getElementById("container-stop-btn").addEventListener("click", async () => {
  try {
    await api("POST", "/container/stop");
    toast("Container stopped");
    loadContainer();
  } catch (e) { toast("Stop failed: " + e.message, false); }
});

document.getElementById("container-refresh-btn").addEventListener("click", loadContainer);

document.getElementById("container-save").addEventListener("click", async () => {
  try {
    await api("PATCH", "/config/container", {
      managed: document.getElementById("container-managed").checked,
      gpu: document.getElementById("container-gpu").checked,
      correction_model: document.getElementById("container-correction-model").value.trim() || "llama3.2:1b",
      rephrase_model: document.getElementById("container-rephrase-model").value.trim() || "llama3.2:3b",
      port: parseInt(document.getElementById("container-port-input").value) || 11435,
    });
    cfg = null;
    toast("Container settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
});

document.getElementById("container-pull-btn").addEventListener("click", async () => {
  const model = document.getElementById("container-pull-model").value.trim();
  if (!model) { toast("Enter a model name", false); return; }
  const btn = document.getElementById("container-pull-btn");
  const status = document.getElementById("container-pull-status");
  btn.disabled = true;
  btn.textContent = "Pulling...";
  status.style.display = "";
  status.textContent = `Pulling ${model}... (this may take a while)`;
  try {
    await api("POST", "/container/pull", { model });
    status.textContent = `Model ${model} pulled successfully.`;
    toast("Model pulled");
    document.getElementById("container-pull-model").value = "";
    loadContainer();
  } catch (e) {
    status.textContent = "Pull failed: " + e.message;
    toast("Pull failed", false);
  }
  btn.disabled = false;
  btn.textContent = "Pull Model";
});

document.getElementById("accuracy-refresh-btn").addEventListener("click", loadAccuracy);

document.getElementById("accuracy-clear-btn").addEventListener("click", async () => {
  try {
    await api("DELETE", "/accuracy");
    toast("Accuracy log cleared");
    loadAccuracy();
  } catch (e) { toast("Clear failed: " + e.message, false); }
});

/* ── Output ─────────────────────────────────────────────────────────────── */

async function loadOutput() {
  await loadConfig();
  document.getElementById("output-hook-mode").value = cfg.hook?.mode || "full";
}

document.getElementById("output-hook-save").addEventListener("click", async () => {
  try {
    await api("PATCH", "/config/hook", {
      mode: document.getElementById("output-hook-mode").value,
    });
    cfg = null;
    toast("Output settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
});

document.getElementById("output-test-btn").addEventListener("click", async () => {
  const text = document.getElementById("output-test-input").value.trim();
  if (!text) { toast("Paste some text first", false); return; }
  const out = document.getElementById("output-test-result");
  out.style.display = "";
  out.textContent = "Detecting...";
  try {
    const res = await api("POST", "/hook/test-options", { text });
    let result = "";
    if (res.options && res.options.length > 0) {
      result += "Detected options:\n";
      res.options.forEach(o => { result += `  ${o.num}. ${o.desc}\n`; });
      result += "\nIVR text:\n  " + (res.ivr_text || "(none)");
    } else {
      result = "No numbered options detected.";
    }
    if (res.speakable) {
      result += "\n\nSpeakable text:\n  " + res.speakable;
    }
    out.textContent = result;
  } catch (e) {
    out.textContent = "Error: " + e.message;
  }
});

/* ── Logs ───────────────────────────────────────────────────────────────── */

async function loadLogs() {
  try {
    const res = await api("GET", "/logs?lines=200");
    document.getElementById("logs-output").textContent = res.logs;
    const el = document.getElementById("logs-output");
    el.scrollTop = el.scrollHeight;
  } catch (e) {
    document.getElementById("logs-output").textContent = "Failed to load logs: " + e.message;
  }
}

document.getElementById("logs-refresh").addEventListener("click", loadLogs);
document.getElementById("logs-clear").addEventListener("click", () => {
  document.getElementById("logs-output").textContent = "";
});

/* ── Tab loaders ─────────────────────────────────────────────────────────── */

const loaders = {
  dashboard: loadDashboard,
  voice: loadVoice,
  studio: loadStudio,
  rephrase: loadRephrase,
  personas: loadPersonas,
  stt: loadSTT,
  container: loadContainer,
  output: loadOutput,
  logs: loadLogs,
};

/* ── Status polling ─────────────────────────────────────────────────────── */

setInterval(async () => {
  const activeTab = document.querySelector(".nav-item.active")?.dataset.tab;
  if (activeTab === "dashboard") loadDashboard();
  // Poll wake word state when STT tab is active
  if (activeTab === "stt") {
    try {
      const ws = await api("GET", "/wakeword/state");
      const el = document.getElementById("stt-wakeword-status");
      if (ws.state === "awake") {
        el.className = "badge badge-yes";
        el.textContent = "Awake";
      } else {
        el.className = "badge badge-no";
        el.textContent = "Sleeping";
      }
    } catch (e) { /* ignore */ }
  }
}, 5000);

/* ── Inline nav links ────────────────────────────────────────────────────── */

document.addEventListener("click", e => {
  const link = e.target.closest(".nav-link-inline");
  if (!link) return;
  e.preventDefault();
  const target = link.dataset.tab;
  if (!target) return;
  navItems.forEach(n => n.classList.remove("active"));
  tabs.forEach(t => t.classList.remove("active"));
  const navItem = document.querySelector(`.nav-item[data-tab="${target}"]`);
  if (navItem) navItem.classList.add("active");
  document.getElementById("tab-" + target).classList.add("active");
  loaders[target]?.();
});

/* ── Initial load ────────────────────────────────────────────────────────── */

loadDashboard();
