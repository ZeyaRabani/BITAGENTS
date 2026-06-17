import { describe, expect, it } from "vitest";
import { WSOL_MINT, type TokenInfo } from "@bitagents/shared";
import { deriveAmounts, assembleDcaPlan, type PlanContext } from "../plan";
import type { ParsedDcaFields } from "../parse";

const SOL: TokenInfo = { symbol: "SOL", mint: WSOL_MINT, decimals: 9, aliases: [] };
const BITAGENTS: TokenInfo = {
  symbol: "BITAGENTS",
  mint: "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY",
  decimals: 6,
  aliases: []
};

function fields(overrides: Partial<ParsedDcaFields>): ParsedDcaFields {
  return {
    outputTokenRef: "BITAGENTS",
    inputTokenRef: "SOL",
    perOrderAmountUi: null,
    totalInputAmountUi: null,
    numberOfOrders: null,
    intervalSeconds: null,
    durationSeconds: null,
    startAt: null,
    slippageBps: null,
    ...overrides
  };
}

describe("deriveAmounts", () => {
  it("derives 100 orders from total / per-order", () => {
    const derived = deriveAmounts(fields({ totalInputAmountUi: 1, perOrderAmountUi: 0.01 }));
    expect(derived.numberOfOrders).toBe(100);
    expect(derived.totalInputAmountUi).toBe(1);
    expect(derived.perOrderAmountUi).toBeCloseTo(0.01, 10);
  });

  it("derives order count from duration / interval", () => {
    const derived = deriveAmounts(
      fields({ perOrderAmountUi: 10, intervalSeconds: 86_400, durationSeconds: 30 * 86_400 })
    );
    expect(derived.numberOfOrders).toBe(30);
    expect(derived.totalInputAmountUi).toBe(300);
  });

  it("computes per-order from total + count", () => {
    const derived = deriveAmounts(fields({ totalInputAmountUi: 1, numberOfOrders: 4 }));
    expect(derived.perOrderAmountUi).toBe(0.25);
  });
});

describe("assembleDcaPlan", () => {
  const mainnetCtx: PlanContext = {
    userWallet: "11111111111111111111111111111111",
    network: "mainnet",
    enableMainnetDca: true
  };
  const devnetCtx: PlanContext = {
    userWallet: "11111111111111111111111111111111",
    network: "devnet",
    enableMainnetDca: false
  };

  it("builds the canonical 100-buy plan and selects jupiter_recurring on mainnet", () => {
    const result = assembleDcaPlan(
      SOL,
      BITAGENTS,
      fields({ totalInputAmountUi: 1, perOrderAmountUi: 0.01, intervalSeconds: 600 }),
      mainnetCtx
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.plan.numberOfOrders).toBe(100);
    expect(result.plan.perOrderAmountUi).toBeCloseTo(0.01, 10);
    expect(result.plan.totalInputAmountUi).toBe(1);
    expect(result.plan.intervalSeconds).toBe(600);
    expect(result.plan.estimatedDurationSeconds).toBe(60_000);
    expect(result.plan.executionMode).toBe("jupiter_recurring");
    expect(result.plan.status).toBe("needs_confirmation");
    expect(result.plan.slippageBps).toBe(100);
  });

  it("selects devnet_demo when not on mainnet", () => {
    const result = assembleDcaPlan(
      SOL,
      BITAGENTS,
      fields({ totalInputAmountUi: 1, perOrderAmountUi: 0.01, intervalSeconds: 600 }),
      devnetCtx
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.plan.executionMode).toBe("devnet_demo");
  });

  it("asks for an interval when none is given", () => {
    const result = assembleDcaPlan(SOL, BITAGENTS, fields({ totalInputAmountUi: 1, numberOfOrders: 10 }), devnetCtx);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.clarification).toMatch(/how often/i);
  });

  it("asks for a budget when none is given", () => {
    const result = assembleDcaPlan(SOL, BITAGENTS, fields({ intervalSeconds: 600 }), devnetCtx);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.clarification).toMatch(/how much/i);
  });

  it("rejects identical input and output tokens", () => {
    const result = assembleDcaPlan(
      SOL,
      SOL,
      fields({ totalInputAmountUi: 1, perOrderAmountUi: 0.01, intervalSeconds: 600 }),
      devnetCtx
    );
    expect(result.ok).toBe(false);
  });
});
