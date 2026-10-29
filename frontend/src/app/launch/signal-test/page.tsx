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

const MIN_POSITION_USDC = 1.0; // keep in sync with agent/new/bounce_trading.py MIN_POSITION_USDC

const PROFILES = [
  { key: "fast_test", label: "Fast test (fires in minutes)", hint: "0.05% drop / 0.03% bounce, 2 min lookback, Binance 1s poll -- pipeline test only" },
  { key: "test", label: "Test", hint: "0.3% drop / 0.2% bounce, 15 min lookback, Binance 1s poll" },
  { key: "real", label: "Real strategy", hint: "10% drop / 5% bounce, 60 min lookback, Binance 1s poll" },
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

type AgentBreakdown = {
  agent_id: string;
  open_positions: number;
  closed_positions: number;
  capital_in_open_positions: number;
  realized_pnl_usdc: number;
  allocation_cap_usdc: number | null;
};

type BounceBalance = {
  agent_wallet: string | null;
  balances: { token: string; deposited: number; withdrawable: number }[];
  agent_breakdown?: AgentBreakdown[];
};

type Strategy = {
  symbol: string;
  profile: string;
  stop_loss_pct: number;
  take_profit_pct: number;
  auto_trade: boolean;
};

type PendingAction = {
  tool: string;
  args: Record<string, unknown>;
};

type LastAutoTrade = {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  at: string;
};

type Position = {
  position_id: string;
  symbol: string;
  status: "open" | "closed";
  entry_usdc_amount: number;
  entry_token_amount: number;
  entry_price_usd: number;
  entry_signature: string | null;
  stop_price_usd: number;
  target_price_usd: number;
  close_reason: string | null;
  close_usdc_amount: number | null;
  close_price_usd: number | null;
  close_signature: string | null;
  created_at: string;
  closed_at: string | null;
};

const SOLSCAN_TX = (sig: string) => `https://solscan.io/tx/${sig}`;

export default function SignalTestPage() {
  const { token, busy: authBusy, error: authError, signIn } = useDcaWalletAuth();
  // Local test only -- hardcoded so there's nothing to paste. Change this if
  // you create a different test agent locally.
  const [agentId, setAgentId] = useState("bounce_18cd4731");
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

  const [balance, setBalance] = useState<BounceBalance | null>(null);
  const [balanceBusy, setBalanceBusy] = useState(false);
  const [balanceError, setBalanceError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [depositSig, setDepositSig] = useState("");
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);

  const [capInput, setCapInput] = useState("");
  const [capBusy, setCapBusy] = useState(false);
  const [capMsg, setCapMsg] = useState<string | null>(null);

  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [strategyForm, setStrategyForm] = useState({ symbol: "SOL", profile: "fast_test", stop_loss_pct: "5", take_profit_pct: "15" });
  const [strategyBusy, setStrategyBusy] = useState(false);
  const [strategyMsg, setStrategyMsg] = useState<string | null>(null);

  const [pending, setPending] = useState<PendingAction | null>(null);
  const [pendingBusy, setPendingBusy] = useState(false);
  const [pendingMsg, setPendingMsg] = useState<string | null>(null);
  const pendingPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [lastAutoTrade, setLastAutoTrade] = useState<LastAutoTrade | null>(null);

  const [positions, setPositions] = useState<Position[]>([]);

  useEffect(() => {
    if (token) void signIn();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshStrategy = useCallback(async () => {
    if (!token || !agentId.trim()) return;
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/strategy`, token);
      if (data.symbol) {
        setStrategy(data);
        setStrategyForm({
          symbol: data.symbol, profile: data.profile,
          stop_loss_pct: String(data.stop_loss_pct), take_profit_pct: String(data.take_profit_pct),
        });
      }
    } catch {
      // no strategy configured yet -- fine, form stays at defaults
    }
  }, [token, agentId]);

  const saveStrategy = useCallback(async () => {
    if (!token || !agentId.trim()) return;
    setStrategyBusy(true);
    setStrategyMsg(null);
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/strategy`, token, {
        method: "POST",
        body: JSON.stringify({
          symbol: strategyForm.symbol, profile: strategyForm.profile,
          stop_loss_pct: Number(strategyForm.stop_loss_pct), take_profit_pct: Number(strategyForm.take_profit_pct),
          auto_trade: true,
        }),
      });
      setStrategy(data);
      setStrategyMsg("Default strategy saved.");
    } catch (err) {
      setStrategyMsg(err instanceof Error ? err.message : "Could not save strategy");
    } finally {
      setStrategyBusy(false);
    }
  }, [token, agentId, strategyForm]);

  const pollPending = useCallback(async () => {
    if (!token || !agentId.trim()) return;
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/pending`, token);
      setPending(data?.tool ? data : null);
    } catch {
      // ignore transient poll failures
    }
    try {
      const auto = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/last-auto-trade`, token);
      if (auto?.tool) {
        setLastAutoTrade((prev) => {
          if (prev && prev.at === auto.at) return prev;
          void refreshBalance();
          return auto;
        });
      }
    } catch {
      // ignore transient poll failures
    }
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/positions`, token);
      if (Array.isArray(data?.positions)) setPositions(data.positions);
    } catch {
      // ignore transient poll failures
    }
  }, [token, agentId]);

  useEffect(() => {
    if (!token || !agentId.trim()) return;
    void refreshStrategy();
    void pollPending();
    pendingPollRef.current = setInterval(() => void pollPending(), 4000);
    return () => {
      if (pendingPollRef.current) clearInterval(pendingPollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, agentId]);

  async function respondPending(approve: boolean) {
    if (!token || !agentId.trim()) return;
    setPendingBusy(true);
    setPendingMsg(null);
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/pending/respond`, token, {
        method: "POST",
        body: JSON.stringify({ approve }),
      });
      setPending(null);
      void refreshBalance();
      setPendingMsg(approve ? `Executed: ${JSON.stringify(data.result)}` : "Rejected -- nothing executed.");
    } catch (err) {
      setPendingMsg(err instanceof Error ? err.message : "Could not respond");
    } finally {
      setPendingBusy(false);
    }
  }

  const [convertBusy, setConvertBusy] = useState(false);
  const [convertMsg, setConvertMsg] = useState<string | null>(null);

  async function convertSolToUsdc() {
    if (!token || !agentId.trim()) return;
    if (!window.confirm("Convert your idle SOL to USDC now? This is a real on-chain swap.")) return;
    setConvertBusy(true);
    setConvertMsg(null);
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/convert-sol`, token, {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      });
      void refreshBalance();
      setConvertMsg(`Converted: ${JSON.stringify(data)}`);
    } catch (err) {
      setConvertMsg(err instanceof Error ? err.message : "Conversion failed");
    } finally {
      setConvertBusy(false);
    }
  }

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
    pollRef.current = setInterval(() => void pollOnce(), 1000);
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

  const refreshBalance = useCallback(async () => {
    if (!token || !agentId.trim()) return;
    setBalanceBusy(true);
    setBalanceError(null);
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/balance`, token);
      setBalance(data);
    } catch (err) {
      setBalanceError(err instanceof Error ? err.message : "Could not load balance");
    } finally {
      setBalanceBusy(false);
    }
  }, [token, agentId]);

  useEffect(() => {
    if (token && agentId.trim()) void refreshBalance();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, agentId]);

  async function copyAddress() {
    if (!balance?.agent_wallet) return;
    try {
      await navigator.clipboard.writeText(balance.agent_wallet);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be unavailable; address is still shown on screen to copy manually
    }
  }

  async function verifyDeposit() {
    if (!token || !agentId.trim() || !depositSig.trim()) return;
    setVerifyBusy(true);
    setVerifyMsg(null);
    try {
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/verify-deposit`, token, {
        method: "POST",
        body: JSON.stringify({ signature: depositSig.trim() }),
      });
      setVerifyMsg(data.message ?? "Deposit verified.");
      setDepositSig("");
      void refreshBalance();
    } catch (err) {
      setVerifyMsg(err instanceof Error ? err.message : "Could not verify deposit");
    } finally {
      setVerifyBusy(false);
    }
  }

  async function setAllocationCap() {
    if (!token || !agentId.trim()) return;
    setCapBusy(true);
    setCapMsg(null);
    try {
      const value = capInput.trim() === "" ? null : Number(capInput.trim());
      const data = await apiCall(`/api/agents/launch/${agentId.trim()}/bounce/allocation-cap`, token, {
        method: "POST",
        body: JSON.stringify({ max_allocation_usdc: value }),
      });
      setCapMsg(
        data.max_allocation_usdc != null
          ? `Cap set to ${data.max_allocation_usdc} USDC for ${agentId.trim()}.`
          : `Cap cleared for ${agentId.trim()} -- full wallet balance available.`
      );
      void refreshBalance();
    } catch (err) {
      setCapMsg(err instanceof Error ? err.message : "Could not set allocation cap");
    } finally {
      setCapBusy(false);
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
      subtitle="Watches a token for a drop-then-bounce via Binance (1s poll). Trades from your per-user Circle bounce wallet."
    >
      <div className="mb-6 rounded-xl border-2 border-warn/60 bg-warn/10 px-4 py-3">
        <p className="font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-warn">
          Local test page -- not part of the real launchpad
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          This page only exists on your machine, on the bounce-agent-signal-engine branch. It is
          not linked from the real app, not deployed, and not something a real user would ever
          see. Prices come from Binance every 1s. Capital sits in your Circle bounce wallet
          (same pattern as DCA / Yield) on mainnet with real SOL -- there is no sandbox mode here.
        </p>
      </div>

      {!token && (
        <div className="mb-6 rounded-xl border border-grid bg-surface/30 p-4 text-sm">
          <p className="text-muted-foreground">Connect and sign in with the wallet that owns the agent ({agentId}).</p>
          <div className="mt-3">
            <WalletMultiButton />
          </div>
          {authBusy && <p className="mt-2 text-xs text-muted-foreground">Signing in...</p>}
          {authError && <p className="mt-2 text-xs text-warn">{authError}</p>}
        </div>
      )}

      {pending && (
        <div className="mb-6">
          <Panel title="Action needs your approval">
            <div className="rounded-xl border-2 border-signal bg-signal/10 p-4">
              <div className="font-mono text-xs uppercase tracking-[0.14em] text-signal">{pending.tool}</div>
              <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground">
                {JSON.stringify(pending.args, null, 2)}
              </pre>
              <p className="mt-2 text-xs text-muted-foreground">
                This will execute exactly these numbers, nothing else, the moment you approve.
              </p>
              <div className="mt-4 flex gap-3">
                <button
                  onClick={() => respondPending(true)}
                  disabled={pendingBusy}
                  className="flex-1 rounded-full bg-signal px-4 py-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-background disabled:opacity-40"
                >
                  {pendingBusy ? "Working..." : "Approve"}
                </button>
                <button
                  onClick={() => respondPending(false)}
                  disabled={pendingBusy}
                  className="flex-1 rounded-full border border-grid px-4 py-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] hover:border-warn disabled:opacity-40"
                >
                  Reject
                </button>
              </div>
              {pendingMsg && (
                <p className="mt-3 whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground">
                  {pendingMsg}
                </p>
              )}
            </div>
          </Panel>
        </div>
      )}
      {!pending && pendingMsg && (
        <div className="mb-6">
          <p className="whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground">{pendingMsg}</p>
        </div>
      )}

      <div className="mb-6">
        <Panel title="Default strategy (set once, used every time this agent fires)">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <label className="font-mono text-[9px] uppercase text-muted-foreground">Symbol</label>
              <input
                value={strategyForm.symbol}
                onChange={(e) => setStrategyForm((s) => ({ ...s, symbol: e.target.value.toUpperCase() }))}
                className="mt-1 w-full rounded-xl border border-grid bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="font-mono text-[9px] uppercase text-muted-foreground">Profile</label>
              <select
                value={strategyForm.profile}
                onChange={(e) => setStrategyForm((s) => ({ ...s, profile: e.target.value }))}
                className="mt-1 w-full rounded-xl border border-grid bg-background px-3 py-2 text-sm"
              >
                {PROFILES.map((p) => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="font-mono text-[9px] uppercase text-muted-foreground">Stop-loss %</label>
              <input
                value={strategyForm.stop_loss_pct}
                onChange={(e) => setStrategyForm((s) => ({ ...s, stop_loss_pct: e.target.value }))}
                type="number" step="any"
                className="mt-1 w-full rounded-xl border border-grid bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="font-mono text-[9px] uppercase text-muted-foreground">Take-profit %</label>
              <input
                value={strategyForm.take_profit_pct}
                onChange={(e) => setStrategyForm((s) => ({ ...s, take_profit_pct: e.target.value }))}
                type="number" step="any"
                className="mt-1 w-full rounded-xl border border-grid bg-background px-3 py-2 text-sm"
              />
            </div>
          </div>
          <button
            onClick={saveStrategy}
            disabled={strategyBusy}
            className="mt-3 rounded-full bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-background disabled:opacity-40"
          >
            {strategyBusy ? "Saving..." : "Save default strategy"}
          </button>
          {strategyMsg && <p className="mt-2 font-mono text-[10px] text-signal">{strategyMsg}</p>}
          {strategy && (
            <p className="mt-2 font-mono text-[10px] text-muted-foreground">
              Currently: watching {strategy.symbol} ({strategy.profile}), {strategy.stop_loss_pct}% stop / {strategy.take_profit_pct}% target.
              {strategy.auto_trade
                ? strategy.profile === "fast_test"
                  ? " fast_test auto-EXECUTES with no approval step when it fires -- SL/TP are volatility-sized, not fixed at the % above."
                  : " A matching watch firing will auto-propose a trade above -- just approve or reject. SL/TP are volatility-sized, not fixed at the % above."
                : ""}
            </p>
          )}
        </Panel>
      </div>

      <div className="mb-6">
        <Panel title="Deposit (Bounce Agent wallet)">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  Send SOL here to fund this agent
                </div>
                {balanceBusy && !balance ? (
                  <p className="mt-2 text-sm text-muted-foreground">Loading...</p>
                ) : balance?.agent_wallet ? (
                  <div className="mt-2 flex items-center gap-2">
                    <code className="flex-1 break-all rounded-xl border border-grid bg-background px-3 py-2 text-xs">
                      {balance.agent_wallet}
                    </code>
                    <button
                      onClick={copyAddress}
                      className="shrink-0 rounded-full border border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] hover:border-signal"
                    >
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-warn">{balanceError ?? "No deposit address yet."}</p>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-4 font-mono text-xs">
                  <div>
                    <span className="text-muted-foreground">Withdrawable: </span>
                    <span className="font-bold text-signal">
                      {balance?.balances?.find((b) => b.token === "USDC")?.withdrawable ?? 0} USDC
                    </span>
                  </div>
                  {!!balance?.balances?.find((b) => b.token === "SOL")?.withdrawable && (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">SOL (gas reserve, or a failed conversion): </span>
                      <span className="text-muted-foreground">
                        {balance?.balances?.find((b) => b.token === "SOL")?.withdrawable} SOL
                      </span>
                      <button
                        onClick={convertSolToUsdc}
                        disabled={convertBusy}
                        className="rounded-full border border-grid px-3 py-1 font-mono text-[9px] uppercase tracking-[0.1em] hover:border-signal disabled:opacity-40"
                      >
                        {convertBusy ? "Converting..." : "Convert to USDC"}
                      </button>
                    </div>
                  )}
                  {convertMsg && (
                    <p className="w-full whitespace-pre-wrap break-all text-[10px] text-muted-foreground">
                      {convertMsg}
                    </p>
                  )}
                  <button
                    onClick={refreshBalance}
                    disabled={balanceBusy}
                    className="text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-40"
                  >
                    {balanceBusy ? "Refreshing..." : "Refresh"}
                  </button>
                </div>
              </div>

              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  Already sent? Paste the transaction signature to credit it
                </div>
                <div className="mt-2 flex gap-2">
                  <input
                    value={depositSig}
                    onChange={(e) => setDepositSig(e.target.value)}
                    placeholder="Transaction signature"
                    className="flex-1 rounded-xl border border-grid bg-background px-3 py-2 text-xs"
                  />
                  <button
                    onClick={verifyDeposit}
                    disabled={verifyBusy || !depositSig.trim()}
                    className="shrink-0 rounded-full bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-background disabled:opacity-40"
                  >
                    {verifyBusy ? "Verifying..." : "Verify"}
                  </button>
                </div>
                {verifyMsg && <p className="mt-2 text-xs text-muted-foreground">{verifyMsg}</p>}

                <div className="mt-4 border-t border-grid pt-4">
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                    Allocation cap for this agent (USDC, blank = no cap)
                  </div>
                  <div className="mt-2 flex gap-2">
                    <input
                      value={capInput}
                      onChange={(e) => setCapInput(e.target.value)}
                      placeholder="e.g. 50"
                      type="number"
                      step="any"
                      className="flex-1 rounded-xl border border-grid bg-background px-3 py-2 text-xs"
                    />
                    <button
                      onClick={setAllocationCap}
                      disabled={capBusy}
                      className="shrink-0 rounded-full border border-grid px-4 py-2 font-mono text-[10px] uppercase tracking-[0.1em] hover:border-signal disabled:opacity-40"
                    >
                      {capBusy ? "Setting..." : "Set cap"}
                    </button>
                  </div>
                  {capMsg && <p className="mt-2 text-xs text-muted-foreground">{capMsg}</p>}
                </div>
              </div>
            </div>

            {!!balance?.agent_breakdown?.length && (
              <div className="mt-5 border-t border-grid pt-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  Per-agent breakdown (one shared wallet, tracked separately per agent)
                </div>
                <div className="mt-2 space-y-2">
                  {balance.agent_breakdown.map((a) => (
                    <div
                      key={a.agent_id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-grid bg-surface/30 px-3 py-2 text-xs"
                    >
                      <span className="font-mono">{a.agent_id}</span>
                      <span className="text-muted-foreground">
                        {a.open_positions} open &middot; {a.closed_positions} closed
                      </span>
                      <span className="text-muted-foreground">
                        {a.capital_in_open_positions} USDC in open positions
                        {a.allocation_cap_usdc != null ? ` (cap: ${a.allocation_cap_usdc} USDC)` : " (no cap)"}
                      </span>
                      <span className={a.realized_pnl_usdc >= 0 ? "font-bold text-signal" : "font-bold text-warn"}>
                        {a.realized_pnl_usdc >= 0 ? "+" : ""}
                        {a.realized_pnl_usdc} USDC realized
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Panel>
        </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Panel title="Start a watch">
          <div className="space-y-4">
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
            <p className="text-sm text-muted-foreground">Start a watch to see it update here every 1 second (Binance oracle).</p>
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

              {lastAutoTrade && (
                <div className="rounded-xl border-2 border-signal bg-signal/10 p-4">
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal">
                    Auto-executed (fast_test -- no approval needed for this profile)
                  </div>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    {new Date(lastAutoTrade.at).toLocaleTimeString()} -- {String(lastAutoTrade.args.symbol)},{" "}
                    {String(lastAutoTrade.args.amount_usdc)} USDC, {String(lastAutoTrade.args.stop_loss_pct)}%
                    stop / {String(lastAutoTrade.args.take_profit_pct)}% target (volatility-sized)
                  </p>
                  <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground">
                    {JSON.stringify(lastAutoTrade.result, null, 2)}
                  </pre>
                </div>
              )}

              {watch.state === "fired" && (() => {
                const usdcAvailable = balance?.balances.find((b) => b.token === "USDC")?.withdrawable ?? 0;
                const strategyMatches = !!strategy && strategy.auto_trade
                  && strategy.symbol === watch.symbol && strategy.profile === watch.profile;

                if (pending) {
                  return (
                    <div className="rounded-xl bg-signal/10 p-4 text-sm text-signal">
                      Signal fired, and a trade has been proposed -- see the Pending Action card above to
                      approve or reject it.
                    </div>
                  );
                }
                if (!strategyMatches) {
                  return (
                    <div className="rounded-xl bg-signal/10 p-4 text-sm text-signal">
                      Signal fired, but no Default Strategy with auto-trade is set for {watch.symbol} /{" "}
                      {watch.profile}, so nothing was proposed automatically. Set one above, or ask the
                      agent in chat to open a position.
                    </div>
                  );
                }
                if (usdcAvailable < MIN_POSITION_USDC) {
                  return (
                    <div className="rounded-xl bg-signal/10 p-4 text-sm text-signal">
                      Signal fired, but your available balance ({usdcAvailable.toFixed(4)} USDC) is below the{" "}
                      {MIN_POSITION_USDC} USDC minimum trade size, so nothing was proposed. Deposit more or
                      convert idle SOL to USDC above.
                    </div>
                  );
                }
                if (watch.profile === "fast_test") {
                  return (
                    <div className="rounded-xl bg-signal/10 p-4 text-sm text-signal">
                      Signal fired. fast_test auto-executes with no approval step -- the trade should
                      already be done, see the result above (or wait a moment for it to appear).
                    </div>
                  );
                }
                return (
                  <div className="rounded-xl bg-signal/10 p-4 text-sm text-signal">
                    Signal fired. A trade should be proposed shortly -- if nothing appears above within a
                    few seconds, ask the agent in chat to open a position directly.
                  </div>
                );
              })()}

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

      <div className="mt-6">
        <Panel title="Position history (open + closed)">
          {positions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No positions yet -- they&apos;ll show up here once a trade executes.</p>
          ) : (
            <div className="space-y-2">
              {positions.map((p) => (
                <div
                  key={p.position_id}
                  className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-xl border border-grid bg-surface/30 p-3 text-xs md:grid-cols-5"
                >
                  <div>
                    <div className="font-mono text-[9px] uppercase text-muted-foreground">Status</div>
                    <div className={`mt-0.5 font-mono font-bold uppercase ${p.status === "open" ? "text-signal" : "text-muted-foreground"}`}>
                      {p.status}{p.status === "closed" && p.close_reason ? ` (${p.close_reason})` : ""}
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[9px] uppercase text-muted-foreground">Symbol / size</div>
                    <div className="mt-0.5">{p.symbol} -- {p.entry_usdc_amount} USDC</div>
                  </div>
                  <div>
                    <div className="font-mono text-[9px] uppercase text-muted-foreground">Entry / close price</div>
                    <div className="mt-0.5">
                      ${p.entry_price_usd?.toFixed(4)}
                      {p.close_price_usd != null ? ` -> $${p.close_price_usd.toFixed(4)}` : ""}
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[9px] uppercase text-muted-foreground">Stop / target</div>
                    <div className="mt-0.5">${p.stop_price_usd?.toFixed(4)} / ${p.target_price_usd?.toFixed(4)}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[9px] uppercase text-muted-foreground">Transactions</div>
                    <div className="mt-0.5 flex flex-wrap gap-2">
                      {p.entry_signature && (
                        <a
                          href={SOLSCAN_TX(p.entry_signature)}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full border border-grid px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-signal hover:border-signal"
                        >
                          Entry tx
                        </a>
                      )}
                      {p.close_signature && (
                        <a
                          href={SOLSCAN_TX(p.close_signature)}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full border border-grid px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-signal hover:border-signal"
                        >
                          Close tx
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}
