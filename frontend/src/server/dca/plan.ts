import {
  DCA_RISK_WARNINGS,
  JUPITER_MIN_ORDER_USD,
  computePerOrderAmount,
  estimateDurationSeconds,
  nowIso,
  validateDcaPlan,
  type DcaExecutionMode,
  type DcaPlan,
  type SolanaNetwork,
  type TokenInfo
} from "@bitagents/shared";
import type { ParsedDcaFields } from "./parse";

export interface PlanContext {
  userWallet: string;
  network: SolanaNetwork;
  enableMainnetDca: boolean;
  executionMode?: DcaExecutionMode;
}

export interface DerivedAmounts {
  numberOfOrders: number | null;
  totalInputAmountUi: number | null;
  perOrderAmountUi: number | null;
}

/**
 * Resolve the (total, perOrder, numberOfOrders) triangle from whatever subset
 * the user provided, optionally using a stated duration + interval to derive
 * the order count. Total + count are treated as authoritative for per-order.
 */
export function deriveAmounts(fields: ParsedDcaFields): DerivedAmounts {
  let numberOfOrders = fields.numberOfOrders;
  let total = fields.totalInputAmountUi;
  let perOrder = fields.perOrderAmountUi;
  const interval = fields.intervalSeconds;
  const duration = fields.durationSeconds;

  if (numberOfOrders == null && total != null && perOrder != null && perOrder > 0) {
    numberOfOrders = Math.max(1, Math.round(total / perOrder));
  }
  if (numberOfOrders == null && duration != null && interval != null && interval > 0) {
    numberOfOrders = Math.max(1, Math.round(duration / interval));
  }
  if (total == null && perOrder != null && numberOfOrders != null) {
    total = perOrder * numberOfOrders;
  }
  if (total != null && numberOfOrders != null && numberOfOrders > 0) {
    // Total budget + order count fully determine the per-order amount.
    perOrder = computePerOrderAmount(total, numberOfOrders);
  } else if (perOrder == null && total != null && numberOfOrders != null) {
    perOrder = computePerOrderAmount(total, numberOfOrders);
  }

  return { numberOfOrders, totalInputAmountUi: total, perOrderAmountUi: perOrder };
}

export type AssembleResult = { ok: true; plan: DcaPlan } | { ok: false; clarification: string };

function makeId(): string {
  return `dca_${globalThis.crypto.randomUUID()}`;
}

function resolveExecutionMode(ctx: PlanContext): DcaExecutionMode {
  if (ctx.executionMode) return ctx.executionMode;
  if (ctx.network === "mainnet" && ctx.enableMainnetDca) return "jupiter_recurring";
  return "devnet_demo";
}

export function assembleDcaPlan(
  inputToken: TokenInfo,
  outputToken: TokenInfo,
  fields: ParsedDcaFields,
  ctx: PlanContext
): AssembleResult {
  const interval = fields.intervalSeconds;
  if (interval == null) {
    return {
      ok: false,
      clarification:
        "How often should I buy? For example: 'every 10 minutes', 'every hour', or 'every day'."
    };
  }

  const { numberOfOrders, totalInputAmountUi, perOrderAmountUi } = deriveAmounts(fields);

  if (numberOfOrders == null || (totalInputAmountUi == null && perOrderAmountUi == null)) {
    return {
      ok: false,
      clarification:
        "How much should I spend? Tell me a total budget and either a per-buy amount or how many buys — " +
        "e.g. '0.01 SOL each using 1 SOL total' or 'for 30 buys'."
    };
  }

  const total = totalInputAmountUi ?? (perOrderAmountUi ?? 0) * numberOfOrders;
  const perOrder = perOrderAmountUi ?? computePerOrderAmount(total, numberOfOrders);
  const slippageBps = fields.slippageBps ?? 100;
  const executionMode = resolveExecutionMode(ctx);
  const estimatedDurationSeconds = estimateDurationSeconds(numberOfOrders, interval);

  const warnings: string[] = [];
  if (executionMode === "jupiter_recurring") {
    warnings.push(
      `Jupiter Recurring requires roughly $${JUPITER_MIN_ORDER_USD} minimum value per buy. ` +
        "Smaller buys may be rejected — you can increase the size or use Devnet Demo Mode."
    );
  }
  if (executionMode === "devnet_demo") {
    warnings.push("Devnet Demo Mode simulates executions — no real tokens are purchased.");
  }
  warnings.push(...DCA_RISK_WARNINGS);

  const now = nowIso();
  const plan: DcaPlan = {
    id: makeId(),
    userWallet: ctx.userWallet,
    inputMint: inputToken.mint,
    outputMint: outputToken.mint,
    inputSymbol: inputToken.symbol,
    outputSymbol: outputToken.symbol,
    inputDecimals: inputToken.decimals,
    outputDecimals: outputToken.decimals,
    totalInputAmountUi: total,
    perOrderAmountUi: perOrder,
    numberOfOrders,
    intervalSeconds: interval,
    startAt: fields.startAt,
    slippageBps,
    estimatedDurationSeconds,
    network: ctx.network,
    executionMode,
    status: "needs_confirmation",
    warnings,
    createdAt: now,
    updatedAt: now,
    ordersExecuted: 0,
    spentInputUi: 0,
    receivedOutputUi: 0,
    lastExecutedAt: null,
    nextExecutionAt: null,
    jupiterOrderAccount: null,
    jupiterRequestId: null,
    createSignature: null,
    cancelSignature: null,
    agentWalletAddress: null,
    error: null
  };

  const validation = validateDcaPlan(plan);
  if (validation.errors.length > 0) {
    return { ok: false, clarification: validation.errors.join(" ") };
  }
  plan.warnings = [...warnings, ...validation.warnings];

  return { ok: true, plan };
}

/**
 * Re-assemble a plan from a client-supplied draft, server-side. The draft's
 * numeric choices (budget/count/interval) are kept but everything derived,
 * gated, or security-relevant (per-order amount, execution mode, warnings,
 * id, timestamps, status) is recomputed so the client cannot forge them.
 */
export function rebuildPlanFromDraft(draft: DcaPlan, ctx: PlanContext): AssembleResult {
  const inputToken: TokenInfo = {
    symbol: draft.inputSymbol,
    mint: draft.inputMint,
    decimals: draft.inputDecimals,
    aliases: []
  };
  const outputToken: TokenInfo = {
    symbol: draft.outputSymbol,
    mint: draft.outputMint,
    decimals: draft.outputDecimals,
    aliases: []
  };
  const fields: ParsedDcaFields = {
    outputTokenRef: draft.outputMint,
    inputTokenRef: draft.inputMint,
    perOrderAmountUi: draft.perOrderAmountUi,
    totalInputAmountUi: draft.totalInputAmountUi,
    numberOfOrders: draft.numberOfOrders,
    intervalSeconds: draft.intervalSeconds,
    durationSeconds: null,
    startAt: draft.startAt,
    slippageBps: draft.slippageBps
  };
  return assembleDcaPlan(inputToken, outputToken, fields, ctx);
}
