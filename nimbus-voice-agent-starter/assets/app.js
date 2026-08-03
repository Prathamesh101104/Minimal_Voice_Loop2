// Core: catalog loading, shared layout (nav/footer), icons, and small helpers.

// Resolve assets/data relative to THIS module, so the site works no matter
// which subpath it is mounted at (root, a nested folder, Live Preview, etc.).
const asset = (rel) => new URL(rel, import.meta.url).href;

const NAV_LINKS = [
  { href: "products.html", label: "Products" },
  { href: "pricing.html", label: "Pricing" },
  { href: "support.html", label: "Support" },
  { href: "about.html", label: "Company" },
  { href: "playground.html", label: "Playground" },
];

// ---- Inline SVG icon set (stroke = currentColor) ----
const ICONS = {
  "sales-crm": '<path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
  marketing: '<path d="M3 11l16-6v14L3 13z"/><path d="M11.5 18.5a3 3 0 0 1-5.7-1.3"/><path d="M19 9a3 3 0 0 1 0 6"/>',
  finance: '<path d="M12 1v22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  "hr-people": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  support: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/>',
  projects: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  analytics: '<path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6" rx="1"/><rect x="12" y="7" width="3" height="10" rx="1"/><rect x="17" y="13" width="3" height="4" rx="1"/>',
  "it-security": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
  bolt: '<path d="M13 2L4.5 13.5H11l-1 8.5L19.5 10H13z"/>',
  puzzle: '<path d="M19 11h-1.5a2 2 0 1 0-4 0H8a2 2 0 0 0-2 2v3.5a2 2 0 1 1 0 4V21h11a2 2 0 0 0 2-2v-3.5a2 2 0 1 0 0-4z"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4"/>',
  building: '<rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 8h.01M15 8h.01M9 12h.01M15 12h.01M9 16h6"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/>',
  mic: '<rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M12 17v4"/><path d="M8 21h8"/>',
  flask: '<path d="M9 3h6"/><path d="M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3"/><path d="M7.5 14h9"/>',
  arrow: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
};

export function icon(name, cls = "") {
  const body = ICONS[name] || ICONS.sparkle;
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

export const catIconName = (id) => (ICONS[id] ? id : "sparkle");

let _catalog = null;

// Load and cache the catalog JSON. Validates the shape at the boundary.
export async function loadCatalog() {
  if (_catalog) return _catalog;
  const url = asset("../data/catalog.json");
  let res;
  try {
    res = await fetch(url, { cache: "no-cache" });
  } catch (networkErr) {
    throw new Error("Could not reach the catalog. Serve the folder over HTTP (not file://) and try again.");
  }
  if (!res.ok) throw new Error(`Failed to load catalog (HTTP ${res.status})`);
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error("The catalog file is not valid JSON.");
  }
  if (!data || !Array.isArray(data.products) || !data.company) {
    throw new Error("Catalog JSON is missing required fields.");
  }
  _catalog = data;
  return data;
}

export const tone = (i) => `tone-${((i % 8) + 8) % 8}`;

export const initials = (name) =>
  name.replace(/^Nimbus\s+/i, "").trim().slice(0, 2).toUpperCase();

export function fromPrice(product) {
  const paid = (product.tiers || []).filter((t) => typeof t.priceMonthly === "number" && t.priceMonthly > 0);
  if (!paid.length) return { label: "Free", sub: "" };
  const min = Math.min(...paid.map((t) => t.priceAnnualMonthly ?? t.priceMonthly));
  return { label: `$${min}`, sub: "/user/mo" };
}

export const param = (k) => new URLSearchParams(location.search).get(k);

// Tiny DOM builder. el("div", {class:"x"}, [child, "text"])
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

export const escapeHtml = (s = "") =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Brand mark (image tile) used in nav + footer.
const brandMark = (size = 34) =>
  `<img class="logo" src="${asset("favicon.svg")}" alt="Nimbus logo" width="${size}" height="${size}" />`;

