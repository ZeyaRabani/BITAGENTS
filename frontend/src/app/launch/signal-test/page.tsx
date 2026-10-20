"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { AppShell, Panel } from "@/components/AppShell";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";

type Watch = {
  watch_id: string;
  symbol: string;
  profile: string;
  state: "neutral" | "armed" | "fired" | "cooldown";
  price_usd?: number;
  drop_pct: number;
  bounce_pct: number;
  lookback_minutes: number;
  sample_interval_seconds: number;
  armed_low_usd?: number | null;
  rolling_high?: number;
  rolling_low?: number;
};

const PROFILES = [
  { key: "fast_test", label: "Fast test (fires in minutes)", hint: "0.05% drop / 0.03% bounce, 2 min lookback -- pipeline test only" },
  { key: "test", label: "Test", hint: "0.3% drop / 0.2% bounce, 15 min lookback" },
  { key: "real", label: "Real strategy", hint: "10% drop / 5% bounce, 60 min lookback" },
] as const;

const STATE_COLOR: Record<Watch["state"], string> = {
  neutral: "text-muted-foreground",
  armed: "text-warn",
  fired: "text-signal",
  cooldown: "text-muted-foreground",
};

const STATE_LABEL: Record<Watch["state"], string> = {
  neutral: "Watching",
  armed: "Armed -- waiting for bounce",
  fired: "FIRED -- signal complete",
  cooldown: "Cooldown",
};

async function apiCall(path: string, token: string, init?: RequestInit) {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(init?.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? data.error ?? "Request failed");
  return data;
}

type ChatMessage = { id: string; role: "user" | "assistant"; content: string; actions?: unknown[] };

