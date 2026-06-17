import { uiAmountToRawAmount } from "@bitagents/shared";
import { dcaConfig, jupiterHeaders, jupiterRecurringBase, type DcaServerConfig } from "./config";

// ---------------------------------------------------------------------
// Jupiter Recurring (DCA) API client — time-based orders only.
// Docs: https://dev.jup.ag/docs/recurring
//
// NOTE ON FEES: Jupiter's Recurring API charges a 0.1% protocol fee and does
// NOT currently allow integrators to take a fee. BITAGENTS therefore does not
// add any integrator fee on recurring orders; the business model uses a
// separate subscription / agent-service fee instead (see /utility).
//
// NOTE ON NETWORK: Jupiter Recurring is mainnet-only. Devnet plans are handled
// by the simulated Devnet Demo Mode scheduler, never by this client.
// ---------------------------------------------------------------------

export interface JupiterTimeParams {
  inAmount: number;
  numberOfOrders: number;
  interval: number;
  minPrice: number | null;
  maxPrice: number | null;
  startAt: number | null;
}

export interface CreateRecurringOrderInput {
  user: string;
  inputMint: string;
  outputMint: string;
  inputDecimals: number;
  totalInputAmountUi: number;
  numberOfOrders: number;
  intervalSeconds: number;
  startAt: number | null;
}

export interface JupiterErrorShape {
  code: number;
  error: string;
  status: string;
}

export type CreateRecurringOrderResult =
  | { ok: true; requestId: string; transaction: string }
  | { ok: false; error: string; code?: number; minOrder?: boolean };

/** Build the exact request body Jupiter expects for a time-based order. */
export function buildCreateOrderBody(input: CreateRecurringOrderInput) {
  const params: JupiterTimeParams = {
    inAmount: uiAmountToRawAmount(input.totalInputAmountUi, input.inputDecimals),
    numberOfOrders: input.numberOfOrders,
    interval: input.intervalSeconds,
    minPrice: null,
    maxPrice: null,
    startAt: input.startAt
  };
  return {
    user: input.user,
    inputMint: input.inputMint,
    outputMint: input.outputMint,
    params: { time: params }
  };
}

function looksLikeMinOrderError(message: string): boolean {
  return /minimum is/i.test(message) || /valued at/i.test(message);
}

export async function createJupiterRecurringOrder(
  input: CreateRecurringOrderInput,
  config: DcaServerConfig = dcaConfig()
): Promise<CreateRecurringOrderResult> {
  const body = buildCreateOrderBody(input);
  try {
    const response = await fetch(`${jupiterRecurringBase(config)}/createOrder`, {
      method: "POST",
      headers: jupiterHeaders(config),
      body: JSON.stringify(body)
    });
    const payload = (await response.json().catch(() => null)) as
      | { requestId?: string; transaction?: string }
      | JupiterErrorShape
      | null;

    if (!response.ok || !payload || !("transaction" in payload) || !payload.transaction) {
      const message =
        payload && "error" in payload && payload.error
          ? payload.error
          : `Jupiter rejected the order (HTTP ${response.status}).`;
      return {
        ok: false,
        error: message,
        code: payload && "code" in payload ? payload.code : response.status,
        minOrder: looksLikeMinOrderError(message)
      };
    }

    return { ok: true, requestId: payload.requestId ?? "", transaction: payload.transaction };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "Network error contacting Jupiter." };
  }
}

export interface ExecuteRecurringOrderResult {
  status: "Success" | "Failed";
  signature: string | null;
  order: string | null;
  error: string | null;
}

