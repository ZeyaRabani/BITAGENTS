"""Uniform, authenticated strategy service consumed by Aomi app skills.

Adapters own strategy-specific behavior. HTTP handlers own no financial logic.
Adding a strategy means implementing this adapter interface, not another chat loop.
"""

from typing import Any, Callable, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @classmethod
    def parse_configuration(cls, values: dict) -> dict:
        try:
            return cls.model_validate(values).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_context=False, include_input=False)) from exc


class DcaConfiguration(Parameters):
    input_token: str = Field(min_length=1, max_length=64)
    output_token: str = Field(min_length=1, max_length=64)
    amount_per_buy: float = Field(gt=0)
    interval: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    total_budget: float = Field(gt=0)
    max_executions: int = Field(ge=1)
    slippage_bps: int = Field(default=100, ge=1, le=5000)


class DcaUpdate(Parameters):
    amount_per_buy: float | None = Field(default=None, gt=0)
    interval: str | None = Field(default=None, min_length=1, max_length=64)
    total_budget: float | None = Field(default=None, gt=0)
    max_executions: int | None = Field(default=None, ge=1)
    slippage_bps: int | None = Field(default=None, ge=1, le=5000)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("Provide at least one configuration change")
        return self


class ScheduleRequest(Parameters):
    configuration: dict[str, Any]


class StatusRequest(Parameters):
    action: Literal["pause", "resume", "cancel"]


class RunRequest(Parameters):
    plan_id: str = Field(min_length=1, max_length=128)
    # Live runs are scheduled, not replayable POSTs that force another buy.
    mode: Literal["preview"] = "preview"


class Strategy(Protocol):
    def describe(self) -> dict: ...
    def schedule(self, wallet: str, configuration: dict) -> dict: ...
    def list(self, wallet: str) -> dict: ...
    def get(self, wallet: str, plan_id: str) -> dict: ...
    def update(self, wallet: str, plan_id: str, configuration: dict) -> dict: ...
    def status(self, wallet: str, plan_id: str, action: str) -> dict: ...
    def history(self, wallet: str, plan_id: str) -> dict: ...
    def run(self, wallet: str, plan_id: str) -> dict: ...


class DcaStrategy:
    def __init__(self, service):
        self.service = service

    def describe(self) -> dict:
        return {
            "id": "dca", "name": "Recurring token buy", "chain": "solana",
            "description": "Buy a fixed token amount at a fixed interval.",
            "configuration_schema": DcaConfiguration.model_json_schema(),
            "update_schema": DcaUpdate.model_json_schema(),
            "run_modes": ["preview"], "execution": "bitagents_scheduler",
            "signing": "bitagents_agent_wallet", "platform_fee_bps": 50,
            "unsupported": ["price_trigger", "stop_loss", "take_profit", "equity_shorts"],
        }

    @staticmethod
    def checked(result: dict) -> dict:
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    def schedule(self, wallet: str, configuration: dict) -> dict:
        values = DcaConfiguration.parse_configuration(configuration)
        return self.checked(self.service.create_dca_plan(
            **values, user_wallet=wallet, start_immediately=False,
        ))

    def list(self, wallet: str) -> dict:
        return self.checked(self.service.list_dca_plans(user_wallet=wallet))

    def get(self, wallet: str, plan_id: str) -> dict:
        return self.checked(self.service.get_dca_plan(plan_id, user_wallet=wallet))

    def update(self, wallet: str, plan_id: str, configuration: dict) -> dict:
        values = DcaUpdate.parse_configuration(configuration)
        return self.checked(self.service.update_dca_plan(plan_id, wallet, **values))

    def status(self, wallet: str, plan_id: str, action: str) -> dict:
        plan = self.get(wallet, plan_id)
        if action == "resume" and plan.get("status") not in ("active", "paused"):
            raise HTTPException(status_code=409, detail="Only active or paused strategies can resume")
        return self.checked(self.service.update_dca_plan_status(plan_id, action, user_wallet=wallet))

    def history(self, wallet: str, plan_id: str) -> dict:
        return self.checked(self.service.get_dca_history(plan_id, user_wallet=wallet))

    def run(self, wallet: str, plan_id: str) -> dict:
        # _run_plan_execution(dry_run=True) can mutate exhausted plans. Quote
        # directly after ownership validation so previews have no writes.
        plan = self.get(wallet, plan_id)
        return self.checked(self.service.execute_swap_buy(
            plan["input_token"], plan["output_token"], plan["amount_per_buy"],
            plan.get("slippage_bps", 100), dry_run=True, user_wallet=wallet,
        ))


def create_strategy_router(require_wallet: Callable, strategies: dict[str, Strategy]) -> APIRouter:
    router = APIRouter(prefix="/strategies", tags=["Strategy service"])

    def resolve(strategy: str) -> Strategy:
        if strategy not in strategies:
            raise HTTPException(status_code=404, detail="Unknown strategy")
        return strategies[strategy]

    @router.get("")
    def catalog(wallet: str = Depends(require_wallet)) -> dict:
        return {"strategies": [adapter.describe() for adapter in strategies.values()]}

    @router.get("/{strategy}/plans")
    def plans(strategy: str, wallet: str = Depends(require_wallet)) -> dict:
        return resolve(strategy).list(wallet)

    @router.post("/{strategy}/plans")
    def schedule(strategy: str, body: ScheduleRequest, wallet: str = Depends(require_wallet)) -> dict:
        return resolve(strategy).schedule(wallet, body.configuration)

    @router.get("/{strategy}/plans/{plan_id}")
    def get(strategy: str, plan_id: str, wallet: str = Depends(require_wallet)) -> dict:
        return resolve(strategy).get(wallet, plan_id)

    @router.patch("/{strategy}/plans/{plan_id}")
    def update(strategy: str, plan_id: str, body: ScheduleRequest, wallet: str = Depends(require_wallet)) -> dict:
        return resolve(strategy).update(wallet, plan_id, body.configuration)

    @router.post("/{strategy}/plans/{plan_id}/status")
    def status(strategy: str, plan_id: str, body: StatusRequest, wallet: str = Depends(require_wallet)) -> dict:
        return resolve(strategy).status(wallet, plan_id, body.action)

    @router.get("/{strategy}/plans/{plan_id}/executions")
    def history(strategy: str, plan_id: str, wallet: str = Depends(require_wallet)) -> dict:
        return resolve(strategy).history(wallet, plan_id)

    @router.post("/{strategy}/run")
    def run(strategy: str, body: RunRequest, wallet: str = Depends(require_wallet)) -> dict:
        return resolve(strategy).run(wallet, body.plan_id)

    return router
