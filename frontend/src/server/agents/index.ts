import type { AgentResult, AgentTask } from "@bitagents/shared";
import { computeWalletWatcher } from "@/server/agents/walletWatcher";
import { computeTokenResearch } from "@/server/agents/tokenResearch";
import { computeMarketResearch } from "@/server/agents/marketResearch";

export async function runAgent(task: AgentTask): Promise<AgentResult> {
  switch (task.type) {
    case "wallet_watcher":
      if (!("walletAddress" in task.input)) {
        throw new Error("Wallet Watcher requires a wallet address.");
      }
      return computeWalletWatcher(task.input, task.network);
    case "token_research":
      if (!("query" in task.input)) {
        throw new Error("Token Research requires a query.");
      }
      return computeTokenResearch(task.input, task.network);
    case "market_research":
      if (!("query" in task.input)) {
        throw new Error("Market Research requires a query.");
      }
      return computeMarketResearch(task.input, task.network);
    default:
      throw new Error(`Unknown agent type: ${task.type as string}`);
  }
}

export { llmConfigured } from "@/server/agents/llm";
