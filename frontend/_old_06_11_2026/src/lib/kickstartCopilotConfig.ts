export const KICKSTART_COPILOT = {
  id: "kickstart-copilot",
  name: "EasyA Analysis Agent",
  slug: "kickstart-copilot",
  tagline: "Solana token analysis",
  description:
    "AI agent for live Solana token research - price, liquidity, holders, risk checks, health scores, and diligence summaries.",
  status: "Running" as const,
  model: "meta-llama/llama-3.1-8b-instruct",
  cluster: "mainnet-beta",
  dataSource: "EASY Screener",
  dataSourceUrl: "https://easyscreener.xyz",
};

export const KICKSTART_EXAMPLE_PROMPTS = [
  "Market buy 0.01 SOL of BITAGENTS",
  "Give me an overview of BITAGENTS",
  "Analyze BITAGENTS token health",
  "Compare CPX and BITAGENTS",
  "Show my EasyA trading wallet balance",
  "Place a limit buy: spend 0.1 SOL on BITAGENTS when price drops to $0.015 or below",
  "Buy 0.0001 SOL of BITAGENTS when market cap is below $46,000, every minute, until SOL runs out or market cap goes above $46,000",
  "Buy 0.01 SOL of BITAGENTS every time price goes below $0.02 until my SOL runs out",
  "List my active limit orders",
] as const;
