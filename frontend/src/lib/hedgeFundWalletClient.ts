export type HfTokenBalanceRow = {
  token: string;
  mint?: string | null;
  deposited: number;
  spent_in_strategies?: number;
  reserved_for_strategies?: number;
  reserved_for_plans?: number;
  withdrawn?: number;
  available: number;
  withdrawable?: number;
};

export type HfUserDepositBalances = {
  user_wallet: string;
  balances: HfTokenBalanceRow[];
  agent_wallet: string | null;
  max_strategy_usdc?: number;
};

export type HfAgentWalletInfo = {
  agent_wallet: string | null;
  cluster?: string;
  allowed_tokens?: string[];
  max_strategy_usdc?: number;
  management_fee_pct?: number;
  performance_fee_pct?: number;
  usdc_mint?: string;
  sol_mint?: string;
  live_trading?: boolean;
  configured?: boolean;
  wallet_provider?: "circle" | "local";
  per_user_wallet?: boolean;
  circle_error?: string;
};

export type HfDepositVerifyResponse = {
  status: string;
  message?: string;
  deposits?: Array<{
    token: string;
    amount: number;
    signature: string;
    explorer_url?: string;
  }>;
  balances?: HfUserDepositBalances;
  error?: string;
};

export const HF_DEPOSIT_TOKEN_DECIMALS: Record<string, number> = {
  SOL: 9,
  USDC: 6,
};

export const HF_DEPOSIT_TOKEN_MINTS: Record<string, string> = {
  SOL: "So11111111111111111111111111111111111111112",
  USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
};

export async function fetchHfAgentWallet(
  authToken: string
): Promise<HfAgentWalletInfo | null> {
  try {
    const res = await fetch("/api/agents/hedge-fund/wallet/agent", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as HfAgentWalletInfo;
  } catch {
    return null;
  }
}

export async function fetchHfUserBalances(
  authToken: string
): Promise<HfUserDepositBalances | null> {
  try {
    const res = await fetch("/api/agents/hedge-fund/wallet/balance", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as HfUserDepositBalances;
  } catch {
    return null;
  }
}

export async function verifyHfDeposit(
  signature: string,
  authToken: string
): Promise<HfDepositVerifyResponse> {
  const res = await fetch("/api/agents/hedge-fund/wallet/deposit", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ signature: signature.trim() }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : "Deposit verification failed"
    );
  }
  return data as HfDepositVerifyResponse;
}

function isRetryableVerifyError(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("not found") ||
    lower.includes("wait") ||
    lower.includes("offline") ||
    lower.includes("503") ||
    lower.includes("network") ||
    lower.includes("pending")
  );
}

/** Verify a deposit signature with retries while the RPC indexes the transaction. */
export async function verifyHfDepositWithRetry(
  signature: string,
  authToken: string,
  maxAttempts = 12
): Promise<HfDepositVerifyResponse> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const result = await verifyHfDeposit(signature, authToken);
      if (result.status === "confirmed" || result.status === "already_recorded") {
        return result;
      }
      if (result.error) {
        lastError = new Error(result.error);
        if (!isRetryableVerifyError(result.error)) throw lastError;
      }
    } catch (err) {
      lastError = err instanceof Error ? err : new Error("Deposit verification failed");
      if (!isRetryableVerifyError(lastError.message)) throw lastError;
    }
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }
  throw lastError ?? new Error("Deposit verification failed");
}

export async function withdrawHfTokens(
  token: string,
  amount: number,
  authToken: string
): Promise<{ status: string; signature?: string; balances?: HfUserDepositBalances }> {
  const res = await fetch("/api/agents/hedge-fund/wallet/withdraw", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ token, amount }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : "Withdraw failed"
    );
  }
  return data;
}
