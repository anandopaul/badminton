#!/usr/bin/env python3
"""Run Rally Atlas's local API and Vite development servers."""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOCAL_CONFIG = PROJECT_ROOT / ".rally-atlas.local.json"
EXAMPLE_CONFIG = PROJECT_ROOT / ".rally-atlas.local.json.example"
API_PORT = 3001
WEB_PORT = 5173


class StartupError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check local requirements and run the Rally Atlas web app and chat API."
    )
    parser.add_argument(
        "--ollama-url",
        help="Override OLLAMA_BASE_URL and the local config file.",
    )
    parser.add_argument(
        "--model",
        help="Override OLLAMA_MODEL and the local config file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check data, dependencies, and Ollama connectivity without starting servers.",
    )
    return parser.parse_args()


def load_local_config() -> dict[str, str]:
    if not LOCAL_CONFIG.exists():
        return {}

    try:
        config = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StartupError(f"Cannot read {LOCAL_CONFIG.name}: {error}") from error

    if not isinstance(config, dict):
        raise StartupError(f"{LOCAL_CONFIG.name} must contain a JSON object.")

    allowed_keys = {"ollama_base_url", "ollama_model"}
    unknown_keys = set(config) - allowed_keys
    if unknown_keys:
        names = ", ".join(sorted(str(key) for key in unknown_keys))
        raise StartupError(f"Unknown key(s) in {LOCAL_CONFIG.name}: {names}")

    for key, value in config.items():
        if not isinstance(value, str) or not value.strip():
            raise StartupError(f"{key} in {LOCAL_CONFIG.name} must be a non-empty string.")

    return config


def resolve_settings(args: argparse.Namespace) -> tuple[str, str]:
    config = load_local_config()
    base_url = (
        args.ollama_url
        or os.environ.get("OLLAMA_BASE_URL")
        or config.get("ollama_base_url")
    )
    model = (
        args.model
        or os.environ.get("OLLAMA_MODEL")
        or config.get("ollama_model")
        or "qwen2.5-coder:14b"
    )

    if not base_url:
        raise StartupError(
            f"Set OLLAMA_BASE_URL or copy {EXAMPLE_CONFIG.name} to "
            f"{LOCAL_CONFIG.name} and enter the current Windows WSL adapter IP."
        )

    validate_ollama_url(base_url)
    if not model.strip():
        raise StartupError("OLLAMA_MODEL must not be empty.")
    return base_url.rstrip("/"), model.strip()


def validate_ollama_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise StartupError("Ollama URL must be an absolute HTTP(S) URL.")
    try:
        parsed.port
    except ValueError as error:
        raise StartupError("Ollama URL has an invalid port.") from error
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise StartupError(
            "Ollama URL must be a local server root without credentials, "
            "query parameters, or API paths."
        )

    hostname = parsed.hostname.casefold()
    if hostname in {"localhost", "host.docker.internal", "ollama"}:
        return
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as error:
        raise StartupError(
            "Ollama URL must use a loopback/private IP or a local service hostname."
        ) from error
    if not (address.is_loopback or address.is_private):
        raise StartupError("Ollama URL must not point to a public IP address.")


def check_local_requirements() -> None:
    if os.name != "posix":
        raise StartupError(
            "Run this script inside the Linux Rally Atlas Dev Container; "
            "Windows only needs to run Ollama and its WSL port forward."
        )

    missing_modules = [
        name
        for name in ("fastapi", "httpx", "uvicorn")
        if importlib.util.find_spec(name) is None
    ]
    if missing_modules:
        modules = ", ".join(missing_modules)
        raise StartupError(
            f"Missing API packages ({modules}) for {sys.executable}. Install them with "
            f"`{sys.executable} -m pip install -r api/requirements.txt`."
        )

    if shutil.which("npm") is None or shutil.which("node") is None:
        raise StartupError("Install Node.js 22+ and npm in the Dev Container.")
    if not (WEB_DIR / "node_modules").is_dir():
        raise StartupError("Frontend dependencies are missing; run `npm ci --prefix web`.")

    profile_file = OUTPUT_DIR / "player_profile.json"
    if not profile_file.is_file():
        raise StartupError(
            f"{profile_file.relative_to(PROJECT_ROOT)} is missing. "
            "Run `python3 build_player_profiles.py` from the repository root."
        )
    season_files = list(OUTPUT_DIR.glob("[0-9][0-9][0-9][0-9]/*.json"))
    if not season_files:
        raise StartupError(
            "No season JSON files were found under output/<year>/. "
            "Restore or collect the local season exports first."
        )


