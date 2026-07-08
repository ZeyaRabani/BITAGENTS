import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { KickstartCopilotConsole } from "@/components/agents/KickstartCopilotConsole";
import { KICKSTART_COPILOT } from "@/lib/kickstartCopilotConfig";

export const metadata: Metadata = {
  title: "EasyA Analysis Agent - BIT Agents",
  description:
    "Solana token analysis agent - live price, liquidity, holders, health scores, and risk checks.",
};

export default function KickstartCopilotPage() {
  return (
    <AppShell
      title={KICKSTART_COPILOT.name}
      subtitle={`${KICKSTART_COPILOT.tagline} · ${KICKSTART_COPILOT.description}`}
    >
      <KickstartCopilotConsole />
    </AppShell>
  );
}
