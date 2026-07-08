export type EasyaTokenBalanceRow = {
  token: string;
  mint?: string | null;
  deposited: number;
  acquired_from_swaps?: number;
  withdrawn?: number;
  reserved_for_orders: number;
  spent: number;
  available: number;
  withdrawable?: number;
};

export type EasyaUserBalances = {
  user_wallet: string;
  balances: EasyaTokenBalanceRow[];
  agent_wallet: string | null;
  platform_fee_rate?: number;
};

export type EasyaAgentWalletInfo = {
  agent_wallet: string | null;
  configured: boolean;
  platform_fee_pct?: string;
  platform_fee_rate?: number;
};

export async function fetchEasyaAgentWallet(): Promise<EasyaAgentWalletInfo | null> {
  try {
    const res = await fetch("/api/agents/kickstart-copilot/wallet/agent", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as EasyaAgentWalletInfo;
  } catch {
    return null;
  }
}

export async function fetchEasyaBalances(authToken: string): Promise<EasyaUserBalances | null> {
  try {
    const res = await fetch("/api/agents/kickstart-copilot/wallet/balance", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as EasyaUserBalances;
  } catch {
    return null;
  }
}

export async function verifyEasyaDeposit(signature: string, authToken: string) {
  const res = await fetch("/api/agents/kickstart-copilot/wallet/deposit", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ signature: signature.trim() }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : data.error ?? "Deposit failed");
  }
  return data;
}
