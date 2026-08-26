"use client";

import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import {
  createAssociatedTokenAccountInstruction,
  createTransferInstruction,
  getAssociatedTokenAddress,
  getAccount,
} from "@solana/spl-token";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { useCallback, useEffect, useState } from "react";
import { Panel } from "@/components/AppShell";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import {
  DEPOSIT_TOKEN_DECIMALS,
  DEPOSIT_TOKEN_MINTS,
  fetchVolumeAgentWallet,
  fetchVolumeUserBalances,
  resolveVolumeToken,
  verifyVolumeDepositWithRetry,
  type DepositVerifyResponse,
  type ResolvedToken,
  type TokenBalanceRow,
  type UserDepositBalances,
} from "@/lib/volumeWalletClient";

const PRESET_TOKENS = ["SOL", "USDC"] as const;
const PENDING_DEPOSIT_KEY = "volume_pending_deposit_signature";

function savePendingDepositSignature(signature: string) {
  try {
    sessionStorage.setItem(PENDING_DEPOSIT_KEY, signature);
  } catch {
    /* ignore */
  }
}

function clearPendingDepositSignature() {
  try {
    sessionStorage.removeItem(PENDING_DEPOSIT_KEY);
  } catch {
    /* ignore */
  }
}

function readPendingDepositSignature(): string | null {
  try {
    return sessionStorage.getItem(PENDING_DEPOSIT_KEY);
  } catch {
    return null;
  }
}

