// developer playground script

let BACKEND_URL = localStorage.getItem("nimbus_backend_url") || "http://127.0.0.1:8000";
let WS_URL = BACKEND_URL.replace("http", "ws");

let ws = null;
let scatterChart = null;
let latencyChart = null;
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let currentPlaybackAudio = null;
let isRecording = false;
let isCallActive = false;
let activeCallSessionId = null;
let activeRecognition = null;
let startQueryTime = null;
let currentAsrLatency = 0;
let currentTurnLatencies = {};

function getAuthHeaders() {
  const headers = {};
  const oai = localStorage.getItem("nimbus_openai_key");
  const gem = localStorage.getItem("nimbus_gemini_key");
  const el = localStorage.getItem("nimbus_elevenlabs_key");
  if (oai) headers["X-OpenAI-Key"] = oai;
  if (gem) headers["X-Gemini-Key"] = gem;
  if (el) headers["X-ElevenLabs-Key"] = el;
  return headers;
}

// Cart synchronizer
function getLocalCart() {
  try {
    return JSON.parse(localStorage.getItem("nimbus_cart") || "[]");
  } catch {
    return [];
  }
}

function saveLocalCart(cart) {
  localStorage.setItem("nimbus_cart", JSON.stringify(cart));
  renderCart(cart);
}

function renderCart(cart) {
  const listEl = document.getElementById("cart-items-list");
  const totalBadge = document.getElementById("cart-price-badge");
  
  if (!listEl || !totalBadge) return;
  
  let total = 0;
  listEl.innerHTML = "";
  
  if (!cart || cart.length === 0) {
    listEl.innerHTML = `<div class="cart-empty" style="font-size: 0.85rem; color: var(--text-muted); text-align: center; padding: 0.5rem 0;">Cart is empty</div>`;
    totalBadge.textContent = "$0";
    return;
  }
  
  cart.forEach((it) => {
    const cost = (parseFloat(it.price) || 0) * (parseInt(it.seats) || 1);
    total += cost;
    
    const row = document.createElement("div");
    row.className = "cart-item-row";
    row.innerHTML = `
      <span><strong>${it.product_name}</strong> (${it.tier} &middot; ${it.seats} seat)</span>
      <strong>$${cost}/mo</strong>
    `;
    listEl.appendChild(row);
  });
  
  totalBadge.textContent = `$${total.toFixed(2)}/mo`;
}

