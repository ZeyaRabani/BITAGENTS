"use client";

import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { useCallback, useEffect, useState } from "react";
import { Panel } from "@/components/AppShell";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import {
  fetchYieldAgentWallet,
  fetchYieldUserBalances,
  verifyYieldDepositWithRetry,
  withdrawYieldTokens,
  type YieldDepositVerifyResponse,
  type YieldTokenBalanceRow,
  type YieldUserDepositBalances,
} from "@/lib/yieldWalletClient";

const PENDING_DEPOSIT_KEY = "yield_pending_deposit_signature";

function savePendingDepositSignature(signature: string) {
  try {
    sessionStorage.setItem(PENDING_DEPOSIT_KEY, signature);
  } catch {
    /* ignore storage errors */
  }
}

function clearPendingDepositSignature() {
  try {
    sessionStorage.removeItem(PENDING_DEPOSIT_KEY);
  } catch {
    /* ignore storage errors */
  }
}

function readPendingDepositSignature(): string | null {
  try {
    return sessionStorage.getItem(PENDING_DEPOSIT_KEY);
  } catch {
    return null;
  }
}

function signatureFromError(err: unknown): string | null {
  const message = err instanceof Error ? err.message : String(err);
  const match = message.match(/\b[1-9A-HJ-NP-Za-km-z]{80,100}\b/);
  return match?.[0] ?? null;
}

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
  const [busy, setBusy] = useState(false);
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);
  const [manualSignature, setManualSignature] = useState("");
  const [depositPhase, setDepositPhase] = useState<string | null>(null);
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

  function applyVerifiedBalances(result: YieldDepositVerifyResponse) {
    if (result.balances?.balances) {
      setBalances(result.balances.balances);
      onBalancesChange?.(result.balances);
    }
  }

  async function runDepositVerification(
    signature: string,
    options?: { clearManualInput?: boolean; useVerifyBusy?: boolean }
  ): Promise<boolean> {
    if (!authToken) {
      setError("Connect wallet and sign in before verifying a deposit.");
      return false;
    }

    const trimmed = signature.trim();
    if (trimmed.length < 80) {
      setError("Enter a valid Solana transaction signature.");
      return false;
    }

    if (options?.useVerifyBusy !== false) {
      setVerifyBusy(true);
    }
    setError(null);
    setSuccess(null);

    try {
      const verified = await verifyYieldDepositWithRetry(trimmed, authToken);
      applyVerifiedBalances(verified);
      if (!verified.balances?.balances) {
        await refreshBalances();
      }
      setLastTx(trimmed);
      clearPendingDepositSignature();
      setSuccess(
        verified.message ??
          (verified.status === "already_recorded"
            ? "Deposit already credited to your balance."
            : "Deposit verified and credited to your balance.")
      );
      if (options?.clearManualInput) {
        setManualSignature("");
      }
      return true;
    } catch (err) {
      savePendingDepositSignature(trimmed);
      setManualSignature(trimmed);
      const message = err instanceof Error ? err.message : "Deposit verification failed";
      setError(
        `${message} Your transfer may still be confirming - we will keep retrying automatically.`
      );
      return false;
    } finally {
      if (options?.useVerifyBusy !== false) {
        setVerifyBusy(false);
      }
    }
  }

  useEffect(() => {
    if (!authToken) return;
    const pending = readPendingDepositSignature();
    if (!pending) return;
    setManualSignature(pending);
    void runDepositVerification(pending, { useVerifyBusy: false }).then((ok) => {
      if (ok) clearPendingDepositSignature();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when auth becomes available
  }, [authToken]);

  useEffect(() => {
    if (!authToken) return;
    const pending = readPendingDepositSignature();
    if (!pending) return;

    const interval = window.setInterval(() => {
      void runDepositVerification(pending, { useVerifyBusy: false }).then((ok) => {
        if (ok) clearPendingDepositSignature();
      });
    }, 8000);

    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- poll until pending deposit is credited
  }, [authToken, success]);

  async function onDeposit() {
    setError(null);
    setSuccess(null);
    setLastTx(null);
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
      setError("Enter a SOL amount greater than 0.");
      return;
    }

    setBusy(true);
    setDepositPhase("Preparing transaction…");
    let signature: string | null = null;

    try {
      const dest = new PublicKey(agentWallet);
      const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");
      const tx = new Transaction().add(
        SystemProgram.transfer({
          fromPubkey: publicKey,
          toPubkey: dest,
          lamports: Math.round(parsed * LAMPORTS_PER_SOL),
        })
      );
      tx.recentBlockhash = blockhash;
      tx.feePayer = publicKey;

      setDepositPhase("Approve in wallet…");
      signature = await sendTransaction(tx, connection);
      setLastTx(signature);
      setManualSignature(signature);
      savePendingDepositSignature(signature);

      setDepositPhase("Confirming on-chain…");
      try {
        await connection.confirmTransaction(
          { signature, blockhash, lastValidBlockHeight },
          "confirmed"
        );
      } catch {
        // Blockhash can expire while the transfer is still landing. Verification retries below.
      }
    } catch (err) {
      const recovered = signature ?? signatureFromError(err);
      if (recovered) {
        signature = recovered;
        setLastTx(recovered);
        setManualSignature(recovered);
        savePendingDepositSignature(recovered);
      } else {
        setError(err instanceof Error ? err.message : "Deposit failed");
        setDepositPhase(null);
        setBusy(false);
        return;
      }
    }

    if (signature) {
      setDepositPhase("Crediting your balance…");
      const credited = await runDepositVerification(signature, { useVerifyBusy: false });
      setDepositPhase(null);
      setBusy(false);
      if (credited) {
        setAmount("");
      }
      return;
    }

    setDepositPhase(null);
    setBusy(false);
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
      const result = await withdrawYieldTokens("SOL", parsed, authToken);
      setSuccess("Idle SOL sent back to your wallet.");
      if (result.signature) setLastTx(result.signature);
      await refreshBalances();
      setWithdrawAmount("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Withdraw failed");
    } finally {
      setWithdrawBusy(false);
    }
  }

  const idle = balances.find((row) => row.token === "SOL");

  return (
    <Panel title="Capital">
      <p className="text-sm text-muted-foreground">
        Send SOL to your Yield Agent wallet. After you send funds, the deposit is verified and
        credited automatically. If confirmation expires, paste the transaction hash below and
        verify it. The agent uses the credited balance when it stakes the best protocol for your
        requirements.
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
            Idle SOL
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
        <input
          type="number"
          min="0"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="Deposit SOL"
          disabled={busy || verifyBusy}
          className="w-36 border border-grid bg-background px-3 py-2 font-mono text-sm disabled:opacity-50"
        />
        <button
          type="button"
          disabled={busy || verifyBusy || !connected}
          onClick={() => void onDeposit()}
          className="bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
        >
          {busy || verifyBusy ? depositPhase ?? "Processing…" : "Deposit"}
        </button>
      </div>

      <div className="mt-4 border-t border-grid pt-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">
          Verify deposit by signature
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Already sent a deposit? Paste your transaction hash to credit your balance. Each
          signature can only be used once and must be a SOL transfer you signed to the Yield Agent
          wallet.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto]">
          <input
            type="text"
            value={manualSignature}
            onChange={(e) => setManualSignature(e.target.value)}
            disabled={verifyBusy || !connected || !authToken}
            placeholder="Transaction signature (base58)"
            className="border border-grid bg-background px-3 py-2.5 font-mono text-sm outline-none focus:border-signal disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() =>
              void runDepositVerification(manualSignature, { clearManualInput: true })
            }
            disabled={verifyBusy || !connected || !authToken || !manualSignature.trim()}
            className="border border-signal px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-signal transition hover:bg-signal/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {verifyBusy ? "Verifying…" : "Verify tx"}
          </button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <input
          type="number"
          min="0"
          step="0.01"
          value={withdrawAmount}
          onChange={(e) => setWithdrawAmount(e.target.value)}
          placeholder="Withdraw idle SOL"
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
