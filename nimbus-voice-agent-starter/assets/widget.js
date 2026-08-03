// "Talk to Nimbus" - the finalized voice agent embedded on the site.
// Text + voice (mic VAD endpointing -> ASR -> chat -> TTS) with barge-in.
// Reads the shared agent config the Playground writes to localStorage (same
// origin), and mirrors the server cart into the site's `nimbus_cart`.
(function () {
  "use strict";
  var BASE = window.NIMBUS_API_BASE || "http://localhost:8000";
  var CART_KEY = "nimbus_cart";
  var SID_KEY = "nimbus_widget_session";
  var CFG_KEY = "nimbus_agent_config";

  var session = localStorage.getItem(SID_KEY);
  if (!session) { session = "w-" + Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem(SID_KEY, session); }

  // ---- shared config (written by the Playground / Voice page) ----
  function cfg() {
    var c = {};
    try { c = JSON.parse(localStorage.getItem(CFG_KEY) || "{}"); } catch (e) {}
    return {
      model_key: c.model_key || "openai-lite",
      response_length: c.response_length || "medium",
      knowledge: c.knowledge || "rag",
      top_k: c.top_k || 4, rerank: !!c.rerank,
      verbatim_turns: c.verbatim_turns != null ? c.verbatim_turns : 6,
      temperature: c.temperature != null ? c.temperature : 0.5,
      system_prompt: c.system_prompt || null,
      tools_enabled: c.tools_enabled !== undefined ? c.tools_enabled : true,
      enabled_tools: c.enabled_tools && c.enabled_tools.length ? c.enabled_tools : null,
      asr: c.asr && c.asr !== "browser" ? c.asr : "elevenlabs",
      tts: c.tts || "elevenlabs", voice: c.voice || "Sarah",
      endpoint: c.endpoint || 700, buffer: c.buffer != null ? c.buffer : 120,
      barge: c.barge || "low",
    };
  }
  function chatBody(message, mode) {
    var c = cfg();
    return JSON.stringify({
      session_id: session, message: message, mode: mode || "batch",
      model_key: c.model_key, response_length: c.response_length,
      use_context: c.knowledge === "ragless", use_rag: c.knowledge === "rag",
      top_k: c.top_k, rerank: c.rerank, verbatim_turns: c.verbatim_turns,
      temperature: c.temperature, system_prompt: c.system_prompt,
      tools_enabled: c.tools_enabled, enabled_tools: c.enabled_tools,
    });
  }

  // ---- styles ----
  var css =
    "#nb-fab{position:fixed;right:20px;bottom:20px;z-index:9999;border:none;cursor:pointer;width:58px;height:58px;border-radius:50%;background:linear-gradient(135deg,#6e8bff,#9d7bff);color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.25);font-size:24px;display:grid;place-items:center}" +
    "#nb-panel{position:fixed;right:20px;bottom:88px;z-index:9999;width:368px;max-width:calc(100vw - 32px);height:540px;max-height:calc(100vh - 120px);background:#fff;border:1px solid #e6e8ee;border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.22);display:none;flex-direction:column;overflow:hidden;font-family:Inter,system-ui,sans-serif}" +
    "#nb-panel.open{display:flex}" +
    "#nb-head{padding:13px 15px;background:linear-gradient(135deg,#6e8bff,#9d7bff);color:#fff;font-weight:600;font-family:'Space Grotesk',Inter,sans-serif;display:flex;justify-content:space-between;align-items:center}" +
    "#nb-head small{display:block;font-weight:400;opacity:.85;font-size:11px}" +
    "#nb-head a{color:#fff;font-size:11px;text-decoration:underline;opacity:.9}" +
    "#nb-head .hbtns{display:flex;align-items:center;gap:4px}" +
    "#nb-gear,#nb-x{background:transparent;border:none;color:#fff;font-size:18px;cursor:pointer;line-height:1;padding:2px 4px}" +
    "#nb-settings{position:absolute;inset:54px 0 0 0;background:#fff;z-index:2;padding:14px;overflow-y:auto;display:none;flex-direction:column;gap:11px}" +
    "#nb-settings.open{display:flex}" +
    "#nb-settings h4{margin:0 0 2px;font-family:'Space Grotesk',Inter,sans-serif;font-size:14px}" +
    "#nb-settings label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#5b6475}" +
    "#nb-settings select{border:1px solid #d8dce6;border-radius:8px;padding:7px 9px;font:inherit;font-size:13px;color:#1a1f2b}" +
    "#nb-settings .row{display:flex;gap:8px}#nb-settings .row label{flex:1}" +
    "#nb-settings .tg{flex-direction:row;align-items:center;justify-content:space-between}" +
    "#nb-savecfg{border:none;background:#6e8bff;color:#fff;border-radius:9px;padding:9px;cursor:pointer;font-weight:600;margin-top:4px}" +
    "#nb-settings .pl{font-size:11px;color:#8b93a7}#nb-settings .pl a{color:#6e8bff}" +
    "#nb-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#f7f8fb}" +
    ".nb-m{padding:9px 12px;border-radius:13px;max-width:86%;font-size:14px;line-height:1.45;white-space:pre-wrap}" +
    ".nb-u{align-self:flex-end;background:#6e8bff;color:#fff}" +
    ".nb-a{align-self:flex-start;background:#fff;border:1px solid #e6e8ee;color:#1a1f2b}" +
    ".nb-a.cancelled{opacity:.65}" +
    ".nb-sys{align-self:center;color:#8b93a7;font-size:12px;text-align:center}" +
    ".nb-sys a{color:#6e8bff;text-decoration:underline}" +
    ".nb-tools{align-self:flex-start;font-size:11px;color:#6e8bff}" +
    "#nb-status{font-size:11px;color:#8b93a7;padding:3px 14px;background:#f7f8fb;min-height:16px}" +
    "#nb-form{display:flex;gap:7px;padding:10px;border-top:1px solid #eef0f4;background:#fff;align-items:center}" +
    "#nb-mic{border:1px solid #d8dce6;background:#fff;color:#6e8bff;border-radius:10px;width:40px;height:38px;cursor:pointer;display:grid;place-items:center;flex:0 0 auto}" +
    "#nb-mic.on{background:#6e8bff;color:#fff;border-color:#6e8bff}" +
    "#nb-mic.spk{background:#d29922;color:#fff;border-color:#d29922}" +
    "#nb-in{flex:1;border:1px solid #d8dce6;border-radius:10px;padding:9px 11px;font:inherit;font-size:14px;min-width:0}" +
    "#nb-send{border:none;background:#6e8bff;color:#fff;border-radius:10px;padding:0 13px;cursor:pointer;font-weight:600}";
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  var fab = document.createElement("button");
  fab.id = "nb-fab"; fab.title = "Talk to Nimbus"; fab.innerHTML = "&#128172;";
  var panel = document.createElement("div");
  panel.id = "nb-panel";
  panel.innerHTML =
    '<div id="nb-head"><div>Talk to Nimbus<small>Text or voice · full tools</small></div>' +
    '<div class="hbtns"><button id="nb-gear" title="Agent settings">&#9881;</button><button id="nb-x" aria-label="Close">&times;</button></div></div>' +
    '<div id="nb-settings"></div>' +
    '<div id="nb-msgs"><div class="nb-m nb-sys">Ask by typing, or tap the mic to talk. Try "add Nimbus CRM Pro to my cart".</div></div>' +
    '<div id="nb-status"></div>' +
    '<form id="nb-form"><button id="nb-mic" type="button" title="Voice"><svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"/></svg></button>' +
    '<input id="nb-in" autocomplete="off" placeholder="Ask Nimbus..." /><button id="nb-send" type="submit">Send</button></form>';
  document.body.appendChild(fab); document.body.appendChild(panel);

  var msgs = panel.querySelector("#nb-msgs"), input = panel.querySelector("#nb-in"),
      sendBtn = panel.querySelector("#nb-send"), micBtn = panel.querySelector("#nb-mic"),
      statusEl = panel.querySelector("#nb-status");

  function add(role, text) { var d = document.createElement("div"); d.className = "nb-m nb-" + role; d.textContent = text; msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight; return d; }
  function status(t) { statusEl.textContent = t || ""; }
  function toggle(open) { panel.classList.toggle("open", open); if (open) setTimeout(function () { input.focus(); }, 50); }
  fab.addEventListener("click", function () { toggle(!panel.classList.contains("open")); });
  panel.querySelector("#nb-x").addEventListener("click", function () { toggle(false); });

  // ---- in-widget settings (writes the shared config the Playground also uses) ----
  var settingsEl = panel.querySelector("#nb-settings"), gearBtn = panel.querySelector("#nb-gear");
  var VOICEMAP = {};
  function buildSettings() {
    var c = cfg();
    settingsEl.innerHTML =
      '<h4>Agent settings</h4>' +
      '<label>Model<select id="s-model"></select></label>' +
      '<label>Knowledge<select id="s-know">' +
        opt(["rag", "ragless", "none"], c.knowledge, { rag: "RAG (retrieve)", ragless: "RAGless (full context)", none: "None" }) + '</select></label>' +
      '<label class="tg">Tools (cart, pricing, sorting...)<input type="checkbox" id="s-tools"' + (c.tools_enabled ? " checked" : "") + '></label>' +
      '<div class="row"><label>Speech in (ASR)<select id="s-asr">' + opt(["openai", "gemini", "elevenlabs"], c.asr) + '</select></label>' +
      '<label>Speech out (TTS)<select id="s-tts">' + opt(["openai", "gemini", "elevenlabs"], c.tts) + '</select></label></div>' +
      '<label>Voice<select id="s-voice"></select></label>' +
      '<label>Barge-in (interrupt)<select id="s-barge">' +
        opt(["off", "low", "medium", "high"], c.barge, { off: "Off", low: "Low sensitivity", medium: "Medium sensitivity", high: "High sensitivity" }) + '</select></label>' +
      '<button id="nb-savecfg">Save settings</button>' +
      '<div class="pl">Full controls (latency, RAG viz, system prompt) in the <a href="playground.html">Playground &#8599;</a></div>';
    // populate models
    fetch(BASE + "/models").then(function (r) { return r.json(); }).then(function (d) {
      settingsEl.querySelector("#s-model").innerHTML = d.models.map(function (m) {
        return '<option value="' + m.key + '"' + (m.key === c.model_key ? " selected" : "") + '>' + m.label + '</option>';
      }).join("");
    }).catch(function () {});
    // voices depend on TTS provider
    fetch(BASE + "/voices").then(function (r) { return r.json(); }).then(function (d) {
      VOICEMAP = d.tts || {}; syncVoiceSel(c.voice);
    }).catch(function () {});
    settingsEl.querySelector("#s-tts").addEventListener("change", function () { syncVoiceSel(); });
    settingsEl.querySelector("#nb-savecfg").addEventListener("click", saveSettings);
  }
  function opt(vals, sel, labels) {
    return vals.map(function (v) { return '<option value="' + v + '"' + (v === sel ? " selected" : "") + '>' + ((labels && labels[v]) || v) + '</option>'; }).join("");
  }
  function syncVoiceSel(want) {
    var prov = settingsEl.querySelector("#s-tts").value, list = VOICEMAP[prov] || [];
    settingsEl.querySelector("#s-voice").innerHTML = opt(list, want || list[0]);
  }
  function saveSettings() {
    var prev = {}; try { prev = JSON.parse(localStorage.getItem(CFG_KEY) || "{}"); } catch (e) {}
    var next = Object.assign({}, prev, {
      model_key: val("#s-model"), knowledge: val("#s-know"), tools_enabled: settingsEl.querySelector("#s-tools").checked,
      asr: val("#s-asr"), tts: val("#s-tts"), voice: val("#s-voice"), barge: val("#s-barge"),
    });
    localStorage.setItem(CFG_KEY, JSON.stringify(next));
    settingsEl.classList.remove("open");
    add("sys", "Settings saved.");
  }
  function val(sel) { return settingsEl.querySelector(sel).value; }
  gearBtn.addEventListener("click", function () {
    if (settingsEl.classList.contains("open")) { settingsEl.classList.remove("open"); return; }
    buildSettings(); settingsEl.classList.add("open");
  });

  // ---- cart bridge ----
  function syncCart() {
    fetch(BASE + "/cart?session_id=" + encodeURIComponent(session)).then(function (r) { return r.json(); })
      .then(function (d) {
        var items = (d.items || []).map(function (i) { return { product_id: i.product_id, product_name: i.product_name, tier: i.tier, seats: i.seats, price: i.price_monthly }; });
        localStorage.setItem(CART_KEY, JSON.stringify(items));
        window.dispatchEvent(new Event("nimbus:cart-refresh"));
      }).catch(function () {});
  }

  // ---- chat turn (shared by text + voice) ----
  function chatTurn(message, onText) {
    var bubble = add("a", "...");
    // We send to REST /api/reason or WS reason
    // Translate widget fields to local ReasonRequest schema
    return fetch(BASE + "/api/reason", { 
      method: "POST", 
      headers: { 
        "Content-Type": "application/json",
        "X-OpenAI-Key": localStorage.getItem("nimbus_openai_key") || "",
        "X-Gemini-Key": localStorage.getItem("nimbus_gemini_key") || "",
        "X-ElevenLabs-Key": localStorage.getItem("nimbus_elevenlabs_key") || ""
      }, 
      body: JSON.stringify({
        query: message,
        history: [], // Let server load or pass basic turn
        cart: JSON.parse(localStorage.getItem(CART_KEY) || "[]")
      }) 
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) { bubble.textContent = "Sorry, " + d.error; return null; }
        bubble.textContent = d.text;
        var calls = d.tool_calls || [];
        if (calls.length) { 
          add("tools", "ran: " + calls.map(function (c) { return c.name; }).join(", ")); 
          if (d.cart) {
            localStorage.setItem(CART_KEY, JSON.stringify(d.cart));
            window.dispatchEvent(new Event("nimbus:cart-refresh"));
          }
        }
        if (onText) onText(d.text, bubble);
        return d;
      })
      .catch(function (e) { bubble.textContent = "Connection error: " + e.message; return null; });
  }

  // text send
  panel.querySelector("#nb-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var v = input.value.trim(); if (!v) return; input.value = "";
    add("u", v); sendBtn.disabled = true; input.disabled = true;
    chatTurn(v).finally(function () { sendBtn.disabled = false; input.disabled = false; input.focus(); });
  });

  // ============ VOICE ============
  var V = { on: false, phase: "idle", stream: null, ac: null, an: null, buf: null,
            ttsAn: null, ttsBuf: null, rec: null, chunks: [], lastVoice: 0, noise: 0.01,
            queue: [], src: null, playing: false, cancelled: false,
            echoGain: 0.4, bargeFrames: 0, playTs: 0 };
  var BARGE_GRACE = 350;
  var BARGE_PRESETS = { off: { en: false, th: 1, fr: 999 }, low: { en: true, th: 0.09, fr: 11 }, medium: { en: true, th: 0.06, fr: 8 }, high: { en: true, th: 0.04, fr: 5 } };
  function bargeP() { return BARGE_PRESETS[cfg().barge] || BARGE_PRESETS.low; }

  function rmsOf(an, b) { an.getFloatTimeDomainData(b); var s = 0; for (var i = 0; i < b.length; i++) s += b[i] * b[i]; return Math.sqrt(s / b.length); }
  function mic() { return rmsOf(V.an, V.buf); }
  function ttsLvl() { return V.playing ? rmsOf(V.ttsAn, V.ttsBuf) : 0; }
  function thr() { return Math.max(0.012, V.noise * 2 + 0.01); }

  function setMic(cls, txt) { micBtn.className = cls; if (txt !== undefined) status(txt); }

  async function ensureMic() {
    if (V.stream) return;
    V.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    V.ac = new (window.AudioContext || window.webkitAudioContext)();
    var s = V.ac.createMediaStreamSource(V.stream);
    V.an = V.ac.createAnalyser(); V.an.fftSize = 1024; V.buf = new Float32Array(V.an.fftSize); s.connect(V.an);
    V.ttsAn = V.ac.createAnalyser(); V.ttsAn.fftSize = 1024; V.ttsBuf = new Float32Array(V.ttsAn.fftSize); V.ttsAn.connect(V.ac.destination);
  }
  async function calibrate() { var a = [], t = performance.now(); while (performance.now() - t < 450) { a.push(mic()); await new Promise(function (r) { setTimeout(r, 30); }); } V.noise = a.reduce(function (x, y) { return x + y; }, 0) / a.length; }

  function loop() {
    if (!V.on) return;
    var lvl = mic(), now = performance.now(), th = thr();
    if (V.phase === "speaking") {
      var bp = bargeP(), out = ttsLvl(), residual = lvl - V.echoGain * out;
      var speaking = residual > bp.th;
      if (!speaking && out > 0.005) V.echoGain = Math.min(4, Math.max(0, V.echoGain * 0.97 + (lvl / out) * 0.03));
      if (bp.en && now - V.playTs > BARGE_GRACE) { V.bargeFrames = speaking ? V.bargeFrames + 1 : Math.max(0, V.bargeFrames - 1); if (V.bargeFrames >= bp.fr) bargeIn(); }
    } else if (V.phase === "listening" && lvl > th) { beginRec();
    } else if (V.phase === "recording") { if (lvl > th) V.lastVoice = now; if (now - V.lastVoice > cfg().endpoint) endRec(); }
    requestAnimationFrame(loop);
  }

  function pickMime() { var ms = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]; for (var i = 0; i < ms.length; i++) if (MediaRecorder.isTypeSupported(ms[i])) return ms[i]; return ""; }
  function beginRec() {
    V.chunks = []; V.rec = new MediaRecorder(V.stream, { mimeType: pickMime() });
    V.rec.ondataavailable = function (e) { if (e.data.size) V.chunks.push(e.data); };
    V.rec.onstop = onRec; V.rec.start(); V.lastVoice = performance.now();
    V.phase = "recording"; setMic("on", "listening...");
  }
  function endRec() { if (V.rec && V.rec.state !== "inactive") V.rec.stop(); }
  async function onRec() {
    var blob = new Blob(V.chunks, { type: V.rec.mimeType });
    if (blob.size < 1200) { V.phase = "listening"; status("listening..."); return; }
    V.phase = "thinking"; setMic("on", "transcribing...");
    var fd = new FormData(); fd.append("provider", cfg().asr); fd.append("file", blob, "u.webm");
    fd.append("X-OpenAI-Key", localStorage.getItem("nimbus_openai_key") || "");
    fd.append("X-Gemini-Key", localStorage.getItem("nimbus_gemini_key") || "");
    fd.append("X-ElevenLabs-Key", localStorage.getItem("nimbus_elevenlabs_key") || "");
    try {
      var d = await (await fetch(BASE + "/api/asr", { method: "POST", body: fd })).json();
      if (d.error || !d.text) { V.phase = "listening"; status(d.error ? "ASR: " + d.error : "listening..."); return; }
      add("u", d.text);
      var chat = await chatTurn(d.text);
      if (chat) await speak(chat.text); else resume();
    } catch (e) { V.phase = "listening"; status("error: " + e.message); }
  }

  // TTS via Web Audio + double-talk barge
  async function speak(text) {
    V.cancelled = false; V.phase = "thinking"; setMic("spk", "speaking...");
    var c = cfg(), ab;
    try {
      var fd = new FormData();
      fd.append("text", text);
      fd.append("provider", c.tts);
      var r = await fetch(BASE + "/api/tts", { 
        method: "POST",
        headers: {
          "X-OpenAI-Key": localStorage.getItem("nimbus_openai_key") || "",
          "X-Gemini-Key": localStorage.getItem("nimbus_gemini_key") || "",
          "X-ElevenLabs-Key": localStorage.getItem("nimbus_elevenlabs_key") || ""
        },
        body: fd
      });
      if (!r.ok) { resume(); return; }
      var resJson = await r.json();
      if (resJson.use_browser_speech) {
        // Fallback to browser voice speech
        window.speechSynthesis.cancel();
        var utterance = new SpeechSynthesisUtterance(text);
        utterance.onend = function() { resume(); };
        window.speechSynthesis.speak(utterance);
        return;
      }
      var audio_b64 = resJson.audio;
      var binaryString = window.atob(audio_b64);
      var len = binaryString.length;
      var bytes = new Uint8Array(len);
      for (var i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      ab = bytes.buffer;
    } catch (e) { resume(); return; }
    await new Promise(function (res) { setTimeout(res, c.buffer); });
    if (V.cancelled) return;
    V.phase = "speaking"; V.playTs = performance.now(); V.bargeFrames = 0;
    enqueue(ab);
  }
  async function enqueue(ab) {
    if (V.cancelled) return;
    var b; try { b = await V.ac.decodeAudioData(ab.slice(0)); } catch (e) { return; }
    V.queue.push(b); if (!V.playing) playNext();
  }
  function playNext() {
    if (V.cancelled) { V.queue = []; V.playing = false; return; }
    var b = V.queue.shift();
    if (!b) { V.playing = false; if (V.phase === "speaking") resume(); return; }
    V.playing = true; var s = V.ac.createBufferSource(); s.buffer = b; s.connect(V.ttsAn);
    s.onended = function () { V.src = null; playNext(); }; V.src = s;
    if (!V.playTs) V.playTs = performance.now(); s.start();
  }
  function stopAudio() { V.cancelled = true; V.queue = []; if (V.src) { try { V.src.onended = null; V.src.stop(); } catch (e) {} V.src = null; } V.playing = false; }
  function bargeIn() {
    stopAudio();
    var last = msgs.querySelectorAll(".nb-a"); if (last.length) last[last.length - 1].classList.add("cancelled");
    resume();
  }
  function resume() { if (!V.on) { setMic("", ""); return; } V.playing = false; V.phase = "listening"; setMic("on", "listening..."); }

  async function startVoice() {
    try { await ensureMic(); } catch (e) { status("mic permission denied"); return; }
    if (V.ac.state === "suspended") await V.ac.resume();
    V.on = true; V.phase = "listening"; setMic("on", "calibrating...");
    await calibrate(); status("listening..."); requestAnimationFrame(loop);
  }
  function stopVoice() { V.on = false; stopAudio(); if (V.rec && V.rec.state !== "inactive") try { V.rec.stop(); } catch (e) {} V.phase = "idle"; setMic("", ""); }
  micBtn.addEventListener("click", function () { V.on ? stopVoice() : startVoice(); });
})();
