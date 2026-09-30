"use client";

import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import {
  createAssociatedTokenAccountInstruction,
  createTransferInstruction,
  getAccount,
  getAssociatedTokenAddress,
} from "@solana/spl-token";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { useCallback, useEffect, useState } from "react";
import { Panel } from "@/components/AppShell";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import {
  fetchYieldAgentWallet,
  fetchYieldUserBalances,
  verifyYieldDepositWithRetry,
  withdrawYieldTokens,
  type YieldTokenBalanceRow,
  type YieldUserDepositBalances,
} from "@/lib/yieldWalletClient";

const PENDING_DEPOSIT_KEY = "yield_pending_deposit_signature";
const DEPOSIT_ASSETS = ["SOL", "USDC", "USDT"] as const;
const DEPOSIT_MINTS: Record<string, string> = {
  USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  USDT: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
};
const DEPOSIT_DECIMALS: Record<string, number> = { USDC: 6, USDT: 6 };

export function YieldAgentDeposit({
  cluster,
  authToken,
  onBalancesChange,
}: {
  cluster?: string;
  authToken?: string | null;
  onBalancesChange?: (balances: YieldUserDepositBalances | null) => void;
}) {
  const { connection } = useConnection();
  const { publicKey, sendTransaction, connected } = useWallet();
  const [agentWallet, setAgentWallet] = useState<string | null>(null);
  const [balances, setBalances] = useState<YieldTokenBalanceRow[]>([]);
  const [amount, setAmount] = useState("");
  const [asset, setAsset] = useState<(typeof DEPOSIT_ASSETS)[number]>("SOL");
  const [busy, setBusy] = useState(false);
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);
  const [withdrawAmount, setWithdrawAmount] = useState("");

  const refreshBalances = useCallback(async () => {
    if (!publicKey || !authToken) {
      setBalances([]);
      onBalancesChange?.(null);
      return;
    }
    const data = await fetchYieldUserBalances(authToken);
    if (data) {
      setBalances(data.balances);
      onBalancesChange?.(data);
    }
  }, [publicKey, authToken, onBalancesChange]);

  useEffect(() => {
    if (!authToken) {
      setAgentWallet(null);
      return;
    }
    void fetchYieldAgentWallet(authToken).then((info) => {
      setAgentWallet(info?.agent_wallet ?? null);
    });
  }, [authToken]);

  useEffect(() => {
    void refreshBalances();
  }, [refreshBalances]);

  async function onDeposit() {
    setError(null);
    setSuccess(null);
    if (!connected || !publicKey) {
      setError("Connect your wallet first.");
      return;
    }
    if (!authToken) {
      setError("Approve the wallet sign-in message.");
      return;
    }
    if (!agentWallet) {
      setError("Yield agent wallet is not ready yet.");
      return;
    }
    const parsed = Number(amount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError(`Enter a ${asset} amount greater than 0.`);
      return;
    }
    setBusy(true);
    try {
      const dest = new PublicKey(agentWallet);
      const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");
      const tx = new Transaction();
      if (asset === "SOL") {
        tx.add(
          SystemProgram.transfer({
            fromPubkey: publicKey,
            toPubkey: dest,
            lamports: Math.round(parsed * LAMPORTS_PER_SOL),
          })
        );
      } else {
        const mint = new PublicKey(DEPOSIT_MINTS[asset]);
        const decimals = DEPOSIT_DECIMALS[asset] ?? 6;
        const rawAmount = BigInt(Math.round(parsed * 10 ** decimals));
        const userAta = await getAssociatedTokenAddress(mint, publicKey);
        const agentAta = await getAssociatedTokenAddress(mint, dest);
        try {
          await getAccount(connection, agentAta);
        } catch {
          tx.add(createAssociatedTokenAccountInstruction(publicKey, agentAta, dest, mint));
        }
        tx.add(createTransferInstruction(userAta, agentAta, publicKey, rawAmount));
      }
      tx.recentBlockhash = blockhash;
      tx.feePayer = publicKey;
      const signature = await sendTransaction(tx, connection);
      setLastTx(signature);
      try {
        sessionStorage.setItem(PENDING_DEPOSIT_KEY, signature);
      } catch {
        /* ignore */
      }
      await connection.confirmTransaction({ signature, blockhash, lastValidBlockHeight }, "confirmed");
      const verified = await verifyYieldDepositWithRetry(signature, authToken);
      setSuccess(verified.message ?? "Deposit credited.");
      try {
        sessionStorage.removeItem(PENDING_DEPOSIT_KEY);
      } catch {
        /* ignore */
      }
      await refreshBalances();
      setAmount("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deposit failed");
    } finally {
      setBusy(false);
    }
  }

  async function onWithdraw() {
    setError(null);
    setSuccess(null);
    if (!authToken) {
      setError("Approve the wallet sign-in message.");
      return;
    }
    const parsed = Number(withdrawAmount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError("Enter a withdraw amount greater than 0.");
      return;
    }
    setWithdrawBusy(true);
    try {
      const result = await withdrawYieldTokens(asset, parsed, authToken);
      setSuccess(`Idle ${asset} sent back to your wallet.`);
      if (result.signature) setLastTx(result.signature);
      await refreshBalances();
      setWithdrawAmount("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Withdraw failed");
    } finally {
      setWithdrawBusy(false);
    }
  }

  const idle = balances.find((row) => row.token === asset);

  return (
    <Panel title="Capital">
      <p className="text-sm text-muted-foreground">
        Send {asset} to your Yield Agent Circle wallet. The agent uses that balance when it stakes
        the best protocol for your requirements.
      </p>
      {agentWallet && (
        <p className="mt-3 break-all font-mono text-[11px] text-muted-foreground">
          Agent wallet: {agentWallet}
          {cluster ? ` · ${cluster}` : ""}
        </p>
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="border border-grid bg-surface/30 px-3 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Idle {asset}
          </div>
          <div className="mt-1 font-display text-2xl font-bold tabular-nums text-signal">
            {idle?.available ?? 0}
          </div>
        </div>
        <div className="border border-grid bg-surface/30 px-3 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Deposited
          </div>
          <div className="mt-1 font-display text-2xl font-bold tabular-nums">
            {idle?.deposited ?? 0}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <select
          value={asset}
          onChange={(e) => setAsset(e.target.value as (typeof DEPOSIT_ASSETS)[number])}
          disabled={busy || withdrawBusy}
          className="border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground disabled:opacity-50"
        >
          {DEPOSIT_ASSETS.map((token) => (
            <option key={token} value={token}>
              {token}
            </option>
          ))}
        </select>
        <input
          type="number"
          min="0"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder={`Deposit ${asset}`}
          disabled={busy}
          className="w-36 border border-grid bg-background px-3 py-2 font-mono text-sm disabled:opacity-50"
        />
        <button
          type="button"
          disabled={busy || !connected}
          onClick={() => void onDeposit()}
          className="bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
        >
          {busy ? "Depositing…" : "Deposit"}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <input
          type="number"
          min="0"
          step="0.01"
          value={withdrawAmount}
          onChange={(e) => setWithdrawAmount(e.target.value)}
          placeholder={`Withdraw idle ${asset}`}
          disabled={withdrawBusy}
          className="w-36 border border-grid bg-background px-3 py-2 font-mono text-sm disabled:opacity-50"
        />
        <button
          type="button"
          disabled={withdrawBusy || !connected}
          onClick={() => void onWithdraw()}
          className="border border-grid px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground disabled:opacity-40"
        >
          {withdrawBusy ? "Sending…" : "Withdraw idle"}
        </button>
      </div>

      {error && <p className="mt-3 font-mono text-[11px] text-warn">{error}</p>}
      {success && <p className="mt-3 font-mono text-[11px] text-signal">{success}</p>}
      {lastTx && (
        <a
          href={explorerUrlForSignature(lastTx, cluster)}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block break-all font-mono text-[10px] text-signal hover:underline"
        >
          {lastTx} ↗
        </a>
      )}
    </Panel>
  );
}
