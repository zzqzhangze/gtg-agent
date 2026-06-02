// ── State ──────────────────────────────────────────────
const STATE = {
  sessionId: loadSessionId(),
  sessionName: "",
  pendingFiles: [],
  isSending: false,
  currentMessages: [], // [{role, content, files?}]
};

const MAX_SESSIONS = 20;

// ── DOM References ─────────────────────────────────────
let els = {};

document.addEventListener("DOMContentLoaded", () => {
  // Configure marked for chat-style markdown
  if (typeof marked !== "undefined") {
    marked.setOptions({
      gfm: true,
      breaks: true,
    });
  }

  els = {
    messages: document.getElementById("messages"),
    loading: document.getElementById("loading"),
    welcome: document.getElementById("welcome"),
    fileBar: document.getElementById("file-bar"),
    fileList: document.getElementById("file-list"),
    fileInput: document.getElementById("file-input"),
    attachBtn: document.getElementById("attach-btn"),
    messageInput: document.getElementById("message-input"),
    sendBtn: document.getElementById("send-btn"),
    themeToggle: document.getElementById("theme-toggle"),
    newSessionBtn: document.getElementById("new-session"),
    chatContainer: document.getElementById("chat-container"),
    sidebar: document.getElementById("sidebar"),
    sidebarToggle: document.getElementById("sidebar-toggle"),
    sessionList: document.getElementById("session-list"),
    newSessionSidebar: document.getElementById("new-session-sidebar"),
  };

  initTheme();
  loadCurrentMessages();
  updateSessionDisplay();
  renderSidebar();
  bindEvents();
  bindSidebarEvents();
  bindMcpEvents();
  bindWelcomeEvents();
});

// ── Session Persistence ────────────────────────────────
function escapeHtml(str) {
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function getFileIcon(fileName) {
  const ext = fileName.split(".").pop().toLowerCase();
  const imgExts = ["png","jpg","jpeg","gif","svg","webp","bmp","ico"];
  const codeExts = ["py","js","ts","jsx","tsx","java","go","rs","c","cpp","h","css","html","sh","yaml","json","xml"];
  const dataExts = ["csv","xlsx","xls","json"];
  const docExts = ["pdf","md","txt","doc","docx"];
  const archiveExts = ["zip","tar","gz","rar","7z"];
  if (imgExts.includes(ext)) return "🖼️";
  if (codeExts.includes(ext)) return "📄";
  if (dataExts.includes(ext)) return "📊";
  if (docExts.includes(ext)) return "📝";
  if (archiveExts.includes(ext)) return "📦";
  return "📎";
}

function loadSessionId() {
  let sid = localStorage.getItem("session_id");
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem("session_id", sid);
  }
  return sid;
}

function getSessions() {
  try {
    return JSON.parse(localStorage.getItem("sessions")) || [];
  } catch {
    return [];
  }
}

function saveSessions(sessions) {
  while (sessions.length > MAX_SESSIONS) sessions.shift();
  localStorage.setItem("sessions", JSON.stringify(sessions));
}

function findSessionIndex(sessions, id) {
  return sessions.findIndex(s => s.id === id);
}

function saveCurrentSession() {
  const sessions = getSessions();
  const idx = findSessionIndex(sessions, STATE.sessionId);
  const entry = {
    id: STATE.sessionId,
    name: STATE.sessionName || "",
    timestamp: new Date().toISOString(),
    firstMessage: getFirstMessage(STATE.currentMessages),
    messages: STATE.currentMessages,
  };

  if (idx >= 0) {
    if (sessions[idx].name && !STATE.sessionName) entry.name = sessions[idx].name;
    sessions[idx] = entry;
  } else {
    sessions.push(entry);
  }
  saveSessions(sessions);
}

