# Web UI Implementation Plan

> status: in_progress (v2 — sidebar + session history)
> branch: feat/web-ui
> created: 2026-05-31
> updated: 2026-06-01
>
> 注册：`.sisyphus/plans/INDEX.md`
>
> **Sub-plan of:** `.sisyphus/plans/agent-intelligence-upgrade.md`
>
> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 该计划随 agent 主计划同步更新，前端界面需反映 agent 当前能力。

**Goal:** Add a browser-based chat interface to My Deep Agent, served by the existing FastAPI backend.

**Architecture:** FastAPI serves static files (`static/index.html`, `style.css`, `app.js`) alongside its REST API. The front-end is a pure HTML/CSS/JS SPA that calls `POST /chat` via Fetch API — no build step, no npm.

**Tech Stack:** FastAPI (static file serving), vanilla HTML/CSS/JS (ES6+), CSS custom properties (dark mode).

**Design doc:** `docs/agent-web-ui-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `api.py` | **Modify** | Mount `StaticFiles` at `/static/`, set `/` to serve `index.html` |
| `static/index.html` | **Create** | HTML5 page skeleton: header, chat area, file preview bar, input area |
| `static/style.css` | **Create** | All styles: layout, message bubbles, dark mode (CSS vars), responsive, animations |
| `static/app.js` | **Create** | All JS logic: session mgmt, message send/render, file upload/download, dark toggle, error handling |

---

### Task 1: FastAPI Static File Serving

**Files:**
- Modify: `api.py` (add imports + mount + root route update)

- [x] **Step 1: Add static file imports to api.py**
- [x] **Step 2: Mount StaticFiles and update root route**
- [x] **Step 3: Create temporary placeholder**
- [x] **Step 4: Verify static serving**
- [x] **Step 5: Commit**

```bash
git add api.py static/index.html static/style.css static/app.js
git commit -m "feat: add static file serving for web UI"
```

---

### Task 2: HTML Page Skeleton

**Files:**
- Create: `static/index.html`

- [x] **Step 1: Write the full index.html**

Structure (semantic HTML5):
```
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>My Deep Agent</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <!-- Header -->
  <header id="header">
    <div class="logo">🤖 My Deep Agent</div>
    <div class="header-actions">
      <button id="theme-toggle" title="切换暗色模式">🌙</button>
      <button id="new-session" title="新会话">🆕</button>
    </div>
  </header>

  <!-- Chat Container -->
  <main id="chat-container">
    <div id="messages"></div>
    <div id="loading" class="hidden">
      <span class="dot-pulse"></span> 思考中...
    </div>
  </main>

  <!-- File Preview Bar -->
  <div id="file-bar" class="hidden">
    <div id="file-list"></div>
  </div>

  <!-- Input Area -->
  <footer id="input-area">
    <button id="attach-btn" title="上传文件">📎</button>
    <input type="file" id="file-input" multiple hidden>
    <textarea id="message-input" rows="1" placeholder="输入消息..." maxlength="10000"></textarea>
    <button id="send-btn" title="发送">➤</button>
  </footer>

  <script src="/static/app.js"></script>
</body>
</html>
```

Note: `id="file-input"` is hidden; `#attach-btn` triggers its click.

- [x] **Step 2: Commit**

```bash
git add static/index.html
git commit -m "feat: implement chat UI - HTML page skeleton"
```

---

### Task 3: CSS Theming and Dark Mode

**Files:**
- Create: `static/style.css`

- [x] **Step 1: Write style.css with CSS variables and full layout**

Sections:
1. **CSS Reset** — box-sizing, margin/padding zero, font-family system stack
2. **CSS Variables (light)** — `:root` with color tokens per design doc
3. **CSS Variables (dark)** — `html.dark` overriding relevant tokens
4. **Layout** — full viewport height, flex column, header/chat/input
5. **Header** — fixed top, flex row, logo + actions
6. **Chat Container** — flex-grow, overflow-y auto, scrollable message area
7. **Message Bubbles** — user (right, blue), AI (left, gray), markdown content
8. **Loading Indicator** — dot-pulse CSS animation
9. **File Preview Bar** — flex row, file chips with delete button
10. **Input Area** — sticky bottom, textarea auto-grow, send button
11. **Responsive** — `< 640px` adjustments
12. **Animations** — fade-in for new messages, smooth scroll
13. **Utilities** — `.hidden`, scrollbar styling

Color tokens (from design doc):

