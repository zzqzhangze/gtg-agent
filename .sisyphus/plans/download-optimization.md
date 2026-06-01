# 文件下载优化 Implementation Plan

> status: completed (v1 — merged to master)
> branch: feat/download-optimization
> created: 2026-06-01
> updated: 2026-06-01

**Goal:** 解决文件下载的 session 隔离、元信息展示、过期清理和批量下载问题

**Architecture:** 将文件存储从 `downloads/{filename}` 改为 `downloads/{session_id}/{filename}`，替换 FastAPI StaticFiles 为动态路由端点，在前端芯片中显示文件大小/类型/摘要，添加服务器端过期清理和 zip 打包功能。

**Tech Stack:** Python/FastAPI, vanilla JS (前端), shutil/zipfile (后端打包), os (文件清理)

**前置阅读：**
- 文件下载原理见 `/downloads` → `StaticFiles`（将替换为动态端点）
- 前端文件芯片渲染见 `static/app.js:439-453`
- 后端下载逻辑见 `src/agent/nodes.py:645-710`
- API 下载路由见 `api.py:41-43`（StaticFiles）和 `api.py:111-125`（现有 FileResponse）

---

## Chunk 1: 后端存储路径改造 + 动态下载端点

### Task 1: 修改 download_files 节点，存入 session 子目录

**Files:**
- Modify: `src/agent/nodes.py:645-710` (`download_files` 函数)

- [ ] **Step 1: 修改 download_files() 接收 session_id 参数**

需要让 `download_files` 节点能拿到 `session_id`。目前 `SandboxAgentState` 没有 `session_id` 字段，但 LangGraph 的 `config` 中有 `thread_id`（在 api.py 中传入）。

方案：在 `SandboxAgentState` 中加 `session_id` 字段，`api.py` 调用 graph.stream 时传入。

修改 `src/agent/state.py`，在 `SandboxAgentState` 末尾添加：

```python
# download_files 的输出路径中用 session_id 隔离
session_id: str | None = None
```

修改 `api.py:89`，在 `config` 中额外传入 session_id：

```python
# 当前:
config = {"configurable": {"thread_id": session_id}}

# 改为:
config = {
    "configurable": {"thread_id": session_id},
    "metadata": {"session_id": session_id},
}
```

然后在 `download_files` 节点中读取。但 LangGraph 节点无法直接读取 config。更好的办法是在 state 中设置 session_id。

或者更简单：在 api.py 的 graph.stream 调用之前，在 `input_data` 中预置 `session_id`。

修改 `api.py:84-88`：

```python
input_data = {
    "messages": [{"role": "user", "content": message}],
    "input_files": local_files,
    "output_files": [],
    "session_id": session_id,  # 新增
}
```

这样 `download_files` 就可以通过 `state.get("session_id")` 拿到 session_id。

- [ ] **Step 2: 修改 download_files 中的文件存储路径**

修改 `nodes.py:663-694`，将文件存入 `downloads/{session_id}/` 子目录：

```python
def download_files(state: SandboxAgentState) -> dict[str, Any]:
    output_files: list[dict[str, Any]] = state.get("output_files", [])
    if not output_files:
        print("[文件下载] 没有需要下载的文件，跳过。")
        return {"downloaded_paths": []}

    if not state.get("sandbox_id"):
        print("[文件下载] 错误：没有可用的沙箱。")
        return {"downloaded_paths": []}

    client = SandboxClient()
    sb = client.get_sandbox(name=state["sandbox_id"])

    # 使用 session_id 隔离，回退到 "default"
    session_id = state.get("session_id", "default")
    download_dir = os.path.join(os.getcwd(), "downloads", session_id)
    os.makedirs(download_dir, exist_ok=True)

    high_value = [f for f in output_files if f.get("value") == "high"]
    low_value = [f for f in output_files if f.get("value") != "high"]

    downloaded = []
    for f in high_value:
        sandbox_path = f["path"]
        basename = os.path.basename(sandbox_path)
        local_path = os.path.join(download_dir, basename)

        print(f"[文件下载] 📦 {basename} → {local_path}")
        content = sb.read(sandbox_path)

        # 文件名去重
        counter = 1
        orig = local_path
        while os.path.exists(local_path):
            name, ext = os.path.splitext(orig)
            local_path = f"{name}_{counter}{ext}"
            counter += 1

        with open(local_path, "wb") as f_out:
            f_out.write(content)

        # 获取文件大小
        file_size = os.path.getsize(local_path)

        downloaded.append({
            "sandbox": sandbox_path,
            "local": local_path,
            "size": file_size,
            "mime_type": f.get("mime_type", "unknown"),
            "summary": f.get("summary", ""),
        })

    # ... 打印结果摘要（同现有逻辑）
    print(f"\n{'=' * 48}")
    if downloaded:
        print(f"  ✅ 已下载 {len(downloaded)} 个文件：")
        for d in downloaded:
            print(f"     📄 {os.path.basename(d['sandbox'])} → {d['local']} ({d['size']} bytes)")
            if d["summary"]:
                print(f"        {d['summary']}")
    if low_value:
        print(f"  🗑️ 跳过 {len(low_value)} 个低价值文件：")
        for f in low_value:
            print(f"     - {os.path.basename(f['path'])} ({f.get('summary', '中间文件，无需下载')})")
    print(f"{'=' * 48}\n")

    return {"downloaded_paths": downloaded}
```

