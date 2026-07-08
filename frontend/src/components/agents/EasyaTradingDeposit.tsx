"use client";

import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { useCallback, useEffect, useState } from "react";
import { Panel } from "@/components/AppShell";
import {
  fetchEasyaAgentWallet,
  fetchEasyaBalances,
  verifyEasyaDeposit,
  type EasyaTokenBalanceRow,
} from "@/lib/easyaWalletClient";

export function EasyaTradingDeposit({
  authToken,
  refreshTick = 0,
}: {
  authToken?: string | null;
  refreshTick?: number;
}) {
  const { connection } = useConnection();
  const { publicKey, sendTransaction, connected } = useWallet();
  const [agentWallet, setAgentWallet] = useState<string | null>(null);
  const [balances, setBalances] = useState<EasyaTokenBalanceRow[]>([]);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const info = await fetchEasyaAgentWallet();
    setAgentWallet(info?.agent_wallet ?? null);
    if (authToken) {
      const bal = await fetchEasyaBalances(authToken);
      setBalances(bal?.balances ?? []);
    }
  }, [authToken]);

  useEffect(() => {
    void load();
  }, [load, refreshTick]);

  const solBalance = balances.find((b) => b.token === "SOL");

  async function onDeposit() {
    if (!publicKey || !agentWallet || !authToken || !amount.trim()) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const lamports = Math.round(parseFloat(amount) * LAMPORTS_PER_SOL);
      if (!Number.isFinite(lamports) || lamports <= 0) {
        throw new Error("Enter a valid SOL amount");
      }
      const tx = new Transaction().add(
        SystemProgram.transfer({
          fromPubkey: publicKey,
          toPubkey: new PublicKey(agentWallet),
          lamports,
        })
      );
      const sig = await sendTransaction(tx, connection);
      await connection.confirmTransaction(sig, "confirmed");
      await verifyEasyaDeposit(sig, authToken);
      setMessage(`Deposited ${amount} SOL. Ready for Jupiter buys (0.1% fee per fill).`);
      setAmount("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deposit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Trading wallet · Jupiter buys">
      <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
        Deposit SOL to fund one-time market or limit buys. Platform fee: <strong>0.1%</strong> per
        successful swap. Separate from the DCA agent wallet.
      </p>
      {agentWallet ? (
        <p className="mb-2 break-all font-mono text-[10px] text-foreground/80">
          Deposit address: {agentWallet}
        </p>
      ) : (
        <p className="mb-2 text-xs text-warn">EasyA trading wallet not configured on server.</p>
      )}
      {solBalance && (
        <p className="mb-3 font-mono text-xs text-signal">
          Available: {solBalance.available} SOL · Deposited: {solBalance.deposited} SOL
          {solBalance.reserved_for_orders > 0 &&
            ` · Reserved: ${solBalance.reserved_for_orders} SOL`}
        </p>
      )}
      {error && (
        <div className="mb-3 border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">{error}</div>
      )}
      {message && (
        <div className="mb-3 border border-signal/30 bg-signal/10 px-3 py-2 text-xs text-signal">
          {message}
        </div>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="number"
          min="0"
          step="0.001"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          disabled={busy || !connected || !authToken}
          placeholder="SOL amount"
          className="flex-1 border border-grid bg-background px-3 py-2 font-mono text-sm outline-none focus:border-signal disabled:opacity-50"
        />
        <button
          type="button"
          disabled={busy || !connected || !authToken || !amount.trim() || !agentWallet}
          onClick={() => void onDeposit()}
          className="bg-signal px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-primary-foreground disabled:opacity-40"
        >
          Deposit SOL
        </button>
      </div>
    </Panel>
  );
}
