"""HTTP routes for the agent builder. Mounted by agents_api.py under /builder."""

from __future__ import annotations

import hmac
import os
import re
from dataclasses import asdict
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import aomi_bridge, compiler, market, paper, store, strategies
from .contract import Context, Holding
from .spec import AgentSpec, Unsupported, compose_spec

ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


class CreateBody(BaseModel):
    prompt: str = Field(min_length=20, max_length=2000)


class EvaluateBody(BaseModel):
    wallet: str
    build: bool = False


class ModeBody(BaseModel):
    mode: Literal["paper", "live"]


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = None


def _public(a: dict[str, Any]) -> dict[str, Any]:
    return {k: a[k] for k in ("id", "owner_wallet", "prompt", "spec", "spec_sha", "compose_meta",
                              "app_name", "mode", "build_status", "build", "created_at", "updated_at")}


def _agent(agent_id: str) -> dict[str, Any]:
    a = store.get_agent(agent_id)
    if not a:
        raise HTTPException(404, "No such strategy.")
    return a


def _paper_holdings(book: dict[str, Any]) -> list[Holding]:
    return [Holding(mint=m, symbol=p["symbol"], amount=p["raw"] / 10 ** p["decimals"], decimals=p["decimals"])
            for m, p in book["positions"].items() if p["raw"] > 0]


