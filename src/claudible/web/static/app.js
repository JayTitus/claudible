/* Claudible Config UI */

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch("/api" + path, opts);
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err);
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
  } catch (e) {
    console.error("Dashboard load failed:", e);
  }
}

/* ── Voice ──────────────────────────────────────────────────────────────── */

let voicesData = [];

async function loadVoice() {
  if (!cfg) await loadConfig();
  try {
    voicesData = await api("GET", "/voices");
  } catch { voicesData = []; }

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
      voice: document.getElementById("voice-select").value,
      speed: parseFloat(document.getElementById("voice-speed").value),
      language: document.getElementById("voice-language").value,
      voices_dir: document.getElementById("voice-dir").value,
    });
    cfg = null; // invalidate cache
    toast("Voice settings saved");
  } catch (e) { toast("Save failed: " + e.message, false); }
});

/* ── Rephrase ──────────────────────────────────────────────────────────── */

async function loadRephrase() {
  if (!cfg) await loadConfig();
  document.getElementById("rephrase-enabled").checked = cfg.rephrase.enabled;
  document.getElementById("rephrase-url").value = cfg.rephrase.api_url;
  document.getElementById("rephrase-key").value = cfg.rephrase.api_key;

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
  } catch {}

  // Set current model in dropdown (add as option if not present)
  await fetchModels(false);
}

async function fetchModels(showToast = true) {
  const sel = document.getElementById("rephrase-model");
  try {
    const models = await api("GET", "/models");
    const current = cfg?.rephrase?.model || "";
    sel.innerHTML = "";
    let found = false;
    models.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.id;
      if (m.id === current) { opt.selected = true; found = true; }
      sel.appendChild(opt);
    });
    if (!found && current) {
      const opt = document.createElement("option");
      opt.value = current;
      opt.textContent = current + " (configured)";
      opt.selected = true;
      sel.prepend(opt);
    }
    if (showToast) toast(`Found ${models.length} models`);
  } catch (e) {
    sel.innerHTML = "";
    if (cfg?.rephrase?.model) {
      const opt = document.createElement("option");
      opt.value = cfg.rephrase.model;
      opt.textContent = cfg.rephrase.model;
      sel.appendChild(opt);
    }
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
    const personas = await api("GET", "/personas");
    container.innerHTML = "";
    personas.forEach(p => {
      const card = document.createElement("div");
      card.className = "persona-card";
      const badgeCls = p.custom ? "persona-badge-custom" : "persona-badge-builtin";
      const badgeText = p.custom ? "custom" : "built-in";
      card.innerHTML = `
        <div class="persona-header">
          <span class="persona-name">${esc(p.name)}</span>
          <span class="persona-badge ${badgeCls}">${badgeText}</span>
        </div>
        <div class="form-group" style="margin: 0.5rem 0 0.25rem;">
          <label>Trigger Word</label>
          <div class="input-row">
            <input type="text" class="persona-trigger" value="${esc(p.trigger_word)}" placeholder="(none)">
            <select class="persona-trigger-mode">
              <option value="always"${p.trigger_mode === "always" ? " selected" : ""}>Always listening</option>
              <option value="ptt"${p.trigger_mode === "ptt" ? " selected" : ""}>PTT only</option>
            </select>
            <button class="btn btn-secondary btn-sm persona-trigger-save">Save</button>
          </div>
        </div>
        <div class="persona-prompt" data-name="${esc(p.name)}">${esc(p.prompt)}</div>
      `;
      // Trigger word + mode save
      card.querySelector(".persona-trigger-save").addEventListener("click", async () => {
        const tw = card.querySelector(".persona-trigger").value;
        const tm = card.querySelector(".persona-trigger-mode").value;
        try {
          await api("PATCH", `/personas/${encodeURIComponent(p.name)}/trigger`, { trigger_word: tw, trigger_mode: tm });
          toast("Trigger settings saved");
        } catch (e) { toast("Save failed: " + e.message, false); }
      });
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
      // Toggle expand on click
      const promptEl = card.querySelector(".persona-prompt");
      promptEl.addEventListener("click", () => promptEl.classList.toggle("expanded"));
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = '<div class="card">Failed to load personas</div>';
  }
}

function toggleEdit(card, persona) {
  let area = card.querySelector(".persona-edit-area");
  if (area) { area.remove(); return; }
  area = document.createElement("div");
  area.className = "persona-edit-area";
  area.innerHTML = `
    <textarea rows="5">${esc(persona.prompt)}</textarea>
    <button class="btn btn-primary btn-sm">Save</button>
  `;
  area.querySelector("button").addEventListener("click", async () => {
    const newPrompt = area.querySelector("textarea").value;
    const tw = card.querySelector(".persona-trigger").value;
    try {
      await api("PUT", `/personas/${encodeURIComponent(persona.name)}`, { prompt: newPrompt, trigger_word: tw });
      toast("Persona updated");
      loadPersonas();
    } catch (e) { toast("Save failed: " + e.message, false); }
  });
  card.appendChild(area);
}

async function deletePersona(name) {
  if (!confirm(`Delete persona "${name}"?`)) return;
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
  const trigger = document.getElementById("persona-new-trigger").value.trim();
  const triggerMode = document.getElementById("persona-new-trigger-mode").value;
  if (!name || !prompt) { toast("Name and prompt required", false); return; }
  try {
    await api("PUT", `/personas/${encodeURIComponent(name)}`, { prompt, trigger_word: trigger, trigger_mode: triggerMode });
    document.getElementById("persona-create-form").reset();
    toast("Persona created");
    loadPersonas();
  } catch (e) { toast("Create failed: " + e.message, false); }
});