function loadCurrentMessages() {
  const sessions = getSessions();
  const idx = findSessionIndex(sessions, STATE.sessionId);
  if (idx >= 0 && sessions[idx].messages) {
    STATE.currentMessages = sessions[idx].messages;
    STATE.sessionName = sessions[idx].name || "";
    els.messages.innerHTML = "";
    for (const msg of STATE.currentMessages) {
      renderMessage(msg.role, msg.content, msg.files, true);
    }
  } else {
    STATE.currentMessages = [];
    STATE.sessionName = "";
  }
}

function getFirstMessage(messages) {
  if (!messages || messages.length === 0) return "";
  const first = messages[0];
  return first && first.role === "user" ? first.content : "";
}

function truncate(text, len) {
  if (!text) return "";
  return text.length > len ? text.slice(0, len) + "…" : text;
}

// ── Session Display ────────────────────────────────────
function updateSessionDisplay() {
  // Session info is shown in the sidebar entries
}

function resetSession() {
  saveCurrentSession();

  STATE.sessionId = crypto.randomUUID();
  STATE.currentMessages = [];
  STATE.sessionName = "";
  localStorage.setItem("session_id", STATE.sessionId);
  els.messages.innerHTML = "";
  STATE.pendingFiles = [];
  updateFileBar();
  updateSessionDisplay();

  const sessions = getSessions();
  sessions.push({
    id: STATE.sessionId,
    name: "",
    timestamp: new Date().toISOString(),
    firstMessage: "",
    messages: [],
  });
  saveSessions(sessions);
  renderSidebar();
  updateWelcomeVisibility();
}

// ── Sidebar ────────────────────────────────────────────
function renderSidebar() {
  const list = els.sessionList;
  if (!list) return;
  const sessions = getSessions();
  list.innerHTML = "";

  const reversed = [...sessions].reverse();
  for (const sess of reversed) {
    const item = document.createElement("div");
    item.className = "session-item";
    if (sess.id === STATE.sessionId) item.classList.add("active");
    item.dataset.sessionId = sess.id;

    const displayName = sess.name || truncate(sess.firstMessage, 40) || "新会话";
    const isCurrentSession = sess.id === STATE.sessionId;
    item.innerHTML = `
      <div class="sess-header">
        <button class="sess-del" title="删除此会话">✕</button>
        <div class="sess-name">${escapeHtml(displayName)}</div>
      </div>
      <div class="sess-meta">
        <span>#${sess.id.split("-")[0]}</span>
        <span>${getRelativeTime(sess.timestamp)}</span>
      </div>
      ${sess.firstMessage && !sess.name ? `<div class="sess-preview">${escapeHtml(truncate(sess.firstMessage, 60))}</div>` : ""}
    `;

    const nameEl = item.querySelector(".sess-name");
    nameEl.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      if (nameEl.contentEditable === "true") return;
      startRename(sess.id, nameEl);
    });

    item.addEventListener("click", (e) => {
      if (e.target.closest(".sess-del")) return;
      if (sess.id !== STATE.sessionId) switchSession(sess.id);
    });

    const delBtn = item.querySelector(".sess-del");
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      confirmDeleteSession(sess.id, isCurrentSession);
    });

    list.appendChild(item);
  }
}

function startRename(sessionId, nameEl) {
  nameEl.contentEditable = "true";
  nameEl.focus();
  const range = document.createRange();
  range.selectNodeContents(nameEl);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);

  const finish = () => {
    if (nameEl.contentEditable !== "true") return;
    nameEl.contentEditable = "false";
    const newName = nameEl.textContent.trim();
    if (!newName) {
      const sessions = getSessions();
      const idx = findSessionIndex(sessions, sessionId);
      if (idx >= 0) {
        nameEl.textContent = sessions[idx].name || truncate(sessions[idx].firstMessage, 40) || "新会话";
      }
      return;
    }
    const sessions = getSessions();
    const idx = findSessionIndex(sessions, sessionId);
    if (idx >= 0) {
      sessions[idx].name = newName;
      saveSessions(sessions);
      if (sessionId === STATE.sessionId) STATE.sessionName = newName;
    }
  };

  nameEl.addEventListener("blur", finish, { once: true });
  nameEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      nameEl.blur();
    }
    if (e.key === "Escape") {
      const sessions = getSessions();
      const idx = findSessionIndex(sessions, sessionId);
      if (idx >= 0) {
        nameEl.textContent = sessions[idx].name || truncate(sessions[idx].firstMessage, 40) || "新会话";
      }
      nameEl.blur();
    }
  }, { once: true });
}

