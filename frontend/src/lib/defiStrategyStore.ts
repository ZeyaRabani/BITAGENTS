import type { DefiAgentSlug } from "@/lib/defiAgentsConfig";

export type DefiStrategyRecord = {
  id: string;
  agentSlug: DefiAgentSlug;
  status: "active" | "paused" | "closed";
  createdAt: string;
  params: Record<string, string>;
  note?: string;
};

function storageKey(slug: DefiAgentSlug, wallet: string) {
  return `bitagents-defi-strategies:${slug}:${wallet}`;
}

export function loadDefiStrategies(slug: DefiAgentSlug, wallet: string): DefiStrategyRecord[] {
  if (typeof window === "undefined" || !wallet) return [];
  try {
    const raw = window.localStorage.getItem(storageKey(slug, wallet));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as DefiStrategyRecord[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveDefiStrategies(
  slug: DefiAgentSlug,
  wallet: string,
  strategies: DefiStrategyRecord[]
) {
  if (typeof window === "undefined" || !wallet) return;
  try {
    window.localStorage.setItem(storageKey(slug, wallet), JSON.stringify(strategies));
  } catch {
    // ignore
  }
}

export function createDefiStrategy(
  slug: DefiAgentSlug,
  wallet: string,
  params: Record<string, string>,
  note?: string
): DefiStrategyRecord[] {
  const next: DefiStrategyRecord = {
    id: `str_${Date.now().toString(36)}`,
    agentSlug: slug,
    status: "active",
    createdAt: new Date().toISOString(),
    params,
    note,
  };
  const all = [next, ...loadDefiStrategies(slug, wallet)];
  saveDefiStrategies(slug, wallet, all);
  return all;
}

export function updateDefiStrategyStatus(
  slug: DefiAgentSlug,
  wallet: string,
  id: string,
  status: DefiStrategyRecord["status"]
): DefiStrategyRecord[] {
  const all = loadDefiStrategies(slug, wallet).map((item) =>
    item.id === id ? { ...item, status } : item
  );
  saveDefiStrategies(slug, wallet, all);
  return all;
}
