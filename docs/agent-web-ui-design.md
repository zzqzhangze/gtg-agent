# Agent Web 聊天界面 — 设计方案

> status: updated (v2 — download optimization applied)
> created: 2026-05-31
> updated: 2026-06-01
>
> 对应 plan: `.omo/plans/download-optimization.md`

---

## 1. 目标

为 GTG Agent 提供浏览器端可视化聊天界面，替代/补充现有 CLI REPL 模式，使非技术用户也能通过网页交互使用 Agent。

**MVP 范围：** 聊天对话 + 文件上传/下载 + 会话管理 + 暗色模式。工作流可视化等后续方向暂不纳入。

## 2. 架构

```
┌─ Browser ─────────────────────┐     ┌─ FastAPI Server ────────────┐
│                               │     │                            │
│  static/index.html            │─────│  GET /  → index.html       │
│  static/style.css             │     │  GET /static/*              │
│  static/app.js                │     │  POST /chat (multipart)    │
│                               │     │  GET /files/{sid}/{file}   │
│  Build FormData               │     │                            │
│  → message + session_id       │     │  LangGraph                 │
│  → files[]                    │─────│  → analyze_intent          │
│                               │     │  → create_sandbox          │
│  Render response              │     │  → run_agent               │
│  → 消息气泡                   │     │  → detect_output           │
│  → 下载链接                   │     │  → analyze_output          │
│                               │     │  → download_files          │
└───────────────────────────────┘     └────────────────────────────┘
```

### 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 构建工具 | 无（纯 HTML/CSS/JS）| 零额外依赖，FastAPI 直接 serve |
| CSS 方案 | CSS 自定义属性 (var) | 原生支持暗色模式切换 |
| HTTP 客户端 | Fetch API (ES6+) | 无额外依赖 |
| 会话标识 | crypto.randomUUID() | 浏览器原生，无需后端生成 |
| 持久化 | localStorage | 会话 ID + 暗色偏好 + 会话历史 |
| 消息格式 | Markdown → marked.parse() | 完整 GFM 支持，`static/marked.min.js` 本地引用（< 30KB），内外网通用 |
| 消息格式 | Markdown 字符串 → 前端渲染 | 后端已返回纯文本 |

## 3. 文件结构

```
gtg_agent/
├── static/                   ← 新增
│   ├── index.html            页面骨架
│   ├── style.css             全部样式 + 暗色模式变量
│   ├── app.js                全部交互逻辑
│   └── marked.min.js         Markdown 解析库（本地引用，无网络依赖）
├── api.py                    + 修改：挂载 StaticFiles + 根路由
```

不新增 `package.json`、`node_modules`、构建配置。所有前端代码是普通的静态文件。

## 4. UI 规范

### 4.1 布局（v2 — 含侧边栏）

```
┌──────────────────────────────────────────────────────┐
│  Header                                         24px │
│  ┌────┬──────────────────────────────────────────┐   │
│  │ ☰  │ 🤖 GTG Agent       #a1b2  🌙  🆕   │   │
│  └────┴──────────────────────────────────────────┘   │
│ ┌───────────┬──────────────────────────────────────┐  │
│ │  侧边栏   │  聊天区域                              │  │
│ │  260px    │                                      │  │
│ │           │  ┌──────────────────────────────┐    │  │
│ │ 会话历史   │  │  用户消息（右对齐，蓝色气泡）   │    │  │
│ │ ════════  │  └──────────────────────────────┘    │  │
│ │           │                                      │  │
│ │ ◉ a1b2    │  ┌──────────────────────────────┐    │  │
│ │   自定义名  │  │  AI 回复（左对齐，灰色气泡）    │    │  │
│ │   10:30    │  │  Markdown 渲染内容            │    │  │
│ │   首条预览  │  │  bubble_sort.py ⬇ [下载]     │    │  │
│ │           │  └──────────────────────────────┘    │  │
│ │ ○ c3d4    │                                      │  │
│ │   10:15   │  File Preview Bar (可选)              │  │
│ │           │  ┌──────────────────────────────┐    │  │
│ │ ＋ 新建    │  │  📎 data.csv ✕  script.py ✕  │    │  │
│ │           │  └──────────────────────────────┘    │  │
│ └───────────┴──────────────────────────────────────┘  │
│  Input Area (sticky bottom)                           │
│  ┌─────────────────────────────────────────────────┐  │
│  │ [📎]  [输入消息...                  ] [➤ 发送]   │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**侧边栏特性：**

- 默认收起（`☰` 汉堡菜单展开）
- 每个条目显示：自定义名称（可双击编辑）、短 ID、相对时间、首条消息预览
- 当前会话高亮（`.active`）
- 点击切换会话，收起时自动恢复
- 底部或顶部"＋新建"按钮
- 移动端（<640px）覆盖全屏

**关键 CSS 结构：**

```css
#main { display: flex; flex: 1; overflow: hidden; }

