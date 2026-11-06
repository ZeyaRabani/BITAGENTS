import type { MarketplaceAgent } from "@/lib/agentsCatalog";
import type { LaunchedAgent } from "@/lib/launchAgentClient";

export function mapLaunchedToMarketplaceAgent(agent: LaunchedAgent): MarketplaceAgent {
  const tagline =
    agent.description.trim() ||
    (agent.price_per_month_sol != null
      ? `${agent.price_per_month_sol} SOL / month`
      : "Community-launched agent");

  return {
    id: `launched-${agent.id}`,
    slug: `launched-${agent.id}`,
    name: agent.name,
    category: "Automation",
    description: agent.description || agent.task,
    tagline,
    pricePerTask:
      agent.price_per_month_sol != null ? `${agent.price_per_month_sol} SOL / mo` : undefined,
    rating: 0,
    iconId: "bot",
    available: true,
    verified: false,
    source: "launched",
    href: `/agents/launched/${agent.id}`,
  };
}

export function buildLaunchPreviewAgent(input: {
  name: string;
  description: string;
  task: string;
  visibility: "public" | "private";
  pricePerMonth: string;
}): MarketplaceAgent {
  const name = input.name.trim() || "Untitled agent";
  const description = input.description.trim();
  const task = input.task.trim();
  const price = Number(input.pricePerMonth);
  const priceLabel =
    input.visibility === "public" && Number.isFinite(price) && price > 0
      ? `${price} SOL / mo`
      : undefined;

  return {
    id: "preview-draft",
    slug: "preview-draft",
    name,
    category: "Automation",
    description: description || task || "Your agent description will appear here.",
    tagline:
      description ||
      (task ? task.slice(0, 80) + (task.length > 80 ? "…" : "") : "Marketplace card preview"),
    pricePerTask: priceLabel,
    rating: 0,
    iconId: "bot",
    available: false,
    verified: false,
    source: "launched",
  };
}
