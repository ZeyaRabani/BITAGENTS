import { parseIntervalToSeconds } from "@bitagents/shared";
import { completeJson, llmConfigured } from "@/server/agents/llm";

export interface ParsedDcaFields {
  outputTokenRef: string | null;
  inputTokenRef: string | null;
  perOrderAmountUi: number | null;
  totalInputAmountUi: number | null;
  numberOfOrders: number | null;
  intervalSeconds: number | null;
  durationSeconds: number | null;
  startAt: number | null;
  slippageBps: number | null;
}

// Match a base58 mint address first (so a pasted mint is captured in full),
// otherwise a short token symbol.
const TOKEN = "([1-9A-HJ-NP-Za-km-z]{32,44}|\\$?[A-Za-z][A-Za-z0-9]{1,14})";
const NUM = "([\\d][\\d,]*\\.?\\d*)";

// Words that can follow "buy" but are never a token (so "recurring buy every
// day" doesn't capture "every" as the token to purchase).
const TOKEN_STOPWORDS = new Set([
  "every",
  "each",
  "a",
  "an",
  "the",
  "some",
  "more",
  "into",
  "in",
  "for",
  "with",
  "using",
  "total",
  "budget",
  "spend",
  "and",
  "recurring",
  "secondly",
  "minutely",
  "hourly",
  "daily",
  "weekly"
]);

function isStopword(ref: string | null): boolean {
  return ref != null && TOKEN_STOPWORDS.has(ref.toLowerCase());
}

function toNumber(raw: string | undefined): number | null {
  if (!raw) return null;
  const value = Number(raw.replace(/,/g, ""));
  return Number.isFinite(value) ? value : null;
}

function cleanToken(raw: string | undefined): string | null {
  if (!raw) return null;
  return raw.trim().replace(/^\$/, "");
}

const TIME_WORDS = /(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|wks?)/i;

/**
 * Deterministic, rule-based parser. Works without any LLM and handles the
 * documented example prompts. The agent never invents a token — it only
 * extracts what the user explicitly wrote.
 */
export function parseDcaDeterministic(message: string): ParsedDcaFields {
  const text = message.trim();

  const result: ParsedDcaFields = {
    outputTokenRef: null,
    inputTokenRef: null,
    perOrderAmountUi: null,
    totalInputAmountUi: null,
    numberOfOrders: null,
    intervalSeconds: null,
    durationSeconds: null,
    startAt: null,
    slippageBps: null
  };

  // Output token: the thing being bought, right after "buy"/"dca into"/"accumulate".
  const outputMatch = text.match(new RegExp(`\\b(?:buy|dca(?:\\s+into)?|accumulate|stack)\\s+${TOKEN}`, "i"));
  if (outputMatch) {
    const ref = cleanToken(outputMatch[1]);
    // Avoid capturing a leading amount word ("buy 0.01") or a stopword
    // ("recurring buy every day" must not treat "every" as the token).
    if (ref && !isStopword(ref)) {
      if (!/^\d/.test(ref)) result.outputTokenRef = ref;
      else if (ref.length >= 32) result.outputTokenRef = ref; // mint that starts with a digit
    }
  }

  // Per-order amount: "with 0.01 SOL".
  const perOrderMatch = text.match(new RegExp(`\\bwith\\s+${NUM}\\s*${TOKEN}`, "i"));
  if (perOrderMatch) {
    result.perOrderAmountUi = toNumber(perOrderMatch[1]);
    result.inputTokenRef = cleanToken(perOrderMatch[2]);
  }

  // Total budget: "using 1 SOL total", "total budget: 1 SOL", "1 SOL total".
  const totalMatch =
    text.match(new RegExp(`\\b(?:using|total(?:\\s+budget)?|budget|spend)[:\\s]+${NUM}\\s*${TOKEN}`, "i")) ??
    text.match(new RegExp(`${NUM}\\s*${TOKEN}\\s+total\\b`, "i"));
  if (totalMatch) {
    result.totalInputAmountUi = toNumber(totalMatch[1]);
    if (!result.inputTokenRef) result.inputTokenRef = cleanToken(totalMatch[2]);
  }

  // Interval: "every 10 minutes", "hourly", "each day".
  const everyMatch = text.match(/\b(?:every|each)\s+([^,.]+?)(?=\s+(?:with|for|using|total|budget|and|spend)\b|[,.]|$)/i);
  if (everyMatch) {
    result.intervalSeconds = parseIntervalToSeconds(everyMatch[1]);
  }
  if (result.intervalSeconds == null) {
    const named = text.match(/\b(secondly|minutely|hourly|daily|weekly)\b/i);
    if (named) result.intervalSeconds = parseIntervalToSeconds(named[1]);
  }

  // Number of orders: "for 100 buys", "100 orders", "100 recurring buys".
  const ordersMatch = text.match(/\b(\d+)\s*(?:recurring\s+)?(?:buys?|orders?|times?|purchases?|swaps?)\b/i);
  if (ordersMatch) result.numberOfOrders = toNumber(ordersMatch[1]);

  // Duration: "for 30 days", "over 2 weeks" (only when followed by a time unit).
  const durationMatch = text.match(new RegExp(`\\b(?:for|over|during)\\s+${NUM}\\s*${TIME_WORDS.source}\\b`, "i"));
  if (durationMatch) {
    result.durationSeconds = parseIntervalToSeconds(`${durationMatch[1]} ${durationMatch[2]}`);
  }

  // Slippage: "1% slippage", "slippage 0.5%", "100 bps".
  const slipPct = text.match(/(?:slippage\s*(?:of\s*)?)?([\d.]+)\s*%\s*(?:slippage)?/i);
  const slipBps = text.match(/([\d]+)\s*bps/i);
  if (slipBps) result.slippageBps = toNumber(slipBps[1]);
  else if (slipPct && /slippage/i.test(text)) result.slippageBps = Math.round((toNumber(slipPct[1]) ?? 0) * 100);

  // Start time: "starting in 1 hour".
  const startMatch = text.match(/\bstart(?:ing)?\s+in\s+([^,.]+)/i);
  if (startMatch) {
    const offset = parseIntervalToSeconds(startMatch[1]);
    if (offset) result.startAt = Math.floor(Date.now() / 1000) + offset;
  }

  return result;
}