// Render message in chat box
function appendChatMessage(sender, text) {
  const box = document.getElementById("chat-box");
  if (!box) return;
  
  const row = document.createElement("div");
  row.className = `msg-row ${sender.toLowerCase()}`;
  
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  
  row.innerHTML = `
    <div class="msg-bubble">${text}</div>
    <div class="msg-meta">${sender} &middot; ${timeStr}</div>
  `;
  
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

// Set interaction status badge
function setStatus(statusClass, label) {
  const badge = document.getElementById("status-badge");
  if (!badge) return;
  
  badge.className = `status-badge ${statusClass}`;
  badge.textContent = label;
}

// Config Panel bindings
async function loadConfig() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/config`);
    const data = await res.json();
    
    // Select selectors
    document.getElementById("asr-select").value = localStorage.getItem("nimbus_asr_provider") || data.asr_provider;
    document.getElementById("llm-select").value = localStorage.getItem("nimbus_llm_provider") || data.llm_provider;
    document.getElementById("tts-select").value = localStorage.getItem("nimbus_tts_provider") || data.tts_provider;
    document.getElementById("rag-toggle").checked = localStorage.getItem("nimbus_rag_mode") === null ? data.rag_mode : localStorage.getItem("nimbus_rag_mode") === "true";
    document.getElementById("streaming-toggle").checked = localStorage.getItem("nimbus_streaming_mode") === null ? data.streaming_mode : localStorage.getItem("nimbus_streaming_mode") === "true";
    document.getElementById("top-k-slider").value = localStorage.getItem("nimbus_top_k") || data.top_k;
    document.getElementById("top-k-val").textContent = localStorage.getItem("nimbus_top_k") || data.top_k;
    document.getElementById("endpoint-slider").value = localStorage.getItem("nimbus_endpoint_duration") || data.endpoint_duration;
    document.getElementById("endpoint-val").textContent = `${localStorage.getItem("nimbus_endpoint_duration") || data.endpoint_duration} ms`;
    document.getElementById("verbatim-slider").value = localStorage.getItem("nimbus_verbatim_count") || data.verbatim_count;
    document.getElementById("verbatim-val").textContent = `${localStorage.getItem("nimbus_verbatim_count") || data.verbatim_count} turns`;
    document.getElementById("prompt-textarea").value = localStorage.getItem("nimbus_system_prompt") || data.system_prompt;
    document.getElementById("len-select").value = localStorage.getItem("nimbus_response_length") || data.response_length;
    
    // Load from localStorage
    document.getElementById("openai-key").value = localStorage.getItem("nimbus_openai_key") || "";
    document.getElementById("gemini-key").value = localStorage.getItem("nimbus_gemini_key") || "";
    document.getElementById("elevenlabs-key").value = localStorage.getItem("nimbus_elevenlabs_key") || "";
    document.getElementById("backend-url").value = localStorage.getItem("nimbus_backend_url") || "http://127.0.0.1:8000";
    
    // Set tools checkboxes
    const toolList = document.querySelector(".tool-list");
    if (toolList) {
      const boxes = toolList.querySelectorAll("input[type=checkbox]");
      const savedToolsStr = localStorage.getItem("nimbus_selected_tools");
      const savedTools = savedToolsStr ? JSON.parse(savedToolsStr) : data.selected_tools;
      boxes.forEach(box => {
        box.checked = savedTools.includes(box.value);
      });
    }

    // Auto-apply loaded settings to the server so they stay synchronized
    await saveConfig(false);
  } catch (err) {
    console.error("Error loading config:", err);
  }
}

async function saveConfig(showNotification = true) {
  const payload = {
    asr_provider: document.getElementById("asr-select").value,
    llm_provider: document.getElementById("llm-select").value,
    tts_provider: document.getElementById("tts-select").value,
    rag_mode: document.getElementById("rag-toggle").checked,
    streaming_mode: document.getElementById("streaming-toggle").checked,
    top_k: parseInt(document.getElementById("top-k-slider").value),
    endpoint_duration: parseInt(document.getElementById("endpoint-slider").value),
    verbatim_count: parseInt(document.getElementById("verbatim-slider").value),
    system_prompt: document.getElementById("prompt-textarea").value,
    response_length: document.getElementById("len-select").value,
    selected_tools: []
  };
  
  const boxes = document.querySelectorAll(".tool-list input[type=checkbox]:checked");
  boxes.forEach(b => payload.selected_tools.push(b.value));
  
  // Cache selections locally
  localStorage.setItem("nimbus_asr_provider", payload.asr_provider);
  localStorage.setItem("nimbus_llm_provider", payload.llm_provider);
  localStorage.setItem("nimbus_tts_provider", payload.tts_provider);
  localStorage.setItem("nimbus_rag_mode", payload.rag_mode);
  localStorage.setItem("nimbus_streaming_mode", payload.streaming_mode);
  localStorage.setItem("nimbus_top_k", payload.top_k);
  localStorage.setItem("nimbus_endpoint_duration", payload.endpoint_duration);
  localStorage.setItem("nimbus_verbatim_count", payload.verbatim_count);
  localStorage.setItem("nimbus_system_prompt", payload.system_prompt);
  localStorage.setItem("nimbus_response_length", payload.response_length);
  localStorage.setItem("nimbus_selected_tools", JSON.stringify(payload.selected_tools));
  
  try {
    const res = await fetch(`${BACKEND_URL}/api/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === "success" && showNotification) {
      appendChatMessage("System", "Configurations applied successfully.");
      // Reload vector scatter plot
      loadRAGClusters();
    }
  } catch (err) {
    console.error("Error saving config:", err);
  }
}

// Save API Keys
function saveApiKeys() {
  const oai = document.getElementById("openai-key").value;
  const gem = document.getElementById("gemini-key").value;
  const el = document.getElementById("elevenlabs-key").value;
  const url = document.getElementById("backend-url").value.trim() || "http://127.0.0.1:8000";
  
  localStorage.setItem("nimbus_openai_key", oai);
  localStorage.setItem("nimbus_gemini_key", gem);
  localStorage.setItem("nimbus_elevenlabs_key", el);
  localStorage.setItem("nimbus_backend_url", url);
  
  BACKEND_URL = url;
  WS_URL = url.replace("http", "ws");
  
  appendChatMessage("System", "API Keys and Backend Server URL saved to browser localStorage successfully.");
  // Reload visualizer clusters and websocket connection
  loadRAGClusters();
  connectWebSocket();
}

