# 部署方案备选文档

> 本文档记录除 FastAPI 自建方案之外的其他部署方案，供后续优化升级时参考。
>
> 当前使用方案见 `api.py`（FastAPI 直接包装 LangGraph）。

---

## 方案对比一览

| 方案 | 复杂度 | 吞吐 | 生态集成 | 推荐场景 |
|------|--------|------|----------|----------|
| **FastAPI 自建** ✅ 当前 | ⭐ | 中 | 通用 HTTP | 原型验证、内部工具、初期产品 |
| **LangServe** | ⭐⭐ | 中 | ⭐⭐⭐ LangChain 原生 | 深度 LangChain 生态、Playground |
| **gRPC + 异步 Worker** | ⭐⭐⭐⭐ | ⭐⭐⭐ 高 | 语言无关 | 高并发生产、多语言客户端 |
| **WebSocket Streaming** | ⭐⭐ | 中 | 实时流 | 需要流式输出、长连接场景 |
| **K8s Operator + 事件驱动** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ 极高 | 云原生 | 大规模 SaaS、多租户 |

---

## 方案二：LangServe

### 概述

LangServe 是 LangChain 官方提供的部署工具，一行代码即可将 LangGraph / LangChain Runnable 暴露为 REST API，自带 Playground UI 和 OpenAPI 文档。

### 核心代码

```python
# serve.py
from langserve import add_routes
from fastapi import FastAPI
from src.agent.graph import build_graph

app = FastAPI(title="GTG Agent - LangServe")

graph = build_graph()
add_routes(app, graph, path="/agent")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 优点

- **零胶水代码**：`add_routes` 自动生成 `/invoke`、`/stream`、`/batch` 等端点
- **内置 Playground**：浏览器可视化调试（`/agent/playground`）
- **OpenAPI 文档**：自动生成 Swagger UI
- **LangSmith 集成**：开箱即用的链路追踪

### 缺点

- **灵活性受限**：请求/响应格式被 LangServe 约束，自定义逻辑（如文件上传、多步骤确认）需要额外包装
- **版本锁定**：`langserve` 版本需与 `langchain` / `langgraph` 严格对齐
- **文件上传不原生**：LangServe 的输入是 JSON，大文件需额外用 `UploadFile` 端点

### 适用场景

- 项目已经深度使用 LangChain 生态
- 需要快速获得 API + UI + 文档
- 不需要复杂的自定义输入/输出格式

### 参考

- https://python.langchain.com/docs/langserve/
- https://github.com/langchain-ai/langserve

---

## 方案三：gRPC + 异步 Worker

### 概述

将 Agent 的每次调用包装成 gRPC 服务，使用 proto 定义严格的请求/响应契约。后端采用 Worker 池管理沙箱生命周期。

### 核心结构

```protobuf
// agent.proto
service AgentService {
    rpc Chat (ChatRequest) returns (ChatResponse);
    rpc ChatStream (ChatRequest) returns (stream ChatEvent);
    rpc UploadFile (stream FileChunk) returns (FileInfo);
    rpc DownloadFile (FileRequest) returns (stream FileChunk);
}

message ChatRequest {
    string session_id = 1;
    string message = 2;
    repeated string input_files = 3;
}
```

```python
# worker_pool.py — 沙箱连接池管理
class SandboxPool:
    """预创建一组沙箱，避免每次请求都等待 Docker 启动"""

    _pool: asyncio.Queue[Sandbox]
    _max_size: int
    _idle_timeout: timedelta

    async def acquire(self) -> Sandbox:
        """获取一个空闲沙箱（带超时）"""

    async def release(self, sb: Sandbox):
        """归还沙箱到池中，重置状态"""
```

### 优点

- **高性能**：gRPC 基于 HTTP/2，二进制编码，比 JSON 快 5-10 倍
- **强类型契约**：proto 文件即 API 文档，多语言代码生成
- **双向流**：天然支持文件流式上传/下载
- **Worker 池**：预创建沙箱，消除冷启动延迟

### 缺点

- **基础设施成本高**：需要 proto 编译、gRPC 网关、负载均衡
- **调试困难**：二进制协议，curl 无法直接调试
- **Python gRPC 生态**：asyncio 集成不如 FastAPI 成熟

### 适用场景

- 高并发生产环境（>1000 QPS）
- 多语言客户端（Go、Java、Rust 调用 Python Agent）
- 大文件持续处理（流式上传/下载）

### 参考

- https://grpc.io/docs/languages/python/
- https://github.com/grpc/grpc/tree/master/examples/python

---

## 方案四：WebSocket Streaming

### 概述

在 FastAPI 基础上，增加 WebSocket 端点，支持 Agent 执行过程的实时流式推送（LLM Token、沙箱执行日志、文件处理进度）。

### 核心代码

```python
# websocket_handler.py
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    while True:
        data = await websocket.receive_json()
        input_data = {
            "messages": [{"role": "user", "content": data["message"]}],
            "input_files": data.get("input_files", []),
        }

        async for event in graph.astream(input_data, config, stream_mode="values"):
            # 向客户端推送每个事件
            await websocket.send_json({
                "type": "event",
                "data": serialize_event(event),
            })

            # 检查客户端是否请求取消
            cancel = await websocket.receive_text()
            if cancel == "CANCEL":
                break
