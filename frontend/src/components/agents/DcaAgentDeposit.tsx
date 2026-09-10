"use client";

import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { useCallback, useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Panel } from "@/components/AppShell";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import {
  fetchAgentWallet,
  fetchUserBalances,
  verifyDepositWithRetry,
  withdrawTokens,
  type TokenBalanceRow,
  type UserDepositBalances,
  type DepositVerifyResponse,
} from "@/lib/dcaWalletClient";

const PENDING_DEPOSIT_KEY = "dca_pending_deposit_signature";

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

export function DcaAgentDeposit({
  cluster,
  authToken,
  onBalancesChange,
  refreshTick = 0,
}: {
  cluster?: string;
  authToken?: string | null;
  onBalancesChange?: (balances: UserDepositBalances | null) => void;
  refreshTick?: number;
}) {
  const { connection } = useConnection();
  const { publicKey, sendTransaction, connected } = useWallet();
  const [agentWallet, setAgentWallet] = useState<string | null>(null);
  const [circleError, setCircleError] = useState<string | null>(null);
  const [balances, setBalances] = useState<TokenBalanceRow[]>([]);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);
  const [withdrawToken, setWithdrawToken] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [lastWithdrawTx, setLastWithdrawTx] = useState<string | null>(null);
  const [manualSignature, setManualSignature] = useState("");
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [depositPhase, setDepositPhase] = useState<string | null>(null);
  const [withdrawConfirmOpen, setWithdrawConfirmOpen] = useState(false);
  const [pendingWithdraw, setPendingWithdraw] = useState<{
    token: string;
    amount: number;
    mint?: string | null;
  } | null>(null);

  const refreshBalances = useCallback(async () => {
    if (!publicKey || !authToken) {
      setBalances([]);
      onBalancesChange?.(null);
      return;
    }
    const data = await fetchUserBalances(authToken);
    if (data) {
      setBalances(data.balances);
      onBalancesChange?.(data);
    }
  }, [publicKey, authToken, onBalancesChange]);

  useEffect(() => {
    if (!authToken) {
      setAgentWallet(null);
      setCircleError(null);
      return;
    }
    void fetchAgentWallet(authToken).then((info) => {
      setAgentWallet(info?.agent_wallet ?? null);
      setCircleError(info?.circle_error ?? null);
    });
  }, [authToken]);

  useEffect(() => {
    void refreshBalances();
  }, [refreshBalances]);

  useEffect(() => {
    if (!authToken) return;
    const interval = window.setInterval(() => {
      void refreshBalances();
    }, 60_000);
    return () => window.clearInterval(interval);
  }, [authToken, refreshBalances]);

  useEffect(() => {
    if (refreshTick <= 0) return;
    void refreshBalances();
  }, [refreshTick, refreshBalances]);

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

  useEffect(() => {
    if (withdrawToken) return;
    const first = balances.find((row) => (row.withdrawable ?? 0) > 0);
    if (first) setWithdrawToken(first.token);
  }, [balances, withdrawToken]);

  function applyVerifiedBalances(result: DepositVerifyResponse) {
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
      const verified = await verifyDepositWithRetry(trimmed, authToken);
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

  async function handleDeposit() {
    if (!publicKey || !agentWallet || !amount || !authToken) return;
    const parsed = Number(amount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError("Enter a valid amount");
      return;
    }

    setBusy(true);
    setError(null);
    setSuccess(null);
    setLastTx(null);
    setDepositPhase("Preparing transaction…");

    let signature: string | null = null;

    try {
      const agentPk = new PublicKey(agentWallet);
      const tx = new Transaction();
      const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");

      tx.add(
        SystemProgram.transfer({
          fromPubkey: publicKey,
          toPubkey: agentPk,
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
        // Tx may still land - verification below will retry until indexed.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deposit failed");
      return;
    } finally {
      setDepositPhase(null);
      setBusy(false);
    }

    if (signature) {
      setDepositPhase("Crediting your balance…");
      setBusy(true);
      const credited = await runDepositVerification(signature, { useVerifyBusy: false });
      setDepositPhase(null);
      setBusy(false);
      if (credited) {
        setAmount("");
      }
    }
  }

  const selectedWithdrawRow = balances.find((row) => row.token === withdrawToken);
  const withdrawableAmount = selectedWithdrawRow?.withdrawable ?? 0;

  function requestWithdraw() {
    if (!publicKey || !authToken || !withdrawToken || !withdrawAmount) return;
    const parsed = Number(withdrawAmount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError("Enter a valid withdraw amount");
      return;
    }
    if (parsed > withdrawableAmount + 1e-12) {
      setError(`Maximum withdrawable ${withdrawToken}: ${withdrawableAmount}`);
      return;
    }
    setError(null);
    setPendingWithdraw({
      token: withdrawToken,
      amount: parsed,
      mint: selectedWithdrawRow?.mint,
    });
    setWithdrawConfirmOpen(true);
  }

  async function executeWithdraw() {
    if (!publicKey || !authToken || !pendingWithdraw) return;

    setWithdrawBusy(true);
    setError(null);
    setLastWithdrawTx(null);

    try {
      const result = await withdrawTokens(
        pendingWithdraw.token,
        pendingWithdraw.amount,
        authToken
      );
      if (result.signature) setLastWithdrawTx(result.signature);
      await refreshBalances();
      setWithdrawAmount("");
      setWithdrawConfirmOpen(false);
      setPendingWithdraw(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Withdrawal failed");
    } finally {
      setWithdrawBusy(false);
    }
  }

  return (
    <Panel title="AI Agent wallet · deposit & withdraw">
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Deposit <strong className="text-foreground">SOL only</strong> to the AI Agent wallet on{" "}
            <span className="text-foreground">{cluster ?? "Solana"}</span>. After you send
            funds, your deposit is verified automatically and credited to your balance. You can
            also paste a transaction signature below if verification was missed. Withdrawals still
            support any credited token balance.
          </p>

          <div className="font-mono text-[11px] leading-relaxed text-muted-foreground">
            <span className="uppercase tracking-[0.16em] text-signal">Your DCA agent wallet</span>
            <div className="mt-1 break-all text-foreground">
              {agentWallet ?? (
                authToken
                  ? "Provisioning…"
                  : "Sign in to provision your personal agent wallet"
              )}
            </div>
            {circleError && (
              <div className="mt-2 border border-warn/40 bg-warn/10 px-2 py-1.5 text-[10px] normal-case tracking-normal text-warn">
                {circleError}
              </div>
            )}
            <div className="mt-2 text-[10px] uppercase tracking-[0.14em] text-signal">
              Deposits · SOL only
            </div>
          </div>

        <LegalSignInNotice />

          <div className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-[140px_1fr_auto]">
              <div className="border border-grid bg-background px-3 py-2.5 font-mono text-sm text-foreground">
                SOL
              </div>
              <input
                type="number"
                min="0"
                step="any"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                disabled={busy || verifyBusy || !connected}
                placeholder="Amount"
                className="border border-grid bg-background px-3 py-2.5 font-mono text-sm outline-none focus:border-signal disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void handleDeposit()}
                disabled={busy || !connected || !agentWallet || !amount}
                className="bg-signal px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy || verifyBusy
                  ? depositPhase ?? "Processing…"
                  : "Deposit SOL"}
              </button>
            </div>
          </div>

          {success && (
            <div className="border border-signal/40 bg-signal/10 px-3 py-2 font-mono text-xs text-signal">
              {success}
            </div>
          )}

          {error && (
            <div className="border border-warn/40 bg-warn/10 px-3 py-2 font-mono text-xs text-warn">
              {error}
            </div>
          )}

          {lastTx && (
            <a
              href={explorerUrlForSignature(lastTx, cluster)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex font-mono text-xs text-signal hover:underline"
            >
              Last deposit tx · {lastTx.slice(0, 8)}…{lastTx.slice(-8)} ↗
            </a>
          )}

          <div className="border-t border-grid pt-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">
              Verify deposit by signature
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Already sent a deposit? Paste your transaction hash to credit your balance. Each
              signature can only be used once and must be a transfer you signed to the agent
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
                onClick={() => void runDepositVerification(manualSignature, { clearManualInput: true })}
                disabled={verifyBusy || !connected || !authToken || !manualSignature.trim()}
                className="border border-signal px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-signal transition hover:bg-signal/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {verifyBusy ? "Verifying…" : "Verify tx"}
              </button>
            </div>
          </div>

          <div className="border-t border-grid pt-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">
              Withdraw to your wallet
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Withdraw unused deposits and tokens bought by your DCA plans. Amounts reserved for
              active plans cannot be withdrawn.
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-[140px_1fr_auto]">
              <select
                value={withdrawToken}
                onChange={(e) => setWithdrawToken(e.target.value)}
                disabled={withdrawBusy || !connected || balances.length === 0}
                className="border border-grid bg-background px-3 py-2.5 font-mono text-sm outline-none focus:border-signal disabled:opacity-50"
              >
                {balances.length === 0 ? (
                  <option value="">No balance</option>
                ) : (
                  balances.map((row) => (
                    <option key={row.token} value={row.token}>
                      {row.token} ({row.withdrawable ?? 0})
                    </option>
                  ))
                )}
              </select>
              <input
                type="number"
                min="0"
                step="any"
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                disabled={withdrawBusy || !connected || !withdrawToken}
                placeholder={`Max ${withdrawableAmount}`}
                className="border border-grid bg-background px-3 py-2.5 font-mono text-sm outline-none focus:border-signal disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => requestWithdraw()}
                disabled={
                  withdrawBusy ||
                  !connected ||
                  !authToken ||
                  !withdrawToken ||
                  !withdrawAmount ||
                  withdrawableAmount <= 0
                }
                className="border border-signal px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-signal transition hover:bg-signal/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {withdrawBusy ? "Sending…" : "Withdraw"}
              </button>
            </div>
            {withdrawToken && withdrawableAmount > 0 && (
              <button
                type="button"
                onClick={() => setWithdrawAmount(String(withdrawableAmount))}
                disabled={withdrawBusy || !connected}
                className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:text-signal mr-2"
              >
                Use max · {withdrawableAmount} {withdrawToken}
              </button>
            )}
            {lastWithdrawTx && (
              <a
                href={explorerUrlForSignature(lastWithdrawTx, cluster)}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex font-mono text-xs text-signal hover:underline"
              >
                Last withdraw tx · {lastWithdrawTx.slice(0, 8)}…{lastWithdrawTx.slice(-8)} ↗
              </a>
            )}
          </div>
        </div>

        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">
            Your credited balance
          </div>
          {!connected ? (
            <p className="mt-3 text-sm text-muted-foreground">Connect wallet to view balance.</p>
          ) : balances.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">No verified deposits yet.</p>
          ) : (
            <div className="mt-3 space-y-2">
              {balances.map((row) => (
                <div key={row.token} className="border border-grid bg-background/60 px-3 py-2.5">
                  <div className="flex items-center justify-between font-display text-base font-bold">
                    <span>{row.token}</span>
                    <span className="text-signal tabular-nums">{row.available} avail</span>
                  </div>
                  <div className="mt-1 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                    <span>withdraw {row.withdrawable ?? 0}</span>
                    {(row.acquired_from_dca ?? 0) > 0 && (
                      <span className="text-signal">dca +{row.acquired_from_dca}</span>
                    )}
                  </div>
                  {row.mint && (
                    <div className="mt-1 break-all font-mono text-[9px] text-muted-foreground">
                      {row.mint}
                    </div>
                  )}
                  <div className="mt-1 grid grid-cols-3 gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                    <span>dep {row.deposited}</span>
                    <span>rsv {row.reserved_for_plans}</span>
                    <span>spent {row.spent_in_plans}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={withdrawConfirmOpen}
        onOpenChange={(open) => {
          setWithdrawConfirmOpen(open);
          if (!open) setPendingWithdraw(null);
        }}
        title="Confirm withdrawal"
        description={
          pendingWithdraw ? (
            <>
              <p>
                Please confirm before proceeding: withdraw{" "}
                <strong className="text-foreground">
                  {pendingWithdraw.amount} {pendingWithdraw.token}
                </strong>{" "}
                to your connected wallet.
              </p>
              {pendingWithdraw.mint && (
                <code className="mt-2 block break-all font-mono text-[10px] text-muted-foreground">
                  Mint: {pendingWithdraw.mint}
                </code>
              )}
            </>
          ) : (
            "Please confirm this withdrawal."
          )
        }
        confirmLabel="Withdraw"
        cancelLabel="Cancel"
        busy={withdrawBusy}
        onConfirm={() => void executeWithdraw()}
      />
    </Panel>
  );
}
