import {
  mergeTransactions,
  parseActionResult,
  type ParsedTransaction,
} from "@/lib/dcaActionResults";

export type VolumeAgentAction = {
  tool: string;
  args: Record<string, unknown>;
  result: string;
};

export type VolumeAgentHealth = {
  status: string;
  agent?: string;
  model?: string;
  cluster?: string;
  trading_wallet?: string | null;
  trading_wallet_configured?: boolean;
  platform_fee_rate?: number;
  pool_creation_cost_sol?: number;
  pricing?: string;
  detail?: string;
};

export type VolumeAgentChatResponse = {
  reply: string;
  session_id: string;
  actions: VolumeAgentAction[];
};

export type AgentAction = {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  status: "running" | "done" | "error";
  result: string;
  error?: string;
  transactions: ParsedTransaction[];
};

async function readJsonResponse(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text();
  if (!text.trim()) {
    throw new Error(`Empty response from Volume agent API (${res.status})`);
  }
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    const snippet = text.trim().slice(0, 180);
    throw new Error(`Volume agent API returned non-JSON (${res.status}): ${snippet}`);
  }
}

export async function fetchVolumeAgentHealth(): Promise<VolumeAgentHealth | null> {
  try {
    const res = await fetch("/api/agents/volume/health", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as VolumeAgentHealth;
  } catch {
    return null;
  }
}

export async function sendVolumeAgentMessage(
  message: string,
  authToken: string,
  sessionId?: string
): Promise<VolumeAgentChatResponse> {
  const res = await fetch("/api/agents/volume/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
  });

  const data = await readJsonResponse(res);
  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : "Request failed";
    throw new Error(detail);
  }

  return data as VolumeAgentChatResponse;
}

export function mapVolumeApiActions(actions: VolumeAgentAction[]): AgentAction[] {
  return actions.map((action, index) => {
    const parsed = parseActionResult(action.result);
    return {
      id: `volume-api-${Date.now()}-${index}`,
      tool: action.tool,
      args: action.args ?? {},
      status: parsed.hasError ? "error" : "done",
      result: action.result,
      error: parsed.error,
      transactions: parsed.transactions,
    };
  });
}

export { mergeTransactions, type ParsedTransaction };
