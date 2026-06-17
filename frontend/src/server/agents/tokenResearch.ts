import {
  nowIso,
  type SolanaNetwork,
  type TokenResearchInput,
  type TokenResearchResult
} from "@bitagents/shared";
import { performance } from "node:perf_hooks";
import { fetchTokenSnapshot, isValidPublicKey } from "@/server/agents/solana";
import { rpcUrlForNetwork } from "@/server/env";
import { generateNarrative } from "@/server/agents/llm";
import { scoreSentiment, sha256, titleCase, tokenize } from "@/server/agents/util";

const DISCLAIMER =
  "This report is generated from public on-chain data and deterministic heuristics. " +
  "It is for research and educational purposes only and is not financial advice.";

export async function computeTokenResearch(
  input: TokenResearchInput,
  network: SolanaNetwork
): Promise<TokenResearchResult> {
  const start = performance.now();
  const query = input.query.trim();
  const looksLikeMint = isValidPublicKey(query);

  const onchain: TokenResearchResult["onchain"] = {
    supply: null,
    decimals: null,
    holdersNote: "On-chain holder data was not requested (project name lookup).",
    liquidityNote: "Liquidity data requires a market data provider and is not available from RPC alone.",
    mintAuthorityActive: null,
    freezeAuthorityActive: null
  };

  let mintAddress: string | null = null;
  let resolvedFromMint = false;
  const risks: string[] = [];
  const bullCase: string[] = [];
  const bearCase: string[] = [];

  if (looksLikeMint) {
    mintAddress = query;
    const snapshot = await fetchTokenSnapshot(network, query);
    if (snapshot.exists) {
      resolvedFromMint = true;
      onchain.supply = snapshot.supply;
      onchain.decimals = snapshot.decimals;
      onchain.mintAuthorityActive = snapshot.mintAuthorityActive;
      onchain.freezeAuthorityActive = snapshot.freezeAuthorityActive;
      onchain.holdersNote =
        snapshot.topHolderCount !== null
          ? `Top ${Math.min(10, snapshot.topHolderCount)} accounts hold ~${(snapshot.topHolderShare ?? 0).toFixed(1)}% of supply (from getTokenLargestAccounts).`
          : "Largest-account data was unavailable from this RPC endpoint.";
      onchain.liquidityNote =
        "On-chain mint data only; pool/DEX liquidity requires an external market data source.";

      if (snapshot.mintAuthorityActive) {
        risks.push("Mint authority is still active — supply can be increased (dilution risk).");
      } else {
        bullCase.push("Mint authority is disabled, so the supply is fixed.");
      }
      if (snapshot.freezeAuthorityActive) {
        risks.push("Freeze authority is active — token accounts can be frozen by the authority.");
      } else {
        bullCase.push("Freeze authority is disabled, reducing account-freezing risk.");
      }
      if ((snapshot.topHolderShare ?? 0) > 60) {
        risks.push(`High concentration: top holders control ~${(snapshot.topHolderShare ?? 0).toFixed(1)}% of supply.`);
        bearCase.push("Concentrated ownership can lead to sharp sell pressure.");
      } else if (snapshot.topHolderShare !== null) {
        bullCase.push(`Ownership is reasonably distributed (top holders ~${(snapshot.topHolderShare ?? 0).toFixed(1)}%).`);
      }
    } else {
      onchain.holdersNote = `No SPL mint account was found at this address on ${network}.`;
      risks.push("Address does not resolve to a known SPL token mint on the selected network.");
    }
  } else {
    onchain.holdersNote = "Project-name lookup: connect a token mint address for live on-chain metrics.";
  }

  const tokens = tokenize(query);
  const sentiment = scoreSentiment(tokens);
  sentiment.riskHits.forEach((term) => risks.push(`Narrative mentions a risk-associated term: "${term}".`));

  // Always provide a useful structured baseline even without metadata.
  if (bullCase.length === 0) {
    bullCase.push("Clear narrative or utility can drive organic demand if execution is strong.");
    bullCase.push("Active development and transparent tokenomics support long-term confidence.");
  }
  if (bearCase.length === 0) {
    bearCase.push("Without verifiable liquidity and audits, downside risk is elevated.");
    bearCase.push("Token unlocks or weak demand can pressure price regardless of narrative.");
  }
  risks.push("Always verify the mint address, liquidity, and audits before interacting.");

  const label = looksLikeMint ? `mint ${query.slice(0, 8)}…` : `"${titleCase(query)}"`;
  const fallbackOverview =
    `Research brief for ${label} on ${network}. ` +
    (resolvedFromMint
      ? `The mint resolves on-chain with ${onchain.supply !== null ? onchain.supply.toLocaleString() : "unknown"} supply ` +
        `and ${onchain.decimals ?? "?"} decimals. ${onchain.holdersNote}`
      : "No live mint metadata was resolved, so this brief relies on deterministic structural analysis. ") +
    " Evaluate authorities, holder distribution, liquidity, and team transparency before acting.";

  const narrative = await generateNarrative({
    system:
      "You are a careful crypto research analyst. Write a neutral 3-4 sentence token overview from the provided facts. " +
      "Do not invent prices, market caps, or partnerships. Always stay balanced and never give financial advice.",
    prompt:
      `Query: ${query}\nNetwork: ${network}\nResolved mint: ${resolvedFromMint}\n` +
      `Supply: ${onchain.supply}\nDecimals: ${onchain.decimals}\n` +
      `Mint authority active: ${onchain.mintAuthorityActive}\nFreeze authority active: ${onchain.freezeAuthorityActive}\n` +
      `Holders: ${onchain.holdersNote}`,
    fallback: fallbackOverview
  });

  const core = {
    type: "token_research" as const,
    query,
    mintAddress,
    resolvedFromMint,
    onchain,
    risks: Array.from(new Set(risks)),
    bullCase: Array.from(new Set(bullCase)),
    bearCase: Array.from(new Set(bearCase)),
    network
  };

  return {
    ...core,
    overview: narrative.text,
    disclaimer: DISCLAIMER,
    engine: narrative.engine,
    computedAt: nowIso(),
    runtimeMs: Math.round((performance.now() - start) * 100) / 100,
    resultHash: sha256(core),
    rpcUrl: rpcUrlForNetwork(network)
  };
}
