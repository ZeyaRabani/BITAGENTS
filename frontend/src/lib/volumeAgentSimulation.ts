import { getAgentBySlug } from "@/lib/agentsCatalog";

const catalog = getAgentBySlug("volume");

export const VOLUME_AGENT = {
  id: "volume",
  name: catalog?.name ?? "Volume Agent",
  tagline: catalog?.tagline ?? "Jupiter volume · no pool setup",
  description:
    catalog?.description ??
    "Run volume campaigns with scheduled buy/sell cycles on tokens Jupiter can already swap.",
  platformFeeRate: 0.0025,
  platformFeeLabel: "0.25% per swap leg",
};

export const VOLUME_EXAMPLE_PROMPTS = [
  "Create campaign: swap 0.01 SOL -> BITAGENTS for 10 times every 1 minute",
  "List my volume campaigns",
] as const;
