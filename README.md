# My Deep Agent

本地化的 AI 代码执行 Agent，基于 LangGraph 编排，通过 OpenAI 兼容协议接入任意 LLM，Docker 沙箱安全隔离执行代码。

## 架构

```
用户输入 → analyze_intent（判断是否需要沙箱）
               │
          ┌─────┴─────┐
          │ 需要沙箱   │ 纯聊天
          ▼            ▼
   create_sandbox     run_agent（直接 LLM 回复）
          │
   upload_files（上传用户文件到沙箱）
          │
   run_agent（DeepAgent 在沙箱内写代码+执行）
          │
   download_files（从沙箱下载结果文件）
          │
   cleanup_sandbox（强制销毁容器）
```

## 快速开始

### 依赖

- Python >= 3.13
- 任意兼容 OpenAI 协议的 LLM 服务（如 Ollama、OpenAI API、vLLM、Azure OpenAI 等）
- [OpenSandbox](https://opensandbox.dev/) 沙箱服务

### 安装

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 配置

编辑 `config.env`，按需填写 LLM 地址和模型名（兼容任何 OpenAI API 格式的服务）：

```env
# 例如使用 Ollama 本地模型:
# OPENAI_API_BASE=http://127.0.0.1:11434/v1
# OPENAI_API_KEY=ollama
# MODEL_NAME=qwen3.5:0.8b

# 例如使用 OpenAI:
# OPENAI_API_BASE=https://api.openai.com/v1
# OPENAI_API_KEY=sk-xxxxx
# MODEL_NAME=gpt-4o

# 沙箱服务地址
OPENSANDBOX_API_URL=http://127.0.0.1:8080
```

### 运行

**命令行模式：**

```bash
# 纯聊天测试
python main.py

# 带文件和消息
python main.py "帮我总结这个文件" report.txt data.csv
```

**API 服务模式：**

```bash
# 安装额外依赖
pip install fastapi uvicorn python-multipart

# 启动服务
uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# 调用
curl -X POST http://localhost:8000/chat \
  -F "message=读取并分析这个 CSV" \
  -F "files@=data.csv"
```

API 端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 发送消息 + 上传文件（multipart/form-data） |
| GET | `/files/{session_id}/{filename}` | 下载处理后的文件 |
| GET | `/health` | 健康检查 |
| GET | `/` | API 信息 |

## 项目结构

```
my_deep_agent/
├── api.py              # FastAPI 服务入口（启动后调这个）
├── main.py             # 命令行入口（本地测试用）
├── config.env          # 环境变量配置（改模型、改端口在这里）
├── Agent.md            # 开发者文档：开发原则与规范
├── src/                # 核心代码
│   ├── sandbox/        # 沙箱接口层
│   └── agent/          # Agent 编排层
└── docs/               # 备选方案、设计文档存档
```

> 开发相关说明（核心概念、如何扩展）见 [Agent.md](Agent.md)。

## 许可

MIT
