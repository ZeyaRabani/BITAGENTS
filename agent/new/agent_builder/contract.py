"""The contract every strategy implements.

A strategy never signs and never sends. It reads market data and the wallet's
holdings, and returns orders. `market.build_swap` turns each order into unsigned
Jupiter instructions whose payer is the user's Aomi agent wallet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel


@dataclass
class Holding:
    mint: str
    symbol: str
    amount: float
    decimals: int
    value_usd: float | None = None


@dataclass
class Context:
    wallet: str                      # Aomi agent wallet (SVM address) that will pay and sign
    holdings: list[Holding]
    cash_usd: float                  # balance of the quote token, in USD
    spent_today_usd: float           # sum of today's committed buys for this agent+wallet


@dataclass
class Order:
    side: Literal["buy", "sell"]
    symbol: str                      # underlying, e.g. NVDA
    token_symbol: str                # on-chain token, e.g. NVDAx
    mint: str
    usd: float                       # notional in USD
    reason: str


@dataclass
class Decision:
    orders: list[Order]
    signals: list[dict[str, Any]]    # one row per symbol: what the strategy saw and why
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Strategy(Protocol):
    name: str                        # "signal_basket@1"
    title: str
    summary: str                     # shown to the LLM in the compose pass
    Params: type[BaseModel]

    def evaluate(self, ctx: Context, params: BaseModel, limits: dict[str, Any]) -> Decision: ...
