"""LLM 客户端（OpenAI 兼容协议，标准库实现，零额外依赖）。

- 配置了 OPENAI_API_KEY 且非 mock 模式：真实调用 /chat/completions
- 否则返回 None，由各 Agent 走本地启发式实现（保证无 Key 也能跑通全链路）
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("webmind.llm")


class TokenUsage:
    """累计 token 消耗。"""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0

    def add(self, inp: int, out: int) -> None:
        self.input_tokens += inp
        self.output_tokens += out

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total,
        }


def mock_mode() -> bool:
    mode = (settings.LLM_MOCK_MODE or "auto").lower()
    if mode == "true":
        return True
    if mode == "false":
        return False
    return not settings.OPENAI_API_KEY


def _endpoint() -> str:
    base = (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def chat(
    system: str,
    user: str,
    usage: TokenUsage | None = None,
    json_mode: bool = True,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str | None:
    """调用 LLM，返回文本；不可用时返回 None。"""
    if mock_mode():
        return None

    payload: dict[str, Any] = {
        "model": settings.MODEL_NAME,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        _endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.LLM_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("LLM 调用失败，回退本地实现: %s", exc)
        return None

    if usage is not None:
        token_usage = body.get("usage", {})
        if token_usage:
            usage.add(
                int(token_usage.get("prompt_tokens", 0)),
                int(token_usage.get("completion_tokens", 0)),
            )
        else:
            usage.add(_estimate_tokens(system + user), _estimate_tokens(str(body)))

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError):  # pragma: no cover
        return None


def _estimate_tokens(text: str) -> int:
    """粗略估算：英文 4 字符 ≈ 1 token，中文 1.5 字符 ≈ 1 token。"""
    if not text:
        return 0
    ascii_len = sum(1 for ch in text if ord(ch) < 128)
    cjk_len = len(text) - ascii_len
    return int(ascii_len / 4 + cjk_len / 1.5)


def extract_json(text: str) -> dict | list | None:
    """从 LLM 输出中稳健提取 JSON（容错 ```json 代码块）。"""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None