export function VolumeAgentDeposit({
  cluster,
  authToken,
  onBalancesChange,
  refreshTick = 0,
  poolCreationCostSol = 0.02669,
}: {
  cluster?: string;
  authToken?: string | null;
  onBalancesChange?: (balances: UserDepositBalances | null) => void;
  refreshTick?: number;
  poolCreationCostSol?: number;
}) {
  const { connection } = useConnection();
  const { publicKey, sendTransaction, connected } = useWallet();
  const [agentWallet, setAgentWallet] = useState<string | null>(null);
  const [balances, setBalances] = useState<TokenBalanceRow[]>([]);
  const [token, setToken] = useState<(typeof PRESET_TOKENS)[number] | "custom">("SOL");
  const [customMint, setCustomMint] = useState("");
  const [resolvedCustom, setResolvedCustom] = useState<ResolvedToken | null>(null);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);
  const [manualSignature, setManualSignature] = useState("");
  const [depositPhase, setDepositPhase] = useState<string | null>(null);

  const refreshBalances = useCallback(async () => {
    if (!authToken) return;
    const data = await fetchVolumeUserBalances(authToken);
    if (data) {
      setBalances(data.balances);
      onBalancesChange?.(data);
    }
  }, [authToken, onBalancesChange]);

  useEffect(() => {
    void fetchVolumeAgentWallet().then((info) => {
      setAgentWallet(info?.agent_wallet ?? null);
    });
  }, []);

  useEffect(() => {
    void refreshBalances();
  }, [refreshBalances, refreshTick]);

  useEffect(() => {
    if (!authToken) return;
    const interval = window.setInterval(() => {
      void refreshBalances();
    }, 60_000);
    return () => window.clearInterval(interval);
  }, [authToken, refreshBalances]);

  useEffect(() => {
    if (token !== "custom" || customMint.trim().length < 32) {
      setResolvedCustom(null);
      return;
    }
    const timer = setTimeout(() => {
      void resolveVolumeToken(customMint.trim())
        .then(setResolvedCustom)
        .catch(() => setResolvedCustom(null));
    }, 400);
    return () => clearTimeout(timer);
  }, [token, customMint]);

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
      const verified = await verifyVolumeDepositWithRetry(trimmed, authToken);
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
        `${message} Your transfer may still be confirming — we will keep retrying automatically.`
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

      if (token === "SOL") {
        tx.add(
          SystemProgram.transfer({
            fromPubkey: publicKey,
            toPubkey: agentPk,
            lamports: Math.round(parsed * LAMPORTS_PER_SOL),
          })
        );
      } else {
        let mintAddress: string;
        let decimals: number;
        if (token === "custom") {
          if (!resolvedCustom) {
            setError("Enter a valid SPL token mint");
            setDepositPhase(null);
            setBusy(false);
            return;
          }
          mintAddress = resolvedCustom.mint;
          decimals = resolvedCustom.decimals;
        } else {
          mintAddress = DEPOSIT_TOKEN_MINTS[token];
          decimals = DEPOSIT_TOKEN_DECIMALS[token] ?? 6;
        }

        const mint = new PublicKey(mintAddress);
        const rawAmount = BigInt(Math.round(parsed * 10 ** decimals));
        const userAta = await getAssociatedTokenAddress(mint, publicKey);
        const agentAta = await getAssociatedTokenAddress(mint, agentPk);
        try {
          await getAccount(connection, agentAta);
        } catch {
          tx.add(createAssociatedTokenAccountInstruction(publicKey, agentAta, agentPk, mint));
        }
        tx.add(createTransferInstruction(userAta, agentAta, publicKey, rawAmount));
      }

      tx.recentBlockhash = blockhash;
      tx.feePayer = publicKey;

      setDepositPhase("Approve in wallet…");
      signature = await sendTransaction(tx, connection);
      setLastTx(signature);
      setManualSignature(signature);
      savePendingDepositSignature(signature);

      setDepositPhase("Confirming on-chain…");
      await connection
        .confirmTransaction({ signature, blockhash, lastValidBlockHeight }, "confirmed")
        .catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deposit failed");
      setDepositPhase(null);
      setBusy(false);
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

  return (
    <Panel title="Volume Agent wallet · deposit">
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Deposit your <strong className="text-foreground">token + SOL</strong> to the Volume Agent wallet on{" "}
          {cluster ?? "Solana"}. After you send funds, your deposit is verified automatically and
          credited. You can also paste a transaction signature below if verification was missed.
          If no Meteora DLMM pool exists, reserve ~{poolCreationCostSol} SOL for pool creation plus
          trade budget. Platform fee is <strong className="text-foreground">0.25% per swap leg</strong>.
        </p>

        {!connected && <WalletMultiButton className="!w-full !justify-center" />}
        {connected && !authToken && <LegalSignInNotice />}

        {agentWallet && (
          <p className="font-mono text-[11px] text-muted-foreground break-all">
            Agent wallet: <span className="text-foreground">{agentWallet}</span>
          </p>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 font-mono text-[11px]">
            <span className="text-muted-foreground">Token</span>
            <select
              className="w-full border border-grid bg-background px-3 py-2 text-foreground"
              value={token}
              onChange={(e) => setToken(e.target.value as typeof token)}
              disabled={busy || verifyBusy || !connected}
            >
              {PRESET_TOKENS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
              <option value="custom">Custom SPL mint</option>
            </select>
          </label>
          {token === "custom" && (
            <label className="space-y-1 font-mono text-[11px] sm:col-span-2">
              <span className="text-muted-foreground">Mint address</span>
              <input
                className="w-full border border-grid bg-background px-3 py-2 text-foreground"
                value={customMint}
                onChange={(e) => setCustomMint(e.target.value)}
                placeholder="Token mint for your pair"
                disabled={busy || verifyBusy || !connected}
              />
              {resolvedCustom && (
                <span className="text-signal">
                  {resolvedCustom.symbol} · {resolvedCustom.decimals} decimals
                </span>
              )}
            </label>
          )}
          <label className="space-y-1 font-mono text-[11px]">
            <span className="text-muted-foreground">Amount</span>
            <input
              className="w-full border border-grid bg-background px-3 py-2 text-foreground"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.0"
              inputMode="decimal"
              disabled={busy || verifyBusy || !connected}
            />
          </label>
        </div>

        <button
          type="button"
          onClick={() => void handleDeposit()}
          disabled={busy || verifyBusy || !agentWallet || !connected || !authToken}
          className="w-full border border-signal bg-signal/10 px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-signal disabled:opacity-50"
        >
          {busy || verifyBusy ? depositPhase ?? "Processing…" : "Deposit to Volume Agent"}
        </button>

        {balances.length > 0 && (
          <div className="space-y-2 border border-grid p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Balances</p>
            {balances.map((row) => (
              <div key={row.token} className="flex justify-between font-mono text-[11px]">
                <span>{row.token}</span>
                <span className="text-foreground">
                  {row.available} available · {row.reserved_for_campaigns} reserved
                </span>
              </div>
            ))}
          </div>
        )}

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
            signature can only be used once and must be a transfer you signed to the Volume
            Agent wallet.
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
      </div>
    </Panel>
  );
}
