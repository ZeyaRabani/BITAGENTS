export const KICKSTART_COPILOT = {
  id: "kickstart-copilot",
  name: "EasyA Analysis Agent",
  slug: "kickstart-copilot",
  tagline: "Solana token analysis",
  description:
    "price, liquidity, holders, risk checks, health scores, and diligence summaries.",
  status: "Running" as const,
  model: "meta-llama/llama-3.3-70b-instruct",
  cluster: "mainnet-beta",
  dataSource: "EASY Screener",
  dataSourceUrl: "https://easyscreener.xyz",
};

export const KICKSTART_EXAMPLE_PROMPTS = [
  "Give me an overview of $COLD",
  "Give me an overview of BITAGENTS",
  "Analyze BITAGENTS token health",
  "Search tokens named cold",
  "Compare CPX and BITAGENTS",
] as const;
