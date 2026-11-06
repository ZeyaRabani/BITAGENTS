import type { Metadata } from "next";
import { DefiAgentPage } from "@/components/agents/DefiAgentPage";
import { DEFI_AGENTS } from "@/lib/defiAgentsConfig";

const config = DEFI_AGENTS["options"];

export const metadata: Metadata = {
  title: "Options / Structured Agent - BIT Agents",
  description: config.description,
};

export default function Page() {
  return <DefiAgentPage slug="options" />;
}