def check_ollama(base_url: str, model: str) -> None:
    try:
        with urlopen(f"{base_url}/api/tags", timeout=5) as response:
            data = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise StartupError(
            f"Cannot reach Ollama at {base_url}/api/tags: {error}\n"
            "On Windows, confirm Ollama is running and the portproxy points from "
            "the current WSL adapter IP to 127.0.0.1:11434."
        ) from error

    models = data.get("models") if isinstance(data, dict) else None
    model_names = {
        entry.get("name")
        for entry in models
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    } if isinstance(models, list) else set()
    if model not in model_names:
        available = ", ".join(sorted(model_names)) or "none"
        raise StartupError(
            f"Ollama is reachable, but model {model!r} is not installed. "
            f"Available models: {available}. Install it on Windows with "
            f"`ollama pull {model}`."
        )


def ensure_ports_are_free() -> None:
    for port, service in ((API_PORT, "FastAPI"), (WEB_PORT, "Vite")):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                raise StartupError(
                    f"{service} port {port} is already in use. Stop the existing "
                    "server (usually with Ctrl+C in its terminal), then retry."
                ) from error


def wait_for_http(
    service: str,
    url: str,
    process: subprocess.Popen[bytes],
    timeout_seconds: float = 30,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response yet"
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise StartupError(f"{service} exited during startup with status {exit_code}.")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except HTTPError as error:
            last_error = f"HTTP {error.code}"
        except (URLError, TimeoutError, OSError) as error:
            last_error = str(error)
        time.sleep(0.25)
    raise StartupError(f"{service} did not become ready at {url}: {last_error}")


def stop_processes(processes: list[tuple[str, subprocess.Popen[bytes]]]) -> None:
    for name, process in reversed(processes):
        if process.poll() is None:
            print(f"Stopping {name}...", flush=True)
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    for _, process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()


def run_servers(base_url: str, model: str) -> int:
    ensure_ports_are_free()
    backend_env = os.environ.copy()
    backend_env.update(
        {
            "OLLAMA_BASE_URL": base_url,
            "OLLAMA_MODEL": model,
            "BADMINTON_DATA_DIR": str(OUTPUT_DIR),
        }
    )
    frontend_env = os.environ.copy()
    frontend_env["RALLY_ATLAS_CHAT_API_TARGET"] = f"http://127.0.0.1:{API_PORT}"
    processes: list[tuple[str, subprocess.Popen[bytes]]] = []

    try:
        print("Starting FastAPI...", flush=True)
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(API_PORT),
            ],
            cwd=PROJECT_ROOT,
            env=backend_env,
            start_new_session=True,
        )
        processes.append(("FastAPI", backend))
        wait_for_http("FastAPI", f"http://127.0.0.1:{API_PORT}/health", backend)

        print("Starting Vite...", flush=True)
        frontend = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1"],
            cwd=WEB_DIR,
            env=frontend_env,
            start_new_session=True,
        )
        processes.append(("Vite", frontend))
        wait_for_http("Vite", f"http://127.0.0.1:{WEB_PORT}/", frontend)

        print(
            f"\nRally Atlas is ready at http://127.0.0.1:{WEB_PORT}/\n"
            "Chat uses the local Ollama service. Press Ctrl+C to stop both servers.\n",
            flush=True,
        )
        while True:
            for name, process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    raise StartupError(
                        f"{name} exited unexpectedly with status {exit_code}."
                    )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping Rally Atlas...", flush=True)
        return 0
    finally:
        stop_processes(processes)


def main() -> int:
    args = parse_args()
    try:
        base_url, model = resolve_settings(args)
        check_local_requirements()
        check_ollama(base_url, model)
        print(f"OK: Ollama model {model!r} is available at {base_url}.")
        print("OK: local JSON data and frontend dependencies are present.")
        if args.check:
            print("All checks passed.")
            return 0
        return run_servers(base_url, model)
    except StartupError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