```css
:root {
  --bg: #f5f5f5;
  --surface: #ffffff;
  --surface-hover: #f0f0f0;
  --text: #1a1a1a;
  --text-secondary: #666;
  --border: #e0e0e0;
  --bubble-user: #3b82f6;
  --bubble-user-text: #ffffff;
  --bubble-ai: #f0f0f0;
  --bubble-ai-text: #1a1a1a;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --danger: #ef4444;
  --shadow: 0 2px 8px rgba(0,0,0,0.08);
}

html.dark {
  --bg: #1a1a2e;
  --surface: #16213e;
  --surface-hover: #1e2a4a;
  --text: #e4e4e7;
  --text-secondary: #a1a1aa;
  --border: #2a2a4e;
  --bubble-user: #2563eb;
  --bubble-ai: #2a2a3e;
  --bubble-ai-text: #e4e4e7;
  --accent: #60a5fa;
  --accent-hover: #3b82f6;
  --shadow: 0 2px 8px rgba(0,0,0,0.3);
}
```

Key message bubble CSS:
```css
.message {
  max-width: 80%;
  margin: 8px 16px;
  padding: 12px 16px;
  border-radius: 12px;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.message.user {
  align-self: flex-end;
  background: var(--bubble-user);
  color: var(--bubble-user-text);
  border-bottom-right-radius: 4px;
}
.message.ai {
  align-self: flex-start;
  background: var(--bubble-ai);
  color: var(--bubble-ai-text);
  border-bottom-left-radius: 4px;
}
```

- [x] **Step 2: Verify**

Open `static/index.html` in browser directly (or via FastAPI) — layout should render, dark mode toggle should work.

- [x] **Step 3: Commit**

---

### Task 4: JavaScript Interaction Logic

**Files:**
- Create: `static/app.js`

- [x] **Step 1: Write app.js with all interaction logic**

Sections:

```javascript
// ── State ──────────────────────────────────────────────
const STATE = {
  sessionId: loadSessionId(),
  messages: [],              // [{role, content, files?}]
  pendingFiles: [],          // File objects
  isSending: false,
};

// ── Session Management ─────────────────────────────────
function loadSessionId() { /* localStorage get or create */ }
function resetSession() { /* new UUID → clear UI */ }

// ── DOM References ─────────────────────────────────────
// Cache all element references on DOMContentLoaded

// ── File Upload ────────────────────────────────────────
// attach-btn → file-input.click()
// file-input change → push to STATE.pendingFiles → render file-bar
// file chip delete → remove from pendingFiles
// drag-drop on chat area

// ── Send Message ───────────────────────────────────────
async function sendMessage() {
  // 1. Read input.value, trim, skip if empty
  // 2. Build FormData:
  //    formData.append("message", text)
  //    formData.append("session_id", STATE.sessionId)
  //    for each pendingFile: formData.append("files", file)
  // 3. Disable input, show loading
  // 4. fetch POST /chat, body: formData
  // 5. Parse JSON: {response, downloaded_files}
  // 6. renderMessage("user", text)
  // 7. renderMessage("ai", response, downloaded_files)
  // 8. Clear input, clear pendingFiles, hide loading
  // 9. Scroll to bottom
}

function renderMessage(role, content, files) {
  // Create .message div with class user/ai
  // Set content (escape HTML, support basic markdown)
  // If files: render download links below content
  // Append to #messages, scroll into view
}

// ── Dark Mode ──────────────────────────────────────────
function initTheme() {
  // Check localStorage "theme"
  // If "dark" → add class to html
  // Else check prefers-color-scheme
}
function toggleTheme() { /* toggle html.dark, save to localStorage */ }

// ── Auto-resize Textarea ───────────────────────────────
// On input: textarea.style.height = "auto"; textarea.style.height = textarea.scrollHeight + "px"

// ── Keyboard ───────────────────────────────────────────
// Enter (no Shift) → sendMessage
// Shift+Enter → newline

// ── Init ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  // Bind event listeners
});
```

**File download link format:**
```javascript
if (files && files.length > 0) {
  const dlDiv = document.createElement("div");
  dlDiv.className = "download-links";
  files.forEach(f => {
    const fileName = f.local.split(/[\\/]/).pop();
    const a = document.createElement("a");
    a.href = `/files/${STATE.sessionId}/${fileName}`;
    a.textContent = `📦 ${fileName}`;
    a.target = "_blank";
    dlDiv.appendChild(a);
  });
  bubble.appendChild(dlDiv);
}
```

- [ ] **Step 2: Verify integration**

Manual test flow:
1. Start backend: `uv run uvicorn api:app --host 0.0.0.0 --port 8000`
2. Open `http://localhost:8000/` in browser
3. UI should render with header, empty chat area, input box
4. Type a message → send → see user bubble appear
5. Wait for response → AI bubble with text appears
6. Dark mode toggle works
7. New session button clears chat

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: implement chat UI - JavaScript interaction logic"
```
---

### Task 5: Sidebar + Session History

**Files:**
- Modify: `static/index.html` (sidebar HTML structure, hamburger button, `#main` wrapper)
- Modify: `static/style.css` (sidebar layout, collapsible transitions, session items)
- Modify: `static/app.js` (session history CRUD, sidebar rendering, rename, switch)

