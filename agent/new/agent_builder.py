"""
Conversational agent-builder — the "meta-agent" behind /launch/create.

Users describe the agent they want in plain English; this agent asks natural
follow-up questions and progressively fills in a draft `custom_agents` row via
tool calls, writing the resulting agent's system prompt itself rather than
asking the user to write one. It proposes the finished draft and only calls
finalize_and_launch() after the user explicitly confirms — same
propose-then-confirm pattern already used by the Hedge Fund agent's strategy
proposals.

No trading/wallet tools live here — this agent only edits its own draft row.
"""

from __future__ import annotations

from typing import Any, Optional

import db
from agent_tool_runner import run_tool_agent
from agent_tool_catalog import catalog_summary_for_builder, valid_tool_names
from btc_price_alert import fetch_btc_price_usd
from product_price_watch import fetch_product_price
from digest_watch import fetch_topic_headlines
from hosted_llm import call_openrouter
from notifications import VALID_CHANNELS, send_notification
from telegram_linking import build_deep_link

# Routed directly through OpenRouter (bypassing the shared CapIX-first
# call_llm router) because the platform-locked CapIX model doesn't reliably
# call the tools that actually persist a launched agent -- see
# MARKETPLACE_TESTING_STATUS.md. Scoped to this one agent only; every other
# agent still uses CapIX exactly as before.
BUILDER_MODEL = "openai/gpt-4o-mini"

CATEGORIES = ("Trading", "Research", "Monitoring", "Utility")
TOOL_SCOPES = ("read_only", "trading")