核心变更：
1. `download_dir = os.path.join(os.getcwd(), "downloads", session_id)` — 按 session 隔离
2. 返回值新增 `size` 和 `mime_type` 字段

- [ ] **Step 3: 验证改动不破坏现有逻辑**

```bash
uv run python -c "from src.agent.graph import build_graph; g = build_graph(); print('Graph built OK')"
```

Expected: `Graph built OK`

- [ ] **Step 4: Commit**

```bash
git add src/agent/state.py src/agent/nodes.py api.py
git commit -m "feat: store downloaded files in session-isolated directories"
```

---

### Task 2: 替换 StaticFiles 为动态下载端点

**Files:**
- Modify: `api.py` (删除 line 43 的 StaticFiles 挂载，新增下载端点)

- [ ] **Step 1: 删除 /downloads StaticFiles 挂载，新增动态端点**

删除 `api.py:41-43`：

```python
# 删除这 3 行:
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")
```

新增端点：

```python
from fastapi.responses import FileResponse, StreamingResponse
import zipfile
import io


@app.get("/sessions/{session_id}/downloads/{filename}")
async def download_session_file(session_id: str, filename: str):
    """
    下载指定会话的输出文件。
    文件路径: downloads/{session_id}/{filename}
    """
    # 防止路径穿越
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    file_path = Path("downloads") / session_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


@app.get("/sessions/{session_id}/downloads/zip")
async def download_session_zip(session_id: str):
    """
    将指定会话的所有文件打包为 zip 下载。
    """
    session_dir = Path("downloads") / session_id
    if not session_dir.exists() or not any(session_dir.iterdir()):
        raise HTTPException(status_code=404, detail="该会话没有可下载的文件")

    # 内存中打包
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(session_dir.iterdir()):
            if f.is_file():
                zf.write(str(f), arcname=f.name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={session_id}.zip"},
    )
```

- [ ] **Step 2: 验证启动**

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000
# 访问 http://localhost:8000/docs 确认 Swagger 中看到新端点
```

按 Ctrl+C 停止。

- [ ] **Step 3: Commit**

```bash
git add api.py
git commit -m "feat: add dynamic download endpoint with session isolation and zip batch"
```

---

## Chunk 2: 前端元信息展示 + 新 URL

### Task 3: 更新前端文件芯片，显示大小/类型/摘要，使用新 URL

**Files:**
- Modify: `static/app.js:439-453` (渲染下载芯片部分)
- Modify: `static/style.css:335-380` (文件芯片样式)

- [ ] **Step 1: 更新 app.js 中的芯片渲染逻辑**

修改 `app.js` 中 `renderMessage` 函数的下载链接部分：

```javascript
// 下载链接作为文件芯片
if (files && files.length > 0) {
  const dlDiv = document.createElement("div");
  dlDiv.className = "download-links";
  files.forEach(f => {
    const fileName = f.local.split(/[\\/]/).pop();
    const fileSize = f.size || 0;
    const mimeType = f.mime_type || "unknown";
    const summary = f.summary || "";
    const sessionId = STATE.currentSessionId;
    
    const chip = document.createElement("a");
    chip.className = "file-chip";
    chip.href = `/sessions/${encodeURIComponent(sessionId)}/downloads/${encodeURIComponent(fileName)}`;
    chip.download = fileName;
    chip.title = summary || fileName;
    
    // 文件类型图标
    const icon = getFileIcon(mimeType, fileName);
    
    // 格式化文件大小
    const sizeText = fileSize > 0 ? formatFileSize(fileSize) : "";
    
    chip.innerHTML = `<span class="chip-icon">${icon}</span>`
      + `<span class="chip-name">${escapeHtml(fileName)}</span>`
      + (sizeText ? `<span class="chip-size">${sizeText}</span>` : "")
      + `<span class="chip-arrow">⬇</span>`;
    
    dlDiv.appendChild(chip);
  });
  bubble.appendChild(dlDiv);
}
```

新增辅助函数：

```javascript
function getFileIcon(mimeType, fileName) {
  const ext = fileName.split('.').pop().toLowerCase();
  const imgExts = ['png','jpg','jpeg','gif','svg','webp','bmp','ico'];
  const codeExts = ['py','js','ts','jsx','tsx','java','go','rs','c','cpp','h','css','html','sh','yaml','json','xml'];
  const dataExts = ['csv','xlsx','xls','json'];
  const docExts = ['pdf','md','txt','doc','docx'];
  const archiveExts = ['zip','tar','gz','rar','7z'];
  
  if (imgExts.includes(ext)) return '🖼️';
  if (codeExts.includes(ext)) return '📄';
  if (dataExts.includes(ext)) return '📊';
  if (docExts.includes(ext)) return '📝';
  if (archiveExts.includes(ext)) return '📦';
  return '📎';
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}
```

- [ ] **Step 2: 更新 CSS 适配新的芯片结构**

在 `static/style.css` 的文件芯片部分，增加 `.chip-icon` 和 `.chip-size` 样式：

```css
.file-chip .chip-icon {
  font-size: 14px;
  line-height: 1;
}

