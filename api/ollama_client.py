from __future__ import annotations

from typing import Any

import httpx

from api.config import Settings


class OllamaUnavailableError(RuntimeError):
    """Raised when the configured Ollama server cannot be reached."""


class OllamaTimeoutError(RuntimeError):
    """Raised when Ollama does not finish before the configured timeout."""


class OllamaResponseError(RuntimeError):
    """Raised when Ollama returns an error or an invalid response."""


class OllamaClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    async def complete(self, messages: list[dict[str, str]]) -> str:
        timeout = httpx.Timeout(
            self.settings.ollama_timeout_seconds,
            connect=min(self.settings.ollama_timeout_seconds, 5.0),
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/chat",
                    json={
                        "model": self.settings.ollama_model,
                        "messages": messages,
                        "stream": False,
                    },
                )
        except httpx.TimeoutException as error:
            raise OllamaTimeoutError(
                "The local model did not respond before the timeout."
            ) from error
        except httpx.RequestError as error:
            raise OllamaUnavailableError(
                "Could not reach the local Ollama server. Check that it is running "
                "and that OLLAMA_BASE_URL is reachable from the backend."
            ) from error

        if response.is_error:
            raise OllamaResponseError(
                f"Ollama returned HTTP {response.status_code}."
            )

        try:
            payload: Any = response.json()
        except ValueError as error:
            raise OllamaResponseError("Ollama returned invalid JSON.") from error

        message = payload.get("message") if isinstance(payload, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError(
                "Ollama returned a response without message content."
            )
        return content.strip()
