import type { Metadata } from "next";
import { DefiAgentPage } from "@/components/agents/DefiAgentPage";
import { DEFI_AGENTS } from "@/lib/defiAgentsConfig";

const config = DEFI_AGENTS["treasury"];

export const metadata: Metadata = {
  title: "Treasury / Idle Cash Agent - BIT Agents",
  description: config.description,
};

export default function Page() {
  return <DefiAgentPage slug="treasury" />;
}
