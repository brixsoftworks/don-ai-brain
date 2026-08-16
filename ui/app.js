/* DON wake UI client — WS to the A1 bridge, overlay state machine. */
(() => {
  "use strict";

  const el = (id) => document.getElementById(id);
  const body = document.body;
  const glyph = el("glyph");
  const chip = el("statuschip");
  const transcript = el("transcript");
  const toolline = el("toolline");
  const card = el("approvalcard");
  const actionsBox = el("approval-actions");
  const wsUrl = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";

  let ws = null;
  let deviceId = localStorage.getItem("don_device") ||
    ("dev-" + Math.random().toString(36).slice(2, 10));
  localStorage.setItem("don_device", deviceId);

  const threadId = "default";

  /* ---------------- state machine ---------------- */
  const STATES = ["idle", "listening", "thinking", "speaking", "awaiting-approval", "ending"];
  function setState(s) {
    body.className = "state-" + s;
    chip.textContent = s.replace("-", " ");
  }

  /* ---------------- waveform ---------------- */
  const canvas = el("waveform");
  const ctx = canvas.getContext("2d");
  function drawWave() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const active = body.classList.contains("state-listening") ||
      body.classList.contains("state-speaking");
    const bars = 42;
    ctx.fillStyle = "#ff2233";
    for (let i = 0; i < bars; i++) {
      const h = active ? (Math.random() * 0.8 + 0.2) * 48 : 2;
      ctx.fillRect(i * (canvas.width / bars) + 2, (64 - h) / 2, canvas.width / bars - 4, h);
    }
  }
  setInterval(drawWave, 120);

  /* ---------------- transcript ---------------- */
  function addTurn(who, text) {
    const div = document.createElement("div");
    div.className = "turn " + who;
    const whoEl = document.createElement("span");
    whoEl.className = "who";
    whoEl.textContent = who === "user" ? "operator" : "DON";
    div.appendChild(whoEl);
    div.appendChild(document.createTextNode(text));
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
    return div;
  }

  /* ---------------- approval ---------------- */
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
      li.textContent = a.danger ? ("⚠ " + a.tool + " — " + (a.danger_label || "")) : (a.tool + " — " + (a.reason || ""));
      if (a.danger) li.classList.add("danger");
      actionsBox.appendChild(li);
    });
    card.classList.remove("hidden");
    setState("awaiting-approval");
  }

  el("btn-approve").addEventListener("click", () => answerApproval(true));
  el("btn-reject").addEventListener("click", () => answerApproval(false));

  /* ---------------- websocket ---------------- */
  function connect() {
    ws = new WebSocket(wsUrl + "?device_id=" + deviceId);
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "ping", device_id: deviceId, thread_id: threadId, payload: {} }));
    };
    ws.onmessage = (ev) => {
      let env;
      try { env = JSON.parse(ev.data); } catch { return; }
      if (env.type === "pong") return;
      if (env.type === "status") { setState(env.payload.status || "idle"); return; }
      if (env.type === "approval") { showApproval(env.payload.actions || []); return; }
      if (env.type === "text") {
        const c = env.payload.content || "";
        if (env.payload.final) {
          addTurn("don", c);
          setState("idle");
        }
      }
    };
    ws.onclose = () => setTimeout(connect, 2500);
  }
  connect();
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping", device_id: deviceId, thread_id: threadId, payload: {} }));
    }
  }, 30000);

  /* ---------------- text input ---------------- */
  el("textbar").addEventListener("submit", (e) => {
    e.preventDefault();
    const inp = el("textinput");
    const text = inp.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    addTurn("user", text);
    inp.value = "";
    setState("thinking");
    ws.send(JSON.stringify({ type: "text", device_id: deviceId, thread_id: threadId, payload: { content: text } }));
  });

  /* ---------------- esc ends session ---------------- */
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      setState("ending");
      setTimeout(() => setState("idle"), 900);
    }
  });

  /* ---------------- tool events (debug) ---------------- */
  window.__donToolLine = (msg) => {
    toolline.textContent = msg;
    toolline.classList.remove("hidden");
    setTimeout(() => toolline.classList.add("hidden"), 4000);
  };

  /* fade in */
  requestAnimationFrame(() => setState("idle"));
})();
