export type YieldTokenBalanceRow = {
  token: string;
  mint?: string | null;
  deposited: number;
  spent_in_positions?: number;
  withdrawn?: number;
  available: number;
  withdrawable?: number;
  deployed_lst_approx?: number;
};

export type YieldUserDepositBalances = {
  user_wallet: string;
  balances: YieldTokenBalanceRow[];
  agent_wallet: string | null;
};

export type YieldAgentWalletInfo = {
  agent_wallet: string | null;
  cluster?: string;
  allowed_tokens?: string[];
  configured?: boolean;
  wallet_provider?: "circle" | null;
  per_user_wallet?: boolean;
  circle_error?: string;
  live_routing?: string;
};

export type YieldDepositVerifyResponse = {
  status: string;
  message?: string;
  deposits?: Array<{
    token: string;
    amount: number;
    signature: string;
    explorer_url?: string;
  }>;
  balances?: YieldUserDepositBalances;
  error?: string;
};

export async function fetchYieldAgentWallet(
  authToken: string
): Promise<YieldAgentWalletInfo | null> {
  try {
    const res = await fetch("/api/agents/yield/wallet/agent", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as YieldAgentWalletInfo;
  } catch {
    return null;
  }
}

export async function fetchYieldUserBalances(
  authToken: string
): Promise<YieldUserDepositBalances | null> {
  try {
    const res = await fetch("/api/agents/yield/wallet/balance", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as YieldUserDepositBalances;
  } catch {
    return null;
  }
}

export async function verifyYieldDeposit(
  signature: string,
  authToken: string
): Promise<YieldDepositVerifyResponse> {
  const res = await fetch("/api/agents/yield/wallet/deposit", {
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
  return data as YieldDepositVerifyResponse;
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

export async function verifyYieldDepositWithRetry(
  signature: string,
  authToken: string,
  maxAttempts = 12
): Promise<YieldDepositVerifyResponse> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const result = await verifyYieldDeposit(signature, authToken);
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
  throw lastError ?? new Error("Deposit verification timed out");
}

export async function withdrawYieldTokens(
  token: string,
  amount: number,
  authToken: string
): Promise<{ status: string; signature?: string; error?: string }> {
  const res = await fetch("/api/agents/yield/wallet/withdraw", {
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
  return data as { status: string; signature?: string; error?: string };
}
