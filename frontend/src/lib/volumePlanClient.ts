import { explorerUrlForSignature } from "@/lib/dcaActionResults";

export type VolumeCampaignSummary = {
  id: string;
  name: string;
  base_token: string;
  quote_token: string;
  base_mint?: string;
  quote_mint?: string;
  trade_amount: number;
  interval: string;
  status: string;
  executions_count: number;
  max_executions: number;
  total_budget?: number | null;
  slippage_bps?: number;
  spent_so_far: number;
  pool_address?: string | null;
  pool_exists?: boolean;
  pool_creation_cost_sol?: number;
  platform_fee_rate?: number;
  next_execution_at?: string | null;
  consecutive_failures?: number;
  last_error?: { leg?: string; error?: string; available?: number } | null;
  infrastructure?: {
    pool_creation_error?: { error?: string };
    last_check?: { message?: string; source?: string; jupiter_route?: boolean };
    initial_check?: { message?: string; source?: string; jupiter_route?: boolean };
  };
};

export type VolumeCampaignsResponse = {
  campaigns: VolumeCampaignSummary[];
  count: number;
  user_wallet: string;
};

export type VolumePoolCheck = {
  pool_exists: boolean;
  pool_address?: string | null;
  pool_creation_cost_sol?: number;
  message?: string;
  source?: string;
  jupiter_route?: boolean;
  pool_type?: string | null;
  meteora_url?: string;
  base_token?: string;
  quote_token?: string;
  base_mint?: string;
  quote_mint?: string;
  pair?: string;
  pool?: {
    name?: string;
    bin_step?: number;
    trade_volume_24h?: number;
    liquidity?: number;
  };
};

export type VolumePoolEnsureResult = VolumePoolCheck & {
  status?: string;
  signature?: string;
  explorer_url?: string;
  error?: string;
};

export type VolumeCampaignExecutionsResponse = {
  campaign_id: string;
  name: string;
  executions_count: number;
  spent_so_far: number;
  executions: Array<{
    at?: string;
    cycle?: number;
    trade_amount?: number;
    platform_fee_rate?: number;
    pool_address?: string;
    buy?: { signature?: string; explorer_url?: string; status?: string };
    sell?: { signature?: string; explorer_url?: string; status?: string };
  }>;
  pool_address?: string | null;
};

export type CreateVolumeCampaignInput = {
  base_token: string;
  quote_token?: string;
  trade_amount: number;
  interval: string;
  max_executions: number;
  name?: string;
  total_budget?: number;
  slippage_bps?: number;
  seed_token_amount?: number;
};

async function readError(res: Response): Promise<string> {
  const data = await res.json().catch(() => ({}));
  return typeof data.detail === "string"
    ? data.detail
    : typeof data.error === "string"
      ? data.error
      : "Request failed";
}

export async function fetchVolumeCampaigns(
  authToken: string,
  params?: { active_only?: boolean; status?: string }
): Promise<VolumeCampaignsResponse> {
  const search = new URLSearchParams();
  if (params?.active_only) search.set("active_only", "true");
  if (params?.status) search.set("status", params.status);
  const qs = search.toString();
  const res = await fetch(`/api/agents/volume/campaigns${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as VolumeCampaignsResponse;
}

export async function createVolumeCampaign(
  input: CreateVolumeCampaignInput,
  authToken: string
): Promise<{ status: string; campaign: VolumeCampaignSummary; message?: string }> {
  const res = await fetch("/api/agents/volume/campaigns", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as { status: string; campaign: VolumeCampaignSummary; message?: string };
}

export async function updateVolumeCampaignStatus(
  campaignId: string,
  action: "pause" | "resume" | "cancel",
  authToken: string
): Promise<{ status: string; campaign: VolumeCampaignSummary }> {
  const res = await fetch(`/api/agents/volume/campaigns/${encodeURIComponent(campaignId)}/status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ action }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as { status: string; campaign: VolumeCampaignSummary };
}

export async function provisionVolumeCampaign(
  campaignId: string,
  authToken: string
): Promise<{ status?: string; pool_address?: string; message?: string; error?: string }> {
  const res = await fetch(
    `/api/agents/volume/campaigns/${encodeURIComponent(campaignId)}/provision`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${authToken}` },
    }
  );
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as { status?: string; pool_address?: string; message?: string };
}

export async function fetchVolumeCampaignExecutions(
  campaignId: string,
  authToken: string
): Promise<VolumeCampaignExecutionsResponse> {
  const res = await fetch(
    `/api/agents/volume/campaigns/${encodeURIComponent(campaignId)}/executions`,
    {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    }
  );
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as VolumeCampaignExecutionsResponse;
}

export async function checkVolumePool(
  baseToken: string,
  quoteToken = "SOL"
): Promise<VolumePoolCheck> {
  const params = new URLSearchParams({
    base_token: baseToken.trim(),
    quote_token: quoteToken.trim() || "SOL",
  });
  const res = await fetch(`/api/agents/volume/pool/check?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as VolumePoolCheck;
}

export async function ensureVolumeMeteoraPool(
  baseToken: string,
  quoteToken: string,
  authToken: string,
  createIfMissing = false
): Promise<VolumePoolEnsureResult> {
  const res = await fetch("/api/agents/volume/pool/ensure", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      base_token: baseToken.trim(),
      quote_token: quoteToken.trim() || "SOL",
      create_if_missing: createIfMissing,
    }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as VolumePoolEnsureResult;
}

export function executionExplorerUrl(signature?: string, cluster?: string) {
  if (!signature) return undefined;
  return explorerUrlForSignature(signature, cluster);
}
