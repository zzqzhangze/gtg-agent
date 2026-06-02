# Docker 沙箱抽象层原理

> 本文档解释 Sandbox Client 如何解决"LangGraph 同步执行 vs Sandbox SDK 异步 API"
> 的核心矛盾，以及模板注册表的机制。
>
> **关键文件**: `src/sandbox/client.py`, `src/sandbox/backend.py`

---

## 1. 核心矛盾

```
LangGraph:           同步函数调用（__call__ → 节点依次执行）
Sandbox SDK:         异步协程（async/await）
                            ↓
                    需要桥接层：async → sync
```

解法：**后台常驻事件循环线程** + `asyncio.run_coroutine_threadsafe()`。

```
主线程（同步）                   后台线程（异步）
    │                               │
    ├── create_sandbox()             │
    │   └─ run_async_backend() ────→ │  await Sandbox.create()
    │   ←────── result ───────────── │
    │                               │
    ├── sb.run("python script.py")  │
    │   └─ run_async_backend() ────→ │  await sb.commands.run()
    │   ←────── result ───────────── │
```

## 2. 后台事件循环

```python
_BACKGROUND_LOOP = None      # 全局唯一事件循环
_LOOP_THREAD = None           # 后台守护线程

def get_background_loop():
    if _BACKGROUND_LOOP is None:
        _BACKGROUND_LOOP = asyncio.new_event_loop()
        _LOOP_THREAD = threading.Thread(
            target=_BACKGROUND_LOOP.run_forever,
            daemon=True,        # 主进程退出时自动销毁
        )
        _LOOP_THREAD.start()
    return _BACKGROUND_LOOP

def run_async_backend(coro, timeout=None):
    loop = get_background_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)
```

**设计要点**：
- 线程设为 `daemon=True`：主程序退出时不等待线程，防止进程卡死
- `future.result(timeout)` 让调用方可以设置超时，防止无限阻塞
- 事件循环只创建一次（模块级全局变量），重复利用

---

## 3. LocalSandbox — 异步替身模式

OpenSandbox SDK 的 `Sandbox` 实例是异步的（所有方法返回 coroutine），
但 DeepAgent 的 `BaseSandbox` 协议（`backend`）是同步的。

`LocalSandbox` 是一个**同步包装器**：

```
Sandbox (async)           LocalSandbox (sync)
  ├── files.read_bytes()  ──→  read()
  ├── files.write_file()  ──→  write()
  └── commands.run()      ──→  run()
```

每个方法内部用 `run_async_backend()` 将异步调用转为同步：

```python
def read(self, path: str) -> bytes:
    async def _read():
        return await self.sb.files.read_bytes(path)
    return run_async_backend(_read())

def run(self, cmd: str, timeout: int = 300):
    opts = RunCommandOpts(timeout=timedelta(seconds=timeout))
    async def _execute():
        return await self.sb.commands.run(cmd, opts=opts)
    # 客户端超时 = 服务端超时 + 5s 缓冲
    client_timeout = (timeout + 5) if timeout > 0 else None
    execution = run_async_backend(_execute(), timeout=client_timeout)
    return RunResult(stdout="...", stderr="...", exit_code=...)
```

### 异常处理策略

```python
# 防卡死：检测网络完全断开时抛异常，打断 agent 无限重试
if "All connection attempts failed" in error_msg or "ConnectError" in error_msg:
    raise RuntimeError("Sandbox connection completely lost.")
```

---

## 4. 模板注册表

模板注册表是一个简单的字典，`模板名 → 环境配置`：

```python
_TEMPLATE_REGISTRY = {
    "python-sandbox": {
        "image": "sandbox-registry/.../code-interpreter:v1.0.2",
        "entrypoint": ["/opt/opensandbox/code-interpreter.sh"],
        "env": {"PYTHON_VERSION": "3.11"},
    },
    "data-analysis": {},       # TODO: 替换为 pandas 预装镜像
    "node-sandbox": {},        # TODO: 替换为 node/npm 预装镜像
}
```

**新增模板只需加字典条目**，`create_sandbox()` 自动适配，无需修改逻辑。

`create_sandbox()` 创建流程：

```
create_sandbox(template_name)
  → 查 _TEMPLATE_REGISTRY[template_name]（未找到则回退 python-sandbox）
  → Sandbox.create(image, connection_config, entrypoint, env, timeout)
  → 全局暂存 sb_instance（_GLOBAL_SANDBOXES[sb_name]）
  → 返回 LocalSandbox(name=sb_name, sandbox_instance=sb_instance)
```

---

## 5. LangSmithBackend — BaseSandbox 协议实现

`LangSmithBackend` 是 DeepAgent 框架的 `BaseSandbox` 子类，
负责将 `LocalSandbox` 包装成 agent 可以用的后端：

```python
class LangSmithBackend(BaseSandbox):
    def execute(self, command: str) -> ExecuteResponse:
        result = self._sandbox.run(command, timeout=self._timeout)
        return ExecuteResponse(output=..., exit_code=..., ...)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=p, content=self._sandbox.read(p)) for p in paths]

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        for path, content in files:
            self._sandbox.write(path, content)
```

`upload_files()` 支持批量上传——Skills 系统的 `upload_skills_to_sandbox()` 依赖此方法。

---

## 6. 安全与生命周期

```
create_sandbox → [run_agent 使用沙箱] → cleanup_sandbox
      │                                      │
  创建容器 +                              kill 容器 +
  暂存实例                                删除全局引用
```

```python
_GLOBAL_SANDBOXES = {}    # 全局字典：name → Sandbox 实例

def create_sandbox(...):
    sb_instance = await Sandbox.create(...)
    _GLOBAL_SANDBOXES[sb_name] = sb_instance
    return LocalSandbox(name=sb_name, sandbox_instance=sb_instance)

def delete_sandbox(name):
    sb_instance = _GLOBAL_SANDBOXES.get(name)
    await sb_instance.kill()
    del _GLOBAL_SANDBOXES[name]
```

**安全要点**：
- `cleanup_sandbox` 是 LangGraph 图的终点节点，无论如何都会执行
- 即使 `run_agent` 抛出异常，图仍然会流到 `cleanup_sandbox`
- `_GLOBAL_SANDBOXES` 用字典管理，支持多沙箱并发

---

## 7. 完整数据流

```
用户上传文件                        沙箱输出文件
     │                                   │
     ▼                                   ▼
upload_files():                    detect_output_files():
  sb.write(path, content)            sb.run("find /workspace/output ...")
     │                                   │
     ▼                                   ▼
  /workspace/input/foo.csv          /workspace/output/result.csv
                                         │
                                         ▼
                                    download_files():
                                      sb.read(sandbox_path)
                                      → local_path
```
