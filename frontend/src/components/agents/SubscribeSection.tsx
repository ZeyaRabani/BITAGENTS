"use client";

import { useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { Panel } from "@/components/AppShell";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import {
  confirmSubscriptionNotify,
  fetchAgentSubscription,
  getSubscriptionTelegramStatus,
  startSubscriptionTelegram,
  testSubscriptionNotify,
  type AgentSubscription,
  type LaunchedAgentRecord,
} from "@/lib/launchpadBuilderClient";

/** Lets anyone adopt a public agent and set up their own Telegram
 * destination, without touching the template's own logic -- the reuse
 * model: one agent, many subscribers, each with their own notify setup. */
export function SubscribeSection({ agent }: { agent: LaunchedAgentRecord }) {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError } = useDcaWalletAuth();
  const [subscription, setSubscription] = useState<AgentSubscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [telegramLink, setTelegramLink] = useState<string | null>(null);
  const [testSent, setTestSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    void fetchAgentSubscription(agent.id, token).then((sub) => {
      setSubscription(sub);
      setLoading(false);
    });
  }, [agent.id, token]);

  const linked = subscription?.notify_channel === "telegram" && !!subscription.notify_destination;
  const verified = !!subscription?.notify_verified_at;

  useEffect(() => {
    if (!telegramLink || linked || !token) return;
    const interval = setInterval(async () => {
      const status = await getSubscriptionTelegramStatus(agent.id, token);
      if (status.linked) {
        const fresh = await fetchAgentSubscription(agent.id, token);
        setSubscription(fresh);
        setMsg("Telegram connected — click Send Test below.");
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [telegramLink, linked, agent.id, token]);

  async function connectTelegram() {
    if (!token) return;
    setBusy(true);
    setMsg(null);
    const { ok, data } = await startSubscriptionTelegram(agent.id, token);
    setBusy(false);
    if (ok) {
      setTelegramLink(data.deep_link);
      setTestSent(false);
      setMsg("Click the link, press Start in Telegram, then wait a moment.");
    } else {
      setMsg(data.detail ?? "Failed to start Telegram connect.");
    }
  }

  async function sendTest() {
    if (!token) return;
    setBusy(true);
    setMsg(null);
    const { data } = await testSubscriptionNotify(agent.id, token);
    setBusy(false);
    setTestSent(!!data.ok);
    setMsg(data.ok ? "Test sent — check Telegram, then confirm below." : data.error ?? "Test send failed.");
  }

  async function confirmReceived() {
    if (!token) return;
    setBusy(true);
    setMsg(null);
    const { ok, data } = await confirmSubscriptionNotify(agent.id, token);
    setBusy(false);
    if (ok) {
      setSubscription(data);
      setMsg("Confirmed — you'll now get notified by this agent.");
    } else {
      setMsg(data.detail ?? "Could not confirm.");
    }
  }

  if (!publicKey) {
    return (
      <Panel title="Get notified by this agent">
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">Connect your wallet to subscribe to this agent's alerts.</p>
          <WalletMultiButton className="wallet-adapter-button-trigger!" />
        </div>
      </Panel>
    );
  }

  if (authError) {
    return (
      <Panel title="Get notified by this agent">
        <p className="font-mono text-xs text-warn">Wallet sign-in: {authError}</p>
      </Panel>
    );
  }

  if (authBusy || loading) {
    return (
      <Panel title="Get notified by this agent">
        <p className="font-mono text-xs text-muted-foreground">Loading…</p>
      </Panel>
    );
  }

  if (verified) {
    return (
      <Panel title="Get notified by this agent">
        <p className="text-sm text-signal">
          You're subscribed — alerts go to your connected Telegram.
        </p>
      </Panel>
    );
  }

  return (
    <Panel title="Get notified by this agent">
      <p className="mb-3 text-sm text-muted-foreground">
        Adopt this agent — nothing to build, just tell it where to alert you.
      </p>

      {linked ? (
        <p className="text-xs text-signal">Telegram connected.</p>
      ) : (
        <button
          onClick={connectTelegram}
          disabled={busy}
          className="px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-foreground disabled:opacity-40"
        >
          {telegramLink ? "Re-generate link" : "Connect Telegram"}
        </button>
      )}
      {telegramLink && !linked && (
        <a href={telegramLink} target="_blank" rel="noreferrer" className="mt-2 block text-xs text-signal underline">
          {telegramLink}
        </a>
      )}

      {linked && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={sendTest}
            disabled={busy}
            className="px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-foreground disabled:opacity-40"
          >
            Send Test
          </button>
          <button
            onClick={confirmReceived}
            disabled={busy || !testSent}
            className="bg-signal/10 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-signal disabled:opacity-40"
          >
            I received it — Confirm
          </button>
        </div>
      )}
      {msg && <p className="mt-2 text-xs text-muted-foreground">{msg}</p>}
    </Panel>
  );
}
