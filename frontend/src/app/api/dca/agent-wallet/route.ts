import { lamportsToSol } from "@bitagents/shared";
import { Connection, PublicKey } from "@solana/web3.js";
import { agentWalletGate, ensureAgentWallet } from "@/server/dca/agentWallet";
import { getAgentWallet } from "@/server/dca/store";
import { rpcUrlForNetwork } from "@/server/env";
import { parseNetwork, requirePublicKey } from "@/server/validation";

export const runtime = "nodejs";

async function balanceSol(publicKey: string, network: "mainnet" | "devnet"): Promise<number | null> {
  try {
    const connection = new Connection(rpcUrlForNetwork(network), "confirmed");
    const lamports = await connection.getBalance(new PublicKey(publicKey), "confirmed");
    return lamportsToSol(lamports);
  } catch {
    return null;
  }
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const wallet = url.searchParams.get("wallet") ?? "";
  const network = parseNetwork(url.searchParams.get("network"));
  const gate = agentWalletGate(wallet, network);
  const stored = wallet ? await getAgentWallet(wallet) : undefined;
  const balance = stored ? await balanceSol(stored.publicKey, network) : null;
  return Response.json({
    enabled: gate.enabled,
    reason: gate.reason ?? null,
    caps: gate.caps,
    depositAddress: stored?.publicKey ?? null,
    balanceSol: balance
  });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const wallet = requirePublicKey(body.walletAddress, "wallet address");
    const network = parseNetwork(body.network);
    const gate = agentWalletGate(wallet, network);
    if (!gate.enabled) {
      return Response.json({ ok: false, error: gate.reason }, { status: 403 });
    }
    const stored = await ensureAgentWallet(wallet, network);
    const balance = await balanceSol(stored.publicKey, network);
    return Response.json({
      ok: true,
      depositAddress: stored.publicKey,
      caps: gate.caps,
      balanceSol: balance
    });
  } catch (error) {
    return Response.json({ ok: false, error: (error as Error).message }, { status: 400 });
  }
}
