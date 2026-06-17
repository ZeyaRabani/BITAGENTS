import {
  KNOWN_TOKENS,
  looksLikeMintAddress,
  shortAddress,
  type TokenInfo
} from "@bitagents/shared";
import { Connection, PublicKey } from "@solana/web3.js";
import { mainnetRpcUrl } from "@/server/env";
import { dcaConfig } from "./config";

/** Full token registry = base known tokens + the configured BITAGENTS token. */
export function tokenRegistry(): TokenInfo[] {
  const config = dcaConfig();
  const bitagents: TokenInfo = {
    symbol: config.bitagentsSymbol,
    mint: config.bitagentsMint,
    decimals: 6,
    aliases: [config.bitagentsSymbol.toLowerCase(), "bitagents", "bit agents", "$bitagents"]
  };
  return [bitagents, ...KNOWN_TOKENS];
}

export function findKnownToken(reference: string): TokenInfo | null {
  const ref = reference.trim().toLowerCase().replace(/^\$/, "");
  for (const token of tokenRegistry()) {
    if (token.symbol.toLowerCase() === ref) return token;
    if (token.mint === reference.trim()) return token;
    if (token.aliases.some((alias) => alias === ref)) return token;
  }
  return null;
}

async function fetchMintDecimals(mint: string): Promise<number | null> {
  try {
    const connection = new Connection(mainnetRpcUrl(), "confirmed");
    const info = await connection.getParsedAccountInfo(new PublicKey(mint), "confirmed");
    const value = info.value;
    if (!value || !("parsed" in value.data)) return null;
    const parsed = value.data.parsed as { info?: { decimals?: number } };
    return typeof parsed.info?.decimals === "number" ? parsed.info.decimals : null;
  } catch {
    return null;
  }
}

export type TokenResolution =
  | { ok: true; token: TokenInfo }
  | { ok: false; reason: "needs_mint" | "invalid_mint"; reference: string };

/**
 * Resolve a user-supplied token reference (symbol, alias, or mint address) to a
 * concrete TokenInfo. Unknown symbols return needs_mint so the agent can ask
 * the user for an explicit mint instead of guessing a token for them.
 */
export async function resolveToken(reference: string): Promise<TokenResolution> {
  const trimmed = reference.trim();
  if (!trimmed) return { ok: false, reason: "needs_mint", reference };

  const known = findKnownToken(trimmed);
  if (known) return { ok: true, token: known };

  if (looksLikeMintAddress(trimmed)) {
    try {
      const mint = new PublicKey(trimmed).toBase58();
      const decimals = (await fetchMintDecimals(mint)) ?? 6;
      return {
        ok: true,
        token: { symbol: shortAddress(mint), mint, decimals, aliases: [] }
      };
    } catch {
      return { ok: false, reason: "invalid_mint", reference };
    }
  }

  return { ok: false, reason: "needs_mint", reference };
}
