import type { Metadata } from "next";
import { LegalDocument } from "@/components/legal/LegalDocument";

export const metadata: Metadata = {
  title: "Risk Disclaimer - BITAGENTS",
  description: "Important risks when using BITAGENTS and automated trading tools.",
};

export default function RiskDisclaimerPage() {
  return (
    <LegalDocument
      title="Risk Disclaimer"
      subtitle="Crypto, automation, and AI agents involve significant risk. Read carefully before use."
      updated="June 18, 2026"
      sections={[
        {
          title: "Not financial advice",
          body: [
            "BITAGENTS, its agents, and all outputs are for informational and software automation purposes only. Nothing on this platform is investment, financial, tax, or legal advice.",
            "DYOR - do your own research before allocating any capital.",
          ],
        },
        {
          title: "Market & smart contract risk",
          body: [
            "Digital assets are volatile. You may lose some or all of deposited value due to price moves, slippage, failed swaps, or illiquid markets.",
            "Smart contracts, bridges, RPC nodes, and wallet software may contain bugs or be exploited.",
          ],
        },
        {
          title: "Automation & AI risk",
          body: [
            "AI agents can misunderstand instructions, call tools incorrectly, or hallucinate plan details. Always verify balances, mint addresses, and plan settings.",
            "Scheduled DCA does not guarantee profit and may execute in unfavorable market conditions.",
          ],
        },
        {
          title: "Custodial deposit model",
          body: [
            "Deposits are sent to an agent-operated wallet on Solana. While balances are tracked per user in our ledger, on-chain custody carries operational and security risk.",
            "Only deposit amounts you are willing to lose. Keep main holdings in wallets you control directly when possible.",
          ],
        },
        {
          title: "Token program compatibility",
          body: [
            "Some SPL tokens use Token-2022 extensions, transfer fees, or other features that may cause deposits, swaps, or withdrawals to fail or behave unexpectedly.",
            "Always confirm the exact mint address of any token before creating plans or withdrawing.",
          ],
        },
        {
          title: "Beta software",
          body: [
            "BITAGENTS may be experimental or in beta. Features may change, break, or be discontinued without notice.",
            "By using the platform you accept these risks voluntarily.",
          ],
        },
      ]}
    />
  );
}