def evaluate(agent: dict[str, Any], wallet: str, build: bool, caller: str) -> dict[str, Any]:
    """Run the strategy for `wallet`.

    With build=True each order carries a real Jupiter swap for that wallet. A live agent returns
    it as unsigned instructions for Aomi to stage and sign. A paper agent simulates it on mainnet
    and books the simulated fill against its paper balance; nothing is staged or sent.
    """
    if not ADDRESS.match(wallet):
        raise HTTPException(400, "wallet is not a Solana address.")
    spec = AgentSpec.model_validate(agent["spec"])
    tpl = strategies.get(spec.strategy.template)
    limits = spec.limits.model_dump()
    paper_mode = agent["mode"] != "live"
    usdc = market.USDC
    if paper_mode:
        book = store.paper_book(agent["id"], wallet)
        held, sol, cash = _paper_holdings(book), None, book["cash_usd"]
    else:
        held, sol = market.holdings(wallet)
        cash = next((h.amount for h in held if h.mint == usdc["mint"]), 0.0)
    market.price_holdings(held)
    ctx = Context(wallet=wallet, holdings=held, cash_usd=cash,
                  spent_today_usd=store.spent_today_usd(agent["id"], wallet, agent["mode"]))
    decision = tpl.evaluate(ctx, tpl.Params.model_validate(spec.strategy.params), limits)
    orders: list[dict[str, Any]] = []
    for i, o in enumerate(decision.orders):
        row: dict[str, Any] = {"index": i, **asdict(o)}
        if build:
            try:
                if o.side == "buy":
                    in_mint, out_mint, raw_in = usdc["mint"], o.mint, int(round(o.usd * 10 ** usdc["decimals"]))
                else:
                    pos = next(h for h in held if h.mint == o.mint)
                    in_mint, out_mint, raw_in = o.mint, usdc["mint"], int(round(pos.amount * 10 ** pos.decimals))
                swap = market.build_swap(payer=wallet, input_mint=in_mint, output_mint=out_mint,
                                         raw_amount=raw_in, slippage_bps=spec.limits.slippage_bps)
                row["quote"] = {k: swap[k] for k in ("in_amount", "out_amount", "other_amount_threshold",
                                                     "price_impact_pct", "slippage_bps", "tx_bytes")}
                if paper_mode:
                    sim = paper.simulate_swap(wallet=wallet, swap=swap, input_mint=in_mint, output_mint=out_mint, raw_in=raw_in)
                    row["simulation"] = sim
                    if sim["ok"] and caller == "app":
                        token = market.resolve_xstock(o.symbol)
                        pos = book["positions"].setdefault(o.mint, {"symbol": o.token_symbol, "raw": 0, "decimals": token["decimals"]})
                        if o.side == "buy":
                            book["cash_usd"] -= sim["in_spent_raw"] / 10 ** usdc["decimals"]
                            pos["raw"] += sim["out_received_raw"]
                            tokens, usd = sim["out_received_raw"] / 10 ** pos["decimals"], sim["in_spent_raw"] / 10 ** usdc["decimals"]
                        else:
                            book["cash_usd"] += sim["out_received_raw"] / 10 ** usdc["decimals"]
                            pos["raw"] -= sim["in_spent_raw"]
                            tokens, usd = sim["in_spent_raw"] / 10 ** pos["decimals"], sim["out_received_raw"] / 10 ** usdc["decimals"]
                        row["paper_fill"] = {"tokens": tokens, "usd": usd, "price_usd": usd / tokens if tokens else None}
                        store.save_paper_book(agent["id"], wallet, book)
                else:
                    row["stage"] = {
                        "instructions": swap["instructions"],
                        "address_lookup_tables": swap["address_lookup_tables"],
                        "description": f"{spec.name}: {o.side} ${o.usd:g} of {o.token_symbol} ({o.reason})",
                        "kind": "swap",
                    }
                    row["unsigned_tx_base64"] = swap["unsigned_tx_base64"]
            except Exception as exc:
                row["build_error"] = str(exc)
        orders.append(row)
    out = {
        "agent_id": agent["id"], "agent": spec.name, "strategy": spec.strategy.template, "mode": agent["mode"],
        "wallet": {"address": wallet, "sol": sol, "cash_usd": cash, "quote": spec.limits.quote,
                   "holdings": [asdict(h) for h in held], "spent_today_usd": ctx.spent_today_usd},
        "limits": limits, "signals": decision.signals, "notes": decision.notes, "orders": orders,
    }
    if paper_mode:
        after = store.paper_book(agent["id"], wallet)
        now = _paper_holdings(after)
        market.price_holdings(now)
        out["paper"] = {"start_usd": after["start_usd"], "cash_usd": after["cash_usd"], "holdings": [asdict(h) for h in now],
                        "equity_usd": after["cash_usd"] + sum(h.value_usd or 0 for h in now)}
        out["wallet"]["note"] = "Paper mode: these balances are the strategy's paper book, not on-chain funds."
        if build:
            out["next"] = ("PAPER MODE. Each order's real Jupiter swap was already simulated on Solana mainnet and booked to the "
                           "paper balance; see `simulation` and `paper_fill`. Report the signals, fills and paper balance. "
                           "Say plainly that this was a simulation and no transaction was sent. Do not call svm_stage_ix, "
                           "svm_simulate or svm_commit_txs.")
    elif build:
        out["next"] = ("For each order, in order: call svm_stage_ix with exactly that order's `stage` object, then svm_simulate "
                       "for the staged ids, then svm_commit_txs. Copy the instructions verbatim. Never change an account, amount "
                       "or program." if orders else
                       "No orders this run. Report the signals and notes to the user. Do not stage anything.")
    out["run_id"] = store.add_run(agent["id"], wallet, caller, build,
                                  {"mode": agent["mode"], "signals": decision.signals, "notes": decision.notes,
                                   "wallet": out["wallet"], "paper": out.get("paper")},
                                  [{k: v for k, v in o.items() if k != "unsigned_tx_base64"} for o in orders], None)
    return out


