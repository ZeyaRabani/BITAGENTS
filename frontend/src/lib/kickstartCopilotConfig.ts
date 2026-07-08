export const KICKSTART_COPILOT = {
  id: "kickstart-copilot",
  name: "EasyA Analysis Agent",
  slug: "kickstart-copilot",
  tagline: "Token analysis · Jupiter trading",
  description:
    "EASY Screener research plus one-time market/limit buys via Jupiter (0.1% platform fee on fills).",
  status: "Running" as const,
  model: "meta-llama/llama-3.3-70b-instruct",
  cluster: "mainnet-beta",
  dataSource: "EASY Screener",
  dataSourceUrl: "https://easyscreener.xyz",
};

export const KICKSTART_EXAMPLE_PROMPTS = [
  "Give me an overview of $COLD",
  "Analyze BITAGENTS token health",
  "Market buy BITAGENTS with 0.1 SOL",
  "Limit buy BITAGENTS at $0.00008 for 0.5 SOL",
  "List my trading orders",
] as const;
