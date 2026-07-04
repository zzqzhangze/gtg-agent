# 部署指南

## 前提条件

- [uv](https://docs.astral.sh/uv/)（安装时自动管理 Python 版本）
- [Docker Engine](https://docs.docker.com/engine/install/) 20.10+（沙箱运行环境）
- 任意兼容 OpenAI 协议的 LLM 服务（Ollama / OpenAI / DeepSeek / vLLM 等）

> - **Windows**：安装 [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) 并启用 WSL2 后端
> - **macOS**：安装 [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
> - **Linux (Ubuntu/Debian)**：`sudo apt install docker.io`，或参考[官方文档](https://docs.docker.com/engine/install/ubuntu/)
> - **Linux (CentOS/RHEL/Fedora)**：参考[官方文档](https://docs.docker.com/engine/install/)

---

## 1. 安装依赖

```bash
# 安装 uv（如已安装可跳过）
# Windows（PowerShell）:
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux:
# curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建 .venv 并安装所有依赖
uv sync
```

---

## 2. 启动沙箱服务

项目使用 [OpenSandbox](https://open-sandbox.ai) 管理沙箱容器的生命周期。

```bash
# 生成配置文件（首次运行）
uvx opensandbox-server init-config ~/.sandbox.toml --example docker

# 启动服务（后台运行）
uvx opensandbox-server &
```

> 首次启动会自动拉取沙箱执行镜像（约 2-3 min，取决于网络）。如果自动拉取失败，见常见问题手动拉取。

验证服务就绪：

```bash
curl http://127.0.0.1:8080/v1/health
```

OpenSandbox 配置位于 `~/.sandbox.toml`，如需修改（例如 Docker 网络模式、execd 镜像版本、API 密钥等），直接编辑该文件后重启服务即可。详细配置参考[官方文档](https://open-sandbox.ai/getting-started/configuration)。

---

## 3. 配置 GTG Agent

创建 `config.env` 文件（可参考根目录下的 `config.env` 模板），按需填写：

```env
# ── LLM ──────────────────────────────────────────────────────────────
# 兼容任何 OpenAI API 格式的服务
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxxxx
MODEL_NAME=gpt-4o

# ── Sandbox ──────────────────────────────────────────────────────────
SANDBOX_API_URL=http://127.0.0.1:8080
# SANDBOX_API_KEY=my-secret-api-key-007
# SANDBOX_USE_SERVER_PROXY=false   # 是否通过代理连接沙箱
```

### 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_BASE` | `http://127.0.0.1:11434/v1` | LLM API 地址 |
| `OPENAI_API_KEY` | `ollama` | API 密钥 |
| `MODEL_NAME` | `qwen3.5:0.8b` | 模型名 |
| `SANDBOX_API_URL` | `http://127.0.0.1:8080` | OpenSandbox 服务地址 |
| `SANDBOX_API_KEY` | `my-secret-api-key-007` | 沙箱 API 密钥 |
| `SANDBOX_IMAGE` | `sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2` | 沙箱执行镜像（可改为 Docker Hub 官方镜像） |
| `SANDBOX_LIFETIME_TIMEOUT` | `1800` | 沙箱容器 TTL（秒） |
| `SANDBOX_COMMAND_TIMEOUT` | `60` | 沙箱内单条命令超时（秒） |
| `SANDBOX_REQUEST_TIMEOUT` | `30` | HTTP 请求超时（秒） |

完整的配置项见 [`src/config.py`](../src/config.py#L21-L90)。

---

## 4. 启动 GTG Agent

### 命令行模式

```bash
# 交互式对话（REPL）
python main.py

# 单次执行（带消息和文件）
python main.py "帮我总结这个文件" report.txt data.csv
```

REPL 模式下支持以下命令：

| 命令 | 说明 |
|------|------|
| `/file <路径>` | 添加文件到本轮对话 |
| `/files` | 查看已添加的文件列表 |
| `/clear` | 清空文件列表 |
| `/history` | 显示本轮对话历史 |
| `/history all` | 显示所有历史会话 |
| `/history clear` | 清除本轮对话历史 |
| `/history clear --all` | 清除所有历史会话 |
| `/help` | 显示此帮助 |
| `/exit` | 退出（也可按 Ctrl+C） |

示例：输入 `/file data.csv` 然后发送 `读取这个 CSV，统计每列的空值数量`。

### API 服务模式

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 `http://localhost:8000` 即可使用 Web UI。

#### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 发送对话消息（multipart/form-data，字段 `message`） |
| `/health` | GET | 健康检查 |
| `/api-info` | GET | API 信息 |
| `/files/{session_id}/{filename}` | GET | 下载已上传的文件 |
| `/sessions/{session_id}/downloads/{filename}` | GET | 下载沙箱产出文件 |
| `/sessions/{session_id}/downloads/zip` | GET | 批量打包下载沙箱产出 |
| `/sessions/{session_id}/history` | DELETE | 清除对话历史 |
| `/mcp/` | GET | MCP 工具管理界面 |
| `/mcp/servers` | GET | 列出已注册的 MCP server |
| `/mcp/servers` | POST | 添加 MCP server |
| `/mcp/servers/{id}` | PUT | 更新 MCP server 配置 |
| `/mcp/servers/{id}` | DELETE | 删除 MCP server |
| `/mcp/servers/{id}/test` | POST | 测试 MCP 连接 |
| `/mcp/servers/{id}/sync` | POST | 同步 MCP 工具列表 |
| `/mcp/tools` | GET | 列出 MCP 工具 |
| `/mcp/tools/{id}` | PUT | 启用/禁用 MCP 工具 |

---

## 5. 验证部署

```bash
# 健康检查
curl http://localhost:8000/health

# 发送测试消息
curl -X POST http://localhost:8000/chat \
  -F "message=你好"
```

---

## 常见问题

**Q：沙箱服务启动失败，提示 Docker 连接不上？**  
检查 Docker Desktop 是否运行。Windows 用户需确保 WSL2 集成已启用。

**Q：`uvx opensandbox-server` 找不到命令？**  
确保已安装 `uv` 且版本足够新：`uv --version`。也可改用 `pip install opensandbox-server && opensandbox-server`。

**Q：沙箱创建超时？**  
可能是首次启动需要拉取镜像。检查网络，或调整 `~/.sandbox.toml` 中的超时设置。

**Q：沙箱镜像没有自动拉取 / 拉取失败，怎么手动拉？**  
用 `docker pull` 手动拉取镜像，镜像名即 `config.env` 中 `SANDBOX_IMAGE` 的值：

```bash
docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2
```

如果使用 Docker Hub 官方镜像，改为：

```bash
docker pull opensandbox/code-interpreter:latest
```

拉取成功后重启 OpenSandbox 服务即可。

**Q：`uv sync` 下载依赖太慢，怎么加速？**  
配置国内 PyPI 镜像源，创建或编辑 `~/.config/uv/uv.toml`（Linux/macOS）或 `%APPDATA%\uv\uv.toml`（Windows）：

```toml
[[index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

或在运行命令时临时指定：

```bash
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```
