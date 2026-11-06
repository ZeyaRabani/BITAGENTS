import type { Metadata } from "next";
import { DefiAgentPage } from "@/components/agents/DefiAgentPage";
import { DEFI_AGENTS } from "@/lib/defiAgentsConfig";

const config = DEFI_AGENTS["liquidity"];

export const metadata: Metadata = {
  title: "Liquidity / LP Agent - BIT Agents",
  description: config.description,
};

export default function Page() {
  return <DefiAgentPage slug="liquidity" />;
}
