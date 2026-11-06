export type DefiAgentSlug =
  | "liquidity"
  | "copy-trade"
  | "grid"
  | "liquidation-guard"
  | "funding-perps"
  | "arbitrage"
  | "treasury"
  | "rebalance"
  | "sniper"
  | "options";

export type DefiStrategyField = {
  id: string;
  label: string;
  placeholder?: string;
  type?: "text" | "number" | "select";
  options?: { value: string; label: string }[];
  defaultValue?: string;
};

export type DefiAgentConfig = {
  slug: DefiAgentSlug;
  name: string;
  tagline: string;
  description: string;
  category: "Trading" | "Automation" | "Monitor";
  pricePerTask: string;
  model: string;
  cluster: string;
  assistantLabel: string;
  iconId:
    | "liquidity"
    | "copy"
    | "grid"
    | "shield"
    | "perps"
    | "arb"
    | "treasury"
    | "rebalance"
    | "sniper"
    | "options";
  examplePrompts: readonly string[];
  strategyTitle: string;
  strategyFields: DefiStrategyField[];
  submitLabel: string;
};

export const DEFI_AGENTS: Record<DefiAgentSlug, DefiAgentConfig> = {
  liquidity: {
    slug: "liquidity",
    name: "Liquidity / LP Agent",
    tagline: "Meteora · Orca · Raydium LP",
    description:
      "Open, rebalance, and exit concentrated liquidity positions. Harvest fees and pull LP when IL or TVL drifts.",
    category: "Trading",
    pricePerTask: "0.35% / action",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "LP Agent",
    iconId: "liquidity",
    strategyTitle: "LP strategy",
    submitLabel: "Create LP strategy",
    examplePrompts: [
      "Open a SOL/USDC LP around spot",
      "List my LP strategies",
      "Rebalance when price leaves range",
      "Harvest fees and compound",
    ],
    strategyFields: [
      { id: "pair", label: "Pair", placeholder: "SOL/USDC", defaultValue: "SOL/USDC" },
      { id: "venue", label: "Venue", type: "select", defaultValue: "meteora", options: [
        { value: "meteora", label: "Meteora" },
        { value: "orca", label: "Orca" },
        { value: "raydium", label: "Raydium" },
      ]},
      { id: "capital", label: "Capital (SOL)", type: "number", placeholder: "1.0", defaultValue: "1" },
      { id: "range_pct", label: "Range ±%", type: "number", placeholder: "5", defaultValue: "5" },
    ],
  },
  "copy-trade": {
    slug: "copy-trade",
    name: "Copy-Trade Agent",
    tagline: "Mirror wallets · size caps",
    description:
      "Mirror smart-money wallets with size caps, delay, max slippage, and a kill switch.",
    category: "Trading",
    pricePerTask: "0.5% / copy",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Copy Agent",
    iconId: "copy",
    strategyTitle: "Copy strategy",
    submitLabel: "Start copying",
    examplePrompts: [
      "Copy wallet with 10% size",
      "Pause copy trading",
      "Show open copy positions",
      "Set max slippage to 1%",
    ],
    strategyFields: [
      { id: "whale", label: "Whale wallet", placeholder: "Base58 address" },
      { id: "size_pct", label: "Size %", type: "number", placeholder: "10", defaultValue: "10" },
      { id: "max_slip_bps", label: "Max slip (bps)", type: "number", placeholder: "100", defaultValue: "100" },
      { id: "delay_sec", label: "Delay (sec)", type: "number", placeholder: "3", defaultValue: "3" },
    ],
  },
  grid: {
    slug: "grid",
    name: "Grid / Range Agent",
    tagline: "Buy dips · sell rips",
    description:
      "Place a price grid on a pair. Auto-buy below spot and sell above within your band.",
    category: "Trading",
    pricePerTask: "0.4% / fill",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Grid Agent",
    iconId: "grid",
    strategyTitle: "Grid strategy",
    submitLabel: "Create grid",
    examplePrompts: [
      "Start a SOL grid from 120 to 160",
      "Show grid fills",
      "Tighten range by 5%",
      "Pause the active grid",
    ],
    strategyFields: [
      { id: "pair", label: "Pair", placeholder: "SOL/USDC", defaultValue: "SOL/USDC" },
      { id: "lower", label: "Lower price", type: "number", placeholder: "120" },
      { id: "upper", label: "Upper price", type: "number", placeholder: "160" },
      { id: "grids", label: "Grid levels", type: "number", placeholder: "10", defaultValue: "10" },
      { id: "capital", label: "Capital (SOL)", type: "number", placeholder: "2", defaultValue: "2" },
    ],
  },
  "liquidation-guard": {
    slug: "liquidation-guard",
    name: "Liquidation Guard Agent",
    tagline: "Drift · perps health",
    description:
      "Watch perp or lending health and auto-deleverage or add collateral before liquidation.",
    category: "Monitor",
    pricePerTask: "0.25% / hedge",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Guard Agent",
    iconId: "shield",
    strategyTitle: "Guard rule",
    submitLabel: "Arm guard",
    examplePrompts: [
      "Arm guard at 25% health",
      "Show account health",
      "Deleverage if health drops",
      "Disable liquidation guard",
    ],
    strategyFields: [
      { id: "protocol", label: "Protocol", type: "select", defaultValue: "drift", options: [
        { value: "drift", label: "Drift" },
        { value: "jupiter_perps", label: "Jupiter Perps" },
        { value: "kamino_lend", label: "Kamino Lend" },
      ]},
      { id: "account", label: "Account / sub", placeholder: "default", defaultValue: "default" },
      { id: "health_pct", label: "Min health %", type: "number", placeholder: "25", defaultValue: "25" },
      { id: "action", label: "Action", type: "select", defaultValue: "deleverage", options: [
        { value: "deleverage", label: "Deleverage" },
        { value: "add_collateral", label: "Add collateral" },
        { value: "close", label: "Close position" },
      ]},
    ],
  },
  "funding-perps": {
    slug: "funding-perps",
    name: "Funding / Perps Agent",
    tagline: "Harvest funding · risk caps",
    description:
      "Run funding-aware perp exposure with size, leverage, and drawdown limits.",
    category: "Trading",
    pricePerTask: "0.35% / trade",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Perps Agent",
    iconId: "perps",
    strategyTitle: "Funding strategy",
    submitLabel: "Create funding strategy",
    examplePrompts: [
      "Long SOL funding if positive",
      "Show funding rates",
      "Flatten on 8% drawdown",
      "Cap leverage at 3x",
    ],
    strategyFields: [
      { id: "market", label: "Market", placeholder: "SOL-PERP", defaultValue: "SOL-PERP" },
      { id: "bias", label: "Bias", type: "select", defaultValue: "funding", options: [
        { value: "funding", label: "Follow funding" },
        { value: "long", label: "Long bias" },
        { value: "short", label: "Short bias" },
      ]},
      { id: "size_sol", label: "Size (SOL)", type: "number", placeholder: "1", defaultValue: "1" },
      { id: "max_leverage", label: "Max leverage", type: "number", placeholder: "3", defaultValue: "3" },
    ],
  },
  arbitrage: {
    slug: "arbitrage",
    name: "Arbitrage / Basis Agent",
    tagline: "Spot vs perps · pool gaps",
    description:
      "Hunt spot/perp basis and pool mispricings with a minimum edge and size cap.",
    category: "Trading",
    pricePerTask: "0.2% / arb",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Arb Agent",
    iconId: "arb",
    strategyTitle: "Arb strategy",
    submitLabel: "Enable arb scanner",
    examplePrompts: [
      "Scan SOL basis opportunities",
      "Set min edge to 15 bps",
      "List recent arb candidates",
      "Pause arb scanner",
    ],
    strategyFields: [
      { id: "pair", label: "Pair", placeholder: "SOL", defaultValue: "SOL" },
      { id: "min_edge_bps", label: "Min edge (bps)", type: "number", placeholder: "12", defaultValue: "12" },
      { id: "size_sol", label: "Max size (SOL)", type: "number", placeholder: "1", defaultValue: "1" },
      { id: "mode", label: "Mode", type: "select", defaultValue: "basis", options: [
        { value: "basis", label: "Spot / perp basis" },
        { value: "pool", label: "Pool mispricing" },
        { value: "both", label: "Both" },
      ]},
    ],
  },
  treasury: {
    slug: "treasury",
    name: "Treasury / Idle Cash Agent",
    tagline: "Sweep idle · keep buffer",
    description:
      "Keep a SOL/USDC operating buffer, sweep excess into yield, and pull cash back for buys.",
    category: "Automation",
    pricePerTask: "0.15% / sweep",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Treasury Agent",
    iconId: "treasury",
    strategyTitle: "Treasury policy",
    submitLabel: "Save policy",
    examplePrompts: [
      "Sweep idle USDC above 500",
      "Keep 2 SOL buffer",
      "Show treasury status",
      "Pull 1 SOL back for DCA",
    ],
    strategyFields: [
      { id: "buffer_sol", label: "SOL buffer", type: "number", placeholder: "2", defaultValue: "2" },
      { id: "idle_usdc", label: "Idle USDC threshold", type: "number", placeholder: "500", defaultValue: "500" },
      { id: "venue", label: "Sweep venue", type: "select", defaultValue: "yield_agent", options: [
        { value: "yield_agent", label: "Yield Agent" },
        { value: "kamino", label: "Kamino" },
        { value: "jlp", label: "Jupiter JLP" },
      ]},
    ],
  },
  rebalance: {
    slug: "rebalance",
    name: "Rebalance Agent",
    tagline: "Target weights · bands",
    description:
      "Hold target portfolio weights and rebalance on a schedule or when drift exceeds your band.",
    category: "Automation",
    pricePerTask: "0.3% / rebalance",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Rebalance Agent",
    iconId: "rebalance",
    strategyTitle: "Allocation",
    submitLabel: "Set targets",
    examplePrompts: [
      "Set 50 SOL / 30 USDC / 20 JUP",
      "Rebalance now",
      "Widen band to 5%",
      "Show current weights",
    ],
    strategyFields: [
      { id: "targets", label: "Targets", placeholder: "50 SOL / 30 USDC / 20 JUP", defaultValue: "50 SOL / 30 USDC / 20 JUP" },
      { id: "band_pct", label: "Drift band %", type: "number", placeholder: "3", defaultValue: "3" },
      { id: "capital", label: "Capital (SOL eq.)", type: "number", placeholder: "5", defaultValue: "5" },
    ],
  },
  sniper: {
    slug: "sniper",
    name: "Sniper / Launch Guard Agent",
    tagline: "New pools · risk gates",
    description:
      "Buy new pools with max size, slippage, liquidity, and authority checks before entry.",
    category: "Trading",
    pricePerTask: "0.6% / entry",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Sniper Agent",
    iconId: "sniper",
    strategyTitle: "Launch guard",
    submitLabel: "Arm sniper",
    examplePrompts: [
      "Arm sniper for new SOL pairs",
      "Require mint renounced",
      "Set max buy to 0.5 SOL",
      "Disable sniper",
    ],
    strategyFields: [
      { id: "base", label: "Base", placeholder: "SOL", defaultValue: "SOL" },
      { id: "max_buy", label: "Max buy (SOL)", type: "number", placeholder: "0.5", defaultValue: "0.5" },
      { id: "max_slip_bps", label: "Max slip (bps)", type: "number", placeholder: "300", defaultValue: "300" },
      { id: "min_liq_sol", label: "Min liq (SOL)", type: "number", placeholder: "50", defaultValue: "50" },
    ],
  },
  options: {
    slug: "options",
    name: "Options / Structured Agent",
    tagline: "Collars · covered calls",
    description:
      "Build simple structured payoffs (collar, covered call style) with spot and hedge legs.",
    category: "Trading",
    pricePerTask: "0.45% / structure",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Options Agent",
    iconId: "options",
    strategyTitle: "Structure",
    submitLabel: "Build structure",
    examplePrompts: [
      "Build a SOL collar",
      "Covered call 5% OTM",
      "Show open structures",
      "Close the active collar",
    ],
    strategyFields: [
      { id: "underlying", label: "Underlying", placeholder: "SOL", defaultValue: "SOL" },
      { id: "structure", label: "Structure", type: "select", defaultValue: "collar", options: [
        { value: "collar", label: "Collar" },
        { value: "covered_call", label: "Covered call" },
        { value: "protective_put", label: "Protective put" },
      ]},
      { id: "size", label: "Size (SOL)", type: "number", placeholder: "1", defaultValue: "1" },
      { id: "offset_pct", label: "Strike offset %", type: "number", placeholder: "5", defaultValue: "5" },
    ],
  },
};

export const DEFI_AGENT_LIST = Object.values(DEFI_AGENTS);

export function getDefiAgentConfig(slug: string): DefiAgentConfig | undefined {
  return DEFI_AGENTS[slug as DefiAgentSlug];
}

export function isDefiAgentSlug(value: string): value is DefiAgentSlug {
  return value in DEFI_AGENTS;
}
