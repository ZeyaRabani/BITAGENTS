export type AomiTestHealth = {
  status: string;
  agent: string;
  aomi_configured?: boolean;
  aomi_api_url?: string;
  circle_configured?: boolean;
  cluster?: string;
  max_send_sol?: number;
};

export type AomiTestWallet = {
  agent_wallet?: string | null;
  circle_configured?: boolean;
  cluster?: string;
  max_send_sol?: number;
  error?: string | null;
};

export type AomiTestSendResult = {
  status?: string;
  signature?: string;
  explorer_url?: string;
  agent_wallet?: string;
  destination?: string;
  amount_sol?: number;
  aomi_digest?: string;
  error?: string;
};

async function readJson(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.error === "string"
          ? detail.error
          : data.error ?? "Request failed";
    throw new Error(message);
  }
  return data;
}

export async function fetchAomiTestHealth(): Promise<AomiTestHealth | null> {
  try {
    const res = await fetch("/api/agents/aomi-test/health", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as AomiTestHealth;
  } catch {
    return null;
  }
}

export async function fetchAomiTestWallet(authToken: string): Promise<AomiTestWallet> {
  const res = await fetch("/api/agents/aomi-test/wallet", {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  return (await readJson(res)) as AomiTestWallet;
}

export async function sendAomiTestSol(
  authToken: string,
  body: { destination: string; amount_sol: number }
): Promise<AomiTestSendResult> {
  const res = await fetch("/api/agents/aomi-test/send", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  return (await readJson(res)) as AomiTestSendResult;
}

export async function sendAomiTestMessage(
  message: string,
  authToken: string,
  sessionId?: string
) {
  const res = await fetch("/api/agents/aomi-test/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  return readJson(res) as Promise<{ reply: string; session_id: string }>;
}