// ---- Shared layout ----
export function mountHeader(active = "") {
  const links = NAV_LINKS.map(
    (l) => `<a href="${l.href}" class="${l.label.toLowerCase() === active ? "active" : ""}">${l.label}</a>`
  ).join("");
  const header = el("div", {
    class: "nav",
    html: `<div class="container nav-inner">
      <a href="index.html" class="brand">${brandMark(34)} Nimbus</a>
      <nav class="nav-links">${links}</nav>
      <div class="nav-cta">
        <a href="pricing.html" class="btn btn-ghost btn-sm">Pricing</a>
        <a href="products.html" class="btn btn-primary btn-sm">Get started</a>
      </div>
    </div>`,
  });
  document.body.prepend(header);

  // Subtle border/shadow once the page is scrolled.
  const onScroll = () => header.classList.toggle("scrolled", window.scrollY > 8);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
}

export function mountFooter(catalog) {
  const c = catalog.company;
  const cats = (catalog.categories || [])
    .slice(0, 6)
    .map((cat) => `<li><a href="products.html?cat=${cat.id}">${escapeHtml(cat.name)}</a></li>`)
    .join("");
  const footer = el("footer", {
    class: "footer",
    html: `<div class="container">
      <div class="footer-cols">
        <div>
          <div class="brand">${brandMark(32)} ${escapeHtml(c.name)}</div>
          <p class="footer-tag">${escapeHtml(c.tagline || "")}</p>
          <p class="fictitious">A fictitious company built for the Voice Agents bootcamp (Session 7).</p>
        </div>
        <div><h4>Products</h4><ul>${cats}</ul></div>
        <div><h4>Company</h4><ul>
          <li><a href="about.html">About</a></li>
          <li><a href="pricing.html">Pricing</a></li>
          <li><a href="support.html">Support</a></li>
          <li><a href="playground.html" style="font-weight: 600;">Voice Playground</a></li>
        </ul></div>
        <div><h4>Contact</h4><ul>
          <li>${escapeHtml(c.contact?.sales || "")}</li>
          <li>${escapeHtml(c.contact?.support || "")}</li>
          <li>${escapeHtml(c.contact?.phone || "")}</li>
        </ul></div>
      </div>
      <div class="footer-bottom">
        <span>&copy; ${escapeHtml(String(c.founded || ""))} to present. ${escapeHtml(c.legalName || c.name)} Not a real company.</span>
        <span>${escapeHtml(c.hq || "")}</span>
      </div>
    </div>`,
  });
  document.body.append(footer);
}

// Animate elements with .reveal into view as they enter the viewport.
function observeReveals() {
  const els = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window) || !els.length) {
    els.forEach((e) => e.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          io.unobserve(entry.target);
        }
      });
    },
    { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
  );
  els.forEach((e) => io.observe(e));
}

// Standard page bootstrap: header + content render + footer, with error handling.
export async function bootstrap(active, renderFn) {
  try {
    const catalog = await loadCatalog();
    mountHeader(active);
    await renderFn(catalog);
    mountFooter(catalog);
    observeReveals();
    // Client-side cart (localStorage); loaded lazily so browsing never blocks on it.
    import("./cart.js").then((m) => m.mountCart()).catch(() => {});
    
    // Inject floating AI Voice widget
    try {
      mountVoiceWidget();
    } catch (e) {
      console.error("AI widget load failed", e);
    }
  } catch (err) {
    console.error(err);
    const main = document.querySelector("#app") || document.body;
    main.innerHTML = `<div class="container loading">
      <h2>Something went wrong</h2>
      <p class="muted">${escapeHtml(err.message)}</p>
    </div>`;
  }
}

