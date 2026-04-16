// Use relative URLs so the frontend works regardless of how the page is
// reached (localhost, a tunneled URL, a different host). The backend serves
// the frontend itself, so same-origin fetches always target the right API.
const API = "";

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

// ── Ambient particle background (theme-aware) ─────────────────────────────
const BG = (function initBackground() {
  const canvas = document.getElementById("bg-canvas");
  if (!canvas) return { setTheme() {} };
  const ctx = canvas.getContext("2d");
  if (!ctx) return { setTheme() {} };
  let w, h, particles;

  // Theme palettes: each has particle colors + optional floating glyphs
  const THEMES = {
    default: {
      colors: ["155,127,212", "107,184,196", "201,168,76"],
      glyphs: ["\u2726", "\u2727", "\u00B7"],
    },
    tarot: {
      colors: ["155,127,212", "180,140,255", "120,100,200"],
      glyphs: ["\u2721", "\u2726", "\u2605", "\u263D", "\u2600"],
    },
    bazi: {
      colors: ["110,207,122", "232,116,97", "212,168,76", "196,196,216", "92,184,214"],
      glyphs: ["\u6728", "\u706B", "\u571F", "\u91D1", "\u6C34"],
    },
    iching: {
      colors: ["107,184,196", "140,200,210", "80,160,180"],
      glyphs: ["\u2630", "\u2631", "\u2632", "\u2633", "\u2634", "\u2635", "\u2636", "\u2637"],
    },
  };

  let currentTheme = "default";

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }

  function createParticles() {
    const theme = THEMES[currentTheme] || THEMES.default;
    const count = Math.min(Math.floor((w * h) / 18000), 80);
    particles = Array.from({ length: count }, () => {
      const colorStr = theme.colors[Math.floor(Math.random() * theme.colors.length)];
      // ~15% of particles are glyphs
      const isGlyph = Math.random() < 0.15 && theme.glyphs.length > 0;
      return {
        x: Math.random() * w,
        y: Math.random() * h,
        r: isGlyph ? 0 : (Math.random() * 1.5 + 0.4),
        dx: (Math.random() - 0.5) * 0.15,
        dy: (Math.random() - 0.5) * 0.12,
        alpha: Math.random() * 0.4 + 0.1,
        pulse: Math.random() * Math.PI * 2,
        color: colorStr,
        glyph: isGlyph ? theme.glyphs[Math.floor(Math.random() * theme.glyphs.length)] : null,
        fontSize: isGlyph ? (Math.random() * 12 + 10) : 0,
      };
    });
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
      if (p.glyph) {
        ctx.font = `${p.fontSize}px serif`;
        ctx.fillStyle = `rgba(${p.color}, ${a * 0.7})`;
        ctx.fillText(p.glyph, p.x, p.y);
      } else {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${p.color}, ${a})`;
        ctx.fill();
      }
    }
    requestAnimationFrame(draw);
  }

  resize();
  createParticles();
  draw();
  window.addEventListener("resize", () => { resize(); createParticles(); });

  return {
    setTheme(name) {
      if (name !== currentTheme) {
        currentTheme = name;
        createParticles();
      }
    }
  };
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

// Render a safe markdown subset into an assistant bubble. User messages
// still use textContent — no rendering trust extended to user input.
function renderAssistantMarkdown(el, text) {
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
    el.textContent = text;
    return;
  }
  const html = marked.parse(text, { breaks: true, gfm: true });
  el.innerHTML = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "p", "br", "strong", "em", "b", "i", "u", "s", "code", "pre",
      "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "hr",
    ],
    ALLOWED_ATTR: [],
  });
}

function appendMessage(role, content) {
  const container = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = `message ${role}`;
  if (role === "assistant") {
    renderAssistantMarkdown(div, content);
  } else {
    div.textContent = content;
  }
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
  birthFields.style.display = system === "bazi" ? "" : "none";
  BG.setTheme(system);
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

  // Suit symbols for minor arcana
  const suitSymbol = { wands: "\u269C", cups: "\u2661", swords: "\u2694", pentacles: "\u2B21" };
  function cardSymbol(name) {
    const lower = name.toLowerCase();
    for (const [suit, sym] of Object.entries(suitSymbol)) {
      if (lower.includes(suit)) return sym;
    }
    return "\u2726"; // Major Arcana
  }

  // Tarot spread figure: three-card arc with decorative frame
  let html = '<div class="tarot-spread-figure">';
  html += '<div class="spread-label">Three-Card Spread</div>';
  html += '<div class="spread-arc">';
  cards.forEach((card, i) => {
    const orient = card.is_reversed ? "reversed" : "upright";
    const orientLabel = card.is_reversed ? "\u2193 Reversed" : "\u2191 Upright";
    const pos = positions[i] || `Card ${i+1}`;
    const sym = cardSymbol(card.name);
    const romanNum = ["\u2160", "\u2161", "\u2162"][i] || "";
    html += `<div class="tarot-card ${orient}">
      <div class="card-position">${esc(pos)}</div>
      <div class="card-numeral">${romanNum}</div>
      <div class="card-arcana">${sym}</div>
      <div class="card-name">${esc(card.name)}</div>
      <div class="card-orient">${orientLabel}</div>
    </div>`;
  });
  html += '</div>'; // spread-arc
  html += '<div class="spread-timeline"><span>Past</span><span class="spread-arrow">\u2192</span><span>Present</span><span class="spread-arrow">\u2192</span><span>Future</span></div>';
  html += '</div>'; // tarot-spread-figure
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

  // Five Elements cycle figure — highlight active elements
  const activeElements = new Set();
  eightChar.forEach(([sIdx, bIdx]) => {
    const sEl = STEM_EL[sIdx].split(" ")[1];  // "Yang Wood" -> "Wood"
    const bEl = BRANCH_EL[bIdx].split(" ")[1];
    activeElements.add(sEl);
    activeElements.add(bEl);
  });
  const elems = [
    { name: "Wood",  ch: "\u6728", cls: "elem-wood" },
    { name: "Fire",  ch: "\u706B", cls: "elem-fire" },
    { name: "Earth", ch: "\u571F", cls: "elem-earth" },
    { name: "Metal", ch: "\u91D1", cls: "elem-metal" },
    { name: "Water", ch: "\u6C34", cls: "elem-water" },
  ];
  html += '<div class="wuxing-cycle">';
  html += '<div class="wuxing-title">Five Elements</div>';
  html += '<div class="wuxing-ring">';
  elems.forEach((el, i) => {
    const active = activeElements.has(el.name) ? "wuxing-active" : "";
    html += `<div class="wuxing-node ${el.cls} ${active}" style="--i:${i}">`;
    html += `<span class="wuxing-ch">${el.ch}</span>`;
    html += `<span class="wuxing-en">${el.name}</span>`;
    html += `</div>`;
  });
  // Generating cycle arrows (Wood->Fire->Earth->Metal->Water->Wood)
  html += '<svg class="wuxing-arrows" viewBox="0 0 120 120">';
  // Generating cycle (outer, clockwise): green dashed
  const pts = [[60,8],[108,42],[93,105],[27,105],[12,42]]; // pentagon vertices
  for (let i = 0; i < 5; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % 5];
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    html += `<line x1="${x1}" y1="${y1}" x2="${mx}" y2="${my}" class="wuxing-gen"/>`;
  }
  html += '</svg>';
  html += '</div>'; // wuxing-ring
  html += '</div>'; // wuxing-cycle

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

  // Update system icon, label, and background theme
  const meta = SYSTEM_META[state.system] || { icon: "", label: "" };
  document.getElementById("reading-system-icon").textContent = meta.icon;
  document.getElementById("chat-system-label").textContent = meta.label;
  BG.setTheme(state.system);

  // Reconstruct full conversation: user question -> assistant reply
  if (data.initial_question) {
    state.messages.push({ role: "user", content: data.initial_question });
  }
  state.messages.push({ role: "assistant", content: data.reply });
  appendMessage("assistant", data.reply);

  showScreen("screen-chat");
}

// ── Send a chat message (streaming) ────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById("chat-input");
  const btn = document.getElementById("btn-send");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  btn.disabled = true;
  state.messages.push({ role: "user", content: text });
  appendMessage("user", text);

  const bubble = appendMessage("assistant", "\u2026");
  bubble.classList.add("typing");

  const messagesContainer = document.getElementById("chat-messages");
  let accumulated = "";
  let gotFirstChunk = false;

  try {
    const res = await fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id:         state.userId,
        system:          state.system,
        result_raw:      state.readingRaw,
        symbols:         state.readingSymbols,
        reading_summary: state.readingSummary,
        messages:        state.messages,
      }),
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(errText || `Server error (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let scrollPinned = true;

    // Only auto-scroll if user hasn't scrolled up manually.
    messagesContainer.addEventListener("scroll", () => {
      const nearBottom =
        messagesContainer.scrollHeight -
          messagesContainer.scrollTop -
          messagesContainer.clientHeight < 60;
      scrollPinned = nearBottom;
    }, { passive: true });

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      if (!chunk) continue;
      accumulated += chunk;
      if (!gotFirstChunk) {
        gotFirstChunk = true;
        bubble.classList.remove("typing");
        bubble.classList.add("streaming");
      }
      renderAssistantMarkdown(bubble, accumulated);
      if (scrollPinned) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }
    }

    bubble.classList.remove("streaming");
    // Final render with any trailing buffered bytes
    renderAssistantMarkdown(bubble, accumulated);
    state.messages.push({ role: "assistant", content: accumulated });
  } catch (err) {
    bubble.remove();
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
  document.getElementById("btn-end-session").textContent = "End Session";
  document.getElementById("btn-end-session").classList.remove("btn-session-done");
  BG.setTheme(document.getElementById("input-system").value);
  showScreen("screen-input");
});
