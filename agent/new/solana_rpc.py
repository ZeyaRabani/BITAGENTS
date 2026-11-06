"""Solana JSON-RPC helpers used by the Aomi test agent."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

SOLANA_RPC = os.environ.get(
    "SOLANA_RPC_URL",
    os.environ.get("NEXT_PUBLIC_SOLANA_RPC_URL", "https://api.devnet.solana.com"),
)
SOLANA_CLUSTER = os.environ.get(
    "SOLANA_CLUSTER",
    os.environ.get("NEXT_PUBLIC_SOLANA_CLUSTER", "devnet"),
)
_HEADERS = {"User-Agent": "BITAgents/1.0", "Content-Type": "application/json"}


def is_mainnet() -> bool:
    cluster = SOLANA_CLUSTER.lower()
    if cluster in ("mainnet", "mainnet-beta"):
        return True
    return "mainnet" in SOLANA_RPC.lower() and "devnet" not in SOLANA_RPC.lower()


def sol_rpc(method: str, params: list, timeout: int = 30) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    response = requests.post(SOLANA_RPC, json=payload, headers=_HEADERS, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data.get("result")


def confirm_transaction(
    sig: str,
    timeout_s: int = 90,
    poll_s: float = 1.5,
    *,
    encoded_tx: Optional[str] = None,
) -> dict:
    deadline = time.time() + timeout_s
    polls = 0
    while time.time() < deadline:
        time.sleep(poll_s)
        polls += 1
        if encoded_tx and polls % 2 == 0:
            try:
                sol_rpc(
                    "sendTransaction",
                    [
                        encoded_tx,
                        {
                            "encoding": "base64",
                            "skipPreflight": True,
                            "preflightCommitment": "processed",
                            "maxRetries": 0,
                        },
                    ],
                )
            except Exception:
                pass
        try:
            search_history = polls >= 4 or (deadline - time.time()) < 20
            result = sol_rpc(
                "getSignatureStatuses",
                [[sig], {"searchTransactionHistory": search_history}],
            )
            info = result["value"][0] if result and result.get("value") else None
            if info:
                if info.get("err"):
                    return {"confirmed": False, "error": info["err"]}
                status = info.get("confirmationStatus", "")
                if status in ("confirmed", "finalized"):
                    return {"confirmed": True}
        except Exception:
            pass

    try:
        result = sol_rpc(
            "getSignatureStatuses",
            [[sig], {"searchTransactionHistory": True}],
        )
        info = result["value"][0] if result and result.get("value") else None
        if info:
            if info.get("err"):
                return {"confirmed": False, "error": info["err"]}
            if info.get("confirmationStatus") in ("processed", "confirmed", "finalized"):
                return {"confirmed": True}
    except Exception:
        pass
    try:
        tx = sol_rpc(
            "getTransaction",
            [sig, {"encoding": "base64", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}],
        )
        if tx:
            meta_err = (tx.get("meta") or {}).get("err")
            if meta_err:
                return {"confirmed": False, "error": meta_err}
            return {"confirmed": True}
    except Exception:
        pass

    return {
        "confirmed": False,
        "error": f"Confirmation timed out after {timeout_s}s",
        "retryable": True,
    }
