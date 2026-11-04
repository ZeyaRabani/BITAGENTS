import type { Metadata } from "next";
import { DefiAgentPage } from "@/components/agents/DefiAgentPage";
import { DEFI_AGENTS } from "@/lib/defiAgentsConfig";

const config = DEFI_AGENTS["copy-trade"];

export const metadata: Metadata = {
  title: "Copy-Trade Agent - BIT Agents",
  description: config.description,
};

export default function Page() {
  return <DefiAgentPage slug="copy-trade" />;
}
