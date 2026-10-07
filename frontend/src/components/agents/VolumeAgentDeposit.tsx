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
  type ResolvedToken,
  type TokenBalanceRow,
  type UserDepositBalances,
} from "@/lib/volumeWalletClient";

const PRESET_TOKENS = ["SOL", "USDC"] as const;

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
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);

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
      const signature = await sendTransaction(tx, connection);
      setLastTx(signature);
      await connection.confirmTransaction({ signature, blockhash, lastValidBlockHeight }, "confirmed").catch(() => {});
      const verified = await verifyVolumeDepositWithRetry(signature, authToken);
      await refreshBalances();
      setAmount("");
      setSuccess(
        verified.status === "already_recorded"
          ? "Deposit already credited."
          : "Deposit verified and credited."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deposit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Volume Agent wallet · deposit">
      <div className="space-y-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal">
          {cluster ?? "Solana"} · 0.25% per swap leg · ~{poolCreationCostSol} SOL pool reserve if needed
        </div>

        {!connected && <WalletMultiButton className="!w-full !justify-center" />}
        {connected && !authToken && <LegalSignInNotice />}

        {agentWallet && (
          <p className="font-mono text-[11px] text-muted-foreground break-all">
            Agent wallet: <span className="text-foreground">{agentWallet}</span>
          </p>
        )}

        {authToken && (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 font-mono text-[11px]">
                <span className="text-muted-foreground">Token</span>
                <select
                  className="w-full border-2 border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                  value={token}
                  onChange={(e) => setToken(e.target.value as typeof token)}
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
                    className="w-full border-2 border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                    value={customMint}
                    onChange={(e) => setCustomMint(e.target.value)}
                    placeholder="Token mint for your pair"
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
                  className="w-full border-2 border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0.0"
                  inputMode="decimal"
                />
              </label>
            </div>

            <button
              type="button"
              onClick={() => void handleDeposit()}
              disabled={busy || !agentWallet}
              className="w-full bg-signal/10 px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-signal disabled:opacity-50"
            >
              {busy ? "Sending…" : "Deposit to Volume Agent"}
            </button>

            {balances.length > 0 && (
              <div className="space-y-2 p-3">
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
          </>
        )}

        {error && <p className="font-mono text-[11px] text-warn">{error}</p>}
        {success && <p className="font-mono text-[11px] text-signal">{success}</p>}
        {lastTx && (
          <a
            href={explorerUrlForSignature(lastTx, cluster)}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[11px] text-signal"
          >
            View last deposit on Explorer ↗
          </a>
        )}
      </div>
    </Panel>
  );
}
