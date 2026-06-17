import {
  makeExplorerTxUrl,
  nowIso,
  rawAmountToUiAmount,
  type DcaExecution,
  type DcaPlan
} from "@bitagents/shared";
import { Connection, VersionedTransaction } from "@solana/web3.js";
import { sha256 } from "@/server/agents/util";
import { rpcUrlForNetwork } from "@/server/env";
import { loadKeypair } from "./agentWallet";
import { fetchRawQuote, fetchSwapTransaction, fetchUsdPrice } from "./jupiter";
import {
  addExecution,
  getAgentWallet,
  listActivePlans,
  logError,
  reserveIdempotencyKey,
  updatePlan
} from "./store";

function nextOrderIndex(plan: DcaPlan): number {
  return plan.ordersExecuted + 1;
}

function isDue(plan: DcaPlan, nowMs: number): boolean {
  if (plan.status !== "active") return false;
  if (plan.ordersExecuted >= plan.numberOfOrders) return false;
  if (!plan.nextExecutionAt) return true;
  return new Date(plan.nextExecutionAt).getTime() <= nowMs;
}

/** Mark a plan active and schedule its first execution. */
export function firstExecutionAt(plan: DcaPlan): string {
  if (plan.startAt) return new Date(plan.startAt * 1000).toISOString();
  return nowIso();
}

interface OrderOutcome {
  status: "success" | "failed";
  outputAmountUi: number | null;
  priceUsd: number | null;
  signature: string | null;
  simulated: boolean;
  note: string;
}

async function runDevnetDemoOrder(plan: DcaPlan): Promise<OrderOutcome> {
  // Real compute: fetch live mainnet reference prices, derive a realistic fill,
  // but never submit a transaction. Labeled clearly as a simulation.
  const [inputPrice, outputPrice] = await Promise.all([
    fetchUsdPrice(plan.inputMint),
    fetchUsdPrice(plan.outputMint)
  ]);

  let outputAmountUi: number | null = null;
  if (inputPrice.usdPrice && outputPrice.usdPrice && outputPrice.usdPrice > 0) {
    outputAmountUi = (plan.perOrderAmountUi * inputPrice.usdPrice) / outputPrice.usdPrice;
  }

  const payload = {
    planId: plan.id,
    orderIndex: nextOrderIndex(plan),
    perOrderAmountUi: plan.perOrderAmountUi,
    inputMint: plan.inputMint,
    outputMint: plan.outputMint,
    referencePriceUsd: outputPrice.usdPrice,
    at: nowIso()
  };
  const hash = sha256(payload);

  return {
    status: "success",
    outputAmountUi,
    priceUsd: outputPrice.usdPrice,
    signature: `devnet-sim-${hash.slice(0, 32)}`,
    simulated: true,
    note: "Devnet simulation — no real token purchase."
  };
}

async function runAgentWalletOrder(plan: DcaPlan): Promise<OrderOutcome> {
  // EXPERIMENTAL: signs and sends a real mainnet swap using the encrypted
  // agent wallet key. Only reachable when the mode is enabled + allowlisted.
  const stored = await getAgentWallet(plan.userWallet);
  if (!stored) {
    return { status: "failed", outputAmountUi: null, priceUsd: null, signature: null, simulated: false, note: "No agent wallet found." };
  }

  const rawIn = Math.round(plan.perOrderAmountUi * 10 ** plan.inputDecimals);
  const quote = await fetchRawQuote(plan.inputMint, plan.outputMint, rawIn, plan.slippageBps);
  if (!quote) {
    return { status: "failed", outputAmountUi: null, priceUsd: null, signature: null, simulated: false, note: "No route for this swap." };
  }
  const swapTx = await fetchSwapTransaction(quote, stored.publicKey);
  if (!swapTx) {
    return { status: "failed", outputAmountUi: null, priceUsd: null, signature: null, simulated: false, note: "Could not build swap transaction." };
  }

  try {
    const connection = new Connection(rpcUrlForNetwork(plan.network), "confirmed");
    const tx = VersionedTransaction.deserialize(Buffer.from(swapTx, "base64"));
    tx.sign([loadKeypair(stored)]);
    const signature = await connection.sendRawTransaction(tx.serialize(), { maxRetries: 3 });
    const latest = await connection.getLatestBlockhash("confirmed");
    await connection.confirmTransaction({ signature, ...latest }, "confirmed");

    const outRaw = Number((quote.outAmount as string) ?? 0);
    return {
      status: "success",
      outputAmountUi: rawAmountToUiAmount(outRaw, plan.outputDecimals),
      priceUsd: null,
      signature,
      simulated: false,
      note: "Experimental agent-wallet swap executed on mainnet."
    };
  } catch (error) {
    return {
      status: "failed",
      outputAmountUi: null,
      priceUsd: null,
      signature: null,
      simulated: false,
      note: error instanceof Error ? error.message : "Swap execution failed."
    };
  }
}

