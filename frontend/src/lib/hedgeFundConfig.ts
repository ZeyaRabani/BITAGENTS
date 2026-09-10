export const HEDGE_FUND = {
  slug: "hedge-fund",
  name: "Hedge Fund Agent",
  tagline: "18-analyst · live · 4h monitor",
  description:
    "Deposit SOL, run live Jupiter sleeves (max $100 USD notional, min $5/asset), catalog stocks + crypto mints, 1% start fee and 10% of profit on liquidate back to SOL. Create strategies in chat. Paper mode still available on request.",
  model: "meta-llama/llama-3.1-8b-instruct",
  cluster: "mainnet",
  assistantLabel: "Fund Manager",
  managementFeePct: 1,
  performanceFeePct: 10,
  examplePrompts: [
    "Deposit then create a live strategy for 2 weeks — pick assets, TP 12 SL 6",
    "Create live strategy with NVDA META BTC, horizon 3 days, capital 100",
    "Confirm hs… after I deposit SOL",
    "Show my live PnL and trades",
    "Liquidate my strategy to SOL",
  ],
} as const;
