# Archived from agents_api.py on 06_11_2026. Not imported by the live API.

from launch_agent import (
    chat_with_launched_agent,
    check_agent_access,
    get_launch_config,
    get_marketplace_launched_agent,
    get_owned_or_accessible_agent,
    get_user_launch_dashboard,
    launch_agent,
    list_marketplace_launched_agents,
    list_user_launched_agents,
    subscribe_to_agent,
    update_user_launched_agent,
    withdraw_creator_agent_earnings,
)


class LaunchAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    task: str = Field(min_length=1, max_length=20000)
    modules: list[str] = Field(min_length=1)
    signature: str = Field(default="", max_length=128)
    visibility: str = Field(default="private", pattern="^(public|private)$")
    price_per_month_sol: Optional[float] = Field(default=None, ge=0, le=1000)


@app.get("/launch/config")
def launch_config(_: None = Depends(require_internal_key)) -> dict[str, Any]:
    return get_launch_config()


@app.get("/launch/dashboard")
def launch_dashboard(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    try:
        return get_user_launch_dashboard(auth_wallet)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dashboard failed: {exc}") from exc


@app.get("/launch/public")
def launch_public_list(
    _: None = Depends(require_internal_key),
    limit: int = Query(100, ge=1, le=200),
) -> dict[str, Any]:
    try:
        return list_marketplace_launched_agents(limit=limit)
    except Exception as exc:
        print(f"  ⚠️  /launch/public failed: {exc}")
        return {"agents": [], "count": 0}


@app.get("/launch/public/{agent_id}")
def launch_public_get(
    agent_id: str,
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    result = get_marketplace_launched_agent(agent_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/launch")
def launch_list(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return list_user_launched_agents(auth_wallet)


class SubscribeAgentRequest(BaseModel):
    signature: str = Field(default="", max_length=128)


class LaunchChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None
    history: Optional[list[dict[str, str]]] = None


@app.get("/launch/{agent_id}")
def launch_get(
    agent_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = get_owned_or_accessible_agent(agent_id, auth_wallet)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.patch("/launch/{agent_id}")
def launch_update(
    agent_id: str,
    body: LaunchAgentRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = update_user_launched_agent(
        user_wallet=auth_wallet,
        agent_id=agent_id,
        name=body.name,
        description=body.description or "",
        task=body.task,
        modules=body.modules,
        visibility=body.visibility,
        price_per_month_sol=body.price_per_month_sol,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/launch/{agent_id}/access")
def launch_access(
    agent_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return check_agent_access(agent_id, auth_wallet)


@app.post("/launch/{agent_id}/chat")
def launch_chat(
    agent_id: str,
    body: LaunchChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = chat_with_launched_agent(
        user_wallet=auth_wallet,
        agent_id=agent_id,
        message=body.message,
        history=body.history,
        session_id=body.session_id,
    )
    if result.get("error"):
        status = 403 if result.get("status") in ("payment_required", "private") else 400
        raise HTTPException(status_code=status, detail=result["error"])
    return result


@app.post("/launch/{agent_id}/subscribe")
def launch_subscribe(
    agent_id: str,
    body: SubscribeAgentRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = subscribe_to_agent(
        buyer_wallet=auth_wallet,
        agent_id=agent_id,
        signature=body.signature or "",
    )
    if result.get("error"):
        status = 403 if result.get("status") == "rejected" else 400
        raise HTTPException(status_code=status, detail=result["error"])
    return result


class WithdrawCreatorEarningsRequest(BaseModel):
    amount_sol: Optional[float] = None
    destination_wallet: Optional[str] = None


@app.post("/launch/{agent_id}/withdraw-earnings")
def launch_withdraw_earnings(
    agent_id: str,
    body: WithdrawCreatorEarningsRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = withdraw_creator_agent_earnings(
        user_wallet=auth_wallet,
        agent_id=agent_id,
        amount_sol=body.amount_sol,
        destination_wallet=body.destination_wallet,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/launch")
def launch_create(
    body: LaunchAgentRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    try:
        result = launch_agent(
            user_wallet=auth_wallet,
            name=body.name,
            description=body.description or "",
            task=body.task,
            modules=body.modules,
            signature=body.signature or "",
            visibility=body.visibility,
            price_per_month_sol=body.price_per_month_sol,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Launch failed: {exc}") from exc
    if result.get("error"):
        status = 403 if result.get("status") == "rejected" else 400
        raise HTTPException(status_code=status, detail=result["error"])
    return result