function switchSession(targetId) {
  saveCurrentSession();

  const sessions = getSessions();
  const idx = findSessionIndex(sessions, targetId);
  if (idx < 0) return;

  STATE.sessionId = targetId;
  STATE.currentMessages = sessions[idx].messages || [];
  STATE.sessionName = sessions[idx].name || "";
  localStorage.setItem("session_id", targetId);

  els.messages.innerHTML = "";
  for (const msg of STATE.currentMessages) {
    renderMessage(msg.role, msg.content, msg.files, true);
  }

  STATE.pendingFiles = [];
  updateFileBar();
  updateSessionDisplay();
  renderSidebar();

  if (window.innerWidth <= 640) {
    els.sidebar.classList.add("collapsed");
  }
  updateWelcomeVisibility();
}

async function deleteSession(sessionId, isCurrentSession) {
  // 1. 通知后端删除该会话的持久化记忆
  try {
    await fetch(`/sessions/${encodeURIComponent(sessionId)}/history`, { method: "DELETE" });
  } catch (_) {
    // 后端删除失败不阻塞前端清理
  }

  // 2. 从 localStorage 移除
  let sessions = getSessions();
  const idx = findSessionIndex(sessions, sessionId);
  if (idx >= 0) {
    sessions.splice(idx, 1);
    saveSessions(sessions);
  }

  // 3. 如果删除的是当前会话，新建一个
  if (isCurrentSession) {
    STATE.sessionId = crypto.randomUUID();
    STATE.currentMessages = [];
    STATE.sessionName = "";
    localStorage.setItem("session_id", STATE.sessionId);
    els.messages.innerHTML = "";

    sessions = getSessions();
    sessions.push({
      id: STATE.sessionId,
      name: "",
      timestamp: new Date().toISOString(),
      firstMessage: "",
      messages: [],
    });
    saveSessions(sessions);
    updateSessionDisplay();
  }

  renderSidebar();
}

function confirmDeleteSession(sessionId, isCurrentSession) {
  const name = sessionId === STATE.sessionId ? "当前会话" : "此会话";
  if (!confirm(`确定删除${name}？删除后无法恢复。`)) return;
  deleteSession(sessionId, isCurrentSession);
}

function toggleSidebar() {
  els.sidebar.classList.toggle("collapsed");
}

function getRelativeTime(isoStr) {
  if (!isoStr) return "";
  const now = Date.now();
  const then = new Date(isoStr).getTime();
  const diff = Math.floor((now - then) / 1000);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  const days = Math.floor(diff / 86400);
  if (days < 7) return `${days}天前`;
  return new Date(isoStr).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

// ── Theme ──────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem("theme");
  if (saved === "dark") {
    document.documentElement.classList.add("dark");
    els.themeToggle.textContent = "☀️";
  } else if (saved === "light") {
    document.documentElement.classList.remove("dark");
    els.themeToggle.textContent = "🌙";
  } else {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (prefersDark) {
      document.documentElement.classList.add("dark");
      els.themeToggle.textContent = "☀️";
    }
  }
}

function toggleTheme() {
  const html = document.documentElement;
  const isDark = html.classList.toggle("dark");
  els.themeToggle.textContent = isDark ? "☀️" : "🌙";
  localStorage.setItem("theme", isDark ? "dark" : "light");
}

// ── File Upload ────────────────────────────────────────
function openFilePicker() {
  els.fileInput.value = "";
  els.fileInput.click();
}

