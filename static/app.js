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
  const S = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:1em;height:1em">${d}</svg>`;
  if (imgExts.includes(ext)) return S('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>');
  if (codeExts.includes(ext)) return S('<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2Z"/><polyline points="14 2 14 8 20 8"/>');
  if (dataExts.includes(ext)) return S('<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>');
  if (docExts.includes(ext)) return S('<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2Z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>');
  if (archiveExts.includes(ext)) return S('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>');
  return S('<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>');
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
      try {
        renderMessage(msg.role, msg.content, msg.files, true);
      } catch (_) {
        // 个别消息渲染失败不阻塞整个列表恢复
        console.warn("跳过渲染异常消息", msg);
      }
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
    els.themeToggle.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:20px;height:20px"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
  } else if (saved === "light") {
    document.documentElement.classList.remove("dark");
    els.themeToggle.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:20px;height:20px"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  } else {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (prefersDark) {
      document.documentElement.classList.add("dark");
      els.themeToggle.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:20px;height:20px"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
    }
  }
}

function toggleTheme() {
  const html = document.documentElement;
  const isDark = html.classList.toggle("dark");
  els.themeToggle.innerHTML = isDark
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:20px;height:20px"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:20px;height:20px"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
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
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:14px;height:14px;margin-right:4px"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg> ${escapeHtml(file.name)}
      <span class="file-size">${formatFileSize(file.size)}</span>
      <button class="file-remove" data-index="${i}" aria-label="移除文件">✕</button>
    `;
    chip.querySelector(".file-remove").addEventListener("click", () => removeFile(i));
    list.appendChild(chip);
  });
}

// ── Execution Timeline (执行日志) ──────────────────
function addLogEntry(message) {
  const log = document.getElementById("execution-log");
  if (!log) return;
  const entry = document.createElement("div");
  entry.className = "log-entry active";
  entry.innerHTML =
    '<span class="log-icon">⏳</span>' +
    '<span class="log-text">' + escapeHtml(message) + '</span>' +
    '<span class="typing-dots"><span></span><span></span><span></span></span>';
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function completeActiveEntry() {
  const log = document.getElementById("execution-log");
  if (!log) return;
  const active = log.querySelector(".log-entry.active");
  if (!active) return;
  active.classList.remove("active");
  active.classList.add("completed");
  const icon = active.querySelector(".log-icon");
  if (icon) icon.textContent = "✅";
  const dots = active.querySelector(".typing-dots");
  if (dots) dots.remove();
}

function setDetailText(text) {
  const log = document.getElementById("execution-log");
  if (!log) return;
  // 追加到当前 active 条目（多个 _detail 事件会依次追加成多行）
  const target = log.querySelector(".log-entry.active") || log.lastElementChild;
  if (!target) return;
  const detail = document.createElement("div");
  detail.className = "log-detail";
  detail.textContent = text;
  target.appendChild(detail);
}

function clearExecutionLog() {
  const log = document.getElementById("execution-log");
  if (log) log.innerHTML = "";
}

function finalizeExecutionLog(isError) {
  const log = document.getElementById("execution-log");
  if (!log || log.children.length === 0) return;

  const steps = log.innerHTML;  // 保存日志内容
  const stepCount = (steps.match(/log-entry/g) || []).length;
  log.innerHTML = "";            // 清空

  // 构建折叠块
  const container = document.createElement("div");
  container.className = "execution-summary";

  const toggle = document.createElement("button");
  toggle.className = "execution-toggle";
  toggle.innerHTML = '<span class="toggle-icon">▼</span> 执行链路（' + stepCount + '步）';

  const body = document.createElement("div");
  body.className = "execution-steps open";
  body.innerHTML = steps;

  // 错误场景打标
  if (isError) {
    toggle.innerHTML = '<span class="toggle-icon">▼</span> ⚠️ 执行出错';
    body.classList.add("has-error");
  }

  toggle.addEventListener("click", () => {
    const icon = toggle.querySelector(".toggle-icon");
    body.classList.toggle("open");
    icon.textContent = body.classList.contains("open") ? "▼" : "▶";
  });

  container.appendChild(toggle);
  container.appendChild(body);
  els.messages.appendChild(container);
  scrollToBottom();
}

// ── SSE Event Handling ───────────────────────────────
function handleSSEEvent(data) {
  if (data.type === "status") {
    if (data.phase.endsWith("_detail")) {
      // 详情信息：作为当前步骤的补充说明行
      setDetailText(data.message);
    } else {
      // 新步骤：完成上一步，创建当前步
      completeActiveEntry();
      addLogEntry(data.message);
    }
  } else if (data.type === "done") {
    // 标记最后一步完成
    completeActiveEntry();
    // 将执行日志固化为折叠块插入对话区
    finalizeExecutionLog(false);
    // 渲染最终回复
    const reply = data.data.response || "(无回复)";
    const downloadedFiles = data.data.downloaded_files || [];
    renderMessage("ai", reply, downloadedFiles);
    STATE.currentMessages.push({ role: "ai", content: reply, files: downloadedFiles });
    saveCurrentSession();
    renderSidebar();
    STATE.pendingFiles = [];
    updateFileBar();
  } else if (data.type === "error") {
    completeActiveEntry();
    // 错误步骤打红叉
    const log = document.getElementById("execution-log");
    if (log && log.lastElementChild) {
      const icon = log.lastElementChild.querySelector(".log-icon");
      if (icon) icon.textContent = "❌";
    }
    // 将执行日志固化为折叠块（错误标记）
    finalizeExecutionLog(true);
    const errMsg = `⚠️ ${data.data.message || "执行出错"}`;
    renderMessage("ai", errMsg);
    STATE.currentMessages.push({ role: "ai", content: errMsg });
  }
}

// ── Send Message ──────────────────────────────────────
async function sendMessage() {
  const text = els.messageInput.value.trim();
  if (!text || STATE.isSending) return;

  STATE.isSending = true;
  els.sendBtn.disabled = true;
  els.messageInput.disabled = true;
  els.loading.classList.remove("hidden");
  clearExecutionLog();

  // 记录当前待发文件并立即清空输入栏的文件展示
  const sentFiles = STATE.pendingFiles.slice();
  STATE.pendingFiles = [];
  updateFileBar();

  // 构造可 JSON 序列化的文件信息（File 对象不能直接存 localStorage）
  const fileInfos = sentFiles.map(f => ({ name: f.name, size: f.size }));

  // Show user message immediately (附上文件信息)
  renderMessage("user", text, fileInfos);
  STATE.currentMessages.push({ role: "user", content: text, files: fileInfos });

  // Clear input
  els.messageInput.value = "";
  autoResizeTextarea();

  try {
    const formData = new FormData();
    formData.append("message", text);
    formData.append("session_id", STATE.sessionId);

    for (const file of sentFiles) {
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

    // SSE 流式读取
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 按 SSE 事件边界分割（双换行）
      const parts = buffer.split("\n");
      buffer = parts.pop() || "";  // 不完整的行留在 buffer

      for (const line of parts) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            handleSSEEvent(data);
          } catch (_) {
            // 忽略畸形的 JSON
          }
        }
      }
    }

    // 处理最后可能残留的 SSE 事件
    if (buffer.startsWith("data: ")) {
      try {
        const data = JSON.parse(buffer.slice(6));
        handleSSEEvent(data);
      } catch (_) {}
    }

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

  // File chips: support user-uploaded file info ({name, size}) and server download objects ({local, size, summary})
  if (files && files.length > 0) {
    const dlDiv = document.createElement("div");
    dlDiv.className = "download-links";

    // 判断类型：有 .name 无 .local → 用户文件；有 .local → 服务端下载；否则跳过
    const first = files[0];
    const isUserFile = first && typeof first.name === "string" && typeof first.local !== "string";
    const isServerFile = first && typeof first.local === "string";

    if (isUserFile) {
      // 用户消息：只展示文件名和大小，不可下载
      files.forEach(f => {
        const chip = document.createElement("span");
        chip.className = "file-chip";
        const sizeText = f.size ? formatFileSize(f.size) : "";
        const fname = f.name || "未知文件";
        chip.innerHTML = `<span class="chip-icon">${getFileIcon(fname)}</span>`
          + `<span class="chip-name">${escapeHtml(fname)}</span>`
          + (sizeText ? `<span class="chip-size">${sizeText}</span>` : "");
        dlDiv.appendChild(chip);
      });
    } else if (isServerFile) {
      // AI 回复：提供下载链接
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

      // 打包下载按钮
      const sessionId = STATE.sessionId;
      const fileNames = files.map(f => f.local.split(/[\\/]/).pop());
      const zipUrl = `/sessions/${encodeURIComponent(sessionId)}/downloads/zip?`
        + fileNames.map(n => `files=${encodeURIComponent(n)}`).join("&");
      const zipBtn = document.createElement("a");
      zipBtn.className = "file-chip zip-all";
      zipBtn.href = zipUrl;
      zipBtn.download = `${sessionId}.zip`;
      zipBtn.title = "打包下载本轮文件";
      zipBtn.innerHTML = `<span class="chip-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:1em;height:1em"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg></span><span class="chip-name">打包下载</span><span class="chip-arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;width:1em;height:1em"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg></span>`;
      dlDiv.appendChild(zipBtn);
    }
    // else: 无法识别的文件数据，不渲染

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
