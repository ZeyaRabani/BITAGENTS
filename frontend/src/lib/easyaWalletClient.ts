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
  any_spl_token?: boolean;
  common_tokens?: string[];
  platform_fee_pct?: string;
  platform_fee_rate?: number;
  wallet_provider?: "circle" | "local";
  per_user_wallet?: boolean;
  circle_error?: string;
};

export type EasyaDepositRecord = {
  id: string;
  user_wallet: string;
  signature: string;
  token: string;
  amount: number;
  verified_at: string;
  explorer_url?: string;
};

export type EasyaDepositVerifyResponse = {
  status: string;
  message?: string;
  deposits?: EasyaDepositRecord[];
  balances?: EasyaUserBalances;
};

export async function fetchEasyaAgentWallet(
  authToken: string
): Promise<EasyaAgentWalletInfo | null> {
  try {
    const res = await fetch("/api/agents/kickstart-copilot/wallet/agent", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as EasyaAgentWalletInfo;
  } catch {
    return null;
  }
}

export async function fetchEasyaUserBalances(authToken: string): Promise<EasyaUserBalances | null> {
  try {
    const res = await fetch("/api/agents/kickstart-copilot/wallet/balance", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const data = await res.json();
    if (!res.ok) {
      const detail = typeof data.error === "string" ? data.error : "Failed to load balances";
      throw new Error(detail);
    }
    return data as EasyaUserBalances;
  } catch (err) {
    console.error("fetchEasyaUserBalances failed:", err);
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
    throw new Error(typeof data.error === "string" ? data.error : "Deposit verification failed");
  }
  return data as EasyaDepositVerifyResponse;
}

function isRetryableVerifyError(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("not found") ||
    lower.includes("wait for confirmation") ||
    lower.includes("offline") ||
    lower.includes("503") ||
    lower.includes("could not save") ||
    lower.includes("network") ||
    lower.includes("unknown")
  );
}

/** Verify a deposit signature with retries while the RPC indexes the transaction. */
export async function verifyEasyaDepositWithRetry(
  signature: string,
  authToken: string,
  maxAttempts = 12
): Promise<EasyaDepositVerifyResponse> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      return await verifyEasyaDeposit(signature, authToken);
    } catch (err) {
      lastError = err instanceof Error ? err : new Error("Deposit verification failed");
      if (!isRetryableVerifyError(lastError.message) || attempt >= maxAttempts - 1) {
        throw lastError;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
    }
  }
  throw lastError ?? new Error("Deposit verification failed");
}

export async function withdrawEasyaTokens(token: string, amount: number, authToken: string) {
  const res = await fetch("/api/agents/kickstart-copilot/wallet/withdraw", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ token, amount }),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : "Withdrawal failed";
    throw new Error(detail);
  }
  return data as {
    status: string;
    signature?: string;
    explorer_url?: string;
    balances?: EasyaUserBalances;
  };
}