export async function executeJupiterRecurringOrder(
  requestId: string,
  signedTransaction: string,
  config: DcaServerConfig = dcaConfig()
): Promise<ExecuteRecurringOrderResult> {
  try {
    const response = await fetch(`${jupiterRecurringBase(config)}/execute`, {
      method: "POST",
      headers: jupiterHeaders(config),
      body: JSON.stringify({ requestId, signedTransaction })
    });
    const payload = (await response.json().catch(() => null)) as Partial<{
      status: string;
      signature: string;
      order: string;
      error: string;
    }> | null;

    return {
      status: payload?.status === "Success" ? "Success" : "Failed",
      signature: payload?.signature ?? null,
      order: payload?.order ?? null,
      error: payload?.error ?? (response.ok ? null : `Execute failed (HTTP ${response.status}).`)
    };
  } catch (error) {
    return {
      status: "Failed",
      signature: null,
      order: null,
      error: error instanceof Error ? error.message : "Network error contacting Jupiter."
    };
  }
}

export type CancelRecurringOrderResult =
  | { ok: true; requestId: string; transaction: string }
  | { ok: false; error: string };

export async function cancelJupiterRecurringOrder(
  order: string,
  user: string,
  config: DcaServerConfig = dcaConfig()
): Promise<CancelRecurringOrderResult> {
  try {
    const response = await fetch(`${jupiterRecurringBase(config)}/cancelOrder`, {
      method: "POST",
      headers: jupiterHeaders(config),
      body: JSON.stringify({ order, user, recurringType: "time" })
    });
    const payload = (await response.json().catch(() => null)) as
      | { requestId?: string; transaction?: string }
      | JupiterErrorShape
      | null;

    if (!response.ok || !payload || !("transaction" in payload) || !payload.transaction) {
      const message =
        payload && "error" in payload && payload.error
          ? payload.error
          : `Cancel failed (HTTP ${response.status}).`;
      return { ok: false, error: message };
    }
    return { ok: true, requestId: payload.requestId ?? "", transaction: payload.transaction };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "Network error contacting Jupiter." };
  }
}

export interface JupiterRecurringOrdersResult {
  ok: boolean;
  orders: unknown[];
  error?: string;
}

export async function getJupiterRecurringOrders(
  user: string,
  orderStatus: "active" | "history" = "active",
  config: DcaServerConfig = dcaConfig()
): Promise<JupiterRecurringOrdersResult> {
  const params = new URLSearchParams({
    recurringType: "time",
    orderStatus,
    user,
    page: "1",
    includeFailedTx: "false"
  });
  try {
    const response = await fetch(`${jupiterRecurringBase(config)}/getRecurringOrders?${params.toString()}`, {
      method: "GET",
      headers: jupiterHeaders(config)
    });
    const payload = (await response.json().catch(() => null)) as
      | { orders?: unknown[]; all?: unknown[] }
      | null;
    if (!response.ok) {
      return { ok: false, orders: [], error: `getRecurringOrders failed (HTTP ${response.status}).` };
    }
    const orders = payload?.orders ?? payload?.all ?? [];
    return { ok: true, orders: Array.isArray(orders) ? orders : [] };
  } catch (error) {
    return { ok: false, orders: [], error: error instanceof Error ? error.message : "Network error." };
  }
}

export interface QuoteResult {
  routeable: boolean;
  outAmountRaw: string | null;
  priceImpactPct: number | null;
  error?: string;
}

/** Check whether a route exists (used to flag unrouteable tokens early). */
export async function checkRouteable(
  inputMint: string,
  outputMint: string,
  rawInAmount: number,
  slippageBps: number,
  config: DcaServerConfig = dcaConfig()
): Promise<QuoteResult> {
  const params = new URLSearchParams({
    inputMint,
    outputMint,
    amount: String(rawInAmount),
    slippageBps: String(slippageBps)
  });
  try {
    const response = await fetch(`${config.jupiterBaseUrl}/swap/v1/quote?${params.toString()}`, {
      headers: jupiterHeaders(config)
    });
    if (!response.ok) {
      return { routeable: false, outAmountRaw: null, priceImpactPct: null, error: `HTTP ${response.status}` };
    }
    const payload = (await response.json().catch(() => null)) as Partial<{
      outAmount: string;
      priceImpactPct: string;
    }> | null;
    if (!payload?.outAmount) {
      return { routeable: false, outAmountRaw: null, priceImpactPct: null };
    }
    return {
      routeable: true,
      outAmountRaw: payload.outAmount,
      priceImpactPct: payload.priceImpactPct ? Number(payload.priceImpactPct) : null
    };
  } catch (error) {
    return {
      routeable: false,
      outAmountRaw: null,
      priceImpactPct: null,
      error: error instanceof Error ? error.message : "Network error."
    };
  }
}