// Websocket connection
function connectWebSocket() {
  setStatus("disconnected", "Offline");
  const oai = localStorage.getItem("nimbus_openai_key") || "";
  const gem = localStorage.getItem("nimbus_gemini_key") || "";
  const el = localStorage.getItem("nimbus_elevenlabs_key") || "";
  const queryStr = `?openai_key=${encodeURIComponent(oai)}&gemini_key=${encodeURIComponent(gem)}&elevenlabs_key=${encodeURIComponent(el)}`;
  ws = new WebSocket(`${WS_URL.replace("http", "ws")}/api/voice-loop${queryStr}`);
  
  ws.onopen = () => {
    setStatus("connected", "Ready");
    console.log("WebSocket voice loop connected.");
  };
  
  ws.onclose = () => {
    setStatus("disconnected", "Offline");
    console.log("WebSocket voice loop closed. Reconnecting...");
    setTimeout(connectWebSocket, 3000);
  };
  
  ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data);
    
    if (msg.event === "reason_done") {
      setStatus("speaking", "Speaking");
      appendChatMessage("Agent", msg.text);
      
      // Sync Cart
      if (msg.cart) {
        saveLocalCart(msg.cart);
      }
      
      // Update Latency
      const lat = msg.latency || {};
      currentTurnLatencies = {
        asr_ms: currentAsrLatency || 0,
        rag_ms: lat.rag_ms || 0,
        llm_ms: lat.llm_ms || 0,
        tool_ms: lat.tool_ms || 0,
        tts_ms: 0,
        buffer_ms: 0
      };
      updateLatencyCharts(currentTurnLatencies);
      
      // Highlight RAG visualizer
      if (msg.chunks && msg.query_coord) {
        highlightRAGQuery(msg.chunks, msg.query_coord);
      }
      
      // Update inspection details for RAG vs Full Context
      const detailEl = document.getElementById("rag-details-content");
      if (detailEl) {
        let headerHtml = "";
        if (msg.context_tokens !== undefined) {
          headerHtml = `
            <div style="margin-bottom: 0.8rem; padding: 0.5rem; background: rgba(0, 242, 254, 0.15); border-radius: 4px; border: 1px solid rgba(0, 242, 254, 0.3); font-weight: bold; color: var(--primary-light);">
              📄 Mode: ${msg.rag_mode ? "RAG Retrieval" : "Full Context"} (${msg.context_tokens} tokens)
            </div>
          `;
        }
        if (!msg.rag_mode && msg.context_str) {
          detailEl.innerHTML = headerHtml + `
            <div style="max-height: 250px; overflow-y: auto; background: rgba(255,255,255,0.05); padding: 0.5rem; border-radius: 4px; font-family: monospace; white-space: pre-wrap; font-size: 0.75rem; text-align: left;">
              ${msg.context_str}
            </div>
          `;
        }
      }
    }
    
    if (msg.event === "tts_done") {
      // Handle TTS playback
      currentTurnLatencies.tts_ms = msg.latency_ms || 0;
      currentTurnLatencies.buffer_ms = msg.buffer_latency_ms || 150;
      updateLatencyCharts(currentTurnLatencies);
      
      if (startQueryTime) {
        const ttfa = timeMs() - startQueryTime;
        document.getElementById("ttfa-stream-val").textContent = `${ttfa.toFixed(0)} ms`;
        document.getElementById("ttfa-batch-val").textContent = `-`;
        startQueryTime = null;
      }
      
      if (msg.use_browser_speech) {
        speakBrowser(msg.text);
      } else if (msg.audio) {
        playAudioBase64(msg.audio);
      }
      setTimeout(() => setStatus("connected", "Ready"), 2000);
    }
    
    if (msg.event === "interrupted") {
      console.log("Barge-in verified: Audio playback cancelled.");
      stopSpeech();
      appendChatMessage("System", "Conversation interrupted by user.");
      setStatus("connected", "Ready");
    }
  };
}

// Web Audio browser voice output
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

function speakBrowser(text) {
  stopSpeech();
  const synth = window.speechSynthesis;
  if (!synth) return;
  
  const utterance = new SpeechSynthesisUtterance(cleanTextForTTS(text));
  const voice = getBestBrowserVoice();
  if (voice) {
    utterance.voice = voice;
  }
  utterance.onend = () => {
    setStatus("connected", "Ready");
  };
  synth.speak(utterance);
  currentPlaybackAudio = synth;
}

function playAudioBase64(b64Audio) {
  stopSpeech();
  const audioData = "data:audio/mp3;base64," + b64Audio;
  const audio = new Audio(audioData);
  audio.play();
  audio.onended = () => {
    setStatus("connected", "Ready");
  };
  currentPlaybackAudio = audio;
}

function stopSpeech() {
  if (currentPlaybackAudio) {
    if (currentPlaybackAudio.cancel) {
      // SpeechSynthesis
      currentPlaybackAudio.cancel();
    } else if (currentPlaybackAudio.pause) {
      // Audio element
      currentPlaybackAudio.pause();
    }
    currentPlaybackAudio = null;
  }
}

