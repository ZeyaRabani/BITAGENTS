import { describe, expect, it } from "vitest";
import { AGENT_BOT_CAPS, clampAgentPlan, estimateFundingSol } from "../agentWallet";

describe("clampAgentPlan", () => {
  it("keeps a within-caps test plan unchanged (3 buys x 0.01 SOL / 60s)", () => {
    const result = clampAgentPlan({ numberOfOrders: 3, perOrderAmountUi: 0.01, intervalSeconds: 60 });
    expect(result.numberOfOrders).toBe(3);
    expect(result.perOrderAmountUi).toBe(0.01);
    expect(result.intervalSeconds).toBe(60);
    expect(result.warnings).toHaveLength(0);
  });

  it("caps a 100-buy plan down to the max order count", () => {
    const result = clampAgentPlan({ numberOfOrders: 100, perOrderAmountUi: 0.01, intervalSeconds: 600 });
    expect(result.numberOfOrders).toBe(AGENT_BOT_CAPS.maxOrders);
    expect(result.warnings.some((w) => w.includes("buys"))).toBe(true);
  });

  it("raises a sub-minute interval to the minimum", () => {
    const result = clampAgentPlan({ numberOfOrders: 3, perOrderAmountUi: 0.01, intervalSeconds: 5 });
    expect(result.intervalSeconds).toBe(AGENT_BOT_CAPS.minIntervalSeconds);
  });

  it("caps the total SOL at risk by reducing the order count", () => {
    const result = clampAgentPlan({ numberOfOrders: 10, perOrderAmountUi: 0.05, intervalSeconds: 60 });
    expect(result.perOrderAmountUi * result.numberOfOrders).toBeLessThanOrEqual(AGENT_BOT_CAPS.maxTotalSol);
  });
});

describe("estimateFundingSol", () => {
  it("covers the buys plus headroom for fees and the token account rent", () => {
    const amount = estimateFundingSol(0.01, 3);
    expect(amount).toBeGreaterThan(0.03);
    expect(amount).toBeLessThanOrEqual(0.05);
  });
});
