# 部署指南

## 前提条件

- Python >= 3.13
- [Docker Engine](https://docs.docker.com/engine/install/) 20.10+（沙箱运行环境）
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）
- 任意兼容 OpenAI 协议的 LLM 服务（Ollama / OpenAI / DeepSeek / vLLM 等）

> Windows 用户需先安装 [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) 并启用 WSL2 后端。

---

## 1. 安装依赖

```bash
# 创建 .venv 并安装所有依赖
uv sync
```

---

## 2. 配置

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

## 3. 启动沙箱服务

项目使用 [OpenSandbox](https://open-sandbox.ai) 管理沙箱容器的生命周期。

```bash
# 生成配置文件（首次运行）
uvx opensandbox-server init-config ~/.sandbox.toml --example docker

# 启动服务（后台运行）
uvx opensandbox-server &
```

> 首次启动会自动拉取沙箱执行镜像（约 2-3 分钟，取决于网络）。

验证服务就绪：

```bash
curl http://127.0.0.1:8080/v1/health
```

OpenSandbox 配置位于 `~/.sandbox.toml`，如需修改（例如 Docker 网络模式、execd 镜像版本、API 密钥等），直接编辑该文件后重启服务即可。详细配置参考[官方文档](https://open-sandbox.ai/getting-started/configuration)。

---

## 4. 启动 GTG Agent

### 命令行模式（REPL）

```bash
python main.py
```

支持的命令见 README 或运行 `/help`。

### API 服务模式

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 `http://localhost:8000` 即可使用 Web UI。

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
