"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { YourAgentsList } from "@/components/agents/builder/YourAgents";
import { WalletGate } from "@/components/agents/builder/BuilderUi";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";

export function YourAgentsPage() {
  const { busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();

  return (
    <AppShell
      title="My Agents"
      subtitle="Strategies you composed and deployed from Launch Agent."
    >
      <div className="space-y-6">
        <WalletGate
          authBusy={authBusy}
          authError={authError}
          isAuthenticated={isAuthenticated}
          purpose="list the strategies you built"
        />
        {isAuthenticated ? (
          <YourAgentsList />
        ) : (
          <p className="font-mono text-xs text-muted-foreground">
            Connect your wallet and sign in to see agents owned by this address.
          </p>
        )}
        <Link
          href="/launch-agent"
          className="inline-flex items-center border border-grid px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal hover:text-signal"
        >
          Create an agent
        </Link>
      </div>
    </AppShell>
  );
}
