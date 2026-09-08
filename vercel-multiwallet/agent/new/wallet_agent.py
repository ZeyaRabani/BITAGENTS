import json
import requests
from datetime import datetime
from typing import Any

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1"

ETH_RPC = "https://eth.llamarpc.com"
ETHERSCAN_API = "https://api.etherscan.io/api"

# ToDo: Get one free at https://etherscan.io/apis
ETHERSCAN_KEY = "YourApiKeyToken"

def get_eth_balance(address: str) -> dict:
    """Get native ETH balance of a wallet address."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [address, "latest"],
            "id": 1
        }
        resp = requests.post(ETH_RPC, json=payload, timeout=10)
        result = resp.json()
        if "result" in result:
            wei = int(result["result"], 16)
            eth = wei / 1e18
            return {"address": address, "balance_eth": round(eth, 6), "balance_wei": wei}
        return {"error": result.get("error", "Unknown error")}
    except Exception as e:
        return {"error": str(e)}


def get_transaction_count(address: str) -> dict:
    """Get the number of transactions sent from a wallet (nonce)."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getTransactionCount",
            "params": [address, "latest"],
            "id": 1
        }
        resp = requests.post(ETH_RPC, json=payload, timeout=10)
        result = resp.json()
        if "result" in result:
            count = int(result["result"], 16)
            return {"address": address, "transaction_count": count}
        return {"error": result.get("error", "Unknown error")}
    except Exception as e:
        return {"error": str(e)}


def get_recent_transactions(address: str, limit: int = 5) -> dict:
    """Get recent ETH transactions for a wallet using Etherscan API."""
    try:
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": ETHERSCAN_KEY
        }
        resp = requests.get(ETHERSCAN_API, params=params, timeout=10)
        data = resp.json()

        if data.get("status") == "1":
            txs = []
            for tx in data["result"][:limit]:
                value_eth = int(tx["value"]) / 1e18
                txs.append({
                    "hash": tx["hash"][:16] + "...",
                    "from": tx["from"],
                    "to": tx["to"],
                    "value_eth": round(value_eth, 6),
                    "timestamp": datetime.fromtimestamp(int(tx["timeStamp"])).strftime("%Y-%m-%d %H:%M"),
                    "status": "✅ Success" if tx["txreceipt_status"] == "1" else "❌ Failed",
                    "gas_used": tx["gasUsed"]
                })
            return {"address": address, "transactions": txs, "count": len(txs)}
        else:
            return {"address": address, "transactions": [], "message": data.get("message", "No transactions found or API rate limited")}
    except Exception as e:
        return {"error": str(e)}


def get_token_balances(address: str) -> dict:
    """Get ERC-20 token balances for a wallet using Etherscan."""
    try:
        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "page": 1,
            "offset": 20,
            "sort": "desc",
            "apikey": ETHERSCAN_KEY
        }
        resp = requests.get(ETHERSCAN_API, params=params, timeout=10)
        data = resp.json()

        if data.get("status") == "1":
            tokens = {}
            for tx in data["result"]:
                symbol = tx["tokenSymbol"]
                name = tx["tokenName"]
                decimals = int(tx["tokenDecimal"]) if tx["tokenDecimal"] else 18
                if symbol not in tokens:
                    tokens[symbol] = {"name": name, "symbol": symbol, "recent_activity": 0}
                tokens[symbol]["recent_activity"] += 1

            return {
                "address": address,
                "tokens_with_activity": list(tokens.values())[:10],
                "total_unique_tokens": len(tokens)
            }
        else:
            return {"address": address, "tokens_with_activity": [], "message": "No token activity found"}
    except Exception as e:
        return {"error": str(e)}


def get_block_number() -> dict:
    """Get the current Ethereum block number."""
    try:
        payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
        resp = requests.post(ETH_RPC, json=payload, timeout=10)
        result = resp.json()
        if "result" in result:
            block = int(result["result"], 16)
            return {"current_block": block, "network": "Ethereum Mainnet"}
        return {"error": "Could not fetch block number"}
    except Exception as e:
        return {"error": str(e)}


def get_gas_price() -> dict:
    """Get current Ethereum gas price."""
    try:
        payload = {"jsonrpc": "2.0", "method": "eth_gasPrice", "params": [], "id": 1}
        resp = requests.post(ETH_RPC, json=payload, timeout=10)
        result = resp.json()
        if "result" in result:
            wei = int(result["result"], 16)
            gwei = wei / 1e9
            return {"gas_price_gwei": round(gwei, 2), "gas_price_wei": wei}
        return {"error": "Could not fetch gas price"}
    except Exception as e:
        return {"error": str(e)}