// Microphone audio recording or Native browser Speech Recognition
async function toggleMicrophone() {
  const btn = document.getElementById("mic-btn");
  const asrProvider = document.getElementById("asr-select").value;
  
  if (isRecording) {
    // Stop recording/recognition
    isRecording = false;
    btn.classList.remove("recording");
    setStatus("thinking", "Thinking");
    
    if (activeRecognition) {
      activeRecognition.stop();
    } else if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
  } else {
    // Start recording/recognition
    isRecording = true;
    btn.classList.add("recording");
    
    // Trigger barge-in (stop current speech playback)
    stopSpeech();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "interrupt" }));
    }
    
    // Check key availability for server ASR providers
    const openaiKey = localStorage.getItem("openai_key") || "";
    const geminiKey = localStorage.getItem("gemini_key") || "";
    const hasOpenAI = openaiKey.trim().length > 0;
    const hasGemini = geminiKey.trim().length > 0;
    
    let useBrowserAsr = (asrProvider === "browser");
    if (asrProvider === "openai" && !hasOpenAI) {
      console.log("No OpenAI API key found, falling back to Browser ASR.");
      useBrowserAsr = true;
    } else if (asrProvider === "gemini" && !hasGemini) {
      console.log("No Gemini API key found, falling back to Browser ASR.");
      useBrowserAsr = true;
    }
    
    // 1. Browser Native ASR mode: Start SpeechRecognition directly!
    if (useBrowserAsr) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        activeRecognition = new SpeechRecognition();
        activeRecognition.lang = "en-US";
        activeRecognition.interimResults = false;
        activeRecognition.maxAlternatives = 1;
        
        activeRecognition.onstart = () => {
          setStatus("listening", "Listening (Speech API)...");
        };
        
        activeRecognition.onresult = (event) => {
          const resultText = event.results[0][0].transcript;
          appendChatMessage("You", resultText);
          sendQuery(resultText);
        };
        
        activeRecognition.onerror = (e) => {
          console.error("Speech Recognition Error:", e);
          if (e.error === "no-speech") {
            appendChatMessage("System", "No speech detected. Please speak again.");
          } else {
            appendChatMessage("System", `Speech Recognition error: ${e.error}`);
          }
        };
        
        activeRecognition.onend = () => {
          isRecording = false;
          btn.classList.remove("recording");
          setStatus("connected", "Ready");
          activeRecognition = null;
        };
        
        activeRecognition.start();
        return;
      } else {
        appendChatMessage("System", "Browser Speech Recognition not supported in this browser. Falling back to recording.");
      }
    }
    
    // 2. Server-side ASR: Record audio blob (WebM format)
    setStatus("listening", "Listening...");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      
      // Analyze volume level for custom silence endpoint detection
      setupVolumeVAD(stream);
      
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };
      
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        // Use webm container natively supported by all browsers and OpenAI Whisper
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        await processSpeechInput(audioBlob);
      };
      
      mediaRecorder.start();
    } catch (err) {
      console.error("Microphone access failed:", err);
      isRecording = false;
      btn.classList.remove("recording");
      setStatus("connected", "Ready");
      appendChatMessage("System", "Failed to access microphone. Please grant browser permissions.");
    }
  }
}

// Simple VAD silence threshold detection
function setupVolumeVAD(stream) {
  if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioContext.createMediaStreamSource(stream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 256;
  source.connect(analyser);
  
  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);
  
  const silenceThreshold = 15; // volume index threshold
  const silenceDuration = parseInt(document.getElementById("endpoint-slider").value);
  let silenceStart = null;
  
  function checkVolume() {
    if (!isRecording) return;
    
    analyser.getByteFrequencyData(dataArray);
    let sum = 0;
    for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
    const averageVolume = sum / bufferLength;
    
    if (averageVolume < silenceThreshold) {
      if (silenceStart === null) {
        silenceStart = timeMs();
      } else {
        const elapsed = timeMs() - silenceStart;
        if (elapsed > silenceDuration) {
          console.log(`Silence endpoint detected after ${silenceDuration}ms. Auto-stopping.`);
          toggleMicrophone(); // Stop recording automatically
          return;
        }
      }
    } else {
      silenceStart = null; // Reset silence timer
    }
    
    requestAnimationFrame(checkVolume);
  }
  
  requestAnimationFrame(checkVolume);
}

// Send speech to server ASR + Reason + speak
async function processSpeechInput(audioBlob) {
  const asrProvider = document.getElementById("asr-select").value;
  
  setStatus("thinking", "Transcribing...");
  const startAsr = timeMs();
  
  const formData = new FormData();
  formData.append("file", audioBlob, "user_speech.webm"); // Use webm extension
  formData.append("provider", asrProvider);
  
  try {
    const res = await fetch(`${BACKEND_URL}/api/asr`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData
    });
    const data = await res.json();
    const asrLatency = timeMs() - startAsr;
    
    appendChatMessage("You", data.text);
    sendQuery(data.text, asrLatency);
  } catch (err) {
    console.error("ASR server error:", err);
    setStatus("connected", "Ready");
    appendChatMessage("System", "Error transcribing audio input.");
  }
}