def make_router(require_wallet_session, require_internal_key) -> APIRouter:
    r = APIRouter(prefix="/builder", tags=["agent builder"])

    def require_app_key(x_app_key: Optional[str] = Header(default=None)) -> None:
        # Enforced only when BUILDER_APP_KEY is set. Unset, the evaluate route is open:
        # it returns unsigned swaps and paper fills, and cannot move funds.
        want = os.environ.get("BUILDER_APP_KEY", "")
        if want and (not x_app_key or not hmac.compare_digest(want, x_app_key)):
            raise HTTPException(403, "Invalid app key.")

    @r.get("/templates", dependencies=[Depends(require_internal_key)])
    def templates() -> dict[str, Any]:
        return {"templates": [{"name": s.name, "title": s.title, "summary": s.summary,
                               "params_schema": s.Params.model_json_schema()} for s in strategies.REGISTRY.values()]}

    @r.post("/agents")
    def create(body: CreateBody, wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        try:
            spec, meta = compose_spec(body.prompt)
        except Unsupported as exc:
            raise HTTPException(422, f"Not supported yet: {exc}")
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except RuntimeError as exc:
            raise HTTPException(502, str(exc))
        return _public(store.create_agent(wallet, body.prompt, spec.model_dump(), spec.sha(), meta))

    @r.get("/agents")
    def mine(wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        return {"agents": [_public(a) for a in store.list_agents(wallet)]}

    @r.get("/agents/{agent_id}", dependencies=[Depends(require_internal_key)])
    def get(agent_id: str) -> dict[str, Any]:
        return _public(_agent(agent_id))

    @r.post("/agents/{agent_id}/compile")
    def compile_(agent_id: str, wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        a = _agent(agent_id)
        if a["owner_wallet"] != wallet:
            raise HTTPException(403, "Only the creator can compile this agent.")
        if a["build_status"] == "building":
            raise HTTPException(409, "A build is already running.")
        compiler.start(agent_id)
        return _public(_agent(agent_id))

    @r.post("/agents/{agent_id}/mode")
    def mode(agent_id: str, body: ModeBody, wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        """paper: runs are simulated on mainnet against a paper balance. live: runs are staged for the agent wallet to sign."""
        if _agent(agent_id)["owner_wallet"] != wallet:
            raise HTTPException(403, "Only the creator can change the mode.")
        store.set_mode(agent_id, body.mode)
        return _public(_agent(agent_id))

    @r.get("/agents/{agent_id}/source", dependencies=[Depends(require_internal_key)])
    def source(agent_id: str) -> dict[str, Any]:
        a = _agent(agent_id)
        crate = (a["build"] or {}).get("crate_dir")
        if not crate or not os.path.isdir(crate):
            raise HTTPException(404, "This agent has not been compiled yet.")
        files = {}
        for rel in ("aomi.toml", "Cargo.toml", "src/lib.rs", "src/tool.rs", "src/skill/strategy.md", ".aomi/config.json"):
            with open(os.path.join(crate, rel)) as fh:
                files[rel] = fh.read()
        return {"files": files}

    @r.get("/agents/{agent_id}/runs", dependencies=[Depends(require_internal_key)])
    def runs(agent_id: str) -> dict[str, Any]:
        _agent(agent_id)
        return {"runs": store.list_runs(agent_id)}

    @r.get("/agents/{agent_id}/performance", dependencies=[Depends(require_internal_key)])
    def performance(agent_id: str) -> dict[str, Any]:
        """Paper balances of every wallet that has run this agent, valued at current prices."""
        _agent(agent_id)
        rows = []
        for book in store.paper_books(agent_id):
            held = _paper_holdings(book)
            market.price_holdings(held)
            equity = book["cash_usd"] + sum(h.value_usd or 0 for h in held)
            rows.append({"wallet": book["wallet"], "start_usd": book["start_usd"], "cash_usd": book["cash_usd"],
                         "equity_usd": equity, "pnl_usd": equity - book["start_usd"],
                         "holdings": [asdict(h) for h in held], "updated_at": book["updated_at"],
                         "priced": all(h.value_usd is not None for h in held)})
        return {"books": rows}

    @r.post("/agents/{agent_id}/preview")
    def preview(agent_id: str, body: EvaluateBody, _: str = Depends(require_wallet_session)) -> dict[str, Any]:
        """What the strategy would do for a wallet right now. Never builds a transaction."""
        return evaluate(_agent(agent_id), body.wallet, False, "preview")

    @r.post("/agents/{agent_id}/execute")
    def execute_(agent_id: str, wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        """Live mainnet run: Jupiter build → Aomi stage/simulate/commit → Circle sign → broadcast."""
        from .execute import execute_live

        a = _agent(agent_id)
        if a["owner_wallet"] != wallet:
            raise HTTPException(403, "Only the creator can execute this strategy on-chain.")
        return execute_live(a, wallet)

    @r.post("/agents/{agent_id}/evaluate", dependencies=[Depends(require_app_key)])
    def evaluate_(agent_id: str, body: EvaluateBody) -> dict[str, Any]:
        """Called by the agent's Aomi app. Returns the decision and unsigned swap instructions."""
        a = _agent(agent_id)
        if a["build_status"] != "ready":
            raise HTTPException(409, "This strategy is not deployed.")
        return evaluate(a, body.wallet, body.build, "app")

    def _with_balances(st: dict[str, Any], agent: dict[str, Any]) -> dict[str, Any]:
        st["mode"] = agent["mode"]
        if st.get("wallet"):
            held, sol = market.holdings(st["wallet"]["address"])
            st["wallet"]["sol"] = sol
            st["wallet"]["cash_usd"] = next((h.amount for h in held if h.mint == market.USDC["mint"]), 0.0)
            if agent["mode"] != "live":
                book = store.paper_book(agent["id"], st["wallet"]["address"])
                now = _paper_holdings(book)
                market.price_holdings(now)
                st["paper"] = {"start_usd": book["start_usd"], "cash_usd": book["cash_usd"], "holdings": [asdict(h) for h in now],
                               "equity_usd": book["cash_usd"] + sum(h.value_usd or 0 for h in now)}
        return st

    def _hosted(agent: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Set when agents run on a hosted Aomi through the shared app, not a local backend."""
        app = os.environ.get("AOMI_HOSTED_APP", "").strip()
        if not app:
            return None
        chat = os.environ.get("AOMI_HOSTED_CHAT_URL", "https://staging.aomi.chat").rstrip("/")
        return {"app": app, "chat_url": f"{chat}?app={app}&lock_app=1", "prompt": f"Run strategy {agent['id']}",
                "schedule_prompt": f"Run strategy {agent['id']} every {agent['spec']['strategy']['schedule_minutes']} minutes"}

    def _circle_builder_wallet(user_wallet: str) -> Optional[dict[str, Any]]:
        """Circle custody wallet used for BIT Agents live execute (Aomi gate, then Circle sign)."""
        try:
            from circle_dca_wallets import circle_dca_enabled, resolve_agent_signing_context
            from dca_agent import _is_mainnet
            from solana_rpc import sol_rpc

            if not circle_dca_enabled():
                return None
            signing = resolve_agent_signing_context(user_wallet, "builder")
            pubkey = signing.get("pubkey")
            if not pubkey:
                return None
            sol = None
            try:
                sol = int(sol_rpc("getBalance", [pubkey]).get("value") or 0) / 1_000_000_000
            except Exception:
                sol = None
            cash = 0.0
            try:
                held, _ = market.holdings(pubkey)
                cash = next((h.amount for h in held if h.mint == market.USDC["mint"]), 0.0)
            except Exception:
                pass
            return {
                "address": pubkey,
                "sol": sol,
                "cash_usd": cash,
                "cluster": "mainnet" if _is_mainnet() else "devnet",
                "execution": "jupiter → aomi gate → circle sign",
            }
        except Exception:
            return None

    def _local_only(agent: dict[str, Any]) -> None:
        if _hosted(agent):
            raise HTTPException(409, "This strategy runs on Aomi. Open it there to create a wallet and chat.")

    @r.get("/agents/{agent_id}/aomi")
    def aomi_state(agent_id: str, wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        a = _agent(agent_id)
        hosted = _hosted(a)
        circle = _circle_builder_wallet(wallet)
        if hosted:
            return {
                "connected": a["build_status"] == "ready",
                "app": hosted["app"],
                "mode": a["mode"],
                "hosted": hosted,
                "wallet": circle,
                "live_execute": bool(circle) and a["mode"] == "live" and a["build_status"] == "ready",
                "reason": None if a["build_status"] == "ready" else "Deploy the strategy first.",
            }
        st = _with_balances(aomi_bridge.state(wallet, a["app_name"]), a)
        if circle and not st.get("wallet"):
            st["wallet"] = circle
        st["live_execute"] = a["mode"] == "live" and a["build_status"] == "ready"
        return st

    @r.post("/agents/{agent_id}/aomi/wallet")
    def aomi_wallet(agent_id: str, wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        a = _agent(agent_id)
        _local_only(a)
        return _with_balances(aomi_bridge.create_wallet(wallet, a["app_name"]), a)

    @r.post("/agents/{agent_id}/chat")
    def chat(agent_id: str, body: ChatBody, wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
        a = _agent(agent_id)
        _local_only(a)
        return aomi_bridge.chat(wallet, a["app_name"], body.message, body.session_id)

    return r