def compare_wallets(addresses: list) -> dict:
    """Compare ETH balances across multiple wallets."""
    results = []
    for addr in addresses[:5]:  # limit to 5
        bal = get_eth_balance(addr)
        tx_count = get_transaction_count(addr)
        results.append({
            "address": addr,
            "balance_eth": bal.get("balance_eth", "error"),
            "tx_count": tx_count.get("transaction_count", "error")
        })
    results.sort(key=lambda x: x["balance_eth"] if isinstance(x["balance_eth"], float) else 0, reverse=True)
    return {"comparison": results, "wallets_compared": len(results)}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_eth_balance",
            "description": "Get the native ETH balance of a wallet address",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Ethereum wallet address (0x...)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_transaction_count",
            "description": "Get total number of transactions (nonce) for a wallet address",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Ethereum wallet address"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_transactions",
            "description": "Get recent ETH transactions for a wallet address",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Ethereum wallet address"},
                    "limit": {"type": "integer", "description": "Number of transactions to fetch (default 5, max 10)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_token_balances",
            "description": "Get ERC-20 token activity for a wallet address",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Ethereum wallet address"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_block_number",
            "description": "Get the current Ethereum block number",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_gas_price",
            "description": "Get the current Ethereum gas price in Gwei",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_wallets",
            "description": "Compare ETH balances and transaction counts across multiple wallet addresses",
            "parameters": {
                "type": "object",
                "properties": {
                    "addresses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Ethereum wallet addresses to compare"
                    }
                },
                "required": ["addresses"]
            }
        }
    }
]

TOOL_MAP = {
    "get_eth_balance": get_eth_balance,
    "get_transaction_count": get_transaction_count,
    "get_recent_transactions": get_recent_transactions,
    "get_token_balances": get_token_balances,
    "get_block_number": get_block_number,
    "get_gas_price": get_gas_price,
    "compare_wallets": compare_wallets,
}

SYSTEM_PROMPT = """You are a blockchain wallet monitoring AI agent. You help users track Ethereum wallets, check balances, monitor token activity, and analyze on-chain movements.

You have access to real-time blockchain tools. When users ask about wallet addresses, always use the appropriate tools to fetch live data before responding.

Be concise and clear. Format numbers nicely. Flag anything unusual like very high transaction counts or large transfers."""

def call_ollama(messages: list) -> Any:
    """Send messages to Ollama and return the response."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def execute_tool(tool_name: str, tool_args: dict) -> str:
    """Execute a tool and return result as JSON string."""
    func = TOOL_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = func(**tool_args)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(user_input: str, conversation_history: list) -> tuple[str, list]:
    """Run one turn of the agent loop with tool calling."""
    conversation_history.append({"role": "user", "content": user_input})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    max_iterations = 5
    for i in range(max_iterations):
        response = call_ollama(messages)
        message = response["message"]

        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            assistant_reply = message.get("content", "")
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            return assistant_reply, conversation_history

        print(f"  🔧 Using tools: {[tc['function']['name'] for tc in tool_calls]}")
        messages.append({"role": "assistant", "content": message.get("content", ""), "tool_calls": tool_calls})

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            tool_args = tc["function"].get("arguments", {})
            if isinstance(tool_args, str):
                tool_args = json.loads(tool_args)

            print(f"  📡 Calling {tool_name}({tool_args})...")
            result = execute_tool(tool_name, tool_args)
            print(f"  ✅ Got result")

            messages.append({
                "role": "tool",
                "content": result
            })

    return "Agent reached maximum iterations.", conversation_history

def main():
    print("=" * 60)
    print("  🔍 Wallet Monitoring AI Agent")
    print("  Powered by Ollama")
    print("=" * 60)
    print(f"  Model: {MODEL}")
    print(f"  Network: Ethereum Mainnet")
    print()
    print("  Example questions:")
    print("  • What's the ETH balance of vitalik.eth? → use: 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print("  • Show me recent transactions for 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print("  • What tokens has this wallet interacted with?")
    print("  • What's the current gas price?")
    print("  • Compare these 2 wallets: 0x... and 0x...")
    print()
    print("  Type 'quit' to exit, 'clear' to reset conversation")
    print("=" * 60)
    print()

    conversation_history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("👋 Goodbye!")
            break
        if user_input.lower() == "clear":
            conversation_history = []
            print("🔄 Conversation cleared.\n")
            continue

        print()
        try:
            reply, conversation_history = run_agent(user_input, conversation_history)
            print(f"Agent: {reply}")
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to Ollama. Make sure it's running: `ollama serve`")
        except Exception as e:
            print(f"❌ Error: {e}")
        print()


if __name__ == "__main__":
    main()