import { WSOL_MINT, solToLamports } from "@bitagents/shared";
import {
  createAssociatedTokenAccountIdempotentInstruction,
  createCloseAccountInstruction,
  createTransferInstruction,
  getAccount,
  getAssociatedTokenAddress
} from "@solana/spl-token";
import {
  Connection,
  Keypair,
  PublicKey,
  SystemProgram,
  Transaction,
  VersionedTransaction
} from "@solana/web3.js";
import bs58 from "bs58";

// ---------------------------------------------------------------------------
// Client-side agent wallet.
//
// A throwaway "hot" keypair that can sign its own swaps so it can auto-buy on a
// schedule without a wallet popup each time. The secret key lives ONLY in the
// browser's localStorage — it is never sent to or stored on the server, and is
// never logged. The user funds it with a tiny amount and can sweep everything
// back to their main wallet at any time. Caps keep the at-risk amount small.
// ---------------------------------------------------------------------------

export interface AgentBotCaps {
  maxOrders: number;
  maxPerOrderSol: number;
  maxTotalSol: number;
  minIntervalSeconds: number;
}

export const AGENT_BOT_CAPS: AgentBotCaps = {
  maxOrders: 10,
  maxPerOrderSol: 0.05,
  maxTotalSol: 0.2,
  minIntervalSeconds: 60
};

// Rough headroom for the output token account rent (~0.002 SOL) plus per-swap
// network/priority fees, so the funded amount covers the whole run.
const FUNDING_HEADROOM_SOL = 0.01;

export interface ClampedAgentPlan {
  numberOfOrders: number;
  perOrderAmountUi: number;
  intervalSeconds: number;
  warnings: string[];
}

/** Clamp a parsed plan to the agent-bot safety caps (pure, unit-tested). */
export function clampAgentPlan(
  input: { numberOfOrders: number; perOrderAmountUi: number; intervalSeconds: number },
  caps: AgentBotCaps = AGENT_BOT_CAPS
): ClampedAgentPlan {
  const warnings: string[] = [];
  let numberOfOrders = Math.max(1, Math.floor(input.numberOfOrders));
  let perOrderAmountUi = input.perOrderAmountUi;
  let intervalSeconds = Math.round(input.intervalSeconds);

  if (numberOfOrders > caps.maxOrders) {
    numberOfOrders = caps.maxOrders;
    warnings.push(`Capped to ${caps.maxOrders} buys for safety.`);
  }
  if (perOrderAmountUi > caps.maxPerOrderSol) {
    perOrderAmountUi = caps.maxPerOrderSol;
    warnings.push(`Capped per-buy to ${caps.maxPerOrderSol} SOL for safety.`);
  }
  if (intervalSeconds < caps.minIntervalSeconds) {
    intervalSeconds = caps.minIntervalSeconds;
    warnings.push(`Minimum interval is ${caps.minIntervalSeconds}s; using ${caps.minIntervalSeconds}s.`);
  }
  if (perOrderAmountUi * numberOfOrders > caps.maxTotalSol) {
    numberOfOrders = Math.max(1, Math.floor(caps.maxTotalSol / perOrderAmountUi));
    warnings.push(`Total capped to ${caps.maxTotalSol} SOL — reduced to ${numberOfOrders} buys.`);
  }

  return { numberOfOrders, perOrderAmountUi, intervalSeconds, warnings };
}

/** Suggested amount to fund the agent wallet with (pure, unit-tested). */
export function estimateFundingSol(perOrderAmountUi: number, numberOfOrders: number): number {
  const total = perOrderAmountUi * numberOfOrders + FUNDING_HEADROOM_SOL;
  return Math.round(total * 1e6) / 1e6;
}

function storageKey(userAddress: string): string {
  return `bitagents.dca.agentWallet.${userAddress}`;
}

/** Load the persisted agent keypair for a user, if one exists. */
export function loadAgentKeypair(userAddress: string): Keypair | null {
  if (typeof window === "undefined") return null;
  const secret = window.localStorage.getItem(storageKey(userAddress));
  if (!secret) return null;
  try {
    return Keypair.fromSecretKey(bs58.decode(secret));
  } catch {
    return null;
  }
}

/** Return the user's agent keypair, generating + persisting one if needed. */
export function getOrCreateAgentKeypair(userAddress: string): Keypair {
  const existing = loadAgentKeypair(userAddress);
  if (existing) return existing;
  const keypair = Keypair.generate();
  if (typeof window !== "undefined") {
    window.localStorage.setItem(storageKey(userAddress), bs58.encode(keypair.secretKey));
  }
  return keypair;
}

/** Forget the agent keypair (use only after sweeping funds out). */
export function clearAgentKeypair(userAddress: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(storageKey(userAddress));
}

