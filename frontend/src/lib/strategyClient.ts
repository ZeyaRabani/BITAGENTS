export type StrategyPlan = {
  id: string;
  name: string;
  status: string;
  input_token: string;
  output_token: string;
  amount_per_buy: number;
  interval: string;
  total_budget: number;
  max_executions: number;
  executions_count: number;
  spent_so_far: number;
  next_execution_at: string;
  slippage_bps: number;
};

export type StrategyConfiguration = {
  name: string;
  input_token: string;
  output_token: string;
  amount_per_buy: number;
  interval: string;
  total_budget: number;
  max_executions: number;
  slippage_bps: number;
  start_immediately?: boolean;
};

export type StrategyExecution = {
  amount?: number;
  platform_fee?: number;
  result?: {
    status?: string;
    output_amount?: number;
    estimated_output?: number;
    receipt?: string;
    signature?: string;
  };
};

async function strategyFetch(
  path: string,
  authToken: string,
  init?: { method?: string; body?: unknown }
) {
  const res = await fetch(`/api/agents/strategies${path}`, {
    method: init?.method ?? "GET",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${authToken}`,
      ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const detail = data.detail ?? data.error ?? `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (typeof data.error === "string") throw new Error(data.error);
  return data;
}

export async function fetchStrategiesCatalog(authToken: string) {
  return strategyFetch("", authToken);
}

export async function listDcaPlans(authToken: string) {
  const data = await strategyFetch("/dca/plans", authToken);
  return (data.plans as StrategyPlan[]) ?? [];
}

export async function getDcaPlan(authToken: string, planId: string) {
  const data = await strategyFetch(`/dca/plans/${encodeURIComponent(planId)}`, authToken);
  return (data.plan as StrategyPlan | undefined) ?? (data as unknown as StrategyPlan);
}

export async function createDcaPlan(authToken: string, configuration: StrategyConfiguration) {
  const data = await strategyFetch("/dca/plans", authToken, {
    method: "POST",
    body: { configuration },
  });
  return {
    plan: data.plan as StrategyPlan,
    first_execution: data.first_execution as Record<string, unknown> | undefined,
    status: data.status as string | undefined,
  };
}

export async function updateDcaPlan(
  authToken: string,
  planId: string,
  configuration: Partial<StrategyConfiguration>
) {
  return strategyFetch(`/dca/plans/${encodeURIComponent(planId)}`, authToken, {
    method: "PATCH",
    body: { configuration },
  });
}

export async function setDcaPlanStatus(
  authToken: string,
  planId: string,
  action: "pause" | "resume" | "cancel"
) {
  return strategyFetch(`/dca/plans/${encodeURIComponent(planId)}/status`, authToken, {
    method: "POST",
    body: { action },
  });
}

export async function getDcaPlanExecutions(authToken: string, planId: string) {
  const data = await strategyFetch(`/dca/plans/${encodeURIComponent(planId)}/executions`, authToken);
  return (data.executions as StrategyExecution[]) ?? [];
}

export async function previewDcaBuy(authToken: string, planId: string) {
  return strategyFetch("/dca/run", authToken, {
    method: "POST",
    body: { plan_id: planId, mode: "preview" },
  });
}
