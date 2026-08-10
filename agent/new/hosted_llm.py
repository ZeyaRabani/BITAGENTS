"""
LLM clients: CapIX (primary), self-hosted Ollama, OpenRouter fallback.

CapIX: OpenAI-compatible POST {base}/v1/chat/completions with Bearer auth.
Ollama: POST {base}/api/chat with X-API-Key header.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests

DEFAULT_CAPIX_MODEL = "meta-llama/llama-3.1-8b-instruct"
DEFAULT_CAPIX_API_URL = "https://www.capix.network/api/v1/chat/completions"
DEFAULT_HOSTED_MODEL = "llama3.2:3b"
DEFAULT_HOSTED_BASE_URL = "https://llm.bitagents.app"
HOSTED_CONNECT_TIMEOUT_SECONDS = float(
    os.environ.get("HOSTED_OLLAMA_CONNECT_TIMEOUT", "15")
)
HOSTED_READ_TIMEOUT_SECONDS = float(os.environ.get("HOSTED_OLLAMA_READ_TIMEOUT", "120"))
CAPIX_CONNECT_TIMEOUT_SECONDS = float(os.environ.get("CAPIX_CONNECT_TIMEOUT", "10"))
CAPIX_READ_TIMEOUT_SECONDS = float(os.environ.get("CAPIX_READ_TIMEOUT", "45"))
CAPIX_TIMING_LOG = os.environ.get("CAPIX_TIMING_LOG", "1").strip().lower() not in ("0", "false", "")


def _looks_like_model_tag(value: str) -> bool:
    if not value:
        return False
    if value.startswith("llama") or value.startswith("mistral") or value.startswith("qwen"):
        return True
    return bool(re.fullmatch(r"[\w.-]+:[\w.-]+", value))


def _normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith("http"):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        return ""
    return value.rstrip("/")


def resolve_hosted_base_url() -> str:
    explicit = (
        os.environ.get("HOSTED_OLLAMA_BASE_URL")
        or os.environ.get("HOSTED_OLLAMA_URL")
        or ""
    ).strip()
    if explicit:
        return _normalize_base_url(explicit) or DEFAULT_HOSTED_BASE_URL

    legacy = os.environ.get("HOSTED_OLLAMA_MODEL", "").strip()
    if legacy and not _looks_like_model_tag(legacy):
        return _normalize_base_url(legacy) or DEFAULT_HOSTED_BASE_URL

    return DEFAULT_HOSTED_BASE_URL


def resolve_hosted_model_name() -> str:
    legacy = os.environ.get("HOSTED_OLLAMA_MODEL", "").strip()
    if legacy and _looks_like_model_tag(legacy):
        return legacy
    return (
        os.environ.get("HOSTED_OLLAMA_MODEL_NAME")
        or os.environ.get("OLLAMA_MODEL")
        or DEFAULT_HOSTED_MODEL
    )


HOSTED_OLLAMA_BASE_URL = resolve_hosted_base_url()
HOSTED_OLLAMA_MODEL = resolve_hosted_model_name()
HOSTED_OLLAMA_API_KEY = (
    os.environ.get("HOSTED_MODEL_API_KEY")
    or os.environ.get("HOSTED_OLLAMA_API_KEY")
    or ""
).strip()

CAPIX_API_KEY = (
    os.environ.get("CAPIX_API_KEY")
    or os.environ.get("CAPIX_API_TOKEN")
    or ""
).strip()
CAPIX_API_URL = os.environ.get("CAPIX_API_URL", DEFAULT_CAPIX_API_URL).strip() or DEFAULT_CAPIX_API_URL
CAPIX_MODEL = os.environ.get("CAPIX_MODEL", DEFAULT_CAPIX_MODEL).strip() or DEFAULT_CAPIX_MODEL
CAPIX_PROVIDER = os.environ.get("CAPIX_PROVIDER", "DeepInfra").strip()
CAPIX_MAX_RETRIES = int(os.environ.get("CAPIX_MAX_RETRIES", "2"))

# Legacy OpenRouter (optional fallback)
OPEN_ROUTER_API = (
    os.environ.get("OPEN_ROUTER_API", "")
    or os.environ.get("OPENROUTER_API_KEY", "")
).strip()
OPEN_ROUTER_API_URL = os.environ.get(
    "OPEN_ROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
)
OPEN_ROUTER_SITE_URL = os.environ.get("OPEN_ROUTER_SITE_URL", "https://bitagents.app")
OPEN_ROUTER_APP_NAME = os.environ.get("OPEN_ROUTER_APP_NAME", "BIT Agents")


def use_capix() -> bool:
    return bool(CAPIX_API_KEY)


def use_hosted_ollama() -> bool:
    return bool(HOSTED_OLLAMA_API_KEY) and not use_capix()


def llm_provider() -> str:
    if use_capix():
        return "capix"
    if use_hosted_ollama():
        return "hosted_ollama"
    if OPEN_ROUTER_API:
        return "openrouter"
    return "unconfigured"


def llm_configured() -> bool:
    return use_capix() or bool(HOSTED_OLLAMA_API_KEY) or bool(OPEN_ROUTER_API)


def default_llm_model() -> str:
    if use_capix():
        return CAPIX_MODEL
    if HOSTED_OLLAMA_API_KEY:
        return HOSTED_OLLAMA_MODEL
    if OPEN_ROUTER_API:
        return os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_HOSTED_MODEL)
    return CAPIX_MODEL


DEFAULT_LLM_MODEL = default_llm_model()


def resolve_capix_model(_requested: Optional[str] = None) -> str:
    """Always use the configured CapIX model (default: meta-llama/llama-3.1-8b-instruct).

    Agent-local MODEL tags (llama3.2:3b, mistral, etc.) are ignored so CapIX cannot
    route tool calls to a different upstream model.
    """
    return CAPIX_MODEL


def _capix_provider_block() -> Optional[dict[str, Any]]:
    if not CAPIX_PROVIDER:
        return None
    return {
        "only": [p.strip() for p in CAPIX_PROVIDER.split(",") if p.strip()],
        "allow_fallbacks": False,
    }


def _capix_retry_delay(attempt: int, status_code: Optional[int] = None) -> float:
    if status_code == 429:
        return min(2.0 * (2 ** (attempt - 1)), 30.0)
    return 1.5 * attempt


def _capix_headers() -> dict[str, str]:
    if not CAPIX_API_KEY:
        raise RuntimeError(
            "CAPIX_API_KEY is not set. Add it to agent/new/.env (see .env.example)."
        )
    return {
        "Authorization": f"Bearer {CAPIX_API_KEY}",
        "Content-Type": "application/json",
    }


def _capix_timeouts() -> tuple[float, float]:
    return (CAPIX_CONNECT_TIMEOUT_SECONDS, CAPIX_READ_TIMEOUT_SECONDS)


def _hosted_headers() -> dict[str, str]:
    if not HOSTED_OLLAMA_API_KEY:
        raise RuntimeError(
            "HOSTED_MODEL_API_KEY is not set. Add it to agent/new/.env (see .env.example)."
        )
    return {
        "Content-Type": "application/json",
        "X-API-Key": HOSTED_OLLAMA_API_KEY,
    }


def _openrouter_headers(app_suffix: str = "") -> dict[str, str]:
    if not OPEN_ROUTER_API:
        raise RuntimeError(
            "OPEN_ROUTER_API is not set. Configure hosted Ollama or OpenRouter in agent/new/.env."
        )
    title = OPEN_ROUTER_APP_NAME
    if app_suffix:
        title = f"{title} {app_suffix}".strip()
    return {
        "Authorization": f"Bearer {OPEN_ROUTER_API}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPEN_ROUTER_SITE_URL,
        "X-Title": title,
    }


def _request_timeouts() -> tuple[float, float]:
    return (HOSTED_CONNECT_TIMEOUT_SECONDS, HOSTED_READ_TIMEOUT_SECONDS)


def _parse_json_response(resp: requests.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as exc:
        snippet = (resp.text or "").strip().replace("\n", " ")[:240]
        raise RuntimeError(
            f"Hosted Ollama returned non-JSON ({resp.status_code}): {snippet or resp.reason}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Hosted Ollama returned an unexpected JSON payload.")
    return data


def _error_from_response(resp: requests.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body.get("error"), str):
            return body["error"]
        if isinstance(body.get("error"), dict) and body["error"].get("message"):
            return str(body["error"]["message"])
        if body.get("message"):
            return str(body["message"])
    except Exception:
        pass
    return resp.text or resp.reason or "Unknown error"


def _coerce_tool_arguments(arguments: Any) -> str:
    """Ollama requires tool-call arguments to be valid JSON object strings."""
    if isinstance(arguments, dict):
        return json.dumps(arguments, separators=(",", ":"))
    if not isinstance(arguments, str):
        return "{}"
    text = arguments.strip()
    if not text:
        return "{}"
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return json.dumps(parsed, separators=(",", ":"))
    except json.JSONDecodeError:
        pass
    return "{}"


def _normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    if not tool_calls:
        return []
    normalized: list[dict[str, Any]] = []
    for idx, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name")
        normalized.append(
            {
                "id": tc.get("id") or f"call_{idx}",
                "type": tc.get("type") or "function",
                "function": {
                    "name": name,
                    "arguments": _coerce_tool_arguments(
                        fn.get("arguments", tc.get("arguments", {}))
                    ),
                },
            }
        )
    return normalized


def _sanitize_messages_for_ollama(messages: list) -> list[dict[str, Any]]:
    """Normalize chat history so Ollama can parse tool-call follow-up turns."""
    sanitized: list[dict[str, Any]] = []
    last_tool_name: Optional[str] = None

    for raw in messages:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            continue

        msg: dict[str, Any] = {"role": role}
        content = raw.get("content")
        if content is None:
            msg["content"] = ""
        elif isinstance(content, str):
            msg["content"] = content
        else:
            msg["content"] = json.dumps(content, separators=(",", ":"))

        if role == "assistant" and raw.get("tool_calls"):
            msg["tool_calls"] = _normalize_tool_calls(raw.get("tool_calls"))
            if msg["tool_calls"]:
                last_tool_name = msg["tool_calls"][0]["function"].get("name")

        if role == "tool":
            tool_name = raw.get("tool_name") or raw.get("name") or last_tool_name
            if tool_name:
                msg["tool_name"] = tool_name

        sanitized.append(msg)

    return sanitized


def _normalize_assistant_message(raw: dict[str, Any]) -> dict[str, Any]:
    message = dict(raw or {})
    message.setdefault("role", "assistant")
    if message.get("tool_calls"):
        message["tool_calls"] = _normalize_tool_calls(message["tool_calls"])
    return message


def call_hosted_ollama(
    messages: list,
    *,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    temperature: float = 0.2,
    stream: bool = False,
) -> dict[str, Any]:
    """Call self-hosted Ollama /api/chat. Returns OpenAI-shaped {\"message\": ...}."""
    payload: dict[str, Any] = {
        "model": model or HOSTED_OLLAMA_MODEL,
        "messages": _sanitize_messages_for_ollama(messages),
        "stream": stream,
        "options": {"temperature": temperature},
    }
    if tools:
        has_tool_history = any(
            isinstance(m, dict) and (
                m.get("role") == "tool"
                or (m.get("role") == "assistant" and m.get("tool_calls"))
            )
            for m in payload["messages"]
        )
        if not has_tool_history:
            payload["tools"] = tools

    url = f"{HOSTED_OLLAMA_BASE_URL}/api/chat"
    last_error = "Unknown hosted Ollama error"
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=_hosted_headers(),
                timeout=_request_timeouts(),
                stream=stream,
            )
        except requests.exceptions.ConnectTimeout as exc:
            last_error = (
                f"Connection to {HOSTED_OLLAMA_BASE_URL} timed out after "
                f"{HOSTED_CONNECT_TIMEOUT_SECONDS:g}s. Check HOSTED_OLLAMA_URL, DNS, "
                f"firewall, and that the Ollama gateway is running."
            )
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(last_error) from exc
        except requests.exceptions.ReadTimeout as exc:
            last_error = (
                f"Hosted Ollama read timed out after {HOSTED_READ_TIMEOUT_SECONDS:g}s. "
                f"The model may be overloaded or tool calls are taking too long."
            )
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(last_error) from exc
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"Cannot reach hosted Ollama API at {url}: {last_error}") from exc

        if resp.status_code >= 400:
            last_error = _error_from_response(resp)
            if resp.status_code in (408, 429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(
                f"Hosted Ollama API error ({resp.status_code}): {last_error}"
            )

        if stream:
            raise RuntimeError("Streaming responses are not used by the agent loop yet.")

        data = _parse_json_response(resp)
        message = data.get("message")
        if not isinstance(message, dict):
            last_error = "Hosted Ollama returned no message."
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(last_error)
        return {"message": _normalize_assistant_message(message)}

    raise RuntimeError(f"Hosted Ollama API error: {last_error}")


def call_capix(
    messages: list,
    *,
    model: str,
    tools: Optional[list] = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    resolved_model = resolve_capix_model(model)
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
    }
    provider = _capix_provider_block()
    if provider:
        payload["provider"] = provider
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_error = "Unknown CapIX error"
    max_attempts = max(CAPIX_MAX_RETRIES, 1)
    call_started = time.time()
    for attempt in range(1, max_attempts + 1):
        attempt_started = time.time()
        try:
            resp = requests.post(
                CAPIX_API_URL,
                json=payload,
                headers=_capix_headers(),
                timeout=_capix_timeouts(),
            )
        except requests.exceptions.ConnectTimeout as exc:
            last_error = (
                f"Connection to CapIX timed out after {CAPIX_CONNECT_TIMEOUT_SECONDS:g}s. "
                "Check CAPIX_API_URL and network."
            )
            if attempt < max_attempts:
                time.sleep(_capix_retry_delay(attempt))
                continue
            raise RuntimeError(last_error) from exc
        except requests.exceptions.ReadTimeout as exc:
            last_error = (
                f"CapIX read timed out after {CAPIX_READ_TIMEOUT_SECONDS:g}s. "
                "The model may be overloaded."
            )
            if attempt < max_attempts:
                time.sleep(_capix_retry_delay(attempt))
                continue
            raise RuntimeError(last_error) from exc
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                time.sleep(_capix_retry_delay(attempt))
                continue
            raise RuntimeError(f"Cannot reach CapIX API at {CAPIX_API_URL}: {last_error}") from exc

        if resp.status_code >= 400:
            last_error = _error_from_response(resp)
            if resp.status_code in (408, 429, 500, 502, 503, 504) and attempt < max_attempts:
                time.sleep(_capix_retry_delay(attempt, resp.status_code))
                continue
            raise RuntimeError(
                f"CapIX API error ({resp.status_code}) for model {resolved_model}: {last_error}"
            )

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            last_error = "CapIX returned no choices."
            if attempt < max_attempts:
                time.sleep(_capix_retry_delay(attempt))
                continue
            raise RuntimeError(last_error)
        message = choices[0].get("message") or {}
        if CAPIX_TIMING_LOG:
            attempt_ms = int((time.time() - attempt_started) * 1000)
            total_ms = int((time.time() - call_started) * 1000)
            print(
                f"  ⏱ CapIX call ok: attempt {attempt}/{max_attempts}, "
                f"attempt_ms={attempt_ms}, total_ms={total_ms}, model={resolved_model}"
            )
        return {"message": _normalize_assistant_message(message)}

    if CAPIX_TIMING_LOG:
        total_ms = int((time.time() - call_started) * 1000)
        print(f"  ⏱ CapIX call FAILED after {max_attempts} attempt(s), total_ms={total_ms}: {last_error}")
    raise RuntimeError(f"CapIX API error for model {resolved_model}: {last_error}")


def call_openrouter(
    messages: list,
    *,
    model: str,
    tools: Optional[list] = None,
    temperature: float = 0.2,
    app_suffix: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_error = "Unknown OpenRouter error"
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                OPEN_ROUTER_API_URL,
                json=payload,
                headers=_openrouter_headers(app_suffix),
                timeout=180,
            )
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"Cannot reach OpenRouter API: {last_error}") from exc

        if resp.status_code >= 400:
            last_error = _error_from_response(resp)
            if resp.status_code in (408, 429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"OpenRouter API error ({resp.status_code}): {last_error}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            last_error = "OpenRouter returned no choices."
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(last_error)
        message = choices[0].get("message") or {}
        return {"message": _normalize_assistant_message(message)}

    raise RuntimeError(f"OpenRouter API error: {last_error}")


def ping_capix() -> dict[str, Any]:
    """Lightweight connectivity check for CapIX."""
    if not use_capix():
        return {"ok": False, "error": "CAPIX_API_KEY is not set"}
    started = time.time()
    payload: dict[str, Any] = {
        "model": CAPIX_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "temperature": 0,
    }
    provider = _capix_provider_block()
    if provider:
        payload["provider"] = provider
    try:
        resp = requests.post(
            CAPIX_API_URL,
            json=payload,
            headers=_capix_headers(),
            timeout=(min(CAPIX_CONNECT_TIMEOUT_SECONDS, 10), min(CAPIX_READ_TIMEOUT_SECONDS, 45)),
        )
    except requests.exceptions.ConnectTimeout:
        return {
            "ok": False,
            "url": CAPIX_API_URL,
            "model": CAPIX_MODEL,
            "latency_ms": int((time.time() - started) * 1000),
            "error": f"Connection timed out after {CAPIX_CONNECT_TIMEOUT_SECONDS:g}s.",
        }
    except requests.exceptions.ReadTimeout:
        return {
            "ok": False,
            "url": CAPIX_API_URL,
            "model": CAPIX_MODEL,
            "latency_ms": int((time.time() - started) * 1000),
            "error": f"Model response timed out after {min(CAPIX_READ_TIMEOUT_SECONDS, 45):g}s.",
        }
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "url": CAPIX_API_URL,
            "model": CAPIX_MODEL,
            "latency_ms": int((time.time() - started) * 1000),
            "error": str(exc),
        }

    latency_ms = int((time.time() - started) * 1000)
    if resp.status_code >= 400:
        return {
            "ok": False,
            "url": CAPIX_API_URL,
            "model": CAPIX_MODEL,
            "latency_ms": latency_ms,
            "status_code": resp.status_code,
            "error": _error_from_response(resp),
        }

    try:
        data = resp.json()
    except ValueError as exc:
        return {
            "ok": False,
            "url": CAPIX_API_URL,
            "model": CAPIX_MODEL,
            "latency_ms": latency_ms,
            "status_code": resp.status_code,
            "error": str(exc),
        }

    choices = data.get("choices") or []
    message = choices[0].get("message") if choices else {}
    content = str((message or {}).get("content") or "").strip()
    return {
        "ok": True,
        "url": CAPIX_API_URL,
        "model": CAPIX_MODEL,
        "latency_ms": latency_ms,
        "sample": content[:120] or None,
        "tool_calls_supported": bool((message or {}).get("tool_calls")),
    }