export async function getSolBalance(connection: Connection, publicKey: PublicKey): Promise<number> {
  const lamports = await connection.getBalance(publicKey, "confirmed");
  return lamports / 1e9;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// `connection.confirmTransaction` relies on a websocket signature subscription
// and/or a block-height comparison. Both are unreliable on a public, load-
// balanced RPC like PublicNode: the websocket is flaky, and consecutive HTTP
// requests can hit different backend nodes sitting at slightly different slots,
// so a getBlockHeight from one node can race ahead of the blockhash's
// lastValidBlockHeight from another and trigger a *false* "expired" error even
// though the transaction lands. Instead, confirm purely by polling
// getSignatureStatuses over HTTP on a wall-clock budget (no cross-node height
// comparison), rebroadcasting the raw transaction periodically to help it land.
async function confirmSignature({
  connection,
  signature,
  rawTransaction
}: {
  connection: Connection;
  signature: string;
  rawTransaction?: Uint8Array;
}): Promise<void> {
  const startedAt = Date.now();
  const timeoutMs = 90_000;
  let lastRebroadcast = 0;

  for (;;) {
    const { value } = await connection.getSignatureStatuses([signature], { searchTransactionHistory: true });
    const status = value[0];
    if (status) {
      if (status.err) {
        throw new Error(`Transaction failed on-chain: ${JSON.stringify(status.err)}`);
      }
      if (status.confirmationStatus === "confirmed" || status.confirmationStatus === "finalized") {
        return;
      }
    }

    if (Date.now() - startedAt > timeoutMs) {
      // Grace checks: the tx may have landed right at the deadline but not yet be
      // visible on the node we just hit. Re-poll a few times before giving up.
      for (let i = 0; i < 4; i += 1) {
        await sleep(2500);
        const final = (await connection.getSignatureStatuses([signature], { searchTransactionHistory: true })).value[0];
        if (final && !final.err) return;
        if (final?.err) throw new Error(`Transaction failed on-chain: ${JSON.stringify(final.err)}`);
      }
      throw new Error("Transaction was not confirmed in time. It may still land — check the explorer before retrying.");
    }

    if (rawTransaction && Date.now() - lastRebroadcast > 4000) {
      lastRebroadcast = Date.now();
      try {
        await connection.sendRawTransaction(rawTransaction, { skipPreflight: true, maxRetries: 0 });
      } catch {
        /* rebroadcast is best-effort */
      }
    }

    await sleep(2000);
  }
}

/** Move SOL from the user's connected wallet into the agent wallet (user signs). */
export async function fundAgentWallet({
  connection,
  from,
  to,
  amountSol,
  sendTransaction
}: {
  connection: Connection;
  from: PublicKey;
  to: PublicKey;
  amountSol: number;
  sendTransaction: (transaction: Transaction, connection: Connection) => Promise<string>;
}): Promise<string> {
  const transaction = new Transaction().add(
    SystemProgram.transfer({ fromPubkey: from, toPubkey: to, lamports: solToLamports(amountSol) })
  );
  const latest = await connection.getLatestBlockhash("confirmed");
  transaction.recentBlockhash = latest.blockhash;
  transaction.feePayer = from;
  const signature = await sendTransaction(transaction, connection);
  await confirmSignature({ signature, connection });
  return signature;
}

/** Sign a Jupiter swap (base64 VersionedTransaction) with the agent key and submit it. */
export async function signAndSendSwap({
  base64,
  connection,
  keypair
}: {
  base64: string;
  connection: Connection;
  keypair: Keypair;
}): Promise<string> {
  const transaction = VersionedTransaction.deserialize(Uint8Array.from(Buffer.from(base64, "base64")));
  transaction.sign([keypair]);
  const raw = transaction.serialize();
  const signature = await connection.sendRawTransaction(raw, { maxRetries: 3 });
  await confirmSignature({ signature, connection, rawTransaction: raw });
  return signature;
}

async function sendWithKeypair(
  connection: Connection,
  transaction: Transaction,
  keypair: Keypair
): Promise<string> {
  const latest = await connection.getLatestBlockhash("confirmed");
  transaction.recentBlockhash = latest.blockhash;
  transaction.feePayer = keypair.publicKey;
  transaction.sign(keypair);
  const raw = transaction.serialize();
  const signature = await connection.sendRawTransaction(raw, { maxRetries: 3 });
  await confirmSignature({ signature, connection, rawTransaction: raw });
  return signature;
}

export interface SweepResult {
  tokenSignature: string | null;
  solSignature: string | null;
  tokenAmountRaw: string | null;
}

/**
 * Return everything in the agent wallet to the user's main wallet: first the
 * bought token (transfer + close its account to reclaim rent), then the
 * remaining SOL. Both are signed by the agent key.
 */
export async function sweepAgentWallet({
  connection,
  keypair,
  destination,
  outputMint
}: {
  connection: Connection;
  keypair: Keypair;
  destination: string;
  outputMint: string;
}): Promise<SweepResult> {
  const owner = keypair.publicKey;
  const dest = new PublicKey(destination);
  const result: SweepResult = { tokenSignature: null, solSignature: null, tokenAmountRaw: null };

  if (outputMint && outputMint !== WSOL_MINT) {
    const mint = new PublicKey(outputMint);
    const agentAta = await getAssociatedTokenAddress(mint, owner);
    let amount = 0n;
    try {
      amount = (await getAccount(connection, agentAta)).amount;
    } catch {
      amount = 0n;
    }
    if (amount > 0n) {
      const destAta = await getAssociatedTokenAddress(mint, dest);
      const tx = new Transaction().add(
        createAssociatedTokenAccountIdempotentInstruction(owner, destAta, dest, mint),
        createTransferInstruction(agentAta, destAta, owner, amount),
        createCloseAccountInstruction(agentAta, dest, owner)
      );
      result.tokenSignature = await sendWithKeypair(connection, tx, keypair);
      result.tokenAmountRaw = amount.toString();
    }
  }

  const lamports = await connection.getBalance(owner, "confirmed");
  const feeBuffer = 5000;
  const sendable = lamports - feeBuffer;
  if (sendable > 0) {
    const tx = new Transaction().add(
      SystemProgram.transfer({ fromPubkey: owner, toPubkey: dest, lamports: sendable })
    );
    result.solSignature = await sendWithKeypair(connection, tx, keypair);
  }

  return result;
}