export async function fetchRawQuote(
  inputMint: string,
  outputMint: string,
  rawInAmount: number,
  slippageBps: number,
  config: DcaServerConfig = dcaConfig()
): Promise<Record<string, unknown> | null> {
  const params = new URLSearchParams({
    inputMint,
    outputMint,
    amount: String(rawInAmount),
    slippageBps: String(slippageBps)
  });
  try {
    const response = await fetch(`${config.jupiterBaseUrl}/swap/v1/quote?${params.toString()}`, {
      headers: jupiterHeaders(config)
    });
    if (!response.ok) return null;
    return (await response.json().catch(() => null)) as Record<string, unknown> | null;
  } catch {
    return null;
  }
}

/** Build a swap transaction (base64) for the experimental agent-wallet mode. */
export async function fetchSwapTransaction(
  quoteResponse: Record<string, unknown>,
  userPublicKey: string,
  config: DcaServerConfig = dcaConfig()
): Promise<string | null> {
  try {
    const response = await fetch(`${config.jupiterBaseUrl}/swap/v1/swap`, {
      method: "POST",
      headers: jupiterHeaders(config),
      body: JSON.stringify({ quoteResponse, userPublicKey, wrapAndUnwrapSol: true })
    });
    if (!response.ok) return null;
    const payload = (await response.json().catch(() => null)) as { swapTransaction?: string } | null;
    return payload?.swapTransaction ?? null;
  } catch {
    return null;
  }
}

export interface BuiltSwapTransaction {
  swapTransaction: string;
  lastValidBlockHeight: number | null;
}

/**
 * Build an unsigned base64 swap transaction for a one-time market buy. Unlike
 * the Recurring API this has no per-order minimum, so it powers the immediate
 * "Buy now" path that lets a small purchase go through. The user signs and
 * sends it from their own wallet — no custody, no integrator fee.
 */
export async function buildSwapTransaction(
  quoteResponse: Record<string, unknown>,
  userPublicKey: string,
  config: DcaServerConfig = dcaConfig()
): Promise<BuiltSwapTransaction | null> {
  try {
    const response = await fetch(`${config.jupiterBaseUrl}/swap/v1/swap`, {
      method: "POST",
      headers: jupiterHeaders(config),
      body: JSON.stringify({
        quoteResponse,
        userPublicKey,
        wrapAndUnwrapSol: true,
        dynamicComputeUnitLimit: true
      })
    });
    if (!response.ok) return null;
    const payload = (await response.json().catch(() => null)) as
      | { swapTransaction?: string; lastValidBlockHeight?: number }
      | null;
    if (!payload?.swapTransaction) return null;
    return {
      swapTransaction: payload.swapTransaction,
      lastValidBlockHeight:
        typeof payload.lastValidBlockHeight === "number" ? payload.lastValidBlockHeight : null
    };
  } catch {
    return null;
  }
}

export interface PriceResult {
  usdPrice: number | null;
  decimals: number | null;
}

export async function fetchUsdPrice(
  mint: string,
  config: DcaServerConfig = dcaConfig()
): Promise<PriceResult> {
  try {
    const response = await fetch(`${config.jupiterBaseUrl}/price/v3?ids=${mint}`, {
      headers: jupiterHeaders(config)
    });
    if (!response.ok) return { usdPrice: null, decimals: null };
    const payload = (await response.json().catch(() => null)) as Record<
      string,
      { usdPrice?: number; decimals?: number }
    > | null;
    const entry = payload?.[mint];
    return {
      usdPrice: typeof entry?.usdPrice === "number" ? entry.usdPrice : null,
      decimals: typeof entry?.decimals === "number" ? entry.decimals : null
    };
  } catch {
    return { usdPrice: null, decimals: null };
  }
}
