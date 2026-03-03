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
    document.getElementById("dash-input").innerHTML = badge(s.input_group, "bool");
    document.getElementById("dash-rnnoise").innerHTML = badge(s.rnnoise_active, "bool");

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
      voices_dir: document.getElementById("voice-dir").value,
    });
    cfg = null;
    toast("Voice settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
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
  document.getElementById("stt-dictation-path").value = cfg.stt.nerd_dictation_path;

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
        nerd_dictation_path: document.getElementById("stt-dictation-path").value,
      }),
      api("PATCH", "/config/dictation", {
        keywords: currentKeywords,
      }),
    ]);
    cfg = null;
    toast("STT settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
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
  rephrase: loadRephrase,
  personas: loadPersonas,
  stt: loadSTT,
  logs: loadLogs,
};

/* ── Status polling ─────────────────────────────────────────────────────── */

setInterval(async () => {
  const activeTab = document.querySelector(".nav-item.active")?.dataset.tab;
  if (activeTab === "dashboard") loadDashboard();
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
