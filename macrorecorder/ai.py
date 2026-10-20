"""AI actions through any OpenAI-compatible chat API.

Works with OpenRouter (access to many model families with one key), OpenAI,
and local engines such as Ollama or LM Studio (nothing leaves the PC).
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

PROVIDERS = [
    ("openrouter", "OpenRouter", "https://openrouter.ai/api/v1"),
    ("openai", "OpenAI", "https://api.openai.com/v1"),
    ("ollama", "Ollama (local)", "http://localhost:11434/v1"),
    ("lmstudio", "LM Studio (local)", "http://localhost:1234/v1"),
    ("custom", "Custom (OpenAI-compatible)", ""),
]


class AIError(RuntimeError):
    pass


@dataclass
class AIConfig:
    provider: str = "openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    model: str = ""
    timeout: int = 120

    def headers(self) -> dict:
        h = {"Content-Type": "application/json", "User-Agent": "ActionsRecorder"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if self.provider == "openrouter":
            h["X-Title"] = "Actions Recorder"
        return h


def _request(cfg: AIConfig, path: str, payload: dict | None = None) -> dict:
    if not cfg.base_url:
        raise AIError("AI is not configured (Settings → AI)")
    url = cfg.base_url.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=cfg.headers(), method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise AIError(f"HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise AIError(f"Cannot reach {url}: {e.reason}") from None


def list_models(cfg: AIConfig) -> list[str]:
    data = _request(cfg, "/models")
    items = data.get("data", data.get("models", []))
    return sorted({m.get("id") or m.get("name") for m in items if isinstance(m, dict)} - {None})


def chat(cfg: AIConfig, prompt: str, image_png: bytes | None = None, system: str | None = None,
         max_tokens: int | None = None) -> str:
    if not cfg.model:
        raise AIError("No AI model selected (Settings → AI)")
    content: list | str = prompt
    if image_png is not None:
        b64 = base64.b64encode(image_png).decode("ascii")
        content = [{"type": "text", "text": prompt},
                   {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    payload: dict = {"model": cfg.model, "messages": messages}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    data = _request(cfg, "/chat/completions", payload)
    try:
        msg = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AIError(f"Unexpected answer: {str(data)[:300]}") from None
    if isinstance(msg, list):
        msg = "".join(part.get("text", "") for part in msg if isinstance(part, dict))
    return (msg or "").strip()


FIND_SYSTEM = (
    "You locate user-interface elements in screenshots. Answer ONLY with JSON: "
    '{"found": true, "x": <int>, "y": <int>} giving the pixel coordinates of the CENTER of the '
    'element in the image, or {"found": false} if it is not visible.')


def find_object(cfg: AIConfig, png: bytes, width: int, height: int, description: str) -> tuple[int, int] | None:
    """Ask a vision model where ``description`` is. Returns image pixel coords."""
    prompt = (f"The screenshot is {width}x{height} pixels. Find: {description}\n"
              "Reply with the JSON object only.")
    answer = chat(cfg, prompt, png, system=FIND_SYSTEM, max_tokens=200)
    m = re.search(r"\{.*\}", answer, re.S)
    if not m:
        raise AIError(f"AI answer was not JSON: {answer[:200]}")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        raise AIError(f"AI answer was not JSON: {answer[:200]}") from None
    if not obj.get("found", True) or "x" not in obj:
        return None
    x, y = int(obj["x"]), int(obj["y"])
    if not (0 <= x <= width and 0 <= y <= height):
        return None
    return x, y
