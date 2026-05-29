"""
集中配置模块 — 项目全局配置的单一事实来源。

所有环境变量在此处统一读取、校验、提供默认值。
其他地方需要配置时，应当 ``from src.config import settings`` 而不是直接调用 ``os.getenv()``。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# ── 加载 .env ────────────────────────────────────────────────────────
# 确保在任何业务代码 import 之前将 config.env 读入 os.environ。
# 本模块被 import 时自动执行，幂等。
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.env")
load_dotenv(dotenv_path=_env_path)


@dataclass(frozen=True)
class Settings:
    """应用配置，import 时加载一次，全局不可变。"""

    # ── LLM ──────────────────────────────────────────────────────────
    openai_api_base: str = "http://127.0.0.1:11434/v1"
    openai_api_key: str = "ollama"
    model_name: str = "qwen3.5:0.8b"

    # ── Sandbox ──────────────────────────────────────────────────────
    sandbox_url: str = "http://127.0.0.1:8080"
    sandbox_api_key: str = "my-secret-api-key-007"
    sandbox_use_server_proxy: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        """从环境变量构建配置，缺失时回退到字段默认值。"""
        return cls(
            openai_api_base=os.getenv("OPENAI_API_BASE", cls.openai_api_base),
            openai_api_key=os.getenv("OPENAI_API_KEY", cls.openai_api_key),
            model_name=os.getenv("MODEL_NAME", cls.model_name),
            sandbox_url=os.getenv("SANDBOX_API_URL", cls.sandbox_url),
            sandbox_api_key=os.getenv("SANDBOX_API_KEY", cls.sandbox_api_key),
            sandbox_use_server_proxy=(
                    os.getenv("SANDBOX_USE_SERVER_PROXY", str(cls.sandbox_use_server_proxy)).lower()
                    in ("true", "1", "yes")
            ),
        )


# 全局单例 — 其他模块 ``from src.config import settings`` 即可使用
settings = Settings.from_env()
