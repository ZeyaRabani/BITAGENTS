import { DEFAULT_TASK_PRICE_SOL } from "@bitagents/shared";
import { devnetRpcUrl, mainnetRpcUrl, treasuryWalletAddress } from "@/server/env";
import { dcaConfig } from "@/server/dca/config";

export const runtime = "nodejs";

export async function GET() {
  const treasury = treasuryWalletAddress();
  const config = dcaConfig();

  return Response.json({
    treasuryWallet: treasury ?? "",
    treasuryConfigured: Boolean(treasury),
    defaultNetwork: config.defaultNetwork,
    taskFeeSol: DEFAULT_TASK_PRICE_SOL,
    devnetRpc: devnetRpcUrl(),
    mainnetRpc: mainnetRpcUrl(),
    bitagentsMint: config.bitagentsMint,
    bitagentsSymbol: config.bitagentsSymbol,
    enableMainnetDca: config.enableMainnetDca,
    enableAgentWalletMode: config.enableAgentWalletMode
  });
}
