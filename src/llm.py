"""
LLM 兼容层 — 处理各厂商模型在 OpenAI 协议下的差异。

核心问题：
某些厂商（DeepSeek、OpenRouter 等）在 OpenAI 兼容接口中返回了专有字段
（如 ``reasoning_content``、``reasoning``），而 LangChain 的 ``ChatOpenAI``
在解析响应时丢弃了这些字段，但下次请求又需要原样传回，导致 400 错误。

解决方式：
在 ``ChatOpenAI`` 子类中劫持响应的解析流程，从原始 HTTP 响应 JSON 中提取
专有字段，注入到 ``AIMessage.additional_kwargs`` 中，使其在后续请求中
被 LangChain 正确序列化回 API。
"""

from __future__ import annotations

import json
from typing import Any

import openai
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGeneration, ChatResult

# 已知的模型思考/推理字段（各厂商命名不同）
_REASONING_FIELDS = frozenset({"reasoning_content", "reasoning"})


class ChatOpenAIWithReasoning(ChatOpenAI):
    """Support thinking/reasoning fields from non-OpenAI providers.

    Preserves provider-specific fields (e.g. DeepSeek's ``reasoning_content``,
    ``reasoning``) that the standard ``ChatOpenAI`` drops. These fields are
    stored in ``AIMessage.additional_kwargs`` so they are sent back to the
    API on subsequent requests (required by some providers).
    """

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Override to capture reasoning fields from raw API response."""
        self._ensure_sync_client_available()
        payload = self._get_request_payload(messages, stop=stop, **kwargs)

        # 发起请求，捕获原始 HTTP 响应
        try:
            raw_response = self.client.with_raw_response.create(**payload)
        except openai.BadRequestError as e:
            from langchain_openai.chat_models.base import _handle_openai_bad_request
            _handle_openai_bad_request(e)
            raise  # unreachable, pyright hint
        except openai.APIError as e:
            from langchain_openai.chat_models.base import _handle_openai_api_error
            _handle_openai_api_error(e)
            raise  # unreachable, pyright hint

        response = raw_response.parse()  # type: ignore[possibly-unbound]  # 异常处理器全部 raise，不会走到这里

        result = self._create_chat_result(response, generation_info=None)

        # ── 从原始 JSON 中提取 reasoning 字段，注入到 AIMessage ──
        try:
            raw_json = json.loads(raw_response.http_response.text)
        except (json.JSONDecodeError, AttributeError):
            return result

        for i, choice in enumerate(raw_json.get("choices", [])):
            msg_dict = choice.get("message", {})
            if i >= len(result.generations):
                break
            for gen in result.generations[i]:
                if isinstance(gen, ChatGeneration) and gen.message:
                    for field in _REASONING_FIELDS:
                        if field in msg_dict:
                            gen.message.additional_kwargs[field] = msg_dict[field]

        return result