#sidebar {
  width: 260px;
  flex-shrink: 0;
  transition: width 0.2s, margin-left 0.2s;
}
#sidebar.collapsed {
  width: 0;
  margin-left: -260px;
}

#chat-panel { flex: 1; display: flex; flex-direction: column; }
```

### 4.2 暗色模式

- CSS 自定义属性定义两套色板，通过 `html.dark` 切换
- 默认跟随 `prefers-color-scheme`
- 手动切换后存 `localStorage`
- 色板：

| Token | 亮色 | 暗色 |
|-------|------|------|
| `--bg` | `#f5f5f5` | `#1a1a2e` |
| `--surface` | `#ffffff` | `#16213e` |
| `--text` | `#1a1a1a` | `#e4e4e7` |
| `--bubble-user` | `#3b82f6` | `#2563eb` |
| `--bubble-ai` | `#f0f0f0` | `#2a2a3e` |
| `--accent` | `#3b82f6` | `#60a5fa` |

### 4.3 响应式

- 聊天区域最大宽度 800px，居中
- 移动端（<640px）：圆角减小，内边距缩减，输入框全宽

## 5. 数据流

### 5.1 发送消息

```
1. 用户输入消息 + (可选) 选择文件
2. app.js 构建 FormData:
   └─ message: string
   └─ session_id: string (from localStorage)
   └─ files: File[] (optional)
3. fetch POST /chat, body: FormData
4. 前端显示加载指示器
5. 收到响应 {response, downloaded_files}
6. 渲染消息气泡 + 文件下载链接
7. 清除加载状态，滚动到底部
```

### 5.2 文件下载

```
后端返回 downloaded_files: [{"sandbox": "...", "local": "..."}]
前端从 local 路径提取文件名，构造:
  GET /downloads/{filename}
渲染为:
  <a class="file-chip" href="/downloads/{filename}" download="...">
    <span class="chip-name">{filename}</span> <span class="chip-arrow">⬇</span>
  </a>
（圆角 pill 样式，浅灰背景，hover 变蓝底白字）
```

### 5.3 会话管理（v2 — localStorage 历史存储）

```
页面加载:
  session_id = localStorage.getItem("session_id") || crypto.randomUUID()
  sessions  = JSON.parse(localStorage.getItem("sessions")) || []
  如果 session_id 在 sessions 中 → 恢复消息
  渲染侧边栏

发送消息后:
  push {role, content, files} → STATE.currentMessages[]
  saveCurrentSession() → localStorage "sessions"

切换会话:
  1. saveCurrentSession() 保存当前会话到 localStorage
  2. 加载目标会话的 messages → 重新渲染聊天区
  3. 切换 session_id, 更新侧边栏高亮

会话存储格式:
  { id: uuid, name: "自定义名称", timestamp: ISO, firstMessage: "首条内容", messages: [...] }

命名:
  双击侧边栏名称 → contentEditable → blur/Enter 保存 → localStorage 持久化

限制:
  最多保留 20 个会话，超出后移除最早会话 (FIFO)
```

## 6. 错误处理

| 场景 | 前端行为 |
|------|---------|
| 网络错误 (fetch 失败) | 显示 "连接失败，请检查后端服务" 错误提示 |
| HTTP 4xx/5xx | 解析错误 body，显示具体错误信息 |
| 空响应 | 显示 "未收到有效回复" |
| 文件上传过大 | 浏览器原生限制/提示 |
| 无效 session_id | 后端自动创建新会话（已有逻辑） |

## 7. Git 提交计划

```
feat/web-ui (from master)
  ├── R0  docs: add web-ui design document
  ├── R1  feat: add static/ directory and FastAPI static file serving
  ├── R2  feat: implement chat UI - HTML page skeleton
  ├── R3  feat: implement chat UI - CSS theming and dark mode
  └── R4  feat: implement chat UI - JavaScript interaction logic
```

