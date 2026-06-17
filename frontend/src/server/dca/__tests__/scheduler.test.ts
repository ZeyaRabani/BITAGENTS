import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WSOL_MINT, nowIso, type DcaPlan } from "@bitagents/shared";
import { processDuePlans } from "../scheduler";
import { createPlan, getPlan, listExecutions, reserveIdempotencyKey } from "../store";

const BITAGENTS_MINT = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY";

// Far-future "now" so every scheduled execution is due immediately.
const FUTURE = Date.now() + 365 * 24 * 60 * 60 * 1000;

let counter = 0;
function makeActivePlan(overrides: Partial<DcaPlan> = {}): DcaPlan {
  counter += 1;
  const now = nowIso();
  return {
    id: `dca_test_${counter}_${Math.random().toString(36).slice(2)}`,
    userWallet: `wallet_${counter}`,
    inputMint: WSOL_MINT,
    outputMint: BITAGENTS_MINT,
    inputSymbol: "SOL",
    outputSymbol: "BITAGENTS",
    inputDecimals: 9,
    outputDecimals: 6,
    totalInputAmountUi: 0.03,
    perOrderAmountUi: 0.01,
    numberOfOrders: 3,
    intervalSeconds: 600,
    startAt: null,
    slippageBps: 100,
    estimatedDurationSeconds: 1800,
    network: "devnet",
    executionMode: "devnet_demo",
    status: "active",
    warnings: [],
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
    error: null,
    ...overrides
  };
}

beforeEach(() => {
  // Mock the price reads so the simulated fill is deterministic and offline.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        [WSOL_MINT]: { usdPrice: 150, decimals: 9 },
        [BITAGENTS_MINT]: { usdPrice: 0.000015, decimals: 6 }
      })
    }))
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("processDuePlans (devnet demo lifecycle)", () => {
  it("executes one simulated order per tick and completes the plan", async () => {
    const plan = await createPlan(makeActivePlan());

    // Tick 1: first order should run.
    const tick1 = await processDuePlans(FUTURE);
    const after1 = await getPlan(plan.id);
    expect(after1?.ordersExecuted).toBe(1);
    expect(after1?.status).toBe("active");
    expect(after1?.nextExecutionAt).toBeTruthy();
    expect(tick1.executions.some((execution) => execution.planId === plan.id)).toBe(true);

    // Remaining ticks complete the plan (3 orders total).
    await processDuePlans(FUTURE);
    const final = await processDuePlans(FUTURE);
    expect(final).toBeTruthy();

    const done = await getPlan(plan.id);
    expect(done?.ordersExecuted).toBe(3);
    expect(done?.status).toBe("completed");
    expect(done?.nextExecutionAt).toBeNull();

    const executions = await listExecutions(plan.id);
    expect(executions).toHaveLength(3);
    // Devnet executions are simulated and carry the safety note.
    expect(executions.every((execution) => execution.simulated)).toBe(true);
    expect(executions.every((execution) => execution.signature?.startsWith("devnet-sim-"))).toBe(true);
  });

  it("does not advance a plan that is not yet due", async () => {
    const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    const plan = await createPlan(makeActivePlan({ nextExecutionAt: future }));
    await processDuePlans(Date.now());
    const after = await getPlan(plan.id);
    expect(after?.ordersExecuted).toBe(0);
  });

  it("skips jupiter_recurring plans (Jupiter keepers run those)", async () => {
    const plan = await createPlan(makeActivePlan({ executionMode: "jupiter_recurring", network: "mainnet" }));
    await processDuePlans(FUTURE);
    const after = await getPlan(plan.id);
    expect(after?.ordersExecuted).toBe(0);
  });

  it("is idempotent: a reserved order index is never executed twice", async () => {
    const plan = await createPlan(makeActivePlan());
    // Simulate a concurrent tick having already claimed order #1.
    const firstReserve = await reserveIdempotencyKey(`${plan.id}:1`);
    expect(firstReserve).toBe(true);

    await processDuePlans(FUTURE);
    const after = await getPlan(plan.id);
    // The order was already claimed, so this tick must not double-execute it.
    expect(after?.ordersExecuted).toBe(0);
    const executions = await listExecutions(plan.id);
    expect(executions).toHaveLength(0);
  });
});
