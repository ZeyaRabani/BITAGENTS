"""
Quick LLM connectivity check (CapIX, hosted Ollama, or OpenRouter).

Usage:
  cd agent/new
  python test_hosted_llm.py
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from hosted_llm import (
    CAPIX_API_URL,
    CAPIX_MODEL,
    HOSTED_OLLAMA_BASE_URL,
    HOSTED_OLLAMA_MODEL,
    llm_configured,
    llm_provider,
    ping_llm,
    use_capix,
    use_hosted_ollama,
)


def main() -> None:
    print(f"provider: {llm_provider()}")
    if use_capix():
        print(f"url:      {CAPIX_API_URL}")
        print(f"model:    {CAPIX_MODEL}")
    elif use_hosted_ollama():
        print(f"url:      {HOSTED_OLLAMA_BASE_URL}")
        print(f"model:    {HOSTED_OLLAMA_MODEL}")
    print(f"configured: {llm_configured()}")
    print()
    result = ping_llm()
    print(json.dumps(result, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
