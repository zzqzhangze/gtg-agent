// ── State ──────────────────────────────────────────────
const STATE = {
  sessionId: loadSessionId(),
  pendingFiles: [],
  isSending: false,
};

// ── DOM References ─────────────────────────────────────
let els = {};

document.addEventListener("DOMContentLoaded", () => {
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
  };

  initTheme();
  bindEvents();
});

// ── Session Management ─────────────────────────────────
function loadSessionId() {
  let sid = localStorage.getItem("session_id");
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem("session_id", sid);
  }
  return sid;
}

function resetSession() {
  STATE.sessionId = crypto.randomUUID();
  localStorage.setItem("session_id", STATE.sessionId);
  els.messages.innerHTML = "";
  STATE.pendingFiles = [];
  updateFileBar();
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
    // Follow system preference
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
    renderMessage("ai", data.response || "(无回复)", downloadedFiles);

    // Clear pending files after successful send
    STATE.pendingFiles = [];
    updateFileBar();

  } catch (err) {
    renderMessage("ai", `⚠️ ${err.message || "网络错误，请检查后端服务"}`);
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
function renderMessage(role, content, files) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;

  // Basic Markdown-like rendering:
  // - Code blocks ```...```
  // - Inline code `...`
  // - Bold **...**
  // - Line breaks
  let html = escapeHtml(content);

  // Code blocks (must be before inline code)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const langClass = lang ? ` class="language-${escapeHtml(lang)}"` : "";
    return `<pre${langClass}><code>${escapeHtml(code.trim())}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Paragraphs (double newlines)
  html = html.replace(/\n\n/g, "</p><p>");

  // Single newlines (within paragraph)
  html = html.replace(/\n/g, "<br>");

  // Wrap in <p> tags if not already wrapped by code blocks
  if (!html.startsWith("<pre")) {
    html = "<p>" + html + "</p>";
  }

  bubble.innerHTML = html;

  // Download links
  if (files && files.length > 0) {
    const dlDiv = document.createElement("div");
    dlDiv.className = "download-links";
    files.forEach(f => {
      const fileName = f.local.split(/[\\/]/).pop();
      const a = document.createElement("a");
      a.href = `/files/${STATE.sessionId}/${encodeURIComponent(fileName)}`;
      a.textContent = `📦 ${fileName}`;
      a.target = "_blank";
      a.rel = "noopener";
      dlDiv.appendChild(a);
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
  // Only remove if leaving the container entirely
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

  // New session
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

// ── Utilities ─────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