function mergeFields(base: ParsedDcaFields, extra: Partial<ParsedDcaFields>): ParsedDcaFields {
  const merged: ParsedDcaFields = { ...base };
  (Object.keys(extra) as Array<keyof ParsedDcaFields>).forEach((key) => {
    if (merged[key] == null && extra[key] != null) {
      // @ts-expect-error index assignment across the union of value types
      merged[key] = extra[key];
    }
  });
  return merged;
}

const LLM_SYSTEM =
  "You extract structured fields from a user's dollar-cost-averaging (DCA) instruction. " +
  "Never invent a token the user did not mention. Use null for anything not stated. " +
  "Keys: outputTokenRef (the token to BUY, a symbol or mint), inputTokenRef (the token to SPEND), " +
  "perOrderAmountUi (number), totalInputAmountUi (number), numberOfOrders (integer), " +
  "intervalSeconds (integer seconds between buys), durationSeconds (integer total duration), " +
  "slippageBps (integer). Amounts are in human units, not raw.";

function coerceLlmFields(raw: unknown): Partial<ParsedDcaFields> {
  if (!raw || typeof raw !== "object") return {};
  const obj = raw as Record<string, unknown>;
  const numberOrNull = (value: unknown): number | null =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const stringOrNull = (value: unknown): string | null =>
    typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
  return {
    outputTokenRef: stringOrNull(obj.outputTokenRef),
    inputTokenRef: stringOrNull(obj.inputTokenRef),
    perOrderAmountUi: numberOrNull(obj.perOrderAmountUi),
    totalInputAmountUi: numberOrNull(obj.totalInputAmountUi),
    numberOfOrders: numberOrNull(obj.numberOfOrders),
    intervalSeconds: numberOrNull(obj.intervalSeconds),
    durationSeconds: numberOrNull(obj.durationSeconds),
    slippageBps: numberOrNull(obj.slippageBps)
  };
}

/**
 * Parse a DCA instruction. Deterministic rules are authoritative; an optional
 * LLM only fills gaps the rules could not extract. Returns the engine used so
 * the UI can show whether real model compute or deterministic parsing ran.
 */
export async function parseDcaPrompt(
  message: string
): Promise<{ fields: ParsedDcaFields; engine: "llm" | "deterministic" }> {
  const deterministic = parseDcaDeterministic(message);

  const missingCore =
    !deterministic.outputTokenRef ||
    (deterministic.perOrderAmountUi == null &&
      deterministic.totalInputAmountUi == null &&
      deterministic.numberOfOrders == null);

  if (missingCore && llmConfigured()) {
    const raw = await completeJson(LLM_SYSTEM, message);
    if (raw) {
      return { fields: mergeFields(deterministic, coerceLlmFields(raw)), engine: "llm" };
    }
  }

  return { fields: deterministic, engine: "deterministic" };
}
