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
import { withdrawVolumeTokens, type UserDepositBalances } from "@/lib/volumeWalletClient";

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
  const [userBalances, setUserBalances] = useState<UserDepositBalances | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [withdrawError, setWithdrawError] = useState<string | null>(null);
  const [withdrawSuccess, setWithdrawSuccess] = useState<string | null>(null);

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

  async function withdrawAll() {
    if (!token || !userBalances) return;
    const toWithdraw = userBalances.balances.filter((row) => (row.withdrawable ?? row.available) > 0);
    if (toWithdraw.length === 0) return;

    setWithdrawBusy(true);
    setWithdrawError(null);
    setWithdrawSuccess(null);
    try {
      for (const row of toWithdraw) {
        await withdrawVolumeTokens(row.token, row.withdrawable ?? row.available, token);
      }
      setWithdrawSuccess("Withdrawal sent — funds are on their way back to your wallet.");
      setRefreshTick((t) => t + 1);
    } catch (err) {
      setWithdrawError(err instanceof Error ? err.message : "Withdraw failed");
    } finally {
      setWithdrawBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Buy and sell volume for the <strong className="text-foreground">BITAGENTS token</strong>, paid for
          in SOL. Deposit SOL below, then press one button to start. Platform fee is{" "}
          <strong className="text-foreground">{VOLUME_AGENT.platformFeeLabel}</strong>.
        </p>
      </div>

      {authError && (
        <div className="bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      {publicKey && authBusy && (
        <div className="bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to authenticate.
        </div>
      )}

      <VolumeAgentDeposit
        cluster={cluster}
        authToken={token}
        refreshTick={refreshTick}
        onBalancesChange={setUserBalances}
      />

      {!publicKey && (
        <div className="bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet above, deposit SOL, then start a campaign below.
        </div>
      )}

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to continue.
        </div>
      )}

      {userBalances && userBalances.balances.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 bg-surface/40 px-4 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            <span className="text-foreground">
              {userBalances.user_wallet.slice(0, 4)}…{userBalances.user_wallet.slice(-4)}
            </span>{" "}
            · {userBalances.balances.length} deposited token{userBalances.balances.length === 1 ? "" : "s"}
          </div>
          <button
            type="button"
            disabled={withdrawBusy || !userBalances.balances.some((row) => (row.withdrawable ?? row.available) > 0)}
            onClick={() => void withdrawAll()}
            className="px-3 py-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-signal transition hover:bg-signal/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {withdrawBusy ? "Withdrawing…" : "Withdraw all to my wallet"}
          </button>
        </div>
      )}

      {withdrawError && <p className="font-mono text-[11px] text-warn">{withdrawError}</p>}
      {withdrawSuccess && <p className="font-mono text-[11px] text-signal">{withdrawSuccess}</p>}

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
                className="flex flex-col gap-2 bg-background/60 px-4 py-4 text-left transition hover:bg-surface hover:text-signal disabled:cursor-not-allowed disabled:opacity-40"
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