```

### 优点

- **实时可见**：用户可以看到 LLM 逐字输出 + 沙箱执行日志
- **可取消**：长任务支持中途取消
- **连接复用**：一个 WebSocket 用于多次对话

### 缺点

- **连接管理复杂**：断线重连、心跳保活
- **向后兼容**：仍需保留 REST 端点供非浏览器客户端使用
- **状态同步**：多设备同时连接同一会话需要额外的冲突处理

### 适用场景

- Web 前端交互式应用
- 需要展示执行过程（而非只展示结果）
- 支持用户中途干预（如取消长时间运行的任务）

---

## 方案五：K8s Operator + 事件驱动

### 概述

将每个 Agent 会话建模为 Kubernetes 自定义资源（CRD），利用 Operator 模式管理沙箱 Pod 的生命周期。消息队列（如 RabbitMQ / Redis Stream）解耦请求接收与处理。

### 架构

```
                     ┌──────────────┐
  HTTP Request ─────►│   Gateway    │
                     └──────┬───────┘
                            │ 消息
                            ▼
                     ┌──────────────┐
                     │   Message    │
                     │    Queue     │
                     └──────┬───────┘
                            │ 事件
                            ▼
  ┌─────────────────────────────────────────────┐
  │              K8s Operator                   │
  │                                             │
  │  1. Watch Queue → 新任务                     │
  │  2. Create SandboxPod (CR)                  │
  │  3. SandboxPod 内含 Agent + Sidecar         │
  │  4. Agent 执行完毕 → 结果写回 Queue / ObjectStore │
  │  5. Operator 清理 SandboxPod                │
  └─────────────────────────────────────────────┘
```

### 核心资源

```yaml
# crd/agentsession.yaml
apiVersion: agent.mydeep.io/v1
kind: AgentSession
spec:
  sessionId: "uuid-xxx"
  message: "总结这个文件"
  inputFiles:
    - name: report.docx
      source: "oss://bucket/report.docx"
  llmConfig:
    model: "qwen3.5:0.8b"
    baseUrl: "http://ollama:11434/v1"
  sandboxSpec:
    image: "sandbox-registry/code-interpreter:v1.0.2"
    timeout: 3600
    resources:
      cpu: "1"
      memory: "2Gi"
status:
  phase: Running | Succeeded | Failed
  outputMessage: "..."
  outputFiles:
    - name: summary.txt
      url: "oss://bucket/summary.txt"
```

### 优点

- **弹性伸缩**：K8s 原生 HPA，根据队列深度自动扩缩 Worker
- **故障隔离**：每个请求独立 Pod，crash 不影响其他请求
- **可观测性**：天然集成 Prometheus、Loki、Tempo
- **资源管理**：精准控制每个会话的 CPU/内存上限

### 缺点

- **运维极重**：需要 K8s 集群、Operator 开发、CRD 管理
- **冷启动延迟**：每个请求创建 Pod + 拉取镜像 + 启动沙箱
- **开发迭代慢**：修改代码 → 构建镜像 → 部署 Operator

### 适用场景

- 大规模 SaaS 服务（每日 10 万+ 请求）
- 已有 K8s 基础设施的团队
- 需要严格资源隔离的多租户场景

---

## 升级路径建议

```
FastAPI 自建                    LangServe                     gRPC + Worker
   (原型阶段)       ─────►    (LangChain 深度)    ─────►    (高并发生产)
       │                                                            │
       │                                                            │
       └──────────────────── WebSocket ──────────────────────────────┘
                                │
                                ▼
                      K8s Operator (大规模 SaaS)
```

### 各阶段触发条件

| 阶段 | 触发条件 |
|------|----------|
| FastAPI → LangServe | 需要 Playground UI / 深度 LangSmith 可观测性 / 自动 API 文档 |
| FastAPI → WebSocket | 用户需要看到 LLM 逐字输出、实时沙箱日志 |
| FastAPI/LangServe → gRPC | QPS > 500 / 多语言客户端接入 / 大文件流式传输 |
| gRPC → K8s Operator | 每日 10 万+ 请求 / 多租户 / 需要 SLA 保障 |

---

## 附录：各方案依赖清单

| 方案 | 新增依赖 | 额外基础设施 |
|------|----------|-------------|
| FastAPI 自建 | `fastapi`, `uvicorn`, `python-multipart` | 无（`uv add fastapi uvicorn python-multipart`） |
| LangServe | `langserve` | 无（可选 LangSmith） |
| gRPC + Worker | `grpcio`, `grpcio-tools` | 无（可选 etcd/Redis） |
| WebSocket | `websockets`（内置 FastAPI） | 无 |
| K8s Operator | `kopf` 或 `kube-operator` | K8s 集群、CRD、镜像仓库、对象存储 |
