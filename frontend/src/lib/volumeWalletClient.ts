export type TokenBalanceRow = {
  token: string;
  mint?: string | null;
  deposited: number;
  acquired_from_campaigns?: number;
  spent_in_campaigns?: number;
  reserved_for_campaigns: number;
  withdrawn?: number;
  available: number;
  withdrawable?: number;
};

export type UserDepositBalances = {
  user_wallet: string;
  balances: TokenBalanceRow[];
  agent_wallet: string | null;
};

export type AgentWalletInfo = {
  agent_wallet: string | null;
  cluster?: string;
  platform_fee_rate?: number;
  pool_creation_cost_sol?: number;
  any_spl_token?: boolean;
  common_tokens?: string[];
};

export type ResolvedToken = {
  symbol: string;
  mint: string;
  decimals: number;
  name?: string;
};

export type DepositVerifyResponse = {
  status: string;
  message?: string;
  deposits?: Array<{
    token: string;
    amount: number;
    signature: string;
    explorer_url?: string;
  }>;
  balances?: UserDepositBalances;
  error?: string;
};

export const DEPOSIT_TOKEN_DECIMALS: Record<string, number> = {
  SOL: 9,
  USDC: 6,
  USDT: 6,
};

export const DEPOSIT_TOKEN_MINTS: Record<string, string> = {
  SOL: "So11111111111111111111111111111111111111112",
  USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  USDT: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
};

export async function fetchVolumeAgentWallet(): Promise<AgentWalletInfo | null> {
  try {
    const res = await fetch("/api/agents/volume/wallet/agent", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as AgentWalletInfo;
  } catch {
    return null;
  }
}

export async function resolveVolumeToken(query: string): Promise<ResolvedToken> {
  const params = new URLSearchParams({ query: query.trim() });
  const res = await fetch(`/api/agents/volume/tokens/resolve?${params}`, { cache: "no-store" });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(typeof data.error === "string" ? data.error : "Unknown token");
  }
  return data as ResolvedToken;
}

export async function fetchVolumeUserBalances(
  authToken: string
): Promise<UserDepositBalances | null> {
  try {
    const res = await fetch("/api/agents/volume/wallet/balance", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as UserDepositBalances;
  } catch {
    return null;
  }
}

export async function verifyVolumeDeposit(
  signature: string,
  authToken: string
): Promise<DepositVerifyResponse> {
  const res = await fetch("/api/agents/volume/wallet/deposit", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ signature }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : data.error ?? "Deposit verify failed");
  }
  return data as DepositVerifyResponse;
}

export async function verifyVolumeDepositWithRetry(
  signature: string,
  authToken: string,
  maxAttempts = 8
): Promise<DepositVerifyResponse> {
  let lastError = "Deposit verification failed";
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const result = await verifyVolumeDeposit(signature, authToken);
      if (result.status === "confirmed" || result.status === "already_recorded") {
        return result;
      }
      if (result.error) lastError = result.error;
    } catch (err) {
      lastError = err instanceof Error ? err.message : lastError;
    }
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, 2500));
    }
  }
  throw new Error(lastError);
}

export async function withdrawVolumeTokens(
  token: string,
  amount: number,
  authToken: string,
  options?: { convertToQuote?: boolean; quoteToken?: string }
): Promise<{
  status: string;
  signature?: string;
  balances?: UserDepositBalances;
  swap?: { swap_signature?: string; output_amount?: number; output_token?: string };
  converted_from?: { token: string; amount: number };
}> {
  const res = await fetch("/api/agents/volume/wallet/withdraw", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      token,
      amount,
      convert_to_quote: options?.convertToQuote ?? false,
      quote_token: options?.quoteToken ?? "SOL",
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : data.error ?? "Withdraw failed");
  }
  return data;
}
