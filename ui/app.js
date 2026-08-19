/* DON wake UI client — WS to the A1 bridge, overlay state machine.
 * Features: real Web Audio API waveform, mic PTT, streaming transcript,
 * approval card, barge-in cancel, auto-reconnect.
 */
(() => {
  "use strict";

  const el = (id) => document.getElementById(id);
  const body = document.body;
  const glyph     = el("glyph");
  const chip      = el("statuschip");
  const modelChip = el("modelchip");
  const transcript = el("transcript");
  const toolline  = el("toolline");
  const card      = el("approvalcard");
  const actionsBox = el("approval-actions");
  const micBtn    = el("micbtn");
  const wsUrl = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";

  let ws = null;
  let deviceId = localStorage.getItem("don_device") ||
    ("dev-" + Math.random().toString(36).slice(2, 10));
  localStorage.setItem("don_device", deviceId);

  const threadId = "default";

  /* ─── state machine ─────────────────────────────────────────────── */
  function setState(s) {
    body.className = "state-" + s;
    chip.textContent = s.replace(/-/g, " ");
  }

  /* ─── Web Audio waveform ─────────────────────────────────────────── */
  const canvas = el("waveform");
  const ctx    = canvas.getContext("2d");
  let   _analyser = null;      // mic AnalyserNode
  let   _dataArr  = null;
  let   _animId   = null;

  function startWaveform(stream) {
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source   = audioCtx.createMediaStreamSource(stream);
      _analyser = audioCtx.createAnalyser();
      _analyser.fftSize = 128;
      _dataArr  = new Uint8Array(_analyser.frequencyBinCount);
      source.connect(_analyser);
      drawWave();
    } catch (e) {
      console.warn("Web Audio not available:", e);
      drawWaveFake();
    }
  }

  function stopWaveform() {
    if (_animId) { cancelAnimationFrame(_animId); _animId = null; }
    _analyser = null;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function drawWave() {
    _animId = requestAnimationFrame(drawWave);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!_analyser) return;
    _analyser.getByteTimeDomainData(_dataArr);
    const bars = _dataArr.length;
    const barW = canvas.width / bars;
    ctx.fillStyle = "#ff2233";
    for (let i = 0; i < bars; i++) {
      const v = _dataArr[i] / 128.0;          // 0–2 range
      const h = Math.abs(v - 1.0) * canvas.height * 2.2;
      const y = (canvas.height - h) / 2;
      ctx.fillRect(i * barW + 1, y, Math.max(barW - 2, 1), Math.max(h, 1));
    }
  }

  function drawWaveFake() {
    if (_animId) cancelAnimationFrame(_animId);
    const active = body.classList.contains("state-listening") ||
                   body.classList.contains("state-speaking");
    _animId = requestAnimationFrame(() => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const bars = 42;
      ctx.fillStyle = "#ff2233";
      for (let i = 0; i < bars; i++) {
        const h = active ? (Math.random() * 0.75 + 0.15) * 48 : 2;
        ctx.fillRect(i * (canvas.width / bars) + 2, (64 - h) / 2, canvas.width / bars - 4, h);
      }
      drawWaveFake();
    });
  }

  /* ─── mic / PTT ─────────────────────────────────────────────────── */
  let _micStream   = null;
  let _mediaRec    = null;
  let _audioChunks = [];

  async function startMic() {
    try {
      _micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      startWaveform(_micStream);
      _audioChunks = [];
      _mediaRec = new MediaRecorder(_micStream);
      _mediaRec.ondataavailable = (e) => { if (e.data.size > 0) _audioChunks.push(e.data); };
      _mediaRec.onstop = _onMicStop;
      _mediaRec.start(200);  // 200ms chunks
      micBtn.classList.add("recording");
      setState("listening");
    } catch (e) {
      console.warn("Mic access denied:", e);
    }
  }

  function stopMic() {
    if (_mediaRec && _mediaRec.state !== "inactive") _mediaRec.stop();
    if (_micStream) { _micStream.getTracks().forEach(t => t.stop()); _micStream = null; }
    micBtn.classList.remove("recording");
    stopWaveform();
    setState("thinking");
  }

  async function _onMicStop() {
    if (_audioChunks.length === 0) return;
    const blob   = new Blob(_audioChunks, { type: "audio/webm" });
    const buffer = await blob.arrayBuffer();
    const b64    = btoa(String.fromCharCode(...new Uint8Array(buffer)));
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "audio_in",
        device_id: deviceId,
        thread_id: threadId,
        payload: { audio: b64, final: true, sample_rate: 16000 },
      }));
    }
  }

  micBtn.addEventListener("click", () => {
    if (_mediaRec && _mediaRec.state === "recording") {
      stopMic();
    } else {
      startMic();
    }
  });

  /* ─── transcript ─────────────────────────────────────────────────── */
  function addTurn(who, text) {
    const div = document.createElement("div");
    div.className = "turn " + who;
    const whoEl = document.createElement("span");
    whoEl.className = "who";
    whoEl.textContent = who === "user" ? "operator" : "DON";
    div.appendChild(whoEl);
    // render basic markdown bold/code
    const p = document.createElement("span");
    p.innerHTML = text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code style='background:#2a0a14;padding:1px 5px;border-radius:4px'>$1</code>")
      .replace(/\n/g, "<br>");
    div.appendChild(p);
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
    return div;
  }

  let _streamingTurn = null;
  function streamToken(token) {
    if (!_streamingTurn) {
      _streamingTurn = addTurn("don", "");
    }
    _streamingTurn.querySelector("span:last-child").textContent += token;
    transcript.scrollTop = transcript.scrollHeight;
  }

  /* ─── approval ──────────────────────────────────────────────────── */
  async function answerApproval(decision) {
    await fetch("/api/v1/approval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: threadId, decision }),
    });
    card.classList.add("hidden");
    actionsBox.innerHTML = "";
    setState("thinking");
  }

  function showApproval(actions) {
    actionsBox.innerHTML = "";
    (actions || []).forEach((a) => {
      const li = document.createElement("li");
      const danger = a.danger || "";
      const icon = danger === "destructive" ? "🔴" : danger === "action" ? "⚡" : "ℹ";
      li.textContent = `${icon} ${a.tool}(${JSON.stringify(a.args || {}).slice(0, 80)}) — ${a.reason || danger}`;
      if (danger === "destructive" || danger === "action") li.classList.add("danger");
      actionsBox.appendChild(li);
    });
    card.classList.remove("hidden");
    setState("awaiting-approval");
  }

  el("btn-approve").addEventListener("click", () => answerApproval(true));
  el("btn-reject").addEventListener("click",  () => answerApproval(false));

  /* ─── websocket ──────────────────────────────────────────────────── */
  function connect() {
    ws = new WebSocket(wsUrl + "?device_id=" + deviceId + "&type=laptop");
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "ping", device_id: deviceId, thread_id: threadId, payload: {} }));
    };
    ws.onmessage = (ev) => {
      let env;
      try { env = JSON.parse(ev.data); } catch { return; }

      if (env.type === "pong") return;

      if (env.type === "status") {
        const s = env.payload && env.payload.status ? env.payload.status : env.payload;
        setState(s || "idle");
        if (s === "idle" || s === "done") { _streamingTurn = null; stopWaveform(); }
        if (s === "speaking") drawWaveFake();
        return;
      }

      if (env.type === "approval") {
        showApproval(env.payload.actions || []);
        return;
      }

      if (env.type === "text") {
        const c = (env.payload && env.payload.content) || "";
        if (env.payload && env.payload.streaming) {
          streamToken(c);
        } else if (env.payload && env.payload.final) {
          if (_streamingTurn) {
            _streamingTurn = null;
          } else {
            addTurn("don", c);
          }
          setState("idle");
        }
        return;
      }

      if (env.type === "audio_out") {
        // play streamed TTS audio from the server
        const b64 = env.payload && env.payload.audio;
        if (!b64) return;
        try {
          const bytes   = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
          const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          audioCtx.decodeAudioData(bytes.buffer, (decoded) => {
            const src = audioCtx.createBufferSource();
            src.buffer = decoded;
            src.connect(audioCtx.destination);
            src.start();
          });
          drawWaveFake();
        } catch (e) {
          console.warn("audio_out playback error:", e);
        }
      }
    };
    ws.onclose = () => setTimeout(connect, 2500);
    ws.onerror = () => ws.close();
  }
  connect();

  // heartbeat ping every 30s
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping", device_id: deviceId, thread_id: threadId, payload: {} }));
    }
  }, 30000);

  /* ─── text input ─────────────────────────────────────────────────── */
  el("textbar").addEventListener("submit", (e) => {
    e.preventDefault();
    const inp  = el("textinput");
    const text = inp.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    addTurn("user", text);
    inp.value = "";
    setState("thinking");
    ws.send(JSON.stringify({
      type: "text", device_id: deviceId, thread_id: threadId,
      payload: { content: text },
    }));
  });

  /* ─── keyboard shortcuts ─────────────────────────────────────────── */
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      // barge-in cancel
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "cancel", device_id: deviceId, thread_id: threadId, payload: {} }));
      }
      stopMic();
      setState("ending");
      setTimeout(() => setState("idle"), 900);
    }
  });

  /* ─── tool events (debug) ───────────────────────────────────────── */
  window.__donToolLine = (msg) => {
    toolline.textContent = "⚙ " + msg;
    toolline.classList.remove("hidden");
    setTimeout(() => toolline.classList.add("hidden"), 4500);
  };

  /* ─── init ───────────────────────────────────────────────────────── */
  requestAnimationFrame(() => setState("idle"));
})();
