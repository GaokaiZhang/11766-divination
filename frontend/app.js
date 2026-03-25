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
  appendSystemNote(`⚠ ${msg}`);
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
  btn.disabled = true;
  btn.textContent = "Reading the signs…";

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
    btn.textContent = "Begin Reading";
  }
});

// ── Clarification submit ───────────────────────────────────────────────────
document.getElementById("btn-clarify-submit").addEventListener("click", async () => {
  const answer = document.getElementById("clarify-answer").value.trim();
  if (!answer) return;

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
  }
});

// ── Reading display helpers ─────────────────────────────────────────────────
function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

function renderTarotReading(raw, summary) {
  const cards = raw.cards || [];
  const positions = raw.positions || [];
  let html = '<div class="reading-cards">';
  cards.forEach((card, i) => {
    const orient = card.is_reversed ? "reversed" : "upright";
    const orientLabel = card.is_reversed ? "↓ Reversed" : "↑ Upright";
    const pos = positions[i] || `Card ${i+1}`;
    html += `<div class="tarot-card ${orient}">
      <div class="card-position">${esc(pos)}</div>
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
    if (v === 7 || v === 9) return isChanging ? "———o———" : "—————————";
    return isChanging ? "——— x ———" : "———   ———";
  }).reverse();

  let html = `<div class="iching-hexagram">`;
  html += `<div><div class="hex-unicode">${esc(primary.unicode || "")}</div>`;
  html += `<div class="hex-name">#${primary.number} ${esc(primary.chinese || "")} (${esc(primary.pinyin || "")})</div>`;
  html += `<div class="hex-english">${esc(primary.english || "")}</div></div>`;
  html += `<div class="hex-lines">`;
  lineSymbols.forEach(l => { html += `<div class="hex-line">${l}</div>`; });
  html += `</div>`;
  if (transformed) {
    html += `<div class="hex-arrow">⟶</div>`;
    html += `<div class="hex-transform">`;
    html += `<div class="hex-unicode">${esc(transformed.unicode || "")}</div>`;
    html += `<div class="hex-name">#${transformed.number} ${esc(transformed.chinese || "")}</div>`;
    html += `<div class="hex-english">${esc(transformed.english || "")}</div>`;
    html += `</div>`;
  }
  html += `</div>`;
  html += `<pre class="reading-text">${esc(summary)}</pre>`;
  return html;
}

function renderBaziReading(raw, summary) {
  return `<pre class="reading-text">${esc(summary)}</pre>`;
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

  // Reconstruct full conversation: user question → assistant reply
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

  const indicator = appendMessage("assistant", "…");
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
  document.getElementById("btn-end-session").disabled = true;
});