/* ── STT ────────────────────────────────────────────────────────────────── */

async function loadSTT() {
  if (!cfg) await loadConfig();
  const [s, n] = await Promise.all([loadStatus(), api("GET", "/noise")]);

  document.getElementById("stt-ptt-key").value = cfg.stt.push_to_talk_key;
  document.getElementById("stt-toggle-key").value = cfg.stt.toggle_key;
  document.getElementById("stt-hold-mode").checked = cfg.stt.hold_mode;
  document.getElementById("stt-vosk-model").value = cfg.stt.vosk_model;
  document.getElementById("stt-dictation-path").value = cfg.stt.nerd_dictation_path;
  renderKeywords(cfg.dictation?.keywords || {});

  document.getElementById("stt-input-group").innerHTML = badge(s.input_group, "bool");
  document.getElementById("stt-rnnoise-installed").innerHTML = badge(n.installed, "bool");
  document.getElementById("stt-rnnoise-active").innerHTML = badge(n.active, "bool");

  // Show install button when not installed, hide enable/disable
  document.getElementById("stt-noise-install").style.display = n.installed ? "none" : "";
  document.getElementById("stt-noise-enable").style.display = n.installed ? "" : "none";
  document.getElementById("stt-noise-disable").style.display = n.installed ? "" : "none";
}

let currentKeywords = {};

function renderKeywords(kw) {
  currentKeywords = { ...kw };
  const container = document.getElementById("stt-keywords-list");
  container.innerHTML = "";
  for (const [word, key] of Object.entries(currentKeywords)) {
    const row = document.createElement("div");
    row.className = "input-row";
    row.style.marginBottom = "0.35rem";
    row.innerHTML = `
      <input type="text" value="${esc(word)}" style="flex:1" readonly>
      <input type="text" value="${esc(key)}" style="flex:1" readonly>
      <button class="btn btn-danger btn-sm">X</button>
    `;
    row.querySelector("button").addEventListener("click", () => {
      delete currentKeywords[word];
      renderKeywords(currentKeywords);
    });
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

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

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

/* ── Initial load ────────────────────────────────────────────────────────── */

loadDashboard();
