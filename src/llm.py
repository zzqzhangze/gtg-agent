"""
LLM 兼容层 — 处理各厂商模型在 OpenAI 协议下的差异。

核心问题：
某些厂商（DeepSeek、OpenRouter 等）在 OpenAI 兼容接口中返回了专有字段
（如 ``reasoning_content``、``reasoning``），而 LangChain 的 ``ChatOpenAI``
两层丢失了这些字段：

1. 接收响应时：OpenAI Python 库解析时丢弃未知字段
2. 发送请求时：``_convert_message_to_dict`` 只提取 ``tool_calls``、
   ``function_call``、``audio`` 三个 ``additional_kwargs`` 键，无通用透传

解决方式：
在 ``ChatOpenAI`` 子类中同时拦截两端的处理：

- ``_generate``（接收）：从原始 HTTP 响应 JSON 中提取 reasoning 字段，
  注入到 ``AIMessage.additional_kwargs``
- ``_get_request_payload``（发送）：从 ``AIMessage.additional_kwargs`` 中读出
  reasoning 字段，回填到序列化后的消息 dict
"""

from __future__ import annotations

import json
import logging
from typing import Any

import openai
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGeneration, ChatResult

logger = logging.getLogger("llm")

# 已知的模型思考/推理字段（各厂商命名不同）
_REASONING_FIELDS = frozenset({"reasoning_content", "reasoning"})


class ChatOpenAIWithReasoning(ChatOpenAI):
    """Support thinking/reasoning fields from non-OpenAI providers.

    Preserves provider-specific fields (e.g. DeepSeek's ``reasoning_content``,
    ``reasoning``) that the standard ``ChatOpenAI`` drops. These fields are
    stored in ``AIMessage.additional_kwargs`` so they are sent back to the
    API on subsequent requests (required by some providers).
    """

    # ── 接收端：从响应中提取 reasoning 字段 ───────────────────────────

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Override to capture reasoning fields from raw API response."""
        self._ensure_sync_client_available()

        # DIAG: Show message types on entry
        logger.debug(
            "DIAG: _generate called with %d msgs. Types: %s, AIMsgs: %d",
            len(messages),
            [type(m).__name__ for m in messages],
            sum(1 for m in messages if isinstance(m, AIMessage)),
        )
        for i, m in enumerate(messages):
            if isinstance(m, AIMessage):
                logger.debug(
                    "DIAG:   msg[%d] AIMsg additional_kwargs keys: %s",
                    i, list(m.additional_kwargs.keys()),
                )

        payload = self._get_request_payload(messages, stop=stop, **kwargs)

        # DIAG: Show the ACTUAL payload being sent
        logger.debug(
            "DIAG: Payload has %d msgs. Roles: %s. Has msg with reasoning_content: %s",
            len(payload.get("messages", [])),
            [m.get("role") for m in payload.get("messages", [])],
            any("reasoning_content" in m for m in payload.get("messages", [])),
        )

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

        response = raw_response.parse()

        result = self._create_chat_result(response, generation_info=None)

        # 从原始 JSON 中提取 reasoning 字段，注入到 AIMessage
        try:
            raw_json = json.loads(raw_response.http_response.text)
        except (json.JSONDecodeError, AttributeError):
            logger.debug("DIAG: Could not parse raw response JSON")
            return result

        for i, choice in enumerate(raw_json.get("choices", [])):
            msg_dict = choice.get("message", {})
            if i >= len(result.generations):
                break
            gen = result.generations[i]
            if isinstance(gen, ChatGeneration) and gen.message:
                for field in _REASONING_FIELDS:
                    if field in msg_dict:
                        gen.message.additional_kwargs[field] = msg_dict[field]
                        logger.debug(
                            "DIAG: Extracted %s from response (len=%d)",
                            field, len(str(msg_dict[field])),
                        )

        return result

    # ── 发送端：将 reasoning 字段回填到请求消息中 ─────────────────────

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Override to inject reasoning fields back into serialized messages.

        Parent's ``_convert_message_to_dict`` drops arbitrary ``additional_kwargs``
        keys. This method re-injects ``reasoning_content`` / ``reasoning`` after
        the parent finishes serialization.
        """
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        messages = self._convert_input(input_).to_messages()
        msg_dicts = payload.get("messages", [])
        if not msg_dicts:
            return payload

        injected = False
        for i, m in enumerate(messages):
            if isinstance(m, AIMessage) and i < len(msg_dicts):
                for field in _REASONING_FIELDS:
                    if field in m.additional_kwargs:
                        msg_dicts[i][field] = m.additional_kwargs[field]
                        injected = True
                        logger.debug(
                            "DIAG: Injected %s=%s into msg[%d]",
                            field, repr(m.additional_kwargs[field])[:80], i,
                        )

        if not injected:
            # Check if there are ANY AIMessages with reasoning fields
            ai_msgs = [(i, m) for i, m in enumerate(messages) if isinstance(m, AIMessage)]
            logger.debug(
                "DIAG: No reasoning_content injected. %d AI msgs. "
                "additional_kwargs keys: %s",
                len(ai_msgs),
                [list(m.additional_kwargs.keys()) for _, m in ai_msgs],
            )
            # DIAG: print ALL message types
            logger.debug(
                "DIAG: ALL %d messages types: %s",
                len(messages),
                [(i, type(m).__name__, m.__class__.__bases__[0].__name__ if hasattr(m.__class__.__bases__[0], '__name__') else '?', hasattr(m, 'additional_kwargs'), list(getattr(m, 'additional_kwargs', {}).keys())) for i, m in enumerate(messages)],
            )

        return payload
