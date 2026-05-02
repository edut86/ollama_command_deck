"""Small Ollama HTTP client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .config import get_ollama_api_key, get_ollama_base_url

# Model name substrings that support the `think` option in Ollama
_THINKING_PATTERNS = ("qwen3", "deepseek-r1", "phi4-reasoning", "qwq")


def _should_think(model: str) -> bool:
    lowered = model.lower()
    return any(p in lowered for p in _THINKING_PATTERNS)


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size: int | None = None
    modified_at: str | None = None


class OllamaError(RuntimeError):
    pass


def _request_json(path: str, payload: dict | None = None, timeout: int = 30, base_url: str | None = None) -> dict:
    url = f"{base_url or get_ollama_base_url()}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = get_ollama_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers, method="GET" if payload is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaError(f"Could not reach Ollama at {url}: {exc}") from exc


def list_models(base_url: str | None = None) -> list[OllamaModel]:
    data = _request_json("/api/tags", base_url=base_url)
    return [
        OllamaModel(name=item["name"], size=item.get("size"), modified_at=item.get("modified_at"))
        for item in data.get("models", [])
        if item.get("name")
    ]


@dataclass(frozen=True)
class ThinkingChunk:
    """Streaming reasoning trace from a thinking-capable model."""
    text: str


@dataclass
class ChatStats:
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_duration_ms: float = 0.0

    def __str__(self) -> str:
        tps = (self.response_tokens / (self.total_duration_ms / 1000)) if self.total_duration_ms else 0
        return (
            f"prompt tokens: {self.prompt_tokens}  "
            f"response tokens: {self.response_tokens}  "
            f"total: {self.total_duration_ms:.0f}ms  "
            f"speed: {tps:.1f} tok/s"
        )


def stream_chat(
    model: str,
    messages: Iterable[dict[str, str]],
    timeout: int = 300,
    collect_stats: bool = False,
    images: list[str] | None = None,
    base_url: str | None = None,
    keep_alive: str | None = None,
) -> Iterator[str | ThinkingChunk | ChatStats]:
    """Stream chat tokens.  `images` is a list of base64-encoded image strings
    to attach to the last user message (requires a vision model). Thinking-capable
    models also yield `ThinkingChunk(text)` items separately from normal content."""
    url = f"{base_url or get_ollama_base_url()}/api/chat"
    msg_list = list(messages)
    if images:
        # Attach images to the last user message
        for i in range(len(msg_list) - 1, -1, -1):
            if msg_list[i].get("role") == "user":
                msg_list[i] = {**msg_list[i], "images": images}
                break
    payload: dict = {"model": model, "messages": msg_list, "stream": True}
    if keep_alive:
        payload["keep_alive"] = keep_alive
    if _should_think(model):
        payload["options"] = {"think": True}
    headers = {"Content-Type": "application/json"}
    api_key = get_ollama_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                event = json.loads(raw_line.decode("utf-8"))
                msg = event.get("message", {})
                thinking = msg.get("thinking")
                if thinking:
                    yield ThinkingChunk(text=thinking)
                content = msg.get("content")
                if content:
                    yield content
                if event.get("done"):
                    if collect_stats:
                        yield ChatStats(
                            prompt_tokens=event.get("prompt_eval_count", 0),
                            response_tokens=event.get("eval_count", 0),
                            total_duration_ms=event.get("total_duration", 0) / 1_000_000,
                        )
                    break
    except urllib.error.URLError as exc:
        raise OllamaError(f"Could not chat with Ollama at {url}: {exc}") from exc
