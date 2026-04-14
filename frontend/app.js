const API = "http://localhost:8000";

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  userId: null,
  system: "tarot",
  readingRaw: null,
  readingSymbols: [],   // symbols for RAG query expansion on follow-up turns
  readingSummary: "",    // summary for context on follow-up turns
  messages: [],          // [{role, content}] conversation history
};

// ── System metadata ────────────────────────────────────────────────────────
const SYSTEM_META = {
  tarot:  { icon: "\u2721", label: "Tarot \u2014 Three-Card Spread" },
  bazi:   { icon: "\u2697", label: "Bazi \u2014 Four Pillars of Destiny" },
  iching: { icon: "\u2637", label: "I Ching \u2014 Book of Changes" },
};

// ── Ambient particle background ────────────────────────────────────────────
(function initBackground() {
  const canvas = document.getElementById("bg-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  let w, h, particles;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }

  function createParticles() {
    const count = Math.min(Math.floor((w * h) / 18000), 80);
    particles = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.5 + 0.4,
      dx: (Math.random() - 0.5) * 0.15,
      dy: (Math.random() - 0.5) * 0.12,
      alpha: Math.random() * 0.5 + 0.15,
      pulse: Math.random() * Math.PI * 2,
    }));
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    for (const p of particles) {
      p.x += p.dx;
      p.y += p.dy;
      p.pulse += 0.008;
      if (p.x < -10) p.x = w + 10;
      if (p.x > w + 10) p.x = -10;
      if (p.y < -10) p.y = h + 10;
      if (p.y > h + 10) p.y = -10;

      const a = p.alpha * (0.6 + 0.4 * Math.sin(p.pulse));
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(155, 127, 212, ${a})`;
      ctx.fill();
    }
    requestAnimationFrame(draw);
  }

  resize();
  createParticles();
  draw();
  window.addEventListener("resize", () => { resize(); createParticles(); });
})();

// ── Copy title text for glow effect ────────────────────────────────────────
document.querySelectorAll(".title-glow").forEach(el => {
  el.setAttribute("data-text", el.textContent);
});

// ── Screen helpers ─────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.getElementById(id).classList.add("active");
}

function appendMessage(role, content) {
  const container = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = content;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function appendSystemNote(text) {
  const container = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = "message system-note";
  div.textContent = text;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function showError(msg) {
  appendSystemNote("\u26A0 " + msg);
}

// ── API helper with error handling ─────────────────────────────────────────
async function apiFetch(endpoint, body) {
  try {
    const res = await fetch(`${API}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error (${res.status})`);
    }
    return await res.json();
  } catch (e) {
    if (e.name === "TypeError" && e.message.includes("fetch")) {
      throw new Error("Cannot reach the server. Is the backend running?");
    }
    throw e;
  }
}

// ── User identity (persists across page loads via localStorage) ────────────
function getUserId() {
  let id = localStorage.getItem("divination_user_id");
  if (!id) {
    id = "user_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("divination_user_id", id);
  }
  return id;
}

// ── Show/hide birth fields based on selected system ────────────────────────
const systemSelect = document.getElementById("input-system");
const birthFields = document.getElementById("birth-fields");

function updateBirthFieldVisibility() {
  const system = systemSelect.value;
  if (system === "bazi") {
    birthFields.style.display = "";
  } else {
    birthFields.style.display = "none";
  }
}

systemSelect.addEventListener("change", updateBirthFieldVisibility);
updateBirthFieldVisibility();

// ── Input form submit ──────────────────────────────────────────────────────
document.getElementById("form-input").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector("button[type=submit]");
  const btnText = btn.querySelector(".btn-text");
  const btnLoading = btn.querySelector(".btn-loading");
  btn.disabled = true;
  btnText.style.display = "none";
  btnLoading.style.display = "";

  state.userId = getUserId();
  state.system = document.getElementById("input-system").value;

  const body = {
    user_id:        state.userId,
    name:           document.getElementById("input-name").value.trim(),
    birth_date:     document.getElementById("input-birth-date").value || null,
    birth_time:     document.getElementById("input-birth-time").value || null,
    birth_location: document.getElementById("input-birth-location").value.trim() || null,
    question:       document.getElementById("input-question").value.trim() || null,
    system:         state.system,
  };

  try {
    const data = await apiFetch("/start", body);
    if (data.needs_clarification) {
      document.getElementById("clarify-question").textContent = data.question;
      showScreen("screen-clarify");
    } else {
      initChatScreen(data);
    }
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btnText.style.display = "";
    btnLoading.style.display = "none";
  }
});

// ── Clarification submit ───────────────────────────────────────────────────
document.getElementById("btn-clarify-submit").addEventListener("click", async () => {
  const answer = document.getElementById("clarify-answer").value.trim();
  if (!answer) return;
  const btn = document.getElementById("btn-clarify-submit");
  btn.disabled = true;
  btn.textContent = "Reading...";

  const timeMap = {
    morning: "07:00", dawn: "04:00", afternoon: "13:00",
    evening: "18:00", night: "21:00", midnight: "23:30",
  };
  const normalized = answer.toLowerCase();
  const mappedTime = timeMap[normalized] || answer;

  const name = document.getElementById("input-name").value.trim();
  const body = {
    user_id:        state.userId,
    name,
    birth_date:     document.getElementById("input-birth-date").value || null,
    birth_time:     mappedTime,
    birth_location: document.getElementById("input-birth-location").value.trim() || null,
    question:       document.getElementById("input-question").value.trim() || null,
    system:         state.system,
  };

  try {
    const data = await apiFetch("/start", body);
    initChatScreen(data);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Continue";
  }
});

// ── Reading display helpers ─────────────────────────────────────────────────
function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

function renderTarotReading(raw, summary) {
  const cards = raw.cards || [];
  const positions = raw.positions || [];

  // Suit symbols for minor arcana (using widely supported characters)
  const suitSymbol = { wands: "\u269C", cups: "\u2661", swords: "\u2694", pentacles: "\u2B21" };
  function cardSymbol(name) {
    const lower = name.toLowerCase();
    for (const [suit, sym] of Object.entries(suitSymbol)) {
      if (lower.includes(suit)) return sym;
    }
    return "\u2726"; // Major Arcana
  }

  let html = '<div class="reading-cards">';
  cards.forEach((card, i) => {
    const orient = card.is_reversed ? "reversed" : "upright";
    const orientLabel = card.is_reversed ? "\u2193 Reversed" : "\u2191 Upright";
    const pos = positions[i] || `Card ${i+1}`;
    const sym = cardSymbol(card.name);
    html += `<div class="tarot-card ${orient}">
      <div class="card-position">${esc(pos)}</div>
      <div class="card-arcana">${sym}</div>
      <div class="card-name">${esc(card.name)}</div>
      <div class="card-orient">${orientLabel}</div>
    </div>`;
  });
  html += '</div>';
  html += `<pre class="reading-text">${esc(summary)}</pre>`;
  return html;
}

function renderIChingReading(raw, summary) {
  const primary = raw.primary || {};
  const lines = raw.lines || [];
  const changing = raw.changing || [];
  const transformed = raw.transformed;

  const lineSymbols = lines.map((v, i) => {
    const pos = i + 1;
    const isChanging = changing.includes(pos);
    const yang = (v === 7 || v === 9);
    const symbol = yang
      ? (isChanging ? "\u2501\u2501\u2501 \u25CB \u2501\u2501\u2501" : "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
      : (isChanging ? "\u2501\u2501\u2501 \u00D7 \u2501\u2501\u2501" : "\u2501\u2501\u2501   \u2501\u2501\u2501");
    return { symbol, isChanging };
  }).reverse();

  let html = `<div class="iching-hexagram">`;

  // Primary hexagram block
  html += `<div class="hex-block">`;
  html += `<div class="hex-unicode">${esc(primary.unicode || "")}</div>`;
  html += `<div class="hex-name">#${primary.number} ${esc(primary.chinese || "")} (${esc(primary.pinyin || "")})</div>`;
  html += `<div class="hex-english">${esc(primary.english || "")}</div>`;
  html += `</div>`;

  // Line diagram
  html += `<div class="hex-lines">`;
  lineSymbols.forEach(l => {
    const cls = l.isChanging ? "hex-line changing" : "hex-line";
    html += `<div class="${cls}">${l.symbol}</div>`;
  });
  html += `</div>`;

  // Transformed hexagram
  if (transformed) {
    html += `<div class="hex-arrow">\u2192</div>`;
    html += `<div class="hex-block hex-transform">`;
    html += `<div class="hex-unicode">${esc(transformed.unicode || "")}</div>`;
    html += `<div class="hex-name">#${transformed.number} ${esc(transformed.chinese || "")}</div>`;
    html += `<div class="hex-english">${esc(transformed.english || "")}</div>`;
    html += `</div>`;
  }

  html += `</div>`; // end iching-hexagram

  if (changing.length > 0) {
    html += `<div class="changing-lines-note">Changing lines: ${changing.join(", ")}</div>`;
  }

  html += `<pre class="reading-text">${esc(summary)}</pre>`;
  return html;
}

function renderBaziReading(raw, summary) {
  const eightChar = raw.eight_char || [];
  const labels = raw.pillar_labels || ["Year", "Month", "Day", "Hour"];
  const hourEstimated = raw.hour_estimated;

  // Stem / Branch lookup tables (must match backend)
  const STEMS    = ["\u7532","\u4E59","\u4E19","\u4E01","\u620A","\u5DF1","\u5E9A","\u8F9B","\u58EC","\u7678"];
  const STEM_PY  = ["Ji\u01CE","Y\u01D0","B\u01D0ng","D\u012Bng","W\u00F9","J\u01D0","G\u0113ng","X\u012Bn","R\u00E9n","Gu\u01D0"];
  const STEM_EL  = ["Yang Wood","Yin Wood","Yang Fire","Yin Fire","Yang Earth",
                    "Yin Earth","Yang Metal","Yin Metal","Yang Water","Yin Water"];
  const BRANCHES    = ["\u5B50","\u4E11","\u5BC5","\u536F","\u8FB0","\u5DF3","\u5348","\u672A","\u7533","\u9149","\u620C","\u4EA5"];
  const BRANCH_PY   = ["Z\u01D0","Ch\u01D2u","Y\u00EDn","M\u01CEo","Ch\u00E9n","S\u00EC","W\u01D4","W\u00E8i","Sh\u0113n","Y\u01D2u","X\u016B","H\u00E0i"];
  const BRANCH_EL   = ["Yang Water","Yin Earth","Yang Wood","Yin Wood","Yang Earth","Yin Fire",
                        "Yang Fire","Yin Earth","Yang Metal","Yin Metal","Yang Earth","Yin Water"];

  function elemClass(el) {
    if (el.includes("Wood"))  return "elem-wood";
    if (el.includes("Fire"))  return "elem-fire";
    if (el.includes("Earth")) return "elem-earth";
    if (el.includes("Metal")) return "elem-metal";
    if (el.includes("Water")) return "elem-water";
    return "";
  }

  if (eightChar.length < 4) {
    return `<pre class="reading-text">${esc(summary)}</pre>`;
  }

  // Day Master
  const dayMasterEl = STEM_EL[eightChar[2][0]];

  let html = '<div class="bazi-chart">';

  // Column headers
  html += '<div class="bazi-row bazi-headers">';
  labels.forEach((label, i) => {
    const cls = i === 2 ? "bazi-col day-pillar" : "bazi-col";
    const extra = (i === 3 && hourEstimated) ? '<span class="bazi-estimated">~est</span>' : '';
    html += `<div class="${cls}"><span class="bazi-label">${esc(label)}${extra}</span></div>`;
  });
  html += '</div>';

  // Stem row
  html += '<div class="bazi-row">';
  eightChar.forEach(([sIdx], i) => {
    const el = STEM_EL[sIdx];
    const cls = i === 2 ? "bazi-col bazi-cell day-pillar" : "bazi-col bazi-cell";
    html += `<div class="${cls} ${elemClass(el)}">
      <span class="bazi-char">${esc(STEMS[sIdx])}</span>
      <span class="bazi-pinyin">${esc(STEM_PY[sIdx])}</span>
      <span class="bazi-element">${esc(el)}</span>
    </div>`;
  });
  html += '</div>';

  // Branch row
  html += '<div class="bazi-row">';
  eightChar.forEach(([, bIdx], i) => {
    const el = BRANCH_EL[bIdx];
    const cls = i === 2 ? "bazi-col bazi-cell day-pillar" : "bazi-col bazi-cell";
    html += `<div class="${cls} ${elemClass(el)}">
      <span class="bazi-char">${esc(BRANCHES[bIdx])}</span>
      <span class="bazi-pinyin">${esc(BRANCH_PY[bIdx])}</span>
      <span class="bazi-element">${esc(el)}</span>
    </div>`;
  });
  html += '</div>';

  html += '</div>'; // end bazi-chart

  // Day Master badge
  html += `<div class="bazi-day-master ${elemClass(dayMasterEl)}">`;
  html += `Day Master: <strong>${esc(dayMasterEl)}</strong>`;
  html += '</div>';

  html += `<pre class="reading-text">${esc(summary)}</pre>`;
  return html;
}

function renderReading(system, raw, summary) {
  if (system === "tarot") return renderTarotReading(raw, summary);
  if (system === "iching") return renderIChingReading(raw, summary);
  if (system === "bazi") return renderBaziReading(raw, summary);
  return `<pre class="reading-text">${esc(summary)}</pre>`;
}

// ── Initialise the chat screen with a reading ──────────────────────────────
function initChatScreen(data) {
  const display = document.getElementById("reading-display");
  display.innerHTML = renderReading(state.system, data.reading_raw, data.reading_summary);
  state.readingRaw = data.reading_raw;
  state.readingSymbols = data.symbols || [];
  state.readingSummary = data.reading_summary || "";
  state.messages = [];

  // Update system icon and label in chat header
  const meta = SYSTEM_META[state.system] || { icon: "", label: "" };
  document.getElementById("reading-system-icon").textContent = meta.icon;
  document.getElementById("chat-system-label").textContent = meta.label;

  // Reconstruct full conversation: user question -> assistant reply
  if (data.initial_question) {
    state.messages.push({ role: "user", content: data.initial_question });
  }
  state.messages.push({ role: "assistant", content: data.reply });
  appendMessage("assistant", data.reply);

  showScreen("screen-chat");
}

// ── Send a chat message ────────────────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById("chat-input");
  const btn = document.getElementById("btn-send");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  btn.disabled = true;
  state.messages.push({ role: "user", content: text });
  appendMessage("user", text);

  const indicator = appendMessage("assistant", "\u2026");
  indicator.classList.add("typing");

  try {
    const data = await apiFetch("/chat", {
      user_id:         state.userId,
      system:          state.system,
      result_raw:      state.readingRaw,
      symbols:         state.readingSymbols,
      reading_summary: state.readingSummary,
      messages:        state.messages,
    });
    indicator.classList.remove("typing");
    indicator.textContent = data.reply;
    state.messages.push({ role: "assistant", content: data.reply });
  } catch (err) {
    indicator.remove();
    // Remove the user message that failed from both state and DOM
    state.messages.pop();
    const msgs = document.getElementById("chat-messages");
    const lastUserMsg = msgs.querySelector(".message.user:last-of-type");
    if (lastUserMsg) lastUserMsg.remove();
    showError(err.message);
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

document.getElementById("btn-send").addEventListener("click", sendMessage);
document.getElementById("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ── End session ────────────────────────────────────────────────────────────
document.getElementById("btn-end-session").addEventListener("click", async () => {
  if (state.messages.length === 0) return;

  try {
    const data = await apiFetch("/end-session", {
      user_id: state.userId, messages: state.messages,
    });
    const themes = data.extracted_themes || [];
    const themeText = themes.length
      ? `Session saved. Themes noted: ${themes.join(", ")}.`
      : "Session saved.";
    appendSystemNote(themeText);
  } catch (err) {
    showError(err.message);
  }
  const endBtn = document.getElementById("btn-end-session");
  endBtn.disabled = true;
  endBtn.textContent = "\u2713 Session Saved";
  endBtn.classList.add("btn-session-done");
});

// ── New reading ───────────────────────────────────────────────────────────
document.getElementById("btn-new-reading").addEventListener("click", () => {
  state.readingRaw = null;
  state.readingSymbols = [];
  state.readingSummary = "";
  state.messages = [];
  document.getElementById("chat-messages").innerHTML = "";
  document.getElementById("reading-display").innerHTML = "";
  document.getElementById("btn-end-session").disabled = false;
  showScreen("screen-input");
});