function handleFileSelected(e) {
  const files = Array.from(e.target.files);
  for (const file of files) {
    STATE.pendingFiles.push(file);
  }
  updateFileBar();
}

function removeFile(index) {
  STATE.pendingFiles.splice(index, 1);
  updateFileBar();
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + "B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + "KB";
  return (bytes / (1024 * 1024)).toFixed(1) + "MB";
}

function updateFileBar() {
  const list = els.fileList;
  list.innerHTML = "";

  if (STATE.pendingFiles.length === 0) {
    els.fileBar.classList.add("hidden");
    return;
  }

  els.fileBar.classList.remove("hidden");
  STATE.pendingFiles.forEach((file, i) => {
    const chip = document.createElement("span");
    chip.className = "file-chip";
    chip.innerHTML = `
      📎 ${escapeHtml(file.name)}
      <span class="file-size">${formatFileSize(file.size)}</span>
      <button class="file-remove" data-index="${i}" aria-label="移除文件">✕</button>
    `;
    chip.querySelector(".file-remove").addEventListener("click", () => removeFile(i));
    list.appendChild(chip);
  });
}

// ── Send Message ──────────────────────────────────────
async function sendMessage() {
  const text = els.messageInput.value.trim();
  if (!text || STATE.isSending) return;

  STATE.isSending = true;
  els.sendBtn.disabled = true;
  els.messageInput.disabled = true;
  els.loading.classList.remove("hidden");

  // Show user message immediately
  renderMessage("user", text);
  STATE.currentMessages.push({ role: "user", content: text });

  // Clear input
  els.messageInput.value = "";
  autoResizeTextarea();

  try {
    const formData = new FormData();
    formData.append("message", text);
    formData.append("session_id", STATE.sessionId);

    for (const file of STATE.pendingFiles) {
      formData.append("files", file);
    }

    const response = await fetch("/chat", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let errorMsg = `请求失败 (${response.status})`;
      try {
        const err = await response.json();
        if (err.detail) errorMsg = err.detail;
      } catch (_) {}
      throw new Error(errorMsg);
    }

    const data = await response.json();
    const downloadedFiles = data.downloaded_files || [];
    const reply = data.response || "(无回复)";
    renderMessage("ai", reply, downloadedFiles);
    STATE.currentMessages.push({ role: "ai", content: reply, files: downloadedFiles });

    // Persist after each exchange
    saveCurrentSession();
    renderSidebar();

    // Clear pending files after successful send
    STATE.pendingFiles = [];
    updateFileBar();

  } catch (err) {
    const errMsg = `⚠️ ${err.message || "网络错误，请检查后端服务"}`;
    renderMessage("ai", errMsg);
    STATE.currentMessages.push({ role: "ai", content: errMsg });
  } finally {
    STATE.isSending = false;
    els.sendBtn.disabled = false;
    els.messageInput.disabled = false;
    els.loading.classList.add("hidden");
    els.messageInput.focus();
    scrollToBottom();
  }
}

// ── Welcome State ─────────────────────────────────────
function updateWelcomeVisibility() {
  if (!els.welcome) return;
  const hasMessages = els.messages && els.messages.children.length > 0;
  els.welcome.classList.toggle("hidden", hasMessages);
}

function bindWelcomeEvents() {
  document.querySelectorAll(".suggestion-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const prompt = btn.dataset.prompt;
      if (prompt && els.messageInput) {
        els.messageInput.value = prompt;
        els.messageInput.focus();
        autoResizeTextarea();
      }
    });
  });
}

