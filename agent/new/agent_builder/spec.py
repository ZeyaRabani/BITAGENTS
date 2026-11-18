"""The agent spec, and the one LLM pass that writes it from a plain-language brief.

The LLM fills a form: which strategy template, its parameters, the schedule, the
limits, and how the Aomi app should talk. Pydantic checks every field against the
template's own schema. A spec that fails validation is sent back once with the
errors; if it fails again the request fails. There is no canned fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import requests
from pydantic import BaseModel, Field, ValidationError, model_validator

from . import strategies

MODEL = os.environ.get("BUILDER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENROUTER_URL = os.environ.get("OPEN_ROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")


class StrategySpec(BaseModel):
    template: str
    params: dict[str, Any]
    schedule_minutes: int = Field(ge=5, le=10_080, description="How often the strategy runs")

    @model_validator(mode="after")
    def _check_params(self) -> "StrategySpec":
        tpl = strategies.get(self.template)
        self.params = tpl.Params.model_validate(self.params).model_dump()
        return self


class AppSpec(BaseModel):
    brief: str = Field(min_length=40, max_length=1200, description="System preamble for the Aomi app, second person")
    skill: str = Field(min_length=80, max_length=4000, description="Markdown instructions for the strategy skill")


class Limits(BaseModel):
    quote: str = Field(default="USDC", pattern="^USDC$")
    max_trade_usd: float = Field(gt=0, le=10_000)
    max_daily_usd: float = Field(gt=0, le=50_000)
    slippage_bps: int = Field(default=100, ge=10, le=500)

    @model_validator(mode="after")
    def _daily_covers_trade(self) -> "Limits":
        if self.max_daily_usd < self.max_trade_usd:
            raise ValueError("max_daily_usd must be at least max_trade_usd")
        return self


class AgentSpec(BaseModel):
    name: str = Field(min_length=3, max_length=40)
    description: str = Field(min_length=10, max_length=240)
    strategy: StrategySpec
    app: AppSpec
    limits: Limits

    def sha(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:12]


def _system_prompt() -> str:
    templates = [
        {"template": s.name, "title": s.title, "what_it_does": s.summary, "params_schema": s.Params.model_json_schema()}
        for s in strategies.REGISTRY.values()
    ]
    return (
        "You configure trading agents for BITAGENTS, a Solana agent marketplace. "
        "The user describes the agent they want. Return ONE JSON object matching this schema and nothing else:\n"
        f"{json.dumps(AgentSpec.model_json_schema())}\n\n"
        "strategy.template must be one of these templates, and strategy.params must satisfy its params_schema:\n"
        f"{json.dumps(templates)}\n\n"
        "Rules:\n"
        "- Use only what the user said. Where they gave no number, choose a cautious one: "
        "per_symbol_usd 5, max_trade_usd 5, max_daily_usd 20, schedule_minutes 60.\n"
        "- limits.max_trade_usd must be >= strategy.params.per_symbol_usd.\n"
        "- Pick the template that matches the rule the user describes. 'Mag7' or 'Magnificent Seven' means the symbols "
        "AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA. limits.max_daily_usd must cover one full basket purchase.\n"
        "- app.brief is the agent's system preamble, in second person ('You are ...'). State what it trades, "
        "its limits, that it only acts through its run and status tools, and that it never invents prices or signals.\n"
        "- app.skill is markdown: when to call status, when to call run, how to report signals and orders, "
        "and that swap instructions returned by run are staged verbatim.\n"
        "- If the request cannot be done with the templates (other chains, leverage, perps, tokens that are "
        "not tokenized stocks), return {\"error\": \"<one sentence saying what is unsupported>\"}."
    )


def _call_llm(messages: list[dict[str, str]]) -> str:
    openrouter = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    capix = os.environ.get("CAPIX_API_KEY", "").strip()
    if openrouter:
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {openrouter}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=90,
        )
        if not resp.ok:
            raise RuntimeError(f"LLM request failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]
    if capix:
        url = os.environ.get(
            "CAPIX_API_URL",
            "https://www.capix.network/api/v1/chat/completions",
        )
        model = os.environ.get("CAPIX_MODEL") or os.environ.get("BUILDER_MODEL") or MODEL
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {capix}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.1},
            timeout=90,
        )
        if not resp.ok:
            raise RuntimeError(f"CapIX request failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError(
        "Set OPEN_ROUTER_API or CAPIX_API_KEY; the builder cannot compose a spec."
    )


class Unsupported(ValueError):
    pass


def compose_spec(prompt: str) -> tuple[AgentSpec, dict[str, Any]]:
    """One LLM pass (plus at most one repair pass). Returns the spec and how it was made."""
    messages = [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": prompt}]
    errors: list[str] = []
    for attempt in (1, 2):
        raw = _call_llm(messages)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            err = f"not valid JSON: {exc}"
        else:
            if isinstance(data, dict) and set(data) == {"error"}:
                raise Unsupported(str(data["error"]))
            try:
                spec = AgentSpec.model_validate(data)
                if spec.limits.max_trade_usd < float(spec.strategy.params.get("per_symbol_usd", 0)):
                    raise ValueError("limits.max_trade_usd is below strategy.params.per_symbol_usd")
                return spec, {"model": MODEL, "llm_passes": attempt, "repaired_errors": errors}
            except (ValidationError, ValueError, KeyError) as exc:
                err = str(exc)
        errors.append(err)
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": f"That spec was rejected:\n{err}\nReturn the corrected JSON object only."}]
    raise ValueError(f"The model could not produce a valid spec: {errors[-1]}")