// Send text query to reasoning engine
async function sendQuery(text, preAsrLatency = 0) {
  startQueryTime = timeMs();
  currentAsrLatency = preAsrLatency;
  setStatus("thinking", "Reasoning...");
  
  // If streaming WebSocket mode is enabled
  const isStreaming = document.getElementById("streaming-toggle").checked;
  if (isStreaming && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: "query",
      text: text,
      history: getConversationHistory(),
      cart: getLocalCart()
    }));
    return;
  }
  
  // Otherwise, REST Batch execution
  const startReason = timeMs();
  try {
    const res = await fetch(`${BACKEND_URL}/api/reason`, {
      method: "POST",
      headers: { 
        "Content-Type": "application/json",
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        query: text,
        history: getConversationHistory(),
        cart: getLocalCart()
      })
    });
    const data = await res.json();
    const reasonLatency = timeMs() - startReason;
    
    // Save state
    saveLocalCart(data.cart);
    appendChatMessage("Agent", data.text);
    
    // Highlight clusters
    if (data.chunks && data.query_coord) {
      highlightRAGQuery(data.chunks, data.query_coord);
    }
    
    // Update inspection details for RAG vs Full Context
    const detailEl = document.getElementById("rag-details-content");
    if (detailEl) {
      let headerHtml = "";
      if (data.context_tokens !== undefined) {
        headerHtml = `
          <div style="margin-bottom: 0.8rem; padding: 0.5rem; background: rgba(0, 242, 254, 0.15); border-radius: 4px; border: 1px solid rgba(0, 242, 254, 0.3); font-weight: bold; color: var(--primary-light);">
            📄 Mode: ${data.rag_mode ? "RAG Retrieval" : "Full Context"} (${data.context_tokens} tokens)
          </div>
        `;
      }
      if (!data.rag_mode && data.context_str) {
        detailEl.innerHTML = headerHtml + `
          <div style="max-height: 250px; overflow-y: auto; background: rgba(255,255,255,0.05); padding: 0.5rem; border-radius: 4px; font-family: monospace; white-space: pre-wrap; font-size: 0.75rem; text-align: left;">
            ${data.context_str}
          </div>
        `;
      }
    }
    
    // 2. TTS execution
    setStatus("thinking", "Synthesizing voice...");
    const ttsProvider = document.getElementById("tts-select").value;
    
    const startTts = timeMs();
    const ttsRes = await fetch(`${BACKEND_URL}/api/tts`, {
      method: "POST",
      headers: { 
        "Content-Type": "application/x-www-form-urlencoded",
        ...getAuthHeaders()
      },
      body: `text=${encodeURIComponent(data.text)}&provider=${ttsProvider}`
    });
    const ttsData = await ttsRes.json();
    const ttsLatency = timeMs() - startTts;
    
    // Compile latency breakdown
    const latencies = {
      asr_ms: preAsrLatency,
      rag_ms: data.latency.rag_ms,
      llm_ms: data.latency.llm_ms,
      tool_ms: data.latency.tool_ms,
      tts_ms: ttsLatency,
      buffer_ms: 150
    };
    updateLatencyCharts(latencies);
    
    if (startQueryTime) {
      const ttfa = timeMs() - startQueryTime;
      document.getElementById("ttfa-batch-val").textContent = `${ttfa.toFixed(0)} ms`;
      document.getElementById("ttfa-stream-val").textContent = `-`;
      startQueryTime = null;
    }
    
    setStatus("speaking", "Speaking");
    // Play voice
    if (ttsData.use_browser_speech) {
      speakBrowser(data.text);
    } else if (ttsData.audio) {
      playAudioBase64(ttsData.audio);
    }
    
  } catch (err) {
    console.error("Reasoning error:", err);
    setStatus("connected", "Ready");
    appendChatMessage("System", "Failed to retrieve response from AI reasoning layer.");
  }
}

// Fetch historical messages from playground chat log
function getConversationHistory() {
  const bubbles = document.querySelectorAll("#chat-box .msg-row");
  const history = [];
  bubbles.forEach((b) => {
    const isUser = b.classList.contains("user");
    const content = b.querySelector(".msg-bubble").textContent;
    history.push({
      role: isUser ? "user" : "assistant",
      content: content
    });
  });
  return history;
}

