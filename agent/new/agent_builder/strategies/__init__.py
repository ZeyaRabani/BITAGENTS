from __future__ import annotations

from ..contract import Strategy
from .signal_basket import SignalBasket
from .trigger_basket import TriggerBasket

REGISTRY: dict[str, Strategy] = {s.name: s for s in (SignalBasket(), TriggerBasket())}


def get(name: str) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"unknown strategy template {name!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[name]
