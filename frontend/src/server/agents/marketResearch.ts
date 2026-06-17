import {
  nowIso,
  type MarketResearchInput,
  type MarketResearchResult,
  type SolanaNetwork
} from "@bitagents/shared";
import { performance } from "node:perf_hooks";
import { rpcUrlForNetwork } from "@/server/env";
import { generateNarrative } from "@/server/agents/llm";
import { scoreSentiment, sha256, titleCase, tokenize } from "@/server/agents/util";

const DISCLAIMER =
  "Structured research generated from deterministic heuristics (and an optional local model). " +
  "Educational only — not financial advice.";

interface NarrativeEntry {
  match: string[];
  meaning: string;
  useCases: string[];
  opportunities: string[];
  risks: string[];
  monitor: string[];
}

const KNOWLEDGE: NarrativeEntry[] = [
  {
    match: ["defi", "dex", "amm", "lending", "perps", "perp"],
    meaning:
      "Decentralized finance (DeFi) replaces intermediaries with on-chain smart contracts for trading, lending, and derivatives.",
    useCases: ["Permissionless swaps and liquidity", "Over-collateralized lending/borrowing", "On-chain perpetuals and yield"],
    opportunities: ["Real on-chain revenue and fees", "Composability across protocols", "Growing Solana DeFi liquidity"],
    risks: ["Smart-contract exploits", "Liquidity and oracle manipulation", "Regulatory pressure on yield products"],
    monitor: ["TVL and fee trends", "Audit and exploit history", "Stablecoin depeg events"]
  },
  {
    match: ["depin", "infrastructure", "compute", "gpu", "storage", "bandwidth"],
    meaning:
      "DePIN (Decentralized Physical Infrastructure Networks) coordinates real-world hardware — compute, storage, wireless — with token incentives.",
    useCases: ["Decentralized compute/GPU markets", "Distributed storage and CDN", "Sensor and wireless networks"],
    opportunities: ["Token incentives bootstrap supply", "Lower cost vs centralized clouds", "Solana's throughput suits micro-payments"],
    risks: ["Hardware/ops dependency", "Demand may lag token emissions", "Verifying real usage on-chain"],
    monitor: ["Active providers vs paying demand", "Emissions vs real revenue", "Hardware utilization rates"]
  },
  {
    match: ["ai", "agent", "agents", "llm", "inference"],
    meaning:
      "Crypto x AI blends autonomous agents and model inference with on-chain payments, identity, and coordination.",
    useCases: ["Agents that pay for compute/data", "On-chain provenance for AI outputs", "Automated research and execution"],
    opportunities: ["Micro-payments for inference", "Verifiable agent actions", "New agent-driven app categories"],
    risks: ["Hype outpacing real usage", "Hard to verify off-chain compute", "Centralized model dependencies"],
    monitor: ["Real paying usage vs demos", "Proof-of-compute approaches", "Agent safety and key custody"]
  },
  {
    match: ["rwa", "tokenization", "treasury", "bond", "stablecoin", "stable"],
    meaning:
      "Real-World Assets (RWA) bring off-chain value — treasuries, credit, commodities, fiat — on-chain as tokens.",
    useCases: ["Tokenized T-bills and credit", "On-chain stablecoins", "Collateral for DeFi"],
    opportunities: ["Yield from real assets", "24/7 settlement", "Institutional on-ramps"],
    risks: ["Legal/custody and redemption risk", "Issuer and counterparty trust", "Regulatory classification"],
    monitor: ["Issuer transparency/attestations", "Redemption mechanics", "Regulatory developments"]
  },
  {
    match: ["meme", "memecoin", "bonk", "wif", "dogwifhat"],
    meaning:
      "Memecoins are community- and attention-driven tokens with little intrinsic utility, often highly volatile.",
    useCases: ["Community coordination and culture", "Liquidity and speculation", "Onboarding new users"],
    opportunities: ["Viral distribution", "High liquidity on Solana", "Strong community network effects"],
    risks: ["Extreme volatility and drawdowns", "Insider/whale concentration", "Rug-pull and honeypot risk"],
    monitor: ["Holder concentration", "Liquidity lock status", "Social momentum vs fundamentals"]
  },
  {
    match: ["solana", "sol", "firedancer", "validator"],
    meaning:
      "Solana is a high-throughput L1 focused on low fees and fast finality, popular for consumer, DeFi, and DePIN apps.",
    useCases: ["High-frequency DeFi", "Consumer and payments apps", "DePIN micro-transactions"],
    opportunities: ["Low fees enable new app types", "Firedancer client diversity", "Growing developer ecosystem"],
    risks: ["Historical network outages", "Validator hardware requirements", "Competition from other L1/L2s"],
    monitor: ["Network uptime/performance", "Client diversity (Firedancer)", "Active addresses and fees"]
  }
];

function matchEntry(tokens: string[]): NarrativeEntry | null {
  for (const entry of KNOWLEDGE) {
    if (entry.match.some((keyword) => tokens.includes(keyword))) {
      return entry;
    }
  }
  return null;
}

export async function computeMarketResearch(
  input: MarketResearchInput,
  network: SolanaNetwork
): Promise<MarketResearchResult> {
  const start = performance.now();
  const query = input.query.trim();
  const tokens = tokenize(query);
  const sentiment = scoreSentiment(tokens);
  const entry = matchEntry(tokens);
  const label = titleCase(query);

  const meaningFallback = entry
    ? entry.meaning
    : `"${label}" appears to be a crypto keyword, ticker, or narrative. This brief breaks it down structurally: ` +
      "what it likely refers to, where it could be used on-chain, and what to watch. Connect a token mint in the " +
      "Token Research agent for live metrics.";

  const useCases = entry?.useCases ?? [
    "Potential on-chain product or protocol category",
    "Community / ecosystem coordination",
    "Speculative trading and liquidity"
  ];
  const opportunities = entry?.opportunities ?? [
    "Early positioning if the narrative gains adoption",
    "Composability with existing Solana protocols",
    "Network effects from an engaged community"
  ];
  const risks = [
    ...(entry?.risks ?? [
      "Narrative may not convert into real usage",
      "Liquidity and team transparency unknown",
      "High volatility typical of emerging themes"
    ]),
    ...sentiment.riskHits.map((term) => `Query references a risk-associated term: "${term}".`)
  ];
  const thingsToMonitor = entry?.monitor ?? [
    "Real usage and revenue vs hype",
    "Liquidity depth and holder distribution",
    "Developer activity and roadmap delivery"
  ];

  const narrative = await generateNarrative({
    system:
      "You are a neutral crypto market analyst. In 3-4 sentences explain what the keyword/narrative means and why it " +
      "matters on Solana. Use only general, well-known context. Never invent prices or give financial advice.",
    prompt: `Keyword/narrative: ${query}\nNetwork context: ${network}\nDetected theme: ${entry ? entry.match[0] : "general"}`,
    fallback: meaningFallback
  });

  const core = {
    type: "market_research" as const,
    query,
    useCases,
    risks: Array.from(new Set(risks)),
    opportunities,
    thingsToMonitor,
    sentimentScore: sentiment.score,
    network
  };

  return {
    ...core,
    meaning: narrative.text,
    disclaimer: DISCLAIMER,
    engine: narrative.engine,
    computedAt: nowIso(),
    runtimeMs: Math.round((performance.now() - start) * 100) / 100,
    resultHash: sha256(core),
    rpcUrl: rpcUrlForNetwork(network)
  };
}