- [x] **Step 1: Sidebar HTML structure**
  - Wrap `#chat-container`, `#file-bar`, `#input-area` in `#chat-panel`
  - Add `#main` wrapper containing `#sidebar` + `#chat-panel`
  - Add `#sidebar-toggle` (☰) to header-left
  - Add `#session-badge` showing short ID (`#a1b2`) in header-actions
  - Add `#new-session-sidebar` (＋) in sidebar header

- [x] **Step 2: Sidebar CSS**
  - `#main`: `display: flex`, `flex: 1`, `overflow: hidden`
  - `#sidebar`: `width: 260px`, collapsible via `.collapsed` class (width 0 → margin-left -260px)
  - `.sidebar-header`, `.sidebar-title`, `#session-list`
  - `.session-item`: hover, active state, name/meta/preview styling
  - `.sess-name[contenteditable]`: editing state visual
  - Mobile: sidebar covers full screen at <640px

- [x] **Step 3: Session History**
  - `getSessions()` / `saveSessions()` — localStorage with MAX_SESSIONS=20
  - `saveCurrentSession()` — save current messages before switch
  - `loadCurrentMessages()` — restore messages on page load
  - `switchSession(id)` — save current → load target → re-render
  - `resetSession()` — save previous session, create new one
  - Format: `{ id, name, timestamp, firstMessage, messages[] }`

- [x] **Step 4: Sidebar JS**
  - `renderSidebar()` — iterate sessions (reverse order, newest first)
  - Double-click rename → `contentEditable` → blur/Enter save → Escape cancel
  - Click switch → `switchSession(id)` → close sidebar on mobile
  - `toggleSidebar()` — toggle `.collapsed` class
  - `getRelativeTime()` — "刚刚", "N分钟前", "N小时前", "N天前"
  - Auto-save after each message exchange (sendMessage → saveCurrentSession)

- [x] **Step 5: Download link redesign**
  - File chip style (pill shape, subtle background)
  - `.file-chip` with `border-radius: 20px`, hover turns accent blue + white text
  - File name truncated with ellipsis + ⬇ arrow on right

- [x] **Step 6: Markdown rendering (marked.js)**
  - Download `marked.min.js` to `static/` (v15.0.12, local copy, no CDN dependency)
  - Add `<script src="/static/marked.min.js">` before app.js in index.html
  - Replace manual regex markdown with `marked.parse(content)` in renderMessage
  - Config: `gfm: true, breaks: true` for full GFM + chat-style newlines
  - Bubble styles: headings, tables, lists, blockquotes, code blocks, links, images, strikethrough

- [x] **Step 7: Message style improvements**
  - AI bubble: left accent border (`border-left: 3px solid var(--accent)`)
  - Subtle box shadows on bubbles
  - Better spacing (`padding: 14px 18px`)
  - Complete markdown content styling (h1-h6, tables, blockquotes, lists, hr, code, links)
  - User message overrides for light-on-dark content
  - Remove `white-space: pre-wrap` (marked handles line breaks)

- [ ] **Step 8: User test** — user will verify before commit

```bash
# After testing:
git add static/index.html static/style.css static/app.js static/marked.min.js docs/agent-web-ui-design.md test-reports/web-ui-test-report.md .sisyphus/plans/web-ui.md
git commit -m "feat: full markdown rendering with marked.js, file-chip download style, message aesthetic improvements"
```

---

## Manual Verification Checklist

After all tasks are done:

- [ ] `curl http://localhost:8000/` → returns HTML page
- [ ] `curl http://localhost:8000/static/style.css` → returns CSS (200)
- [ ] `curl http://localhost:8000/static/app.js` → returns JS (200)
- [ ] Browser: Page renders with correct layout
- [ ] Browser: Type message → send → message appears as user bubble
- [ ] Browser: Loading indicator shows during request
- [ ] Browser: AI response renders in AI bubble with correct formatting
- [ ] Browser: File upload button opens file picker
- [ ] Browser: Selected files show in preview bar
- [ ] Browser: Dark mode toggle switches theme
- [ ] Browser: New session button clears chat
- [ ] Browser: Session persists across page refresh (same session_id)
- [ ] Browser: Error state shows appropriate message for network failure

## 后续维护指南

> 当 agent-intelligence-upgrade.md 中的方向有变更时，同步检查：
> - 新增状态字段 → 前端是否需展示？
> - 新增节点 → 前端是否需可视化？
> - 新增文件类型 → 前端下载链接是否需要适配？
> - 后端 API 接口变更 → 前端 fetch 路径是否需更新？