async function executeOneOrder(plan: DcaPlan): Promise<DcaExecution | null> {
  const orderIndex = nextOrderIndex(plan);
  const idempotencyKey = `${plan.id}:${orderIndex}`;
  const reserved = await reserveIdempotencyKey(idempotencyKey);
  if (!reserved) return null; // already executed by a concurrent tick

  const startedAt = performance.now();
  let outcome: OrderOutcome;
  try {
    outcome = plan.executionMode === "agent_wallet" ? await runAgentWalletOrder(plan) : await runDevnetDemoOrder(plan);
  } catch (error) {
    await logError("scheduler", error instanceof Error ? error.message : "order failed");
    outcome = { status: "failed", outputAmountUi: null, priceUsd: null, signature: null, simulated: plan.executionMode === "devnet_demo", note: "Execution error." };
  }
  const runtimeMs = Math.round((performance.now() - startedAt) * 100) / 100;

  const execution: DcaExecution = {
    id: globalThis.crypto.randomUUID(),
    planId: plan.id,
    orderIndex,
    status: outcome.status,
    network: plan.network,
    executionMode: plan.executionMode,
    simulated: outcome.simulated,
    inputAmountUi: plan.perOrderAmountUi,
    outputAmountUi: outcome.outputAmountUi,
    priceUsd: outcome.priceUsd,
    signature: outcome.signature,
    runtimeMs,
    resultHash: sha256({ planId: plan.id, orderIndex, outcome, runtimeMs }),
    note: outcome.note,
    scheduledFor: plan.nextExecutionAt ?? nowIso(),
    executedAt: nowIso()
  };
  await addExecution(execution);

  // Update plan progress.
  await updatePlan(plan.id, (current) => {
    if (outcome.status === "success") {
      current.ordersExecuted += 1;
      current.spentInputUi += plan.perOrderAmountUi;
      if (outcome.outputAmountUi) current.receivedOutputUi += outcome.outputAmountUi;
    }
    current.lastExecutedAt = nowIso();
    if (current.ordersExecuted >= current.numberOfOrders) {
      current.status = "completed";
      current.nextExecutionAt = null;
    } else {
      current.nextExecutionAt = new Date(Date.now() + current.intervalSeconds * 1000).toISOString();
    }
  });

  return execution;
}

export interface SchedulerSummary {
  processed: number;
  executions: DcaExecution[];
}

/**
 * Process due plans, executing at most one order per active plan per tick.
 * Jupiter Recurring plans are intentionally skipped — Jupiter's own keepers
 * execute those on-chain; this scheduler only drives devnet simulation and the
 * experimental agent-wallet mode.
 */
export async function processDuePlans(nowMs: number = Date.now()): Promise<SchedulerSummary> {
  const active = await listActivePlans();
  const executions: DcaExecution[] = [];

  for (const plan of active) {
    if (plan.executionMode === "jupiter_recurring") continue;
    if (!isDue(plan, nowMs)) continue;
    const execution = await executeOneOrder(plan);
    if (execution) executions.push(execution);
  }

  return { processed: executions.length, executions };
}
