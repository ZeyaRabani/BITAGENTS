"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import {
  confirmAgentNotify,
  fetchAgentPriceWatch,
  fetchMyLaunchedAgents,
  getAgentNotifyTelegramStatus,
  setAgentNotifyEmail,
  startAgentNotifyTelegram,
  testAgentNotify,
  updateLaunchedAgent,
  type LaunchedAgentRecord,
  type PriceWatch,
} from "@/lib/launchpadBuilderClient";

function NotifySection({ agent, token, onUpdated }: { agent: LaunchedAgentRecord; token: string; onUpdated: (a: LaunchedAgentRecord) => void }) {
  const [channel, setChannel] = useState<"email" | "telegram">(agent.notify_channel ?? "email");
  const [email, setEmail] = useState(agent.notify_channel === "email" ? agent.notify_destination ?? "" : "");
  const [telegramLink, setTelegramLink] = useState<string | null>(null);
  const [telegramLinked, setTelegramLinked] = useState(agent.notify_channel === "telegram");
  const [testSent, setTestSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!telegramLink || telegramLinked) return;
    const interval = setInterval(async () => {
      const status = await getAgentNotifyTelegramStatus(agent.id, token);
      if (status.linked) {
        setTelegramLinked(true);
        setMsg("Telegram connected — click Send Test below.");
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [telegramLink, telegramLinked, agent.id, token]);

  async function saveEmail() {
    setBusy(true);
    setMsg(null);
    const { ok, data } = await setAgentNotifyEmail(agent.id, email.trim(), token);
    setBusy(false);
    setTestSent(false);
    setMsg(ok ? "Email set — click Send Test to verify it." : data.detail ?? "Failed to set email.");
  }

  async function connectTelegram() {
    setBusy(true);
    setMsg(null);
    const { ok, data } = await startAgentNotifyTelegram(agent.id, token);
    setBusy(false);
    if (ok) {
      setTelegramLink(data.deep_link);
      setTelegramLinked(false);
      setTestSent(false);
      setMsg("Click the link, press Start in Telegram, then wait a moment.");
    } else {
      setMsg(data.detail ?? "Failed to start Telegram connect.");
    }
  }

  async function sendTest() {
    setBusy(true);
    setMsg(null);
    const { ok, data } = await testAgentNotify(agent.id, token);
    setBusy(false);
    setTestSent(!!data.ok);
    setMsg(data.ok ? "Test sent — check your inbox/Telegram, then confirm below." : data.error ?? "Test send failed.");
  }

  async function confirmReceived() {
    setBusy(true);
    setMsg(null);
    const { ok, data } = await confirmAgentNotify(agent.id, token);
    setBusy(false);
    if (ok) {
      onUpdated(data);
      setMsg("Confirmed — this agent will now notify this destination.");
    } else {
      setMsg(data.detail ?? "Could not confirm.");
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {(["email", "telegram"] as const).map((c) => (
          <button
            key={c}
            onClick={() => setChannel(c)}
            className={`border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] ${
              channel === c ? "border-signal text-signal" : "border-grid text-muted-foreground"
            }`}
          >
            {c === "email" ? "Email" : "Telegram"}
          </button>
        ))}
      </div>

      {channel === "email" ? (
        <div className="flex gap-2">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="flex-1 border border-grid bg-background px-3 py-2 text-sm text-foreground"
          />
          <button
            onClick={saveEmail}
            disabled={busy || !email.trim()}
            className="border border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-foreground disabled:opacity-40"
          >
            Set
          </button>
        </div>
      ) : telegramLinked ? (
        <p className="text-xs text-signal">Telegram connected.</p>
      ) : (
        <button
          onClick={connectTelegram}
          disabled={busy}
          className="border border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-foreground disabled:opacity-40"
        >
          {telegramLink ? "Re-generate link" : "Connect Telegram"}
        </button>
      )}
      {telegramLink && !telegramLinked && (
        <a href={telegramLink} target="_blank" rel="noreferrer" className="block text-xs text-signal underline">
          {telegramLink}
        </a>
      )}

      {((channel === "email" && agent.notify_destination) || telegramLinked) && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            onClick={sendTest}
            disabled={busy}
            className="border border-grid px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-foreground disabled:opacity-40"
          >
            Send Test
          </button>
          <button
            onClick={confirmReceived}
            disabled={busy || !testSent}
            className="border border-signal bg-signal/10 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-signal disabled:opacity-40"
          >
            I received it — Confirm
          </button>
        </div>
      )}
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
    </div>
  );
}

const STATUS_LABEL: Record<LaunchedAgentRecord["status"], string> = {
  draft: "Draft — not launched",
  testing: "Testing (24h window before public listing)",
  live: "Live",
};

const STATUS_COLOR: Record<LaunchedAgentRecord["status"], string> = {
  draft: "text-muted-foreground",
  testing: "text-signal",
  live: "text-signal",
};

function AgentRow({ agent, token, onUpdated }: { agent: LaunchedAgentRecord; token: string; onUpdated: (a: LaunchedAgentRecord) => void }) {
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState(agent.description ?? "");
  const [priceWatch, setPriceWatch] = useState<PriceWatch | null>(null);
  const [threshold, setThreshold] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) return;
    fetchAgentPriceWatch(agent.id, token).then((pw) => {
      setPriceWatch(pw);
      if (pw) setThreshold(String(pw.threshold_pct));
    });
  }, [editing, agent.id, token]);

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const updates: { description?: string; threshold_pct?: number } = { description };
      if (priceWatch && threshold.trim()) {
        const parsed = Number(threshold);
        if (!Number.isNaN(parsed) && parsed > 0) updates.threshold_pct = parsed;
      }
      const updated = await updateLaunchedAgent(agent.id, updates, token);
      onUpdated(updated);
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="border border-grid bg-surface/40 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-bold">{agent.name ?? "Untitled agent"}</h3>
          <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            {agent.category ?? "Uncategorized"} {agent.handle ? `· @${agent.handle}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`font-mono text-[10px] uppercase tracking-[0.14em] ${STATUS_COLOR[agent.status]}`}>
            {STATUS_LABEL[agent.status]}
          </span>
          {agent.status !== "draft" && (
            <button
              onClick={() => setEditing((v) => !v)}
              className="border border-grid px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-foreground transition hover:border-signal hover:text-signal"
            >
              {editing ? "Cancel" : "Edit"}
            </button>
          )}
        </div>
      </div>

      {!editing && agent.description && (
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{agent.description}</p>
      )}

      {editing && (
        <div className="mt-4 space-y-3 border-t border-grid pt-4">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="mt-1 w-full resize-y border border-grid bg-background px-3 py-2 text-sm text-foreground"
            />
          </div>
          {priceWatch && (
            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                Alert threshold (%) — window resets when you change this
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                className="mt-1 w-32 border border-grid bg-background px-3 py-2 text-sm text-foreground"
              />
            </div>
          )}
          {saveError && <p className="text-xs text-destructive">{saveError}</p>}
          <button
            onClick={save}
            disabled={saving}
            className="border border-signal bg-signal/10 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-signal disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>

          <div className="border-t border-grid pt-4">
            <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Notification destination — change where THIS agent alerts you
            </label>
            <div className="mt-2">
              <NotifySection agent={agent} token={token} onUpdated={onUpdated} />
            </div>
          </div>
        </div>
      )}

      <div className="mt-4 border-t border-grid pt-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Notifications
        </div>
        {agent.notify_channel && agent.notify_destination ? (
          <p className="mt-1 text-sm">
            {agent.notify_channel === "email" ? "Email" : "Telegram"} → {agent.notify_destination}{" "}
            {agent.notify_verified_at ? (
              <span className="text-signal">· verified</span>
            ) : (
              <span className="text-destructive">· not yet verified</span>
            )}
          </p>
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">No notification channel set.</p>
        )}
      </div>
    </article>
  );
}

export default function MyAgentsPage() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, isAuthenticated } = useDcaWalletAuth();
  const [agents, setAgents] = useState<LaunchedAgentRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    fetchMyLaunchedAgents(token)
      .then(setAgents)
      .catch(() => setError("Could not load your agents."))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <div className="mb-8 border-b border-grid pb-6">
        <h1 className="font-display text-3xl font-bold leading-tight md:text-4xl">My agents</h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Every agent you've launched, whatever its status — this is the only place to find one
          again once the chat that created it has ended.
        </p>
      </div>

      {!publicKey ? (
        <div className="border border-grid bg-surface/40 p-5">
          <p className="text-sm text-muted-foreground">Connect your wallet to see your agents.</p>
          <div className="mt-3">
            <WalletMultiButton className="wallet-adapter-button-trigger!" />
          </div>
        </div>
      ) : authBusy || !isAuthenticated ? (
        <div className="border border-grid bg-surface/40 p-5">
          <p className="text-sm text-muted-foreground">Approve the wallet sign-in message to continue.</p>
        </div>
      ) : loading ? (
        <div className="py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
          Loading your agents…
        </div>
      ) : error ? (
        <div className="border border-grid bg-surface/40 p-5 text-sm text-destructive">{error}</div>
      ) : agents.length === 0 ? (
        <div className="border border-grid bg-surface/40 p-5">
          <p className="text-sm text-muted-foreground">You haven't launched an agent yet.</p>
          <Link
            href="/launch/create"
            className="mt-4 inline-flex items-center gap-2 bg-signal px-4 py-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90"
          >
            Launch an agent
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {agents.map((agent) => (
            <AgentRow
              key={agent.id}
              agent={agent}
              token={token!}
              onUpdated={(updated) =>
                setAgents((prev) => prev.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)))
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
