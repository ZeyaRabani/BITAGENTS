import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { MarketAgentConsole } from "@/components/agents/MarketAgentConsole";

export const metadata: Metadata = {
  title: "Sniper Agent - BIT Agents",
  description: "SOL entries after a mint check, with Aomi simulation before Circle signs.",
};

export default function SniperAgentPage() {
  return (
    <AppShell title="Sniper Agent">
      <MarketAgentConsole
        slug="sniper"
        title="Sniper Agent"
        intro="Connected to the Sniper agent. Entries spend SOL, reject a mint that still has authority, and go through Aomi before Circle signs."
        prompts={[
          "Snipe 0.05 SOL into BONK",
          "Set max buy to 0.2",
          "Require mint renounced",
        ]}
      />
    </AppShell>
  );
}
