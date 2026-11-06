import type { LucideIcon } from "lucide-react";
import { ArrowLeftRight, Crosshair, Landmark } from "lucide-react";

export type AgentCategory = "Monitor" | "Research" | "Alerts" | "Automation" | "Trading";

export type AgentIconId = "swap" | "fund" | "sniper";

export const AGENT_ICONS: Record<AgentIconId, LucideIcon> = {
  swap: ArrowLeftRight,
  fund: Landmark,
  sniper: Crosshair,
};

export type MarketplaceAgent = {
  id: string;
  slug: string;
  name: string;
  category: AgentCategory;
  description: string;
  tagline: string;
  pricePerTask?: string;
  runs?: string;
  volumeSol?: string;
  rating: number;
  iconId: AgentIconId;
  available: boolean;
  model?: string;
  cluster?: string;
};

export const FEATURED_AGENTS: MarketplaceAgent[] = [
  {
    id: "dca",
    slug: "dca",
    name: "DCA Agent",
    category: "Trading",
    description:
      "Recurring Jupiter buys. Each swap is simulated on Aomi before the Circle wallet signs it.",
    tagline: "Jupiter buy · Aomi fork · Circle sign",
    pricePerTask: "0.5% / tx",
    runs: "-",
    volumeSol: "-",
    rating: 4.9,
    iconId: "swap",
    available: true,
    model: "meta-llama/llama-3.3-70b-instruct",
    cluster: "mainnet",
  },
  {
    id: "hedge-fund",
    slug: "hedge-fund",
    name: "Hedge Fund Agent",
    category: "Trading",
    description:
      "Sized Jupiter buys and sells from a dedicated Circle wallet. Aomi simulates each swap before Circle signs.",
    tagline: "Buy or sell · Aomi fork · Circle sign",
    pricePerTask: "Aomi gate",
    runs: "-",
    volumeSol: "-",
    rating: 4.8,
    iconId: "fund",
    available: true,
    model: "meta-llama/llama-3.3-70b-instruct",
    cluster: "mainnet",
  },
  {
    id: "sniper",
    slug: "sniper",
    name: "Sniper Agent",
    category: "Trading",
    description:
      "SOL entries into a token after a size cap and a mint-authority check. Aomi simulates the swap before Circle signs.",
    tagline: "SOL entry · renounce check · Aomi fork",
    pricePerTask: "Aomi gate",
    runs: "-",
    volumeSol: "-",
    rating: 4.7,
    iconId: "sniper",
    available: true,
    model: "meta-llama/llama-3.3-70b-instruct",
    cluster: "mainnet",
  },
];

export function getAgentBySlug(slug: string): MarketplaceAgent | undefined {
  return FEATURED_AGENTS.find((agent) => agent.slug === slug);
}
