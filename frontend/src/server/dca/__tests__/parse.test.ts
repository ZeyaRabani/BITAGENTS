import { describe, expect, it } from "vitest";
import { parseIntervalToSeconds } from "@bitagents/shared";
import { parseDcaDeterministic } from "../parse";

describe("parseDcaDeterministic", () => {
  it("parses the canonical BITAGENTS prompt", () => {
    const fields = parseDcaDeterministic(
      "Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total"
    );
    expect(fields.outputTokenRef).toBe("BITAGENTS");
    expect(fields.inputTokenRef).toBe("SOL");
    expect(fields.perOrderAmountUi).toBe(0.01);
    expect(fields.totalInputAmountUi).toBe(1);
    expect(fields.intervalSeconds).toBe(600);
  });

  it("parses a daily USDC prompt with a duration instead of a count", () => {
    const fields = parseDcaDeterministic("Buy SOL every day with 10 USDC for 30 days");
    expect(fields.outputTokenRef).toBe("SOL");
    expect(fields.inputTokenRef).toBe("USDC");
    expect(fields.perOrderAmountUi).toBe(10);
    expect(fields.intervalSeconds).toBe(86_400);
    expect(fields.durationSeconds).toBe(30 * 86_400);
  });

  it("parses a mint address and an explicit order count", () => {
    const mint = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY";
    const fields = parseDcaDeterministic(`Buy ${mint} every hour with 0.05 SOL for 10 buys`);
    expect(fields.outputTokenRef).toBe(mint);
    expect(fields.perOrderAmountUi).toBe(0.05);
    expect(fields.intervalSeconds).toBe(3_600);
    expect(fields.numberOfOrders).toBe(10);
  });

  it("extracts slippage only when the word slippage is present", () => {
    expect(parseDcaDeterministic("buy SOL every hour with 1 USDC 1% slippage").slippageBps).toBe(100);
    expect(parseDcaDeterministic("buy SOL every hour with 1 USDC 50 bps").slippageBps).toBe(50);
    // A bare percentage that is not slippage must not be misread.
    expect(parseDcaDeterministic("buy SOL every hour with 1 USDC").slippageBps).toBeNull();
  });

  it("does not invent a token when none is given", () => {
    const fields = parseDcaDeterministic("set up a recurring buy every day");
    expect(fields.outputTokenRef).toBeNull();
  });
});

describe("parseIntervalToSeconds", () => {
  it("handles plain and named intervals", () => {
    expect(parseIntervalToSeconds("10 minutes")).toBe(600);
    expect(parseIntervalToSeconds("1 hour")).toBe(3_600);
    expect(parseIntervalToSeconds("1 day")).toBe(86_400);
    expect(parseIntervalToSeconds("hourly")).toBe(3_600);
    expect(parseIntervalToSeconds("daily")).toBe(86_400);
  });
});