.file-chip .chip-size {
  font-size: 11px;
  opacity: 0.5;
  margin-left: auto;
}
```

- [ ] **Step 3: 验证**

```bash
# 启动服务
uv run uvicorn api:app --host 0.0.0.0 --port 8000
```

打开浏览器，发送一个需要生成文件的消息，确认：
1. 下载链接 URL 为 `/sessions/{id}/downloads/{file}`
2. 芯片上显示类型图标和文件大小
3. 鼠标悬停显示摘要（title）

- [ ] **Step 4: Commit**

```bash
git add static/app.js static/style.css
git commit -m "feat: show file metadata in download chips and use session-scoped URLs"
```

---

## Chunk 3: 文件过期清理

### Task 4: 添加自动清理机制

**Files:**
- Modify: `api.py` (新增 `_cleanup_expired_files` 函数 + startup 事件)

- [ ] **Step 1: 添加清理函数**

在 `api.py` 末尾添加：

```python
import time
import os


def _cleanup_expired_files(max_age_hours: int = 24):
    """
    清理 downloads/ 下超过 max_age_hours 的文件。
    在 FastAPI startup 事件中调用。
    """
    downloads_root = Path("downloads")
    if not downloads_root.exists():
        return

    now = time.time()
    max_age_seconds = max_age_hours * 3600
    removed_count = 0
    removed_size = 0

    for session_dir in downloads_root.iterdir():
        if not session_dir.is_dir():
            continue
        for f in session_dir.iterdir():
            if f.is_file():
                age = now - f.stat().st_mtime
                if age > max_age_seconds:
                    removed_size += f.stat().st_size
                    f.unlink()
                    removed_count += 1
        # 如果 session 目录空了，删除目录
        if not any(session_dir.iterdir()):
            session_dir.rmdir()

    if removed_count > 0:
        print(f"[清理] 已删除 {removed_count} 个过期文件 ({removed_size / 1024:.1f} KB)")
```

在 FastAPI app 创建后注册 startup 事件：

```python
@app.on_event("startup")
async def startup_cleanup():
    _cleanup_expired_files(max_age_hours=24)
```

- [ ] **Step 2: 验证**

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000
```

观察控制台输出是否显示清理日志（首次运行可能没有过期文件）。

- [ ] **Step 3: Commit**

```bash
git add api.py
git commit -m "feat: add TTL-based file cleanup for downloads directory"
```

---

## Chunk 4: 文档更新

### Task 5: 更新设计文档

**Files:**
- Modify: `docs/agent-web-ui-design.md`
- Modify: `.sisyphus/plans/INDEX.md`

- [ ] **Step 1: 更新设计文档 §8 文件下载原理**

将 `docs/agent-web-ui-design.md` 的 §8.4 注意事项更新，反映新的 session 隔离方案：

- `/downloads` → `/sessions/{session_id}/downloads/{filename}`
- 新增 zip 批量下载端点说明
- 新增自动清理说明（24h TTL）
- 更新链路图

- [ ] **Step 2: 在 INDEX.md 中注册本计划**

```markdown
| [download-optimization.md](./download-optimization.md) | draft | P2 | feat/download-optimization | 2026-06-01 | 2026-06-01 |
```

- [ ] **Step 3: Commit**

```bash
git add docs/agent-web-ui-design.md .sisyphus/plans/INDEX.md .sisyphus/plans/download-optimization.md
git commit -m "docs: add download optimization plan and update design doc"
```

---

## 执行顺序

```
Chunk 1 (后端存储 + 动态端点 + zip)
  └─ Task 1: download_files session 隔离
  └─ Task 2: 动态端点 + zip
Chunk 2 (前端元信息 + 新 URL)
  └─ Task 3: 芯片渲染
Chunk 3 (清理)
  └─ Task 4: TTL 清理
Chunk 4 (文档)
  └─ Task 5: 文档更新
```

各 Task 之间无依赖，Task 1 和 Task 2 可以并行；Task 3 依赖 Task 2（前端 URL 要匹配后端端点）；Task 4 完全独立；Task 5 最后做。
