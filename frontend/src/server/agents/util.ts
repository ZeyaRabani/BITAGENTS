import { createHash } from "node:crypto";

export function sha256(payload: unknown): string {
  const json = typeof payload === "string" ? payload : JSON.stringify(payload);
  return createHash("sha256").update(json).digest("hex");
}

export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s$#.-]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 1);
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

const POSITIVE_TERMS = new Set([
  "growth",
  "adoption",
  "scaling",
  "fast",
  "secure",
  "liquidity",
  "staking",
  "yield",
  "bullish",
  "partnership",
  "mainnet",
  "upgrade",
  "revenue",
  "demand",
  "utility",
  "ecosystem",
  "treasury",
  "airdrop"
]);

const RISK_TERMS = new Set([
  "rug",
  "scam",
  "hack",
  "exploit",
  "inflation",
  "dump",
  "unlock",
  "dilution",
  "centralized",
  "lawsuit",
  "ban",
  "depeg",
  "bearish",
  "vesting",
  "honeypot",
  "mint",
  "freeze"
]);

export interface SentimentBreakdown {
  score: number;
  positiveHits: string[];
  riskHits: string[];
}

/** Deterministic, transparent sentiment heuristic (range -100..100). */
export function scoreSentiment(tokens: string[]): SentimentBreakdown {
  const positiveHits: string[] = [];
  const riskHits: string[] = [];

  for (const token of tokens) {
    if (POSITIVE_TERMS.has(token)) positiveHits.push(token);
    if (RISK_TERMS.has(token)) riskHits.push(token);
  }

  const raw = positiveHits.length * 12 - riskHits.length * 14;
  return {
    score: clamp(raw, -100, 100),
    positiveHits: Array.from(new Set(positiveHits)),
    riskHits: Array.from(new Set(riskHits))
  };
}

export function titleCase(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
