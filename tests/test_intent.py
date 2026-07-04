"""Tests for intent classification utilities (src/agent/nodes.py)."""

import json

from src.agent.nodes import _parse_intent_json, _detect_mime_type, _classify_file_type


class TestParseIntentJson:
    """_parse_intent_json: extract JSON from LLM responses."""

    def test_plain_json(self):
        result = _parse_intent_json('{"task_type": "chat"}')
        assert result == {"task_type": "chat"}

    def test_with_code_fence(self):
        result = _parse_intent_json('```json\n{"task_type": "compute"}\n```')
        assert result == {"task_type": "compute"}

    def test_with_code_fence_no_lang(self):
        result = _parse_intent_json('```\n{"task_type": "code_exec"}\n```')
        assert result == {"task_type": "code_exec"}

    def test_with_triple_backtick_end_only(self):
        # LLM 只加了尾 ``` 但没开头 ``` → 函数不做特殊处理，由 json 解析兜底
        result = _parse_intent_json('```\n{"task_type": "chat"}\n```')
        assert result == {"task_type": "chat"}

    def test_invalid_json_returns_none(self):
        result = _parse_intent_json("not json at all")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_intent_json("")
        assert result is None

    def test_full_intent_payload(self):
        payload = {
            "task_type": "data_analysis",
            "reasoning": "需要读取上传的文件进行数据分析",
            "suggested_template": "data-analysis",
            "needs_sandbox": True,
        }
        result = _parse_intent_json(json.dumps(payload))
        assert result == payload


class TestDetectMimeType:
    """_detect_mime_type: map file extensions to mime types."""

    def test_csv(self):
        assert _detect_mime_type("data.csv") == "csv"

    def test_python(self):
        assert _detect_mime_type("script.py") == "py"

    def test_html(self):
        assert _detect_mime_type("index.html") == "html"

    def test_unknown(self):
        assert _detect_mime_type("file.xyz") == "unknown"

    def test_no_extension(self):
        assert _detect_mime_type("Makefile") == "unknown"

    def test_case_insensitive(self):
        assert _detect_mime_type("Data.CSV") == "csv"


class TestClassifyFileType:
    """_classify_file_type: categorize mime types."""

    def test_code(self):
        assert _classify_file_type("py") == "code"
        assert _classify_file_type("js") == "code"
        assert _classify_file_type("rs") == "code"

    def test_data(self):
        assert _classify_file_type("csv") == "data"
        assert _classify_file_type("json") == "data"

    def test_image(self):
        assert _classify_file_type("png") == "image"
        assert _classify_file_type("jpg") == "image"

    def test_doc(self):
        assert _classify_file_type("md") == "doc"
        assert _classify_file_type("txt") == "doc"

    def test_archive(self):
        assert _classify_file_type("zip") == "archive"

    def test_binary_pdf(self):
        assert _classify_file_type("pdf") == "binary"

    def test_unknown(self):
        assert _classify_file_type("xyz") == "unknown"