function mountVoiceWidget() {
  if (document.querySelector(".nimbus-ai-widget")) return;
  // Create Style
  const style = el("style", {
    html: `
      .nimbus-ai-widget {
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 10000;
        font-family: 'Plus Jakarta Sans', sans-serif;
      }
      .nimbus-ai-btn {
        width: 56px;
        height: 56px;
        border-radius: 50%;
        background: linear-gradient(135deg, #00f2fe, #4facfe);
        border: none;
        box-shadow: 0 4px 16px rgba(0, 242, 254, 0.35);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.3s ease;
      }
      .nimbus-ai-btn:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 24px rgba(0, 242, 254, 0.5);
      }
      .nimbus-ai-window {
        position: absolute;
        bottom: 72px;
        right: 0;
        width: 340px;
        height: 450px;
        background: rgba(18, 22, 35, 0.95);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        transform: translateY(16px) scale(0.95);
        opacity: 0;
        pointer-events: none;
      }
      .nimbus-ai-window.open {
        transform: translateY(0) scale(1);
        opacity: 1;
        pointer-events: auto;
      }
      .nimbus-ai-header {
        padding: 12px 16px;
        background: rgba(255, 255, 255, 0.03);
        border-bottom: 1px solid rgba(255,255,255,0.08);
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .nimbus-ai-header h3 {
        margin: 0;
        font-size: 0.95rem;
        font-weight: 600;
        color: white;
      }
      .nimbus-ai-close {
        background: none;
        border: none;
        color: #cbd5e1;
        cursor: pointer;
        font-size: 0.8rem;
      }
      .nimbus-ai-messages {
        flex: 1;
        padding: 16px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 12px;
        background: rgba(0, 0, 0, 0.1);
      }
      .nimbus-ai-msg {
        max-width: 80%;
        padding: 8px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        line-height: 1.4;
      }
      .nimbus-ai-msg.user {
        align-self: flex-end;
        background: #0d9488;
        color: white;
        border-bottom-right-radius: 2px;
      }
      .nimbus-ai-msg.agent {
        align-self: flex-start;
        background: rgba(18, 22, 35, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.08);
        color: #f1f5f9;
        border-bottom-left-radius: 2px;
      }
      .nimbus-ai-input-bar {
        padding: 12px;
        background: rgba(0,0,0,0.2);
        border-top: 1px solid rgba(255,255,255,0.08);
        display: flex;
        gap: 8px;
        align-items: center;
      }
      .nimbus-ai-input {
        flex: 1;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        color: white;
        padding: 6px 12px;
        font-size: 0.85rem;
        outline: none;
      }
      .nimbus-ai-input:focus {
        border-color: #00f2fe;
      }
      .nimbus-ai-send-btn, .nimbus-ai-mic-btn {
        background: none;
        border: none;
        color: #cbd5e1;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        transition: all 0.2s;
      }
      .nimbus-ai-send-btn svg, .nimbus-ai-mic-btn svg {
        width: 16px;
        height: 16px;
        stroke: currentColor;
      }
      .nimbus-ai-mic-btn.active {
        background: #ef4444;
        color: white;
        animation: widget-pulse 1.5s infinite;
      }
      @keyframes widget-pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
      }
    `
  });
  document.head.appendChild(style);

  // Create UI
  const widget = el("div", {
    class: "nimbus-ai-widget",
    html: `
      <button class="nimbus-ai-btn" aria-label="Talk to Nimbus">${icon("chat")}</button>
      <div class="nimbus-ai-window">
        <div class="nimbus-ai-header">
          <h3>Nimbus AI Assistant</h3>
          <button class="nimbus-ai-close">Close</button>
        </div>
        <div class="nimbus-ai-messages">
          <div class="nimbus-ai-msg agent">Hi there! I am Nimbus, your voice-enabled AI helper. Speak or type to ask me anything about our software products or your cart!</div>
        </div>
        <div class="nimbus-ai-input-bar">
          <button class="nimbus-ai-mic-btn" aria-label="Mic">${icon("mic")}</button>
          <input type="text" class="nimbus-ai-input" placeholder="Type or click mic...">
          <button class="nimbus-ai-send-btn" aria-label="Send">${icon("arrow")}</button>
        </div>
      </div>
    `
  });
  document.body.appendChild(widget);

  // Widget Actions
  const btn = widget.querySelector(".nimbus-ai-btn");
  const win = widget.querySelector(".nimbus-ai-window");
  const close = widget.querySelector(".nimbus-ai-close");
  const send = widget.querySelector(".nimbus-ai-send-btn");
  const input = widget.querySelector(".nimbus-ai-input");
  const msgs = widget.querySelector(".nimbus-ai-messages");
  const mic = widget.querySelector(".nimbus-ai-mic-btn");

  btn.addEventListener("click", () => win.classList.toggle("open"));
  close.addEventListener("click", () => win.classList.remove("open"));

  function cleanTextForTTS(text) {
    if (!text) return "";
    return text
      .replace(/\$(\d+(?:\.\d+)?)\/mo\b/g, "$1 dollars per month")
      .replace(/\$(\d+(?:\.\d+)?)\/yr\b/g, "$1 dollars per year")
      .replace(/(\d+(?:\.\d+)?)\s*\$?\s*\/mo\b/g, "$1 dollars per month")
      .replace(/(\d+(?:\.\d+)?)\s*\$?\s*\/yr\b/g, "$1 dollars per year")
      .replace(/\/mo\b/g, " per month")
      .replace(/\/yr\b/g, " per year")
      .replace(/\/user\/mo\b/g, " per user per month")
      .replace(/\$/g, " dollars ")
      .replace(/&middot;/g, " and ")
      .replace(/&amp;/g, " and ")
      .replace(/\bdogs\b/gi, "Docs")
      .replace(/\bneeds\b/gi, "Leads");
  }

  function getBestBrowserVoice() {
    const synth = window.speechSynthesis;
    if (!synth) return null;
    const voices = synth.getVoices();
    
    // Try natural female/English online voices first (e.g. Jenny, Aria, Zira, Google English)
    let best = voices.find(v => v.lang.startsWith("en") && (v.name.includes("Jenny") || v.name.includes("Aria") || v.name.includes("Zira") || v.name.includes("Google US English")));
    if (best) return best;
    
    // Fallback to any voice containing Zira, Google, Samantha, Hazel
    best = voices.find(v => {
      const n = v.name.toLowerCase();
      return v.lang.startsWith("en") && (n.includes("zira") || n.includes("google") || n.includes("samantha") || n.includes("hazel") || n.includes("female"));
    });
    if (best) return best;
    
    // Fallback to any English voice
    best = voices.find(v => v.lang.startsWith("en"));
    return best || voices[0];
  }

  // Prefetch voices so they are ready
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
  }

  let synthUtterance = null;
  function speak(text) {
    if (synthUtterance) window.speechSynthesis?.cancel();
    synthUtterance = new SpeechSynthesisUtterance(cleanTextForTTS(text));
    const voice = getBestBrowserVoice();
    if (voice) {
      synthUtterance.voice = voice;
    }
    window.speechSynthesis?.speak(synthUtterance);
  }

  async function handleSend() {
    const txt = input.value.trim();
    if (!txt) return;
    input.value = "";

    // Append User Message
    const userMsg = el("div", { class: "nimbus-ai-msg user", text: txt });
    msgs.appendChild(userMsg);
    msgs.scrollTop = msgs.scrollHeight;

    // Call server API
    const agentMsg = el("div", { class: "nimbus-ai-msg agent", text: "..." });
    msgs.appendChild(agentMsg);
    msgs.scrollTop = msgs.scrollHeight;

    try {
      const cartRaw = localStorage.getItem("nimbus_cart") || "[]";
      const cart = JSON.parse(cartRaw);
      
      const headers = { "Content-Type": "application/json" };
      const oai = localStorage.getItem("nimbus_openai_key");
      const gem = localStorage.getItem("nimbus_gemini_key");
      if (oai) headers["X-OpenAI-Key"] = oai;
      if (gem) headers["X-Gemini-Key"] = gem;

      const baseApiUrl = localStorage.getItem("nimbus_backend_url") || "http://127.0.0.1:8000";
      const res = await fetch(`${baseApiUrl}/api/reason`, {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          query: txt,
          history: [],
          cart: cart
        })
      });
      const data = await res.json();
      agentMsg.textContent = data.text;
      
      // Update cart
      if (data.cart) {
        localStorage.setItem("nimbus_cart", JSON.stringify(data.cart));
        // Trigger paint if cart module is imported and drawer exists
        import("./cart.js").then(m => m.mountCart()).catch(() => {});
      }
      
      // Speak response
      speak(data.text);
      
    } catch {
      agentMsg.textContent = "Sorry, my server is offline. Try launching the FastAPI server.py script.";
    }
  }

  send.addEventListener("click", handleSend);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleSend();
  });

  // Mic recognition
  let isListening = false;
  mic.addEventListener("click", () => {
    if (isListening) return;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition not supported in this browser.");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    
    recognition.onstart = () => {
      isListening = true;
      mic.classList.add("active");
    };
    recognition.onresult = (event) => {
      input.value = event.results[0][0].transcript;
    };
    recognition.onend = () => {
      isListening = false;
      mic.classList.remove("active");
      if (input.value) handleSend();
    };
    recognition.start();
  });
}

