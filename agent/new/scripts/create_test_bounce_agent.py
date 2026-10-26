"""
One-time local setup: create a test agent with the price_signal_watch module
enabled, owned by YOUR wallet, so you can use /launch/signal-test without
needing anyone else's wallet or test data.

Usage:
    cd agent/new
    python scripts/create_test_bounce_agent.py <YOUR_WALLET_ADDRESS>

Requires MODE=development in agent/new/.env (so the 1 SOL launch fee is
skipped) and a reachable DATABASE_URL. Prints the new agent_id -- paste that
into the "Agent ID" field on the signal-test page.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/create_test_bounce_agent.py <YOUR_WALLET_ADDRESS>")
        sys.exit(1)

    wallet = sys.argv[1].strip()
    if not wallet:
        print("Wallet address is required.")
        sys.exit(1)

    from launch_agent import launch_agent

    result = launch_agent(
        user_wallet=wallet,
        name="Bounce Test",
        description="Local test agent for the Bounce Agent signal engine.",
        task=(
            "Watch a token for a drop-then-bounce price pattern and trade it with a "
            "stop-loss/take-profit once it fires."
        ),
        modules=["price_signal_watch"],
        signature="",
    )

    if result.get("error"):
        print(f"Failed to create agent: {result['error']}")
        sys.exit(1)

    agent_id = result["agent"]["id"]
    print(f"Created test agent: {agent_id}")
    print(f"Owner wallet: {wallet}")
    print()
    print(f"Paste \"{agent_id}\" into the \"Agent ID\" field on /launch/signal-test,")
    print("and connect the same wallet in the top right.")


if __name__ == "__main__":
    main()
