from __future__ import annotations

import os
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    data_dir: Path

    @classmethod
    def from_environment(cls) -> Settings:
        base_url = os.environ.get(
            "OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        ).rstrip("/")
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("OLLAMA_BASE_URL must be an absolute HTTP(S) URL.")
        if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise ValueError(
                "OLLAMA_BASE_URL must not contain credentials, query parameters, or fragments."
            )
        if parsed_url.path not in {"", "/"}:
            raise ValueError("OLLAMA_BASE_URL must be the server root without an API path.")
        hostname = (parsed_url.hostname or "").casefold()
        if hostname not in {"localhost", "host.docker.internal", "ollama"}:
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError as error:
                raise ValueError(
                    "OLLAMA_BASE_URL must point to a loopback/private host or the local "
                    "Ollama Compose service."
                ) from error
            if not (address.is_loopback or address.is_private):
                raise ValueError(
                    "OLLAMA_BASE_URL must not point to a public network address."
                )

        model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b").strip()
        if not model:
            raise ValueError("OLLAMA_MODEL must not be empty.")

        timeout_raw = os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120")
        try:
            timeout = float(timeout_raw)
        except ValueError as error:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be numeric.") from error
        if timeout <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be greater than zero.")

        data_dir = Path(
            os.environ.get("BADMINTON_DATA_DIR", str(PROJECT_ROOT / "output"))
        ).expanduser()

        return cls(
            ollama_base_url=base_url,
            ollama_model=model,
            ollama_timeout_seconds=timeout,
            data_dir=data_dir.resolve(),
        )