export default function SignalTestPage() {
  const { token, busy: authBusy, error: authError, signIn } = useDcaWalletAuth();
  const [agentId, setAgentId] = useState("");
  const [symbol, setSymbol] = useState("SOL");
  const [profile, setProfile] = useState<(typeof PROFILES)[number]["key"]>("fast_test");
  const [watch, setWatch] = useState<Watch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatSessionId, setChatSessionId] = useState<string | undefined>();
  const [chatBusy, setChatBusy] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (token) void signIn();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pollOnce = useCallback(async () => {
    if (!token || !agentId.trim() || !watch) return;
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/signal-watch/${watch.watch_id}`, token);
      setWatch((prev) => (prev ? { ...prev, ...data } : data));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Poll failed");
    }
  }, [token, agentId, watch]);

  useEffect(() => {
    if (!watch) return;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => void pollOnce(), 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watch?.watch_id]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, chatBusy]);

  async function sendChat() {
    const text = chatInput.trim();
    if (!token || !agentId.trim() || !text) return;
    setChatBusy(true);
    setChatMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: text }]);
    setChatInput("");
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/chat`, token, {
        method: "POST",
        body: JSON.stringify({ message: text, session_id: chatSessionId }),
      });
      setChatSessionId(data.session_id);
      setChatMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: data.reply ?? "(no reply)", actions: data.actions },
      ]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        { id: `e-${Date.now()}`, role: "assistant", content: `Error: ${err instanceof Error ? err.message : "request failed"}` },
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  async function startWatch() {
    if (!token || !agentId.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/signal-watch`, token, {
        method: "POST",
        body: JSON.stringify({ symbol, profile }),
      });
      setWatch(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start watch");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell
      title="Signal watch -- live test"
      subtitle="Watches a token for a drop-then-bounce price pattern. Signal only -- this does not place any trade."
    >
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Panel title="Start a watch">
          <div className="space-y-4">
            {!token && (
              <div className="rounded-xl border border-grid bg-surface/30 p-4 text-sm">
                <p className="text-muted-foreground">Connect and sign in with the wallet that owns the launched agent.</p>
                <div className="mt-3">
                  <WalletMultiButton />
                </div>
                {authBusy && <p className="mt-2 text-xs text-muted-foreground">Signing in...</p>}
                {authError && <p className="mt-2 text-xs text-warn">{authError}</p>}
              </div>
            )}

            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                Agent ID (must have the price_signal_watch module)
              </label>
              <input
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                placeholder="e.g. launch_abc123"
                className="mt-1 w-full rounded-xl border border-grid bg-background px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Symbol</label>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="mt-1 w-full rounded-xl border border-grid bg-background px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Profile</label>
              <div className="mt-2 space-y-2">
                {PROFILES.map((p) => (
                  <button
                    key={p.key}
                    onClick={() => setProfile(p.key)}
                    className={`block w-full rounded-xl border px-3 py-2 text-left text-sm transition ${
                      profile === p.key ? "border-signal bg-surface-2" : "border-grid bg-surface/30"
                    }`}
                  >
                    <div className="font-mono text-xs uppercase tracking-[0.1em]">{p.label}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{p.hint}</div>
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={startWatch}
              disabled={!token || !agentId.trim() || busy}
              className="w-full rounded-full bg-signal px-4 py-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-background disabled:opacity-40"
            >
              {busy ? "Starting..." : "Start watch"}
            </button>

            {error && <p className="text-xs text-warn">{error}</p>}
          </div>
        </Panel>

        <Panel title="Live status">
          {!watch ? (
            <p className="text-sm text-muted-foreground">Start a watch to see it update here every 3 seconds.</p>
          ) : (
            <div className="space-y-4">
              <div className="rounded-xl border border-grid bg-surface/30 p-4 text-center">
                <div className={`font-display text-2xl font-bold ${STATE_COLOR[watch.state]}`}>
                  {STATE_LABEL[watch.state]}
                </div>
                <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  {watch.symbol} -- {watch.profile} profile
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-grid bg-surface/30 p-3">
                  <div className="font-mono text-[9px] uppercase text-muted-foreground">Current price</div>
                  <div className="mt-1 font-display text-lg font-bold">
                    {watch.price_usd != null ? `$${watch.price_usd.toFixed(4)}` : "--"}
                  </div>
                </div>
                <div className="rounded-xl border border-grid bg-surface/30 p-3">
                  <div className="font-mono text-[9px] uppercase text-muted-foreground">Rolling high / low</div>
                  <div className="mt-1 font-mono text-sm">
                    {watch.rolling_high != null ? `$${watch.rolling_high.toFixed(4)}` : "--"} /{" "}
                    {watch.rolling_low != null ? `$${watch.rolling_low.toFixed(4)}` : "--"}
                  </div>
                </div>
                <div className="rounded-xl border border-grid bg-surface/30 p-3">
                  <div className="font-mono text-[9px] uppercase text-muted-foreground">Thresholds</div>
                  <div className="mt-1 font-mono text-sm">
                    {watch.drop_pct}% drop / {watch.bounce_pct}% bounce
                  </div>
                </div>
                <div className="rounded-xl border border-grid bg-surface/30 p-3">
                  <div className="font-mono text-[9px] uppercase text-muted-foreground">Sampling every</div>
                  <div className="mt-1 font-mono text-sm">{watch.sample_interval_seconds}s</div>
                </div>
              </div>

              {watch.state === "fired" && (
                <div className="rounded-xl bg-signal/10 p-4 text-sm text-signal">
                  Signal fired. This is where execution would happen -- not wired yet, so nothing was
                  bought or sold. A human still needs to place the trade.
                </div>
              )}

              <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
                Watch ID: {watch.watch_id}
              </p>
            </div>
          )}
        </Panel>
      </div>

      <div className="mt-6">
        <Panel title="Chat with the agent (real -- can deposit, watch, trade, withdraw)">
          <div className="flex max-h-125 flex-col gap-3 overflow-y-auto pr-1">
            {chatMessages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Try: &quot;What&apos;s my balance and deposit address?&quot; or, once a watch fires,
                &quot;Open a position&quot;.
              </p>
            )}
            {chatMessages.map((m) => (
              <div
                key={m.id}
                className={`rounded-xl px-4 py-3 text-sm whitespace-pre-wrap ${
                  m.role === "user" ? "ml-8 bg-surface/60" : "mr-8 bg-surface-2"
                }`}
              >
                <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                  {m.role === "user" ? "You" : "Agent"}
                </div>
                {m.content}
                {!!m.actions?.length && (
                  <div className="mt-2 font-mono text-[9px] text-muted-foreground">
                    tools called: {(m.actions as { tool: string }[]).map((a) => a.tool).join(", ")}
                  </div>
                )}
              </div>
            ))}
            {chatBusy && <p className="font-mono text-[10px] uppercase text-muted-foreground">Agent is thinking...</p>}
            <div ref={chatEndRef} />
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void sendChat();
            }}
            className="mt-4 flex gap-2"
          >
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={!token || !agentId.trim() || chatBusy}
              placeholder={token ? "Message the agent..." : "Connect wallet and set an agent ID first"}
              className="flex-1 rounded-full border border-grid bg-background px-4 py-2.5 text-sm disabled:opacity-40"
            />
            <button
              type="submit"
              disabled={!token || !agentId.trim() || chatBusy || !chatInput.trim()}
              className="rounded-full bg-signal px-5 py-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-background disabled:opacity-40"
            >
              Send
            </button>
          </form>
        </Panel>
      </div>
    </AppShell>
  );
}
