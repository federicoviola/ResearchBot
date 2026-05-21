"""Configurable LLM clients for grounded query generation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMClientError(ValueError):
    """Raised when an LLM provider cannot be called."""


class LLMClient(Protocol):
    """Minimal chat-completion interface used by query generation."""

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return assistant text for chat messages."""


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    base_url: str
    model: str
    api_key_env: str
    temperature: float
    max_tokens: int


OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "openai_compatible",
    "ollama",
    "lmstudio",
    "lm_studio",
    "vllm",
}


class OpenAICompatibleClient:
    """Client for OpenAI-compatible chat completion APIs."""

    def __init__(self, settings: LLMSettings, timeout: int = 120) -> None:
        self.settings = settings
        self.timeout = timeout

    def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.settings.model or self.settings.model == "configure-me":
            raise LLMClientError(
                "LLM model is not configured. Set llm.model in config/project.yaml."
            )
        url = _chat_completions_url(self.settings.base_url)
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv(self.settings.api_key_env, "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise LLMClientError(f"LLM provider returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise LLMClientError(f"Could not reach LLM provider: {error.reason}") from error
        except json.JSONDecodeError as error:
            raise LLMClientError("LLM provider returned invalid JSON.") from error

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMClientError("LLM provider response did not include message content.") from error
        return str(content).strip()


def client_from_settings(settings: LLMSettings) -> LLMClient:
    provider = settings.provider.strip().lower()
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return OpenAICompatibleClient(settings)
    raise LLMClientError(
        f"Unsupported provider '{settings.provider}'. "
        "Use provider=openai_compatible for Ollama, LM Studio, vLLM, OpenAI, "
        "or any OpenAI-compatible endpoint. Native Claude/Gemini clients are planned."
    )


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"
