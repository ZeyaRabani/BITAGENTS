"use client";

import { useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { Panel } from "@/components/AppShell";
import { VolumeAgentDeposit } from "@/components/agents/VolumeAgentDeposit";
import { VolumeCampaignPanel } from "@/components/agents/VolumeCampaignPanel";
import { VOLUME_AGENT } from "@/lib/volumeAgentSimulation";
import { fetchVolumeAgentHealth, type VolumeAgentHealth } from "@/lib/volumeAgentClient";
import { createVolumeCampaign } from "@/lib/volumePlanClient";
import { useVolumeWalletAuth } from "@/hooks/useVolumeWalletAuth";

const BITAGENTS_MINT = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY";

type Preset = {
  key: string;
  label: string;
  budgetLabel: string;
  description: string;
  trade_amount: number;
  interval: string;
  max_executions: number;
};

const PRESETS: Preset[] = [
  {
    key: "quick",
    label: "Quick test",
    budgetLabel: "~0.2 SOL",
    description: "10 small cycles, 1 minute apart. Good first run to see it working.",
    trade_amount: 0.01,
    interval: "1 minute",
    max_executions: 10,
  },
  {
    key: "standard",
    label: "Standard",
    budgetLabel: "~1 SOL",
    description: "25 cycles, 2 minutes apart. Steady volume over about an hour.",
    trade_amount: 0.02,
    interval: "2 minutes",
    max_executions: 25,
  },
  {
    key: "full_day",
    label: "Full day",
    budgetLabel: "~3 SOL",
    description: "40 cycles, 10 minutes apart. Spread out across most of a day.",
    trade_amount: 0.05,
    interval: "10 minutes",
    max_executions: 40,
  },
];

export function VolumeAgentSimpleConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useVolumeWalletAuth();
  const [health, setHealth] = useState<VolumeAgentHealth | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const cluster = health?.cluster;

  useEffect(() => {
    void fetchVolumeAgentHealth().then(setHealth);
  }, []);

  async function startCampaign(preset: Preset) {
    if (!token) return;
    setBusyKey(preset.key);
    setError(null);
    setSuccess(null);
    try {
      const result = await createVolumeCampaign(
        {
          base_token: BITAGENTS_MINT,
          quote_token: "SOL",
          trade_amount: preset.trade_amount,
          interval: preset.interval,
          max_executions: preset.max_executions,
          name: `BITAGENTS · ${preset.label}`,
        },
        token
      );
      setSuccess(result.message ?? `Campaign ${result.campaign.id} started.`);
      setRefreshTick((t) => t + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start campaign");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="border border-grid bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Buy and sell volume for the <strong className="text-foreground">BITAGENTS token</strong>, paid for
          in SOL. Deposit SOL below, then press one button to start. Platform fee is{" "}
          <strong className="text-foreground">{VOLUME_AGENT.platformFeeLabel}</strong>.
        </p>
        <p className="mt-2 font-mono text-[10px] text-muted-foreground">
          Need any SPL token + Meteora controls?{" "}
          <a href="/agents/volume" className="text-signal underline hover:text-foreground">
            Open full Volume Agent
          </a>
        </p>
      </div>

      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      {publicKey && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to authenticate.
        </div>
      )}

      <VolumeAgentDeposit
        cluster={cluster}
        authToken={token}
        refreshTick={refreshTick}
      />

      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet above, deposit SOL, then start a campaign below.
        </div>
      )}

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to continue.
        </div>
      )}

      <Panel title="Start a BITAGENTS volume campaign">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Pick a size. Each option buys and sells BITAGENTS with your deposited SOL on a timer — no
            pool setup or token addresses to enter, it's already wired to BITAGENTS.
          </p>

          <div className="grid gap-3 sm:grid-cols-3">
            {PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                disabled={!isAuthenticated || busyKey !== null}
                onClick={() => void startCampaign(preset)}
                className="flex flex-col gap-2 border border-grid bg-background/60 px-4 py-4 text-left transition hover:border-signal disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-signal">
                  {preset.label}
                </span>
                <span className="font-mono text-lg text-foreground">{preset.budgetLabel}</span>
                <span className="text-xs leading-relaxed text-muted-foreground">{preset.description}</span>
                <span className="mt-2 bg-signal px-3 py-2 text-center font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-primary-foreground">
                  {busyKey === preset.key ? "Starting…" : "Start this one"}
                </span>
              </button>
            ))}
          </div>

          {error && <p className="font-mono text-[11px] text-warn">{error}</p>}
          {success && <p className="font-mono text-[11px] text-signal">{success}</p>}
        </div>
      </Panel>

      {token && (
        <VolumeCampaignPanel
          authToken={token}
          cluster={cluster}
          refreshTick={refreshTick}
          onCampaignChange={() => setRefreshTick((t) => t + 1)}
        />
      )}
    </div>
  );
}
