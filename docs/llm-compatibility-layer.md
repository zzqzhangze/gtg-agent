# LLM 兼容层原理

> 本文档解释 `ChatOpenAIWithReasoning` 类的必要性、实现原理和适用场景。
>
> **关键文件**: `src/llm.py`

---

## 1. 要解决什么问题

OpenAI 的 Chat Completion API 有一个标准响应格式。但是一些非 OpenAI 厂商
（DeepSeek、OpenRouter 等）在兼容"OpenAI 协议"的同时，会在响应中返回专有字段：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "...",
      "reasoning_content": "先分析需求，然后..."  // ← 非标准字段
    }
  }]
}
```

这个 `reasoning_content` 字段包含模型的"思考过程"（chain-of-thought），
对多轮对话非常重要——下次请求时 API 希望看到这个字段回传。

**但 LangChain 的 `ChatOpenAI` 会丢弃它**，原因有二：

1. **接收端**：OpenAI Python SDK 解析响应时自动丢弃未知字段
2. **发送端**：`_convert_message_to_dict` 只保留 `tool_calls`、`function_call`、`audio`
   三个 `additional_kwargs` 键，没有通用透传机制

---

## 2. 解决方式

在 `ChatOpenAI` 子类中同时拦截两端处理：

```
接收 (_generate):                发送 (_get_request_payload):
  原始 HTTP 响应 JSON               消息列表
       │                                │
       ▼                                ▼
  提取 reasoning_content           序列化消息 dict
       │                                │
       ▼                                ▼
  注入 additional_kwargs           回填 reasoning_content
```

### 2.1 接收端

```python
def _generate(self, messages, stop, run_manager, **kwargs) -> ChatResult:
    raw_response = self.client.with_raw_response.create(**payload)
    response = raw_response.parse()
    result = self._create_chat_result(response, ...)

    # 从原始 HTTP 响应 JSON 中提取 reasoning 字段
    raw_json = json.loads(raw_response.http_response.text)
    for choice in raw_json.get("choices", []):
        msg_dict = choice.get("message", {})
        for field in _REASONING_FIELDS:  # {"reasoning_content", "reasoning"}
            if field in msg_dict:
                gen.message.additional_kwargs[field] = msg_dict[field]
```

关键技巧：使用 `client.with_raw_response.create()` 获取原始 HTTP 响应，
绕过 OpenAI SDK 的解析层，直接读 JSON。

### 2.2 发送端

```python
def _get_request_payload(self, input_, stop, **kwargs) -> dict:
    payload = super()._get_request_payload(...)
    messages = self._convert_input(input_).to_messages()

    for i, m in enumerate(messages):
        if isinstance(m, AIMessage):
            for field in _REASONING_FIELDS:
                if field in m.additional_kwargs:
                    msg_dicts[i][field] = m.additional_kwargs[field]
    return payload
```

在父类序列化完成之后，把 `additional_kwargs` 中的 reasoning 字段
重新注入到序列化后的消息 dict 中。

---

## 3. 思考过程不丢失的连锁反应

```
Round 1:
  请求: {messages: [用户消息]}
  响应: {content: "最终答案", reasoning_content: "思考过程"}
          → additional_kwargs["reasoning_content"] 保存 ✓

Round 2:
  请求: {messages: [
    用户消息,
    {role: "assistant", content: "最终答案", reasoning_content: "思考过程"},
    用户新消息
  ]}
  响应: ... 模型看到历史思考过程，继续正确推理 ✓
```

如果不用这个兼容层：

```
Round 2（无兼容层）:
  请求: {messages: [
    用户消息,
    {role: "assistant", content: "最终答案"},  // reasoning_content 丢失！
    用户新消息
  ]}
  → 某些模型（如 DeepSeek）会报错或行为异常 ✗
```

---

## 4. 已知的厂商差异

| 厂商 | 字段名 | 行为 |
|------|--------|------|
| DeepSeek | `reasoning_content` | 请求/响应都需透传 |
| OpenRouter | `reasoning` | 同上 |
| Qwen (Ollama) | 无特殊字段 | 兼容层不影响 |
| OpenAI | 无特殊字段 | 兼容层不影响 |

`_REASONING_FIELDS` 是一个 `frozenset`，添加新厂商只需增加字段名。

---

## 5. Debug 诊断

兼容层包含大量 `logger.debug("DIAG: ...")` 日志，启用方式：

```python
logging.getLogger("llm").setLevel(logging.DEBUG)
```

会输出：
- 每次 `_generate` 调用时的消息类型分布
- 实际发送给 API 的 payload 消息结构
- 检测到/注入的 `reasoning_content` 长度

---

## 6. 局限性与后续改进

| 问题 | 影响 | 改进方向 |
|------|------|----------|
| 只用 `with_raw_response` | 绕过了 SDK 的流式处理 | 需要同时覆盖 `_stream` 方法 |
| 只在 `_generate` 中处理 | 流式生成不走 `_generate` | 实现 `_stream` 的 reasoning 提取 |
| 字段名硬编码 | 新厂商需要改代码 | 可以考虑从响应中动态发现未知字段 |
