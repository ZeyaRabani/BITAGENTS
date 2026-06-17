import {
  lamportsToSol,
  type SolanaNetwork,
  type WalletSignatureSummary
} from "@bitagents/shared";
import { Connection, PublicKey } from "@solana/web3.js";
import { rpcUrlForNetwork } from "@/server/env";

const TOKEN_PROGRAM_ID = new PublicKey("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
const TOKEN_2022_PROGRAM_ID = new PublicKey("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");

export function readConnection(network: SolanaNetwork): Connection {
  return new Connection(rpcUrlForNetwork(network), "confirmed");
}

export function isValidPublicKey(value: string): boolean {
  try {
    // eslint-disable-next-line no-new
    new PublicKey(value);
    return true;
  } catch {
    return false;
  }
}

export interface WalletSnapshot {
  solBalance: number;
  tokenAccountsCount: number;
  latestSignatures: WalletSignatureSummary[];
  activeDays: number;
  failedCount: number;
}

export async function fetchWalletSnapshot(
  network: SolanaNetwork,
  address: string
): Promise<WalletSnapshot> {
  const connection = readConnection(network);
  const wallet = new PublicKey(address);

  const [lamports, splAccounts, token2022Accounts, signatures] = await Promise.all([
    connection.getBalance(wallet, "confirmed"),
    connection.getParsedTokenAccountsByOwner(wallet, { programId: TOKEN_PROGRAM_ID }, "confirmed"),
    connection
      .getParsedTokenAccountsByOwner(wallet, { programId: TOKEN_2022_PROGRAM_ID }, "confirmed")
      .catch(() => ({ value: [] as unknown[] })),
    connection.getSignaturesForAddress(wallet, { limit: 5 }, "confirmed")
  ]);

  const latestSignatures: WalletSignatureSummary[] = signatures.map((item) => ({
    signature: item.signature,
    slot: item.slot,
    blockTime: item.blockTime ?? null,
    err: item.err !== null
  }));

  const days = new Set(
    latestSignatures
      .filter((sig) => sig.blockTime !== null)
      .map((sig) => new Date((sig.blockTime as number) * 1000).toISOString().slice(0, 10))
  );

  return {
    solBalance: lamportsToSol(lamports),
    tokenAccountsCount: splAccounts.value.length + token2022Accounts.value.length,
    latestSignatures,
    activeDays: days.size,
    failedCount: latestSignatures.filter((sig) => sig.err).length
  };
}

export interface TokenSnapshot {
  exists: boolean;
  supply: number | null;
  decimals: number | null;
  mintAuthorityActive: boolean | null;
  freezeAuthorityActive: boolean | null;
  topHolderCount: number | null;
  topHolderShare: number | null;
}

interface ParsedMintInfo {
  decimals?: number;
  supply?: string;
  mintAuthority?: string | null;
  freezeAuthority?: string | null;
}

export async function fetchTokenSnapshot(
  network: SolanaNetwork,
  mint: string
): Promise<TokenSnapshot> {
  const connection = readConnection(network);
  const mintKey = new PublicKey(mint);

  const accountInfo = await connection.getParsedAccountInfo(mintKey, "confirmed");
  const value = accountInfo.value;

  if (!value || !("parsed" in value.data)) {
    return {
      exists: false,
      supply: null,
      decimals: null,
      mintAuthorityActive: null,
      freezeAuthorityActive: null,
      topHolderCount: null,
      topHolderShare: null
    };
  }

  const info = (value.data.parsed as { info?: ParsedMintInfo }).info ?? {};
  const decimals = typeof info.decimals === "number" ? info.decimals : null;
  const rawSupply = info.supply ? Number(info.supply) : null;
  const supply = rawSupply !== null && decimals !== null ? rawSupply / 10 ** decimals : rawSupply;

  let topHolderCount: number | null = null;
  let topHolderShare: number | null = null;

  try {
    const largest = await connection.getTokenLargestAccounts(mintKey, "confirmed");
    topHolderCount = largest.value.length;
    if (rawSupply && rawSupply > 0) {
      const topSum = largest.value
        .slice(0, 10)
        .reduce((sum, account) => sum + Number(account.amount), 0);
      topHolderShare = Math.min(100, (topSum / rawSupply) * 100);
    }
  } catch {
    // Largest-accounts can be unavailable on some RPCs; leave holder data null.
  }

  return {
    exists: true,
    supply,
    decimals,
    mintAuthorityActive: info.mintAuthority != null,
    freezeAuthorityActive: info.freezeAuthority != null,
    topHolderCount,
    topHolderShare
  };
}
