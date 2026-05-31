# Agent Web 聊天界面 — 设计方案

> status: draft
> created: 2026-05-31
> branch: feat/web-ui
>
> 对应 plan: `.sisyphus/plans/agent-intelligence-upgrade.md` — 支线任务（前端可视化交互）

---

## 1. 目标

为 My Deep Agent 提供浏览器端可视化聊天界面，替代/补充现有 CLI REPL 模式，使非技术用户也能通过网页交互使用 Agent。

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
| 持久化 | localStorage | 会话 ID + 暗色偏好 |
| 消息格式 | Markdown 字符串 → 前端渲染 | 后端已返回纯文本 |

## 3. 文件结构

```
my_deep_agent/
├── static/                   ← 新增
│   ├── index.html            页面骨架
│   ├── style.css             全部样式 + 暗色模式变量
│   └── app.js                全部交互逻辑
├── api.py                    + 修改：挂载 StaticFiles + 根路由
```

不新增 `package.json`、`node_modules`、构建配置。所有前端代码是普通的静态文件。

## 4. UI 规范

### 4.1 布局

```
┌──────────────────────────────────────────────────────┐
│  Header                                          24px│
│  ┌────────────────────────────────────────────────┐  │
│  │  🤖 My Deep Agent           🌙  🆕            │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Chat Area (flex-grow, overflow-y: auto)              │
│  ┌────────────────────────────────────────────────┐  │
│  │                                                │  │
│  │  ┌──────────────────────────────┐              │  │
│  │  │  用户消息（右对齐，蓝色气泡）    │              │  │
│  │  └──────────────────────────────┘              │  │
│  │                                                │  │
│  │  ┌──────────────────────────────┐              │  │
│  │  │  AI 回复（左对齐，灰色气泡）   │              │  │
│  │  │  Markdown 渲染内容            │              │  │
│  │  │  📦 bubble_sort.py [下载]     │              │  │
│  │  └──────────────────────────────┘              │  │
│  │                                                │  │
│  │              🤔 思考中...                      │  │
│  │                                                │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  File Preview Bar (可选)                              │
│  ┌────────────────────────────────────────────────┐  │
│  │  📎 data.csv  ✕  │  📎 script.py  ✕          │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Input Area (sticky bottom)                          │
│  ┌────────────────────────────────────────────────┐  │
│  │  [📎]  [输入消息...                  ]  [➤ 发送] │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
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
  GET /files/{session_id}/{filename}
渲染为 <a href="...">📦 bubble_sort.py</a>
```

### 5.3 会话管理

```
页面加载:
  if (!localStorage.getItem("session_id"))
    session_id = crypto.randomUUID()
    localStorage.setItem("session_id", session_id)

新会话按钮:
  生成新 UUID → 存 localStorage → 清空聊天区域
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

## 8. 不做的（明确排除）

- 工作流可视化（LangGraph 管线图）— 后续方向
- 实时日志流（SSE/WebSocket）— 后续升级
- 用户认证/登录 — 单机工具不需要
- 移动端 App — 仅 Web 响应式
- 单元测试（前端）— MVP 阶段，手动验证
