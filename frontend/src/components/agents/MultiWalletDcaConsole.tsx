"use client";

import { useCallback, useEffect, useState } from "react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { Panel } from "@/components/AppShell";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";

type Balance = { token: string; mint: string; balance: number; is_active?: boolean };
type BalanceResponse = {
  user_wallet: string;
  deposit_address: string;
  balances: Balance[];
  min_sol_to_activate_lamports: number;
};
type Plan = {
  id: string;
  name: string;
  input_token: string;
  output_token: string;
  amount_per_buy: number;
  interval: string;
  max_executions: number | null;
  executions_count: number;
  status: string;
  wallet_mode: string;
};

function shorten(address: string) {
  return `${address.slice(0, 6)}…${address.slice(-6)}`;
}

export function MultiWalletDcaConsole() {
  const { wallet, token, busy, error, isAuthenticated } = useDcaWalletAuth();
  const { connection } = useConnection();
  const { publicKey, sendTransaction } = useWallet();
  const [balance, setBalance] = useState<BalanceResponse | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const [depositAmount, setDepositAmount] = useState("0.01");
  const [depositing, setDepositing] = useState(false);
  const [depositMsg, setDepositMsg] = useState<string | null>(null);

  const [outputToken, setOutputToken] = useState("USDC");
  const [amountPerBuy, setAmountPerBuy] = useState("0.001");
  const [interval, setIntervalStr] = useState("1 hour");
  const [maxExecutions, setMaxExecutions] = useState("3");
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);

  const [withdrawToken, setWithdrawToken] = useState("SOL");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawMsg, setWithdrawMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    Promise.all([
      fetch("/api/multi-wallet/dca/balance", { headers, cache: "no-store" }).then((r) => r.json()),
      fetch("/api/multi-wallet/dca/plans", { headers, cache: "no-store" }).then((r) => r.json()),
    ])
      .then(([b, p]) => {
        if (b.error || b.detail) {
          setLoadError(b.error || b.detail);
        } else {
          setLoadError(null);
          setBalance(b);
        }
        setPlans(p.plans || []);
      })
      .catch(() => setLoadError("Could not reach the agents API."));
  }, [token]);

  useEffect(() => {
    load();
  }, [load, refreshTick]);

  const deposit = async () => {
    if (!publicKey || !balance?.deposit_address) return;
    const parsed = Number(depositAmount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setDepositMsg("Enter a valid amount.");
      return;
    }
    setDepositing(true);
    setDepositMsg(null);
    try {
      const destination = new PublicKey(balance.deposit_address);
      const tx = new Transaction();
      tx.add(
        SystemProgram.transfer({
          fromPubkey: publicKey,
          toPubkey: destination,
          lamports: Math.round(parsed * LAMPORTS_PER_SOL),
        })
      );
      const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");
      tx.recentBlockhash = blockhash;
      tx.feePayer = publicKey;

      setDepositMsg("Approve in wallet…");
      const signature = await sendTransaction(tx, connection);
      setDepositMsg("Confirming on-chain…");
      await connection.confirmTransaction({ signature, blockhash, lastValidBlockHeight }, "confirmed");

      // No separate "verify deposit" step here, unlike the pooled DCA flow --
      // this address belongs only to this user, so the on-chain balance IS
      // the balance. Just refresh and read it straight from the chain.
      setDepositMsg(`Deposited. Signature: ${signature}`);
      setRefreshTick((n) => n + 1);
    } catch (err) {
      setDepositMsg(err instanceof Error ? `Error: ${err.message}` : "Deposit failed.");
    } finally {
      setDepositing(false);
    }
  };

  const createPlan = async () => {
    if (!token) return;
    setCreating(true);
    setCreateMsg(null);
    try {
      const res = await fetch("/api/multi-wallet/dca/plan", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          output_token: outputToken,
          amount_per_buy: parseFloat(amountPerBuy),
          interval,
          max_executions: parseInt(maxExecutions, 10),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setCreateMsg(`Error: ${data.error || data.detail}`);
      } else {
        setCreateMsg(`Plan created: ${data.plan.id}`);
        setRefreshTick((n) => n + 1);
      }
    } catch {
      setCreateMsg("Could not reach the agents API.");
    } finally {
      setCreating(false);
    }
  };

  const withdraw = async () => {
    if (!token) return;
    setWithdrawing(true);
    setWithdrawMsg(null);
    try {
      const res = await fetch("/api/multi-wallet/dca/withdraw", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ token: withdrawToken, amount: parseFloat(withdrawAmount) }),
      });
      const data = await res.json();
      if (!res.ok) {
        setWithdrawMsg(`Error: ${data.error || data.detail}`);
      } else {
        setWithdrawMsg(`Sent. Signature: ${data.signature}`);
        setRefreshTick((n) => n + 1);
      }
    } catch {
      setWithdrawMsg("Could not reach the agents API.");
    } finally {
      setWithdrawing(false);
    }
  };

  if (!wallet) {
    return (
      <Panel title="MULTI-WALLET DCA — CONNECT">
        <WalletMultiButton className="wallet-adapter-button-trigger" />
      </Panel>
    );
  }

  if (!isAuthenticated) {
    return (
      <Panel title="MULTI-WALLET DCA — SIGNING IN">
        <div className="text-xs text-muted-foreground">
          {busy ? "Signing in…" : error ? `Sign-in failed: ${error}` : "Waiting for signature…"}
        </div>
      </Panel>
    );
  }

  const solBalance = balance?.balances.find((b) => b.token === "SOL");

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Panel title="YOUR DEDICATED DCA WALLET">
        <div className="space-y-4 text-sm">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Connected as</div>
            <div className="font-mono text-xs">{shorten(wallet)}</div>
          </div>

          {loadError && <div className="text-xs text-red-400">{loadError}</div>}

          {balance && (
            <>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Your unique deposit address
                </div>
                <div className="rounded-lg border border-grid bg-black/20 px-3 py-2 font-mono text-xs break-all">
                  {balance.deposit_address}
                </div>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-grid px-3 py-2">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">SOL Balance</div>
                  <div className="font-mono text-sm">{solBalance?.balance ?? 0} SOL</div>
                </div>
                <div
                  className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider ${
                    solBalance?.is_active
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-amber-500/10 text-amber-400"
                  }`}
                >
                  {solBalance?.is_active ? "active" : "needs funding"}
                </div>
              </div>

              {balance.balances.slice(1).map((b) => (
                <div key={b.mint} className="flex items-center justify-between rounded-lg border border-grid px-3 py-2">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{b.token}</div>
                  <div className="font-mono text-sm">{b.balance}</div>
                </div>
              ))}

              <div className="border-t border-grid pt-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Deposit SOL (sends directly to your address above, from this wallet)
                </div>
                <div className="flex gap-2">
                  <input
                    value={depositAmount}
                    onChange={(e) => setDepositAmount(e.target.value)}
                    className="flex-1 rounded border border-grid bg-black/20 px-2 py-1 font-mono text-xs"
                  />
                  <button
                    type="button"
                    disabled={depositing}
                    onClick={deposit}
                    className="rounded border border-grid px-3 py-1 text-xs uppercase tracking-wider hover:bg-surface/60 disabled:opacity-50"
                  >
                    {depositing ? "…" : "Deposit"}
                  </button>
                </div>
                {depositMsg && <div className="mt-2 text-xs text-muted-foreground break-all">{depositMsg}</div>}
              </div>
            </>
          )}

          <button
            type="button"
            onClick={() => setRefreshTick((n) => n + 1)}
            className="w-full rounded-lg border border-grid px-3 py-1.5 text-xs uppercase tracking-wider text-muted-foreground hover:bg-surface/60"
          >
            Refresh
          </button>
        </div>
      </Panel>

      <Panel title="CREATE A DCA PLAN">
        <div className="space-y-3 text-sm">
          <p className="text-xs text-muted-foreground">
            Executes from your own wallet above. Deposit SOL there first.
          </p>
          <label className="block text-xs">
            Output token
            <input
              value={outputToken}
              onChange={(e) => setOutputToken(e.target.value)}
              className="mt-1 w-full rounded border border-grid bg-black/20 px-2 py-1 font-mono text-xs"
            />
          </label>
          <label className="block text-xs">
            Amount per buy (SOL)
            <input
              value={amountPerBuy}
              onChange={(e) => setAmountPerBuy(e.target.value)}
              className="mt-1 w-full rounded border border-grid bg-black/20 px-2 py-1 font-mono text-xs"
            />
          </label>
          <label className="block text-xs">
            Interval
            <input
              value={interval}
              onChange={(e) => setIntervalStr(e.target.value)}
              placeholder="e.g. 1 hour, 30 minutes"
              className="mt-1 w-full rounded border border-grid bg-black/20 px-2 py-1 font-mono text-xs"
            />
          </label>
          <label className="block text-xs">
            Number of buys
            <input
              value={maxExecutions}
              onChange={(e) => setMaxExecutions(e.target.value)}
              className="mt-1 w-full rounded border border-grid bg-black/20 px-2 py-1 font-mono text-xs"
            />
          </label>
          <button
            type="button"
            disabled={creating}
            onClick={createPlan}
            className="w-full rounded-lg border border-grid px-3 py-1.5 text-xs uppercase tracking-wider hover:bg-surface/60 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create Plan"}
          </button>
          {createMsg && <div className="text-xs text-muted-foreground break-all">{createMsg}</div>}

          {plans.length > 0 && (
            <div className="mt-4 space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Your plans</div>
              {plans.map((p) => (
                <div key={p.id} className="rounded border border-grid px-2 py-1 font-mono text-[11px]">
                  {p.id} · {p.input_token}→{p.output_token} · {p.amount_per_buy}/buy · {p.status} ·{" "}
                  {p.executions_count}/{p.max_executions ?? "∞"}
                </div>
              ))}
            </div>
          )}

          <div className="mt-6 border-t border-grid pt-4">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Withdraw</div>
            <div className="flex gap-2">
              <input
                value={withdrawToken}
                onChange={(e) => setWithdrawToken(e.target.value)}
                className="w-20 rounded border border-grid bg-black/20 px-2 py-1 font-mono text-xs"
              />
              <input
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                placeholder="amount"
                className="flex-1 rounded border border-grid bg-black/20 px-2 py-1 font-mono text-xs"
              />
              <button
                type="button"
                disabled={withdrawing}
                onClick={withdraw}
                className="rounded border border-grid px-3 py-1 text-xs uppercase tracking-wider hover:bg-surface/60 disabled:opacity-50"
              >
                {withdrawing ? "…" : "Withdraw"}
              </button>
            </div>
            {withdrawMsg && <div className="mt-2 text-xs text-muted-foreground break-all">{withdrawMsg}</div>}
          </div>
        </div>
      </Panel>
    </div>
  );
}
