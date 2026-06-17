import { afterEach, describe, expect, it, vi } from "vitest";
import { WSOL_MINT } from "@bitagents/shared";
import {
  buildCreateOrderBody,
  buildSwapTransaction,
  cancelJupiterRecurringOrder,
  createJupiterRecurringOrder,
  type CreateRecurringOrderInput
} from "../jupiter";

const BITAGENTS_MINT = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY";

const baseInput: CreateRecurringOrderInput = {
  user: "11111111111111111111111111111111",
  inputMint: WSOL_MINT,
  outputMint: BITAGENTS_MINT,
  inputDecimals: 9,
  totalInputAmountUi: 1,
  numberOfOrders: 100,
  intervalSeconds: 600,
  startAt: null
};

function mockFetchOnce(status: number, json: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => json
    }))
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("buildCreateOrderBody", () => {
  it("converts the total budget to a raw lamport amount", () => {
    const body = buildCreateOrderBody(baseInput);
    expect(body.user).toBe(baseInput.user);
    expect(body.inputMint).toBe(WSOL_MINT);
    expect(body.outputMint).toBe(BITAGENTS_MINT);
    // 1 SOL total at 9 decimals => 1_000_000_000 raw, spread over 100 orders.
    expect(body.params.time.inAmount).toBe(1_000_000_000);
    expect(body.params.time.numberOfOrders).toBe(100);
    expect(body.params.time.interval).toBe(600);
    expect(body.params.time.minPrice).toBeNull();
    expect(body.params.time.maxPrice).toBeNull();
  });
});

describe("createJupiterRecurringOrder", () => {
  it("returns the transaction on success", async () => {
    mockFetchOnce(200, { requestId: "req_123", transaction: "BASE64_TX" });
    const result = await createJupiterRecurringOrder(baseInput);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.requestId).toBe("req_123");
    expect(result.transaction).toBe("BASE64_TX");
  });

  it("flags the minimum-order rejection so the UI can offer a fallback", async () => {
    mockFetchOnce(400, {
      code: 400,
      error: "Each order valued at 0.74 USDC, minimum is 50.00 USDC",
      status: "Bad Request"
    });
    const result = await createJupiterRecurringOrder(baseInput);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.minOrder).toBe(true);
    expect(result.code).toBe(400);
    expect(result.error).toMatch(/minimum is/i);
  });

  it("surfaces network errors without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("boom");
      })
    );
    const result = await createJupiterRecurringOrder(baseInput);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toBe("boom");
  });
});

describe("buildSwapTransaction", () => {
  const quote = { inputMint: WSOL_MINT, outputMint: BITAGENTS_MINT, outAmount: "53193192594" };

  it("returns the unsigned transaction and lastValidBlockHeight on success", async () => {
    mockFetchOnce(200, { swapTransaction: "SWAP_TX_BASE64", lastValidBlockHeight: 404954490 });
    const result = await buildSwapTransaction(quote, baseInput.user);
    expect(result).not.toBeNull();
    expect(result?.swapTransaction).toBe("SWAP_TX_BASE64");
    expect(result?.lastValidBlockHeight).toBe(404954490);
  });

  it("returns null when Jupiter omits the transaction", async () => {
    mockFetchOnce(200, { error: "no route" });
    const result = await buildSwapTransaction(quote, baseInput.user);
    expect(result).toBeNull();
  });

  it("returns null on a network error instead of throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("boom");
      })
    );
    const result = await buildSwapTransaction(quote, baseInput.user);
    expect(result).toBeNull();
  });
});

describe("cancelJupiterRecurringOrder", () => {
  it("returns an unsigned cancel transaction", async () => {
    mockFetchOnce(200, { requestId: "req_cancel", transaction: "CANCEL_TX" });
    const result = await cancelJupiterRecurringOrder("OrderAccount111", baseInput.user);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.transaction).toBe("CANCEL_TX");
  });

  it("reports a failure when Jupiter returns no transaction", async () => {
    mockFetchOnce(404, { code: 404, error: "Order not found", status: "Not Found" });
    const result = await cancelJupiterRecurringOrder("missing", baseInput.user);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toMatch(/not found/i);
  });
});