def _build_system_prompt() -> str:
    return f"""You are the BITAGENTS agent-builder — you help someone launch a new AI agent \
on the marketplace by having a natural, open-ended conversation. You are not a form; do not \
demand fields in a fixed order. Ask whatever follow-up questions make sense given what they've \
told you so far.

CRITICAL, before anything else: talking about a field is not the same as setting it. If the \
user's message gives you ANY new concrete detail (a name, an amount, a rule, a confirmation), \
you MUST call the matching tool in that SAME reply, not just acknowledge it in prose and move on. \
Never end a turn having only described what you would do — actually do it via a tool call. \
Specifically: if the user's message is a confirmation (e.g. "yes", "confirm", "launch it") and \
you have already shown them a draft via show_draft, you MUST call finalize_and_launch in that \
exact turn — do not ask another clarifying question instead of finalizing.

Your job across the conversation:
1. Understand what the agent should actually do — its purpose, what it watches/researches/trades, \
   any limits or rules it should follow.
2. Figure out a short name and a lowercase handle (like a username, no "$" prefix — this is not a \
   token) for it.
3. Pick the best-fitting category: Trading, Research, Monitoring, or Utility.
4. Write a one-sentence public description (shown on its marketplace card).
5. Write the actual system prompt the launched agent will run on — this is the most important part. \
   The user will rarely write a good one themselves; that's your job. Write it in second person \
   ("You are..."), specific about behavior, tone, and any limits, based on what they told you.
6. Determine tool_scope: ask directly whether this agent needs to move user funds or execute trades. \
   If yes, tool_scope is "trading" (explain this requires manual review before it can go live with \
   real funds — this capability isn't wired up yet, so say the agent will launch read-only for now \
   and trading comes later). If it only researches, monitors, or advises, tool_scope is "read_only" \
   (launches automatically after a 24h testing window, no review needed). Default to read_only.
7. Pick which real capabilities the agent needs from this fixed catalog — never invent a tool name \
   that isn't listed here, and never suggest the agent can execute custom code:

{catalog_summary_for_builder()}

   Infer which of these fit from what the user described (e.g. "watches whale wallets" needs \
   analyze_wallet + wallet_recent_activity; "researches a token before I buy" needs lookup_token + \
   research_token). Call select_agent_capabilities with your chosen list, then say in plain language \
   what you gave it and why — never show this as a checklist, just narrate it naturally. If nothing \
   in the catalog fits, that's fine — the agent can still be a pure conversational advisor.

Call set_agent_field / set_agent_personality / set_tool_scope / select_agent_capabilities as you \
learn each piece — don't wait until the end to set everything at once. Use show_draft whenever you \
want to check what's already been captured before asking your next question.

If the agent needs to alert the user about something (a price move, a condition being met), you \
need two more things before it can go live, and you must get them in this order:
8. Ask where they want to be alerted: email or Telegram.
   - Email: ask for their address, then call set_notification_channel(channel="email", destination=<address>) \
     right away.
   - Telegram: never ask them to type a chat ID or username — they don't have one to give you. Call \
     start_telegram_connect instead. It returns a link; tell them to click it and press Start in \
     Telegram, then come back and tell you when they've done that. Call check_telegram_connect only \
     after they say so — if it reports linked=false, they haven't pressed Start yet, ask them to \
     and try again; do not guess or invent a chat id. Once linked=true, set_notification_channel is \
     called for you automatically — move straight to the next step.
9. Immediately call send_test_notification — never skip this and never claim you sent something \
   without actually calling the tool. If it returns ok=false, tell the user plainly that the test \
   failed and why (e.g. a sandbox/domain restriction) — do not ask them to confirm receipt of \
   something that was never delivered; offer to try a different destination instead. If it returns \
   ok=true, tell the user a test was sent and ask them to confirm they received it. Only call \
   confirm_notification_received after BOTH send_test_notification succeeded AND the user has \
   explicitly confirmed receipt (e.g. "I got it", "received") — a reply like "yes launch it" after \
   a failed test is not confirmation of receipt, it's the user trying to move past your last message; \
   address the failure first.
If the agent is specifically a Bitcoin price-move watcher (e.g. "alert me when BTC moves X% in an \
hour"), call create_price_watch with the threshold percentage once the notification channel is \
verified — this is what actually makes the alert run in the background after this chat ends.
If the agent is a product-page price-drop watcher instead (e.g. "tell me when this drops in price" \
with a URL), call create_product_price_watch with the URL and drop threshold once the notification \
channel is verified. It tries to fetch the page and read a real price immediately — if it can't \
find one, tell the user honestly which page failed and why, don't guess a price or pretend it \
worked.
If the agent is a recurring daily digest instead (e.g. "summarize news about X every morning"), \
ask what time of day (as an hour, e.g. 8am) they want it, then call create_digest_watch with the \
topic and hour once the notification channel is verified. This is genuinely different from the \
other two: it's not triggered by any condition, it just fires once a day at that hour.

When you believe the draft is complete, call show_draft, present the full configuration clearly to \
the user (name, handle, category, description, the system prompt you wrote, which capabilities it \
has, whether it's read_only or trading, and its verified notification channel if any), and explicitly \
ask them to confirm before launching. Only call finalize_and_launch after they clearly confirm \
(e.g. "yes", "launch it", "confirm") — never call it speculatively or before showing the draft. If \
the agent needs a notification channel, do not call finalize_and_launch until it's verified."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_agent_field",
            "description": "Set a single top-level field on the draft agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["name", "handle", "category", "description"],
                    },
                    "value": {"type": "string"},
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_agent_personality",
            "description": (
                "Write/update the system prompt the launched agent will actually run on. "
                "You write this on the user's behalf based on the conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "system_prompt": {"type": "string"},
                },
                "required": ["system_prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_tool_scope",
            "description": (
                "Set whether this agent is read_only (research/monitoring, launches automatically) "
                "or trading (can move user funds, requires manual review before going live)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_scope": {"type": "string", "enum": list(TOOL_SCOPES)},
                },
                "required": ["tool_scope"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_agent_capabilities",
            "description": (
                "Set which tools from the fixed catalog this agent can use. Replaces any "
                "previous selection. Pass an empty list for a pure conversational agent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["tool_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_draft",
            "description": "Return the current state of the draft agent so you can check what's already set.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_notification_channel",
            "description": (
                "Set where the launched agent should send alerts. For email, call this directly "
                "with the user's address. For Telegram, do NOT call this directly -- use "
                "start_telegram_connect and check_telegram_connect instead, which call this for you."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "enum": list(VALID_CHANNELS)},
                    "destination": {
                        "type": "string",
                        "description": "Email address. Only used for channel=email.",
                    },
                },
                "required": ["channel", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_telegram_connect",
            "description": (
                "Generate a one-click Telegram connect link for the user. They click it, press "
                "Start in Telegram, and come back -- they never type a chat ID."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_telegram_connect",
            "description": (
                "Check whether the user has pressed Start on the link from start_telegram_connect. "
                "Only call after they say they've done it."
            ),
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_test_notification",
            "description": (
                "Send a real test alert to the notification channel set via set_notification_channel. "
                "Call this immediately after set_notification_channel, before asking the user to confirm."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_notification_received",
            "description": (
                "Mark the notification channel as verified. Only call this after the user explicitly "
                "confirms they received the test alert -- never on your own judgment."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_price_watch",
            "description": (
                "Create the background BTC price-watch that will actually run after this chat ends. "
                "Only call this once the notification channel is verified via confirm_notification_received."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold_pct": {
                        "type": "number",
                        "description": "Percent move (up or down) within the rolling window that should trigger an alert.",
                    },
                    "window_hours": {
                        "type": "number",
                        "description": "Rolling window length in hours. Defaults to 1 (e.g. 'moves 1% in one hour').",
                    },
                },
                "required": ["threshold_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_product_price_watch",
            "description": (
                "Create a background watch on a product page URL that alerts when its price drops. "
                "Fetches the page immediately to confirm a price can actually be read -- if it fails, "
                "report the real error to the user, don't invent a price. Only call once the "
                "notification channel is verified via confirm_notification_received."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The product page URL to watch."},
                    "threshold_pct": {
                        "type": "number",
                        "description": "Percent drop from the current price that should trigger an alert.",
                    },
                    "product_label": {
                        "type": "string",
                        "description": "Short human name for the product, for the alert message.",
                    },
                },
                "required": ["url", "threshold_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_digest_watch",
            "description": (
                "Create a recurring daily digest that fires once a day at the given hour, regardless "
                "of any condition -- not a threshold alert. Only call once the notification channel "
                "is verified via confirm_notification_received."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "What to summarize news about each day."},
                    "schedule_hour": {
                        "type": "integer",
                        "description": "Hour of day (0-23, UTC) to send the digest. Defaults to 8.",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_and_launch",
            "description": (
                "Finalize the draft and move it into the 24h testing window. Only call this after "
                "showing the user the full draft and receiving explicit confirmation."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _builder_tools(agent_id: str) -> dict[str, Any]:
    def set_agent_field(**kwargs):
        field = (kwargs.get("field") or "").strip()
        value = (kwargs.get("value") or "").strip()
        if field not in ("name", "handle", "category", "description"):
            return {"error": f"Unknown field: {field}"}
        if field == "category" and value not in CATEGORIES:
            return {"error": f"category must be one of {CATEGORIES}"}
        if field == "handle":
            value = value.lower().lstrip("$").replace(" ", "-")[:40]
        updated = db.update_custom_agent_fields(agent_id, **{field: value})
        return {"ok": True, "draft": updated}

    def set_agent_personality(**kwargs):
        prompt = (kwargs.get("system_prompt") or "").strip()
        if not prompt:
            return {"error": "system_prompt cannot be empty"}
        updated = db.update_custom_agent_fields(agent_id, system_prompt=prompt)
        return {"ok": True, "draft": updated}

    def set_tool_scope(**kwargs):
        scope = (kwargs.get("tool_scope") or "").strip()
        if scope not in TOOL_SCOPES:
            return {"error": f"tool_scope must be one of {TOOL_SCOPES}"}
        updated = db.update_custom_agent_fields(agent_id, tool_scope=scope)
        return {"ok": True, "draft": updated}

    def select_agent_capabilities(**kwargs):
        requested = kwargs.get("tool_names") or []
        valid = valid_tool_names([str(n).strip() for n in requested])
        invalid = [n for n in requested if n not in valid]
        updated = db.update_custom_agent_fields(agent_id, enabled_tools=valid)
        result = {"ok": True, "enabled_tools": valid, "draft": updated}
        if invalid:
            result["ignored_unknown_tools"] = invalid
        return result

    def show_draft(**_kwargs):
        return db.get_custom_agent(agent_id) or {"error": "draft not found"}

    def _set_notification_channel(channel: str, destination: str) -> dict[str, Any]:
        if channel not in VALID_CHANNELS:
            return {"error": f"channel must be one of {VALID_CHANNELS}"}
        if not destination:
            return {"error": "destination cannot be empty"}
        current = db.get_custom_agent(agent_id) or {}
        changed = (
            current.get("notify_channel") != channel
            or current.get("notify_destination") != destination
        )
        fields: dict[str, Any] = {"notify_channel": channel, "notify_destination": destination}
        if changed:
            # Only a REAL change invalidates the prior test-send -- calling this
            # again with the same values (e.g. the model re-confirming) must not
            # wipe out a test that already succeeded.
            fields["notify_test_sent_ok"] = False
        updated = db.update_custom_agent_fields(agent_id, **fields)
        return {"ok": True, "draft": updated}

    def set_notification_channel(**kwargs):
        channel = (kwargs.get("channel") or "").strip()
        destination = (kwargs.get("destination") or "").strip()
        if channel == "telegram":
            return {
                "error": "Don't call this directly for Telegram -- use start_telegram_connect "
                         "so the user connects by clicking a link, not typing a chat ID.",
            }
        return _set_notification_channel(channel, destination)

    def start_telegram_connect(**_kwargs):
        code = db.create_telegram_link_code()
        link = build_deep_link(code)
        if not link:
            return {
                "error": "Telegram isn't configured on the backend yet "
                         "(TELEGRAM_BOT_TOKEN missing) -- offer email instead for now.",
            }
        # Stashed so the NEXT turn auto-resolves this even if you forget to
        # call check_telegram_connect -- see _auto_resolve_telegram_link.
        db.update_custom_agent_fields(agent_id, pending_telegram_code=code)
        return {"ok": True, "code": code, "deep_link": link}

    def check_telegram_connect(**kwargs):
        code = (kwargs.get("code") or "").strip()
        if not code:
            return {"error": "code is required"}
        record = db.get_telegram_link_code(code)
        if not record:
            return {"error": "Unknown code -- call start_telegram_connect again."}
        if not record.get("chat_id"):
            return {"linked": False}
        result = _set_notification_channel("telegram", record["chat_id"])
        result["linked"] = True
        db.update_custom_agent_fields(agent_id, pending_telegram_code=None)
        return result

    def send_test_notification(**_kwargs):
        draft = db.get_custom_agent(agent_id)
        if not draft or not draft.get("notify_channel") or not draft.get("notify_destination"):
            return {"error": "Call set_notification_channel first."}
        result = send_notification(
            draft["notify_channel"],
            draft["notify_destination"],
            subject="Your BITAGENTS test alert",
            body="This is a test alert from the agent you're building on BITAGENTS. "
                 "If you got this, notifications are working.",
        )
        db.update_custom_agent_fields(agent_id, notify_test_sent_ok=bool(result.get("ok")))
        return result

    def confirm_notification_received(**_kwargs):
        updated = db.mark_notification_verified(agent_id)
        if not updated:
            return {"error": "draft not found"}
        if "error" in updated:
            return updated
        return {"ok": True, "draft": updated}

    def create_price_watch(**kwargs):
        threshold_pct = kwargs.get("threshold_pct")
        window_hours = kwargs.get("window_hours") or 1.0
        if threshold_pct is None:
            return {"error": "threshold_pct is required"}
        draft = db.get_custom_agent(agent_id)
        if not draft or not draft.get("notify_verified_at"):
            return {"error": "Notification channel must be verified before creating a price watch."}
        condition_config = {"threshold_pct": float(threshold_pct), "window_hours": float(window_hours)}
        # Idempotent: the model may call this more than once in a turn (e.g.
        # after an earlier attempt errored) -- update the existing watch
        # instead of inserting a duplicate row, which would otherwise fire
        # two alerts for the same real price move.
        existing = db.get_watch_by_agent(agent_id, source_type="btc_price")
        if existing:
            updated = db.update_watch_params(existing["id"], condition_config=condition_config)
            return {"ok": True, "watch": updated}
        try:
            current_price = fetch_btc_price_usd()
        except Exception as exc:
            return {"error": f"Could not reach the price feed: {exc}"}
        watch = db.create_watch(
            "btc_price", {}, "percent_move", condition_config,
            agent_id=agent_id, poll_interval_seconds=60, baseline_value=current_price,
        )
        return {"ok": True, "watch": watch, "current_btc_price_usd": current_price}

    def create_product_price_watch(**kwargs):
        url = (kwargs.get("url") or "").strip()
        threshold_pct = kwargs.get("threshold_pct")
        product_label = (kwargs.get("product_label") or "").strip() or None
        if not url:
            return {"error": "url is required"}
        if threshold_pct is None:
            return {"error": "threshold_pct is required"}
        draft = db.get_custom_agent(agent_id)
        if not draft or not draft.get("notify_verified_at"):
            return {"error": "Notification channel must be verified before creating a price watch."}
        # Same idempotency guard as create_price_watch.
        existing = db.get_watch_by_agent(agent_id, source_type="product_price")
        if existing:
            new_source = {"url": url, "product_label": product_label} if url != existing["source_config"].get("url") else None
            updated = db.update_watch_params(
                existing["id"], source_config=new_source,
                condition_config={"threshold_pct": float(threshold_pct)},
            )
            return {"ok": True, "watch": updated}
        try:
            price, currency = fetch_product_price(url)
        except Exception as exc:
            return {"error": f"Could not read a price from that page: {exc}"}
        watch = db.create_watch(
            "product_price", {"url": url, "product_label": product_label}, "percent_drop",
            {"threshold_pct": float(threshold_pct)},
            agent_id=agent_id, poll_interval_seconds=300, baseline_value=price,
        )
        return {"ok": True, "watch": watch, "current_price": price, "currency": currency}

    def create_digest_watch(**kwargs):
        topic = (kwargs.get("topic") or "").strip()
        schedule_hour = kwargs.get("schedule_hour")
        schedule_hour = int(schedule_hour) if schedule_hour is not None else 8
        if not topic:
            return {"error": "topic is required"}
        if not 0 <= schedule_hour <= 23:
            return {"error": "schedule_hour must be 0-23"}
        draft = db.get_custom_agent(agent_id)
        if not draft or not draft.get("notify_verified_at"):
            return {"error": "Notification channel must be verified before creating a digest watch."}
        existing = db.get_watch_by_agent(agent_id, source_type="news")
        if existing:
            updated = db.update_watch_params(
                existing["id"], source_config={"topic": topic},
                condition_config={"schedule_hour": schedule_hour},
            )
            return {"ok": True, "watch": updated}
        try:
            sample_headlines = fetch_topic_headlines(topic, limit=3)
        except Exception as exc:
            return {"error": f"Could not fetch news for that topic: {exc}"}
        watch = db.create_watch(
            "news", {"topic": topic}, "daily_fire", {"schedule_hour": schedule_hour},
            agent_id=agent_id, poll_interval_seconds=900,
        )
        return {"ok": True, "watch": watch, "sample_headlines": sample_headlines}

    def finalize_and_launch(**_kwargs):
        draft = db.get_custom_agent(agent_id)
        if not draft:
            return {"error": "draft not found"}
        missing = [
            f for f in ("name", "handle", "category", "description", "system_prompt")
            if not (draft.get(f) or "").strip()
        ]
        if missing:
            return {"error": f"Cannot launch yet, missing: {', '.join(missing)}"}
        if draft.get("notify_channel") and not draft.get("notify_verified_at"):
            return {"error": "Notification channel is set but not yet verified. Confirm the test alert first."}
        # A notification channel with no watch behind it is exactly the
        # failure this caught in testing: the agent launches and claims
        # "it will alert you when X happens" while nothing is actually
        # configured to check X. If a channel is set, a watch must exist --
        # call create_price_watch / create_product_price_watch /
        # create_digest_watch (whichever matches what this agent is for)
        # before finalize_and_launch can succeed.
        if draft.get("notify_channel") and not db.get_watch_by_agent(agent_id):
            return {
                "error": "This agent has a verified notification channel but no watch configured yet -- "
                         "call create_price_watch, create_product_price_watch, or create_digest_watch "
                         "(whichever matches what this agent actually does) before launching.",
            }
        finalized = db.finalize_custom_agent(agent_id)
        if not finalized:
            return {"error": "Could not finalize — draft may already be launched."}
        return {"ok": True, "agent": finalized, "status": finalized["status"]}

    return {
        "set_agent_field": set_agent_field,
        "set_agent_personality": set_agent_personality,
        "set_tool_scope": set_tool_scope,
        "select_agent_capabilities": select_agent_capabilities,
        "show_draft": show_draft,
        "set_notification_channel": set_notification_channel,
        "start_telegram_connect": start_telegram_connect,
        "check_telegram_connect": check_telegram_connect,
        "send_test_notification": send_test_notification,
        "confirm_notification_received": confirm_notification_received,
        "create_price_watch": create_price_watch,
        "create_product_price_watch": create_product_price_watch,
        "create_digest_watch": create_digest_watch,
        "finalize_and_launch": finalize_and_launch,
    }


def _launch_blockers(draft: dict[str, Any]) -> list[str]:
    """What's GENUINELY stopping this draft from launching -- not what tool
    was or wasn't called, actual DB state. notify_verified_at is deliberately
    NOT required here: a verified-but-not-yet-confirmed channel is something
    the self-check below can still resolve (the test already succeeded, the
    only gap is one tool call); a channel whose test never succeeded cannot,
    and is a real blocker."""
    missing = [
        f for f in ("name", "handle", "category", "description", "system_prompt")
        if not (draft.get(f) or "").strip()
    ]
    if draft.get("notify_channel") and not draft.get("notify_test_sent_ok"):
        missing.append("a successful notification test-send")
    return missing


def _ensure_finalized_if_ready(
    agent_id: str, reply: str, history: list, actions: list[dict[str, Any]]
) -> tuple[str, list, list[dict[str, Any]]]:
    """Code-level safety net for the exact failure this builder exists to
    prevent: the model narrating success without the underlying tool call
    actually having succeeded. Checks real DB state, not whether a tool was
    merely *attempted* this turn -- a failed finalize_and_launch call still
    leaves status='draft', and the old version of this check treated any
    attempt (success or failure) as "done", which is exactly how an agent
    could get stuck confirming forever without ever launching. Runs on a
    scratch copy of history so a failed/no-op check never pollutes the
    real, persisted conversation the user sees."""
    draft = db.get_custom_agent(agent_id)
    if not draft or draft.get("status") != "draft":
        return reply, history, actions
    blockers = _launch_blockers(draft)
    if blockers:
        return reply, history, actions

    needs_confirm_call = bool(draft.get("notify_channel")) and not draft.get("notify_verified_at")
    # Caught in real testing: an agent can finalize successfully while
    # having NO watch at all -- e.g. create_price_watch was correctly
    # rejected earlier (channel not verified yet) and never retried after
    # verification succeeded. finalize_and_launch now refuses this too, but
    # nudge the model to actually fix it (it has the conversation history
    # to figure out which watch type this agent needs) rather than just
    # leaving it stuck.
    needs_watch = bool(draft.get("notify_channel")) and not db.get_watch_by_agent(agent_id)
    nudge = (
        "SYSTEM CHECK (internal -- not a real user message): every required "
        "field is set and the notification test-send already succeeded. "
        + (
            "It has NOT been marked verified yet -- if the user has already "
            "confirmed receiving the test alert anywhere earlier in this real "
            "conversation (read the actual history, don't assume), call "
            "confirm_notification_received now, then finalize_and_launch. "
            if needs_confirm_call
            else ""
        )
        + (
            "This agent has NO watch configured yet -- re-read the conversation "
            "to see what this agent is actually supposed to watch (BTC price, a "
            "product page, or a news topic) and call the matching create_*_watch "
            "tool with the details the user already gave you, then finalize_and_launch. "
            if needs_watch
            else ""
        )
        + "finalize_and_launch was not confirmed as successful this turn. If "
        "the user already confirmed they want to launch earlier in this "
        "conversation, call finalize_and_launch right now and check its real "
        "return value -- do not just say it worked. If they have not yet "
        "clearly confirmed, call show_draft and note that confirmation is "
        "still needed -- never assume."
    )
    _, _, extra_actions = run_tool_agent(
        nudge,
        list(history),
        system_prompt=_build_system_prompt(),
        tools=TOOLS,
        tool_registry=_builder_tools(agent_id),
        model=BUILDER_MODEL,
        app_suffix="agent-builder-selfcheck",
        llm_call=call_openrouter,
    )
    refreshed = db.get_custom_agent(agent_id)
    if refreshed and refreshed.get("status") != "draft":
        reply = (
            f"{reply}\n\n(Double-checked: {refreshed.get('name') or 'the agent'} "
            f"is now actually live.)"
        )
    return reply, history, actions + extra_actions


def _auto_resolve_telegram_link(agent_id: str) -> None:
    """Deterministic, model-independent resolution of a pending Telegram
    connect code -- runs before every turn so a user pressing Start in
    Telegram is picked up on their very next message, even if the model
    never actually calls check_telegram_connect itself. Real testing
    showed the model narrating "still not connected" without re-checking,
    across multiple retries, while the link had genuinely already
    succeeded server-side -- this removes that dependency entirely."""
    draft = db.get_custom_agent(agent_id)
    if not draft:
        return
    code = draft.get("pending_telegram_code")
    if not code:
        return
    record = db.get_telegram_link_code(code)
    if not record or not record.get("chat_id"):
        return
    db.update_custom_agent_fields(
        agent_id,
        notify_channel="telegram",
        notify_destination=record["chat_id"],
        notify_test_sent_ok=False,
        pending_telegram_code=None,
    )


def run_builder_agent(
    user_input: str,
    conversation_history: list,
    *,
    agent_id: str,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    _auto_resolve_telegram_link(agent_id)
    reply, history, actions = run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=_build_system_prompt(),
        tools=TOOLS,
        tool_registry=_builder_tools(agent_id),
        model=BUILDER_MODEL,
        app_suffix="agent-builder",
        session_id=session_id,
        llm_call=call_openrouter,
    )
    return _ensure_finalized_if_ready(agent_id, reply, history, actions)