每次提交都是可工作的状态：
- R1: 后端 serve 静态文件，浏览器可访问，显示空白页
- R2: 空白页 → 有完整 HTML 骨架
- R3: 骨架 → 带样式的布局（含暗色模式）
- R4: 样式布局 → 完整交互功能

## 8. 文件下载原理（远程部署说明）

### 8.1 完整下载链路

```
沙箱容器                    宿主机                         浏览器
┌────────────┐    ┌─────────────────────┐    ┌──────────────────────────┐
│ /workspace │    │ src/agent/nodes.py  │    │     static/              │
│ /output/   │    │                     │    │     app.js               │
│   foo.py   │───→│ download_files()    │───→│ /sessions/{sid}/downloads│
│   report   │    │ ↓ session_id 隔离    │    │   /foo.py                │
│   .csv     │    │ downloads/{sid}/    │    │ ↓                        │
│   chart    │    │   foo.py            │    │ <a class="file-chip">    │
│   .png     │    │   report.csv        │    │ 🖼️ foo.py  1.2KB ⬇      │
└────────────┘    │   chart.png         │    └──────┬───────────────────┘
                  └─────────────────────┘           │
                                                     │ GET /sessions/{sid}/
                                                     │   downloads/foo.py
                                                     ▼
                                            ┌────────────────────────┐
                                            │    FastAPI              │
                                            │  @app.get("/sessions/   │
                                            │   {sid}/downloads/     │
                                            │   {filename}")         │
                                            │  → FileResponse         │
                                            └────────────────────────┘
```

### 8.2 为什么远程也能下载

文件下载**不依赖文件在用户电脑上**，而是通过 HTTP 从服务器传输：

- **服务器端**：`downloads/{session_id}/` 目录位于服务器磁盘，动态路由端点读取并返回文件
- **浏览器点击链接** → HTTP GET 请求服务器 → 服务器读自己磁盘 → 通过 HTTP 响应把文件流发给浏览器
- **两种场景的下载行为完全一致**，只是 URL 中的主机名不同

| 部署方式 | URL 示例 |
|---------|----------|
| 本地部署 | `http://localhost:8000/sessions/a1b2/downloads/report.csv` |
| 远程部署 | `http://server-ip:8000/sessions/a1b2/downloads/report.csv` |

### 8.3 当前实现的关键路径（代码溯源）

| 环节 | 位置 | 行为 |
|------|------|------|
| 沙箱产出文件 | Agent 写入 `/workspace/output/` | — |
| 扫描发现 | `nodes.py:detect_output_files()` | `find /workspace/output -type f` |
| 价值判断 | `nodes.py:analyze_output_files()` | LLM 判断 high/low + 中文摘要 |
| 下载到本地 | `nodes.py:download_files()` | 高价值文件 → `downloads/{session_id}/{filename}`, 返回 `{sandbox, local, size, mime_type, summary}` |
| 动态端点 | `api.py:download_session_file()` | `GET /sessions/{session_id}/downloads/{filename}` → `FileResponse` |
| ZIP 打包 | `api.py:download_session_zip()` | `GET /sessions/{session_id}/downloads/zip?files=a&files=b` → `StreamingResponse(zip)`，支持 `?files=` 参数精确指定文件 |
| 前端渲染 | `app.js:renderMessage()` | `f.size` → `formatFileSize()` ▶ 显示 "1.2 KB"; `f.local` → 构造 `/sessions/{sid}/downloads/{file}` URL |
| 文件清理 | `api.py:_cleanup_expired_files()` | 启动时清理 `downloads/` 下超过 24h 的文件 |

### 8.4 注意事项

- ~~`/downloads` 路径**没有 session 隔离** → 不同会话的同名文件通过 `_1`, `_2` 后缀去重，但没有 session 前缀~~ ✅ **已修复**：文件按 `downloads/{session_id}/{filename}` 存储，不同会话文件完全隔离
- ~~不设文件过期清理 → 文件永久保留在服务器磁盘（依赖手动清理）~~ ✅ **已修复**：服务启动时自动扫描并删除超过 24 小时的文件
- ~~无访问控制 → 知道 URL 即可下载（单机工具场景可接受）~~ 单机工具场景不变

## 9. 不做的（明确排除）

- 工作流可视化（LangGraph 管线图）— 后续方向
- 实时日志流（SSE/WebSocket）— 后续升级
- 用户认证/登录 — 单机工具不需要
- 移动端 App — 仅 Web 响应式
- 单元测试（前端）— MVP 阶段，手动验证