// ── Render Message ────────────────────────────────────
function renderMessage(role, content, files, isRestore) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;

  // Markdown to HTML via marked (full GFM support)
  let html;
  if (typeof marked !== "undefined") {
    html = marked.parse(content);
  } else {
    html = escapeHtml(content).replace(/\n/g, "<br>");
  }
  bubble.innerHTML = html;

  // Download links as file chips
  if (files && files.length > 0) {
    const dlDiv = document.createElement("div");
    dlDiv.className = "download-links";
    files.forEach(f => {
      const fileName = f.local.split(/[\\/]/).pop();
      const fileSize = f.size || 0;
      const summary = f.summary || "";
      const sessionId = STATE.sessionId;

      const chip = document.createElement("a");
      chip.className = "file-chip";
      chip.href = `/sessions/${encodeURIComponent(sessionId)}/downloads/${encodeURIComponent(fileName)}`;
      chip.download = fileName;
      chip.title = summary || fileName;

      const sizeText = formatFileSize(fileSize);
      chip.innerHTML = `<span class="chip-icon">${getFileIcon(fileName)}</span>`
        + `<span class="chip-name">${escapeHtml(fileName)}</span>`
        + (sizeText ? `<span class="chip-size">${sizeText}</span>` : "")
        + `<span class="chip-arrow">⬇</span>`;

      dlDiv.appendChild(chip);
    });

    // 打包下载按钮（只打包本轮对话的文件）
    const sessionId = STATE.sessionId;
    const fileNames = files.map(f => f.local.split(/[\\/]/).pop());
    const zipUrl = `/sessions/${encodeURIComponent(sessionId)}/downloads/zip?`
      + fileNames.map(n => `files=${encodeURIComponent(n)}`).join("&");
    const zipBtn = document.createElement("a");
    zipBtn.className = "file-chip zip-all";
    zipBtn.href = zipUrl;
    zipBtn.download = `${sessionId}.zip`;
    zipBtn.title = "打包下载本轮文件";
    zipBtn.innerHTML = `<span class="chip-icon">📦</span><span class="chip-name">打包下载</span><span class="chip-arrow">⬇</span>`;
    dlDiv.appendChild(zipBtn);

    bubble.appendChild(dlDiv);
  }

  els.messages.appendChild(bubble);
  updateWelcomeVisibility();
  scrollToBottom();
}

// ── Textarea Auto-resize ──────────────────────────────
function autoResizeTextarea() {
  const ta = els.messageInput;
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 150) + "px";
}

// ── Scroll to Bottom ──────────────────────────────────
function scrollToBottom() {
  requestAnimationFrame(() => {
    els.chatContainer.scrollTop = els.chatContainer.scrollHeight;
  });
}

// ── Drag & Drop ───────────────────────────────────────
function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

function handleDragEnter(e) {
  preventDefaults(e);
  els.chatContainer.classList.add("drag-over");
}

function handleDragLeave(e) {
  preventDefaults(e);
  if (!els.chatContainer.contains(e.relatedTarget)) {
    els.chatContainer.classList.remove("drag-over");
  }
}

function handleDrop(e) {
  preventDefaults(e);
  els.chatContainer.classList.remove("drag-over");
  const files = Array.from(e.dataTransfer.files);
  for (const file of files) {
    STATE.pendingFiles.push(file);
  }
  updateFileBar();
}

