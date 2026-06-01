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
});

// ── Session Persistence ────────────────────────────────
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
    item.innerHTML = `
      <div class="sess-name">${escapeHtml(displayName)}</div>
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

    item.addEventListener("click", () => {
      if (sess.id !== STATE.sessionId) switchSession(sess.id);
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
      const chip = document.createElement("a");
      chip.className = "file-chip";
      chip.href = `/downloads/${encodeURIComponent(fileName)}`;
      chip.download = fileName;
      chip.innerHTML = `<span class="chip-name">${escapeHtml(fileName)}</span> <span class="chip-arrow">⬇</span>`;
      dlDiv.appendChild(chip);
    });
    bubble.appendChild(dlDiv);
  }

  els.messages.appendChild(bubble);
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