def ping_hosted_ollama() -> dict[str, Any]:
    """Lightweight connectivity check for /health and local debugging."""
    if not use_hosted_ollama():
        return {"ok": False, "error": "HOSTED_MODEL_API_KEY is not set"}
    url = f"{HOSTED_OLLAMA_BASE_URL}/api/chat"
    started = time.time()
    try:
        resp = requests.post(
            url,
            json={
                "model": HOSTED_OLLAMA_MODEL,
                "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                "stream": False,
                "options": {"temperature": 0},
            },
            headers=_hosted_headers(),
            timeout=(min(HOSTED_CONNECT_TIMEOUT_SECONDS, 10), min(HOSTED_READ_TIMEOUT_SECONDS, 45)),
        )
    except requests.exceptions.ConnectTimeout:
        return {
            "ok": False,
            "url": url,
            "model": HOSTED_OLLAMA_MODEL,
            "latency_ms": int((time.time() - started) * 1000),
            "error": (
                f"Connection timed out after {HOSTED_CONNECT_TIMEOUT_SECONDS:g}s. "
                "Verify HOSTED_OLLAMA_URL and that llm.bitagents.app is reachable."
            ),
        }
    except requests.exceptions.ReadTimeout:
        return {
            "ok": False,
            "url": url,
            "model": HOSTED_OLLAMA_MODEL,
            "latency_ms": int((time.time() - started) * 1000),
            "error": (
                f"Model response timed out after {min(HOSTED_READ_TIMEOUT_SECONDS, 45):g}s."
            ),
        }
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "url": url,
            "model": HOSTED_OLLAMA_MODEL,
            "latency_ms": int((time.time() - started) * 1000),
            "error": str(exc),
        }

    latency_ms = int((time.time() - started) * 1000)
    if resp.status_code >= 400:
        return {
            "ok": False,
            "url": url,
            "model": HOSTED_OLLAMA_MODEL,
            "latency_ms": latency_ms,
            "status_code": resp.status_code,
            "error": _error_from_response(resp),
        }

    try:
        data = _parse_json_response(resp)
    except RuntimeError as exc:
        return {
            "ok": False,
            "url": url,
            "model": HOSTED_OLLAMA_MODEL,
            "latency_ms": latency_ms,
            "status_code": resp.status_code,
            "error": str(exc),
        }

    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    content = str(message.get("content") or "").strip()
    return {
        "ok": True,
        "url": url,
        "model": HOSTED_OLLAMA_MODEL,
        "latency_ms": latency_ms,
        "sample": content[:120] or None,
        "tool_calls_supported": bool(message.get("tool_calls")),
    }


def ping_llm() -> dict[str, Any]:
    """Ping the active LLM provider."""
    if use_capix():
        return ping_capix()
    if use_hosted_ollama():
        return ping_hosted_ollama()
    return {"ok": False, "error": "No LLM provider configured"}


def call_llm(
    messages: list,
    *,
    model: str,
    tools: Optional[list] = None,
    temperature: float = 0.2,
    app_suffix: str = "",
) -> dict[str, Any]:
    """Primary LLM entry: CapIX → hosted Ollama → OpenRouter."""
    if use_capix():
        return call_capix(
            messages,
            model=resolve_capix_model(model),
            tools=tools,
            temperature=temperature,
        )
    if use_hosted_ollama():
        return call_hosted_ollama(
            messages,
            model=model or HOSTED_OLLAMA_MODEL,
            tools=tools,
            temperature=temperature,
        )
    return call_openrouter(
        messages,
        model=model,
        tools=tools,
        temperature=temperature,
        app_suffix=app_suffix,
    )