// ── Event Binding ─────────────────────────────────────
// ── MCP Management ───────────────────────────────────
const esc = escapeHtml;
const MCP_API = {
  listServers:      () => fetch("/mcp/servers").then(r => r.json()),
  createServer:     (d) => fetch("/mcp/servers", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(d)}).then(r => {if(!r.ok)throw r; return r.json()}),
  deleteServer:     (id) => fetch(`/mcp/servers/${id}`, {method:"DELETE"}).then(r => {if(!r.ok)throw r; return r.json()}),
  syncServer:       (id) => fetch(`/mcp/servers/${id}/sync`, {method:"POST"}).then(r => {if(!r.ok)throw r; return r.json()}),
  listTools:        (sid) => fetch(`/mcp/tools${sid ? `?server_id=${sid}` : ""}`).then(r => r.json()),
  toggleTool:       (id, e) => fetch(`/mcp/tools/${id}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({enabled:e})}).then(r => {if(!r.ok)throw r; return r.json()}),
};

function mcpToast(text, type) {
  const el = document.getElementById("mcp-toast");
  if (!el) return;
  el.innerHTML = `<div class="mcp-toast mcp-toast-${type}">${text}</div>`;
  if (type !== "loading") setTimeout(() => el.innerHTML = "", 4000);
}

function mcpServerNameFromUrl(url) {
  try {
    const u = new URL(url);
    return u.hostname + (u.port ? `:${u.port}` : "");
  } catch { return "mcp-server"; }
}

async function mcpRefresh() {
  const area = document.getElementById("mcp-server-area");
  const empty = document.getElementById("mcp-empty");
  if (!area) return;
  try {
    const servers = await MCP_API.listServers();
    if (!servers.length) {
      area.innerHTML = ""; empty.style.display = "";
      return;
    }
    empty.style.display = "none";

    // Load all tools in parallel
    const allTools = await MCP_API.listTools();
    const toolsByServer = {};
    for (const t of allTools) {
      if (!toolsByServer[t.server_id]) toolsByServer[t.server_id] = [];
      toolsByServer[t.server_id].push(t);
    }

    area.innerHTML = servers.map(s => {
      const tools = toolsByServer[s.id] || [];
      const toolHtml = tools.map(t => `
        <label class="mcp-tool-row">
          <span class="mcp-tool-name"><code>${esc(t.name)}</code></span>
          <span class="mcp-tool-desc">${esc((t.description||"").substring(0,50))}</span>
          <span class="mcp-toggle">
            <input type="checkbox" ${t.enabled ? "checked" : ""} data-tid="${t.id}" />
            <span class="mcp-toggle-track"><span class="mcp-toggle-thumb"></span></span>
          </span>
        </label>
      `).join("");

      return `<div class="mcp-server-card">
        <div class="mcp-server-top">
          <span class="mcp-server-name">${esc(s.name)}</span>
          <span class="mcp-server-url">${esc(s.url)}</span>
          <button class="mcp-server-del" data-sid="${s.id}" title="断开连接">✕</button>
        </div>
        <div class="mcp-server-tools">${toolHtml || '<div class="mcp-no-tools">暂无工具，点同步获取</div>'}</div>
        <div class="mcp-server-actions">
          <button class="mcp-sync-btn" data-sid="${s.id}">↻ 同步工具</button>
        </div>
      </div>`;
    }).join("");

    // Bind events for dynamic content
    area.querySelectorAll(".mcp-server-del").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("断开此 MCP 连接？")) return;
        try {
          await MCP_API.deleteServer(btn.dataset.sid);
          mcpRefresh();
        } catch { mcpToast("断开失败", "error"); }
      });
    });
    area.querySelectorAll(".mcp-sync-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        btn.textContent = "同步中..."; btn.disabled = true;
        try {
          await MCP_API.syncServer(btn.dataset.sid);
          mcpToast("同步完成", "success");
          mcpRefresh();
        } catch { mcpToast("同步失败", "error"); btn.textContent = "↻ 同步工具"; btn.disabled = false; }
      });
    });
    area.querySelectorAll(".mcp-toggle input").forEach(cb => {
      cb.addEventListener("change", async () => {
        try { await MCP_API.toggleTool(cb.dataset.tid, cb.checked); }
        catch { mcpToast("切换失败", "error"); cb.checked = !cb.checked; }
      });
    });
  } catch { area.innerHTML = '<div class="mcp-error-line">加载失败</div>'; }
}

async function mcpConnect(url) {
  const btn = document.getElementById("mcp-connect-btn");
  const mode = document.getElementById("mcp-mode-select").value;
  btn.textContent = "连接中..."; btn.disabled = true;
  mcpToast("正在连接...", "loading");
  try {
    const name = mcpServerNameFromUrl(url);
    const server = await MCP_API.createServer({ name, url, timeout: 60, transport_mode: mode });
    const sync = await MCP_API.syncServer(server.id);
    mcpToast(`✅ 已连接 ${name}，发现 ${sync.tools_count} 个工具`, "success");
    document.getElementById("mcp-url-input").value = "";
    mcpRefresh();
  } catch (e) {
    const text = await e.text().catch(() => "未知错误");
    mcpToast("连接失败: " + text, "error");
  } finally {
    btn.textContent = "连接"; btn.disabled = false;
  }
}

function bindMcpEvents() {
  // Toggle panel
  document.getElementById("mcp-btn")?.addEventListener("click", () => {
    document.getElementById("mcp-panel").classList.toggle("open");
    if (document.getElementById("mcp-panel").classList.contains("open")) mcpRefresh();
  });
  document.getElementById("mcp-panel-close")?.addEventListener("click", () => {
    document.getElementById("mcp-panel").classList.remove("open");
  });

  // Connect: button click + enter key
  document.getElementById("mcp-connect-btn")?.addEventListener("click", () => {
    const url = document.getElementById("mcp-url-input").value.trim();
    if (url) mcpConnect(url);
  });
  document.getElementById("mcp-url-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const url = e.target.value.trim();
      if (url) mcpConnect(url);
    }
  });

  // Drag to resize
  const panel = document.getElementById("mcp-panel");
  const handle = panel?.querySelector(".mcp-drag-handle");
  if (!handle) return;

  // Restore saved width
  const saved = localStorage.getItem("mcp_panel_width");
  if (saved) panel.style.width = saved + "px";

  let startX = 0, startW = 0;
  function onMove(e) {
    const dx = startX - (e.clientX || e.touches?.[0]?.clientX || 0);
    let w = Math.min(Math.max(startW + dx, 260), Math.min(window.innerWidth - 100, 800));
    panel.style.width = w + "px";
  }
  function onUp() {
    panel.classList.remove("resizing");
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    document.removeEventListener("touchmove", onMove);
    document.removeEventListener("touchend", onUp);
    localStorage.setItem("mcp_panel_width", parseInt(panel.style.width));
  }
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startX = e.clientX;
    startW = panel.offsetWidth;
    panel.classList.add("resizing");
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
  handle.addEventListener("touchstart", (e) => {
    startX = e.touches[0].clientX;
    startW = panel.offsetWidth;
    panel.classList.add("resizing");
    document.addEventListener("touchmove", onMove, { passive: true });
    document.addEventListener("touchend", onUp);
  }, { passive: true });
}

function bindEvents() {
  // Send
  els.sendBtn.addEventListener("click", sendMessage);

  // Keyboard
  els.messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize
  els.messageInput.addEventListener("input", autoResizeTextarea);

  // File upload button
  els.attachBtn.addEventListener("click", openFilePicker);
  els.fileInput.addEventListener("change", handleFileSelected);

  // Theme toggle
  els.themeToggle.addEventListener("click", toggleTheme);

  // New session (header button)
  els.newSessionBtn.addEventListener("click", resetSession);

  // Drag & drop
  ["dragenter", "dragover", "dragleave", "drop"].forEach(evt => {
    els.chatContainer.addEventListener(evt, preventDefaults, false);
  });
  els.chatContainer.addEventListener("dragenter", handleDragEnter, false);
  els.chatContainer.addEventListener("dragover", preventDefaults, false);
  els.chatContainer.addEventListener("dragleave", handleDragLeave, false);
  els.chatContainer.addEventListener("drop", handleDrop, false);
}

function bindSidebarEvents() {
  if (els.sidebarToggle) {
    els.sidebarToggle.addEventListener("click", toggleSidebar);
  }
  if (els.newSessionSidebar) {
    els.newSessionSidebar.addEventListener("click", resetSession);
  }
}

// ── Utilities ─────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