// Load RAG Scatter visualizer data
async function loadRAGClusters() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/rag/nodes`, {
      headers: getAuthHeaders()
    });
    const data = await res.json();
    
    if (!data.success || !data.nodes) return;
    
    // Categorize nodes for colors
    const productNodes = data.nodes.filter(n => n.category === "Product");
    const policyNodes = data.nodes.filter(n => n.category === "Policy");
    const faqNodes = data.nodes.filter(n => n.category === "FAQ");
    
    // Draw scatter chart
    const ctx = document.getElementById("ragScatterChart").getContext("2d");
    
    if (scatterChart) {
      scatterChart.destroy();
    }
    
    scatterChart = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Product',
            data: productNodes.map(n => ({ x: n.x, y: n.y, label: n.title })),
            backgroundColor: '#3b82f6',
            pointRadius: 6,
            pointHoverRadius: 8
          },
          {
            label: 'Policy',
            data: policyNodes.map(n => ({ x: n.x, y: n.y, label: n.title })),
            backgroundColor: '#10b981',
            pointRadius: 6,
            pointHoverRadius: 8
          },
          {
            label: 'FAQ',
            data: faqNodes.map(n => ({ x: n.x, y: n.y, label: n.title })),
            backgroundColor: '#8b5cf6',
            pointRadius: 6,
            pointHoverRadius: 8
          },
          {
            label: 'Query',
            data: [],
            backgroundColor: '#ef4444',
            pointRadius: 10,
            pointHoverRadius: 12,
            pointStyle: 'rectRot' // diamond style
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const item = ctx.raw;
                return `${item.label || 'Point'}: (${item.x.toFixed(2)}, ${item.y.toFixed(2)})`;
              }
            }
          }
        },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { display: false } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { display: false } }
        }
      }
    });
  } catch (err) {
    console.error("RAG node loading error:", err);
  }
}

// Highlight retrieved RAG nodes
function highlightRAGQuery(chunks, query_coord) {
  if (!scatterChart) return;
  
  // Set query point in dataset 3 (Query)
  scatterChart.data.datasets[3].data = [{
    x: query_coord[0],
    y: query_coord[1],
    label: "Active Query"
  }];
  
  scatterChart.update();
  
  // Populate RAG inspector
  const inspector = document.getElementById("chunks-inspector");
  if (!inspector) return;
  
  inspector.innerHTML = "";
  chunks.forEach((c) => {
    const chunkCard = document.createElement("div");
    chunkCard.style.padding = "0.5rem";
    chunkCard.style.borderBottom = "1px solid var(--glass-border)";
    chunkCard.innerHTML = `
      <div style="font-weight:600; color:var(--neon-blue);">${c.title} <span style="font-size:0.7rem; color:var(--text-muted);">(${c.category} &middot; Score: ${c.rerank_score.toFixed(2)})</span></div>
      <p style="margin:0.2rem 0 0 0; color:#cbd5e1; font-size:0.75rem; white-space:pre-wrap;">${c.content.slice(0, 150)}...</p>
    `;
    inspector.appendChild(chunkCard);
  });
}
// Draw/Update Latency doughnut Chart
function updateLatencyCharts(latencies) {
  try {
    const canvas = document.getElementById("latencyDoughnutChart");
    if (!canvas) return;
    
    const asr = latencies.asr_ms || 0;
    const rag = latencies.rag_ms || 0;
    const llm = latencies.llm_ms || 0;
    const tool = latencies.tool_ms || 0;
    const tts = latencies.tts_ms || 0;
    const buf = latencies.buffer_ms || 150;
    
    const total = asr + rag + llm + tool + tts + buf;
    
    // 1. Update text elements first (defensive programming)
    const totalEl = document.getElementById("latency-total-value");
    if (totalEl) totalEl.textContent = Math.round(total);
    
    const pct = (val) => total > 0 ? `${((val / total) * 100).toFixed(0)}%` : "0%";
    
    const setLegend = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = `${Math.round(val)} ms (${pct(val)})`;
    };
    
    setLegend("legend-asr", asr);
    setLegend("legend-rag", rag);
    setLegend("legend-llm", llm);
    setLegend("legend-tools", tool);
    setLegend("legend-tts", tts);
    setLegend("legend-buffer", buf);
    
    // 2. Draw/Update Chart.js doughnut chart
    const ctx = canvas.getContext("2d");
    const values = [asr, rag, llm, tool, tts, buf];
    
    // Always destroy previous chart to prevent conflicts
    if (latencyChart) {
      try {
        latencyChart.destroy();
      } catch (e) {
        console.warn("Error destroying latency chart:", e);
      }
      latencyChart = null;
    }
    
    latencyChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['ASR', 'RAG', 'LLM', 'Tools', 'TTS', 'Buffer'],
        datasets: [{
          data: values,
          backgroundColor: [
            'rgb(0, 242, 254)',
            'rgb(168, 85, 247)',
            'rgb(79, 172, 254)',
            'rgb(57, 255, 20)',
            'rgb(245, 158, 11)',
            'rgb(236, 72, 153)'
          ],
          borderWidth: 0,
          weight: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '75%',
        plugins: { legend: { display: false } }
      }
    });
  } catch (err) {
    console.error("Error rendering latency breakdown:", err);
  }
}
// Tab switcher
document.getElementById("tab-visuals").addEventListener("click", () => {
  document.getElementById("tab-visuals").classList.add("active");
  document.getElementById("tab-phone").classList.remove("active");
  document.getElementById("panel-visuals").style.display = "flex";
  document.getElementById("panel-phone").style.display = "none";
});

document.getElementById("tab-phone").addEventListener("click", () => {
  document.getElementById("tab-phone").classList.add("active");
  document.getElementById("tab-visuals").classList.remove("active");
  document.getElementById("panel-phone").style.display = "flex";
  document.getElementById("panel-visuals").style.display = "none";
});

// Phone Call Simulation
const callBtn = document.getElementById("phone-call-btn");
const phoneStatus = document.getElementById("phone-status");
const voiceInput = document.getElementById("phone-voice-input");
const voiceSend = document.getElementById("phone-voice-send");
const phoneMicBtn = document.getElementById("phone-mic-btn");

let isPhoneMicActive = false;
let phoneRecognition = null;

callBtn.addEventListener("click", async () => {
  if (isCallActive) {
    // Hangup
    isCallActive = false;
    activeCallSessionId = null;
    callBtn.textContent = "Call Nimbus Line";
    callBtn.className = "btn-call dial";
    phoneStatus.textContent = "Idle";
    voiceInput.disabled = true;
    voiceSend.disabled = true;
    if (phoneMicBtn) phoneMicBtn.disabled = true;
    stopPhoneMic();
    appendChatMessage("Phone Call", "Call disconnected.");
  } else {
    // Call
    phoneStatus.textContent = "Dialing...";
    try {
      const res = await fetch(`${BACKEND_URL}/api/phone/call`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "phone_number=+1 (800) 555-0142"
      });
      const data = await res.json();
      
      isCallActive = true;
      activeCallSessionId = data.session_id;
      callBtn.textContent = "Hang Up";
      callBtn.className = "btn-call hangup";
      phoneStatus.textContent = "Connected";
      voiceInput.disabled = false;
      voiceSend.disabled = false;
      if (phoneMicBtn) phoneMicBtn.disabled = false;
      
      appendChatMessage("Phone Call Operator", data.greeting);
      
      // Speak greeting then auto-start listening
      const utterance = new SpeechSynthesisUtterance(cleanTextForTTS(data.greeting));
      const voice = getBestBrowserVoice();
      if (voice) utterance.voice = voice;
      utterance.onend = () => {
        if (isCallActive) {
          setTimeout(() => startPhoneMic(), 300);
        }
      };
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      console.error("Phone call initiation error:", err);
      phoneStatus.textContent = "Call failed";
    }
  }
});

// Keypad input digits
const keys = document.querySelectorAll(".phone-key");
keys.forEach((k) => {
  k.addEventListener("click", async () => {
    if (!isCallActive || !activeCallSessionId) return;
    const val = k.dataset.val;
    
    try {
      const res = await fetch(`${BACKEND_URL}/api/phone/dtmf`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `session_id=${activeCallSessionId}&key=${val}`
      });
      const data = await res.json();
      
      appendChatMessage("Keypad Input", `Pressed ${val}`);
      appendChatMessage("Phone Call Operator", data.response);
      
      // Speak response then auto-listen if authenticated
      const utterance = new SpeechSynthesisUtterance(cleanTextForTTS(data.response));
      const voice = getBestBrowserVoice();
      if (voice) utterance.voice = voice;
      utterance.onend = () => {
        if (isCallActive && data.authenticated) {
          setTimeout(() => startPhoneMic(), 300);
        }
      };
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      console.error("DTMF dial error:", err);
    }
  });
});

// Voice simulation inside phone call using server-side ASR
let phoneMediaRecorder = null;
let phoneAudioChunks = [];

function setPhoneMicUI(active) {
  isPhoneMicActive = active;
  if (phoneMicBtn) {
    if (active) {
      phoneMicBtn.style.background = "#dc2626";
      phoneMicBtn.style.color = "#ffffff";
      phoneMicBtn.textContent = "🔴 Listening...";
    } else {
      phoneMicBtn.style.background = "rgba(239, 68, 68, 0.2)";
      phoneMicBtn.style.color = "#f87171";
      phoneMicBtn.textContent = "🎤 Mic";
    }
  }
}

function startPhoneMic() {
  if (!isCallActive || isPhoneMicActive) return;
  
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    // Use browser SpeechRecognition for fast, real-time capture
    phoneRecognition = new SpeechRecognition();
    phoneRecognition.lang = "en-US";
    phoneRecognition.interimResults = false;
    phoneRecognition.maxAlternatives = 1;
    
    phoneRecognition.onstart = () => {
      setPhoneMicUI(true);
    };
    
    phoneRecognition.onresult = (event) => {
      const text = event.results[0][0].transcript;
      voiceInput.value = text;
      sendPhoneSpeech();
    };
    
    phoneRecognition.onerror = (e) => {
      console.error("Phone mic error:", e);
      setPhoneMicUI(false);
      if (e.error === "no-speech") {
        // Auto-retry on no-speech
        setTimeout(() => { if (isCallActive && !isPhoneMicActive) startPhoneMic(); }, 500);
      }
    };
    
    phoneRecognition.onend = () => {
      setPhoneMicUI(false);
      // Auto-restart if call is still active (continuous listening)
      if (isCallActive && !isPhoneMicActive) {
        setTimeout(() => startPhoneMic(), 300);
      }
    };
    
    phoneRecognition.start();
  } else {
    // Fallback: record audio and send to server ASR
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      setPhoneMicUI(true);
      phoneAudioChunks = [];
      phoneMediaRecorder = new MediaRecorder(stream);
      
      phoneMediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) phoneAudioChunks.push(e.data);
      };
      
      phoneMediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        setPhoneMicUI(false);
        
        if (phoneAudioChunks.length === 0) return;
        
        const audioBlob = new Blob(phoneAudioChunks, { type: "audio/webm" });
        const asrProvider = document.getElementById("asr-select").value;
        
        const formData = new FormData();
        formData.append("file", audioBlob, "phone_speech.webm");
        formData.append("provider", asrProvider);
        
        try {
          const res = await fetch(`${BACKEND_URL}/api/asr`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: formData
          });
          const data = await res.json();
          if (data.text && data.text.trim()) {
            voiceInput.value = data.text;
            sendPhoneSpeech();
          }
        } catch (err) {
          console.error("Phone ASR error:", err);
        }
        
        // Auto-restart recording
        if (isCallActive) {
          setTimeout(() => startPhoneMic(), 300);
        }
      };
      
      phoneMediaRecorder.start();
      
      // Auto-stop after 8 seconds max
      setTimeout(() => {
        if (phoneMediaRecorder && phoneMediaRecorder.state !== "inactive") {
          phoneMediaRecorder.stop();
        }
      }, 8000);
    }).catch(err => {
      console.error("Phone mic access failed:", err);
      setPhoneMicUI(false);
    });
  }
}

function stopPhoneMic() {
  setPhoneMicUI(false);
  if (phoneRecognition) {
    phoneRecognition.stop();
    phoneRecognition = null;
  }
  if (phoneMediaRecorder && phoneMediaRecorder.state !== "inactive") {
    phoneMediaRecorder.stop();
  }
}

if (phoneMicBtn) {
  phoneMicBtn.addEventListener("click", () => {
    if (!isCallActive) return;
    
    if (isPhoneMicActive) {
      // Toggle off
      stopPhoneMic();
    } else {
      // Toggle on - start continuous listening
      startPhoneMic();
    }
  });
}

voiceSend.addEventListener("click", sendPhoneSpeech);
voiceInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendPhoneSpeech();
});

async function sendPhoneSpeech() {
  const text = voiceInput.value.trim();
  if (!text || !activeCallSessionId) return;
  
  voiceInput.value = "";
  appendChatMessage("You (Call)", text);
  
  // Stop mic while processing
  const wasListening = isPhoneMicActive;
  stopPhoneMic();
  
  // Barge-in: stop any ongoing speech playback
  stopSpeech();
  
  const openaiKey = localStorage.getItem("nimbus_openai_key") || "";
  const geminiKey = localStorage.getItem("nimbus_gemini_key") || "";
  const anthropicKey = localStorage.getItem("nimbus_anthropic_key") || "";
  
  try {
    const res = await fetch(`${BACKEND_URL}/api/phone/speak`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-OpenAI-Key": openaiKey,
        "X-Gemini-Key": geminiKey,
        "X-Anthropic-Key": anthropicKey
      },
      body: `session_id=${activeCallSessionId}&speech=${encodeURIComponent(text)}`
    });
    const data = await res.json();
    
    appendChatMessage("Phone Call Operator", data.response);
    
    // Play speech and auto-restart mic after it finishes
    const utterance = new SpeechSynthesisUtterance(cleanTextForTTS(data.response));
    const voice = getBestBrowserVoice();
    if (voice) utterance.voice = voice;
    utterance.onend = () => {
      // Auto-restart mic after agent finishes speaking
      if (isCallActive) {
        setTimeout(() => startPhoneMic(), 300);
      }
    };
    utterance.onerror = () => {
      if (isCallActive) {
        setTimeout(() => startPhoneMic(), 300);
      }
    };
    window.speechSynthesis.speak(utterance);
    
    // Sync cart if call modified it
    if (data.cart) {
      saveLocalCart(data.cart);
    }
  } catch (err) {
    console.error("Phone speech error:", err);
    appendChatMessage("System", "Error communicating with phone agent.");
    // Restart mic on error
    if (isCallActive) {
      setTimeout(() => startPhoneMic(), 300);
    }
  }
}

// UI Event hooks
document.getElementById("apply-settings-btn").addEventListener("click", () => saveConfig(true));
document.getElementById("save-keys-btn").addEventListener("click", saveApiKeys);
document.getElementById("mic-btn").addEventListener("click", toggleMicrophone);

// Slider indicators
document.getElementById("top-k-slider").addEventListener("input", (e) => {
  document.getElementById("top-k-val").textContent = e.target.value;
});
document.getElementById("endpoint-slider").addEventListener("input", (e) => {
  document.getElementById("endpoint-val").textContent = `${e.target.value} ms`;
});
document.getElementById("verbatim-slider").addEventListener("input", (e) => {
  document.getElementById("verbatim-val").textContent = `${e.target.value} turns`;
});

// Helpers
const timeMs = () => performance.now();

// Init
window.addEventListener("load", () => {
  loadConfig();
  renderCart(getLocalCart());
  loadRAGClusters();
  connectWebSocket();
});
