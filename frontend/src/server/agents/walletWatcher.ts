import {
  nowIso,
  shortAddress,
  type SolanaNetwork,
  type WalletWatcherInput,
  type WalletWatcherResult
} from "@bitagents/shared";
import { performance } from "node:perf_hooks";
import { fetchWalletSnapshot } from "@/server/agents/solana";
import { rpcUrlForNetwork } from "@/server/env";
import { generateNarrative } from "@/server/agents/llm";
import { sha256 } from "@/server/agents/util";

export async function computeWalletWatcher(
  input: WalletWatcherInput,
  network: SolanaNetwork
): Promise<WalletWatcherResult> {
  const start = performance.now();
  const snapshot = await fetchWalletSnapshot(network, input.walletAddress);

  const riskNotes: string[] = [];
  if (snapshot.solBalance === 0) {
    riskNotes.push(`Wallet holds 0 SOL on ${network}; it may be new, unused, or fully swept.`);
  }
  if (snapshot.failedCount > 0) {
    riskNotes.push(`${snapshot.failedCount} of the latest ${snapshot.latestSignatures.length} transactions failed.`);
  }
  if (snapshot.tokenAccountsCount > 30) {
    riskNotes.push(`High token-account count (${snapshot.tokenAccountsCount}) can indicate airdrop farming or heavy DeFi usage.`);
  }
  if (snapshot.latestSignatures.length === 0) {
    riskNotes.push(`No recent transaction signatures found on ${network}.`);
  } else if (snapshot.activeDays <= 1 && snapshot.latestSignatures.length >= 4) {
    riskNotes.push("Recent activity is bursty (many transactions within a single day).");
  }
  riskNotes.push("Read-only on-chain heuristics. Not financial advice or a security audit.");

  const fallbackSummary =
    `Wallet ${shortAddress(input.walletAddress)} holds ${snapshot.solBalance.toFixed(4)} SOL across ` +
    `${snapshot.tokenAccountsCount} token account${snapshot.tokenAccountsCount === 1 ? "" : "s"} on ${network}. ` +
    (snapshot.latestSignatures.length > 0
      ? `It shows ${snapshot.latestSignatures.length} recent signature${snapshot.latestSignatures.length === 1 ? "" : "s"} (${snapshot.failedCount} failed) across ${snapshot.activeDays || 1} active day(s).`
      : "It has no recent transaction history on this network.");

  const narrative = await generateNarrative({
    system:
      "You are a concise on-chain analyst. Summarize a Solana wallet in 2-3 plain sentences. " +
      "Use only the provided facts, never invent balances or prices, and never give financial advice.",
    prompt:
      `Network: ${network}\nAddress: ${input.walletAddress}\nSOL balance: ${snapshot.solBalance}\n` +
      `Token accounts: ${snapshot.tokenAccountsCount}\nRecent signatures: ${snapshot.latestSignatures.length}\n` +
      `Failed recent tx: ${snapshot.failedCount}\nActive days in sample: ${snapshot.activeDays}`,
    fallback: fallbackSummary
  });

  const core = {
    type: "wallet_watcher" as const,
    walletAddress: input.walletAddress,
    solBalance: snapshot.solBalance,
    tokenAccountsCount: snapshot.tokenAccountsCount,
    latestSignatures: snapshot.latestSignatures,
    riskNotes,
    network
  };

  return {
    ...core,
    summary: narrative.text,
    engine: narrative.engine,
    computedAt: nowIso(),
    runtimeMs: Math.round((performance.now() - start) * 100) / 100,
    resultHash: sha256(core),
    rpcUrl: rpcUrlForNetwork(network)
  };
}
