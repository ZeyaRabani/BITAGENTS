import { DEFAULT_TASK_PRICE_SOL, type SolanaNetwork } from "@bitagents/shared";
import { devnetRpcUrl, mainnetRpcUrl, treasuryWalletAddress } from "@/server/env";

export const runtime = "nodejs";

export async function GET() {
  const treasury = treasuryWalletAddress();
  const defaultNetwork: SolanaNetwork =
    process.env.NEXT_PUBLIC_SOLANA_NETWORK === "mainnet" ? "mainnet" : "devnet";

  return Response.json({
    treasuryWallet: treasury ?? "",
    treasuryConfigured: Boolean(treasury),
    defaultNetwork,
    taskFeeSol: DEFAULT_TASK_PRICE_SOL,
    devnetRpc: devnetRpcUrl(),
    mainnetRpc: mainnetRpcUrl()
  });
}
