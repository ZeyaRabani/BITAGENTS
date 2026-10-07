import type { Metadata } from "next";
import { LegalDocument } from "@/components/legal/LegalDocument";

export const metadata: Metadata = {
  title: "Terms of Service - BITAGENTS",
  description: "Terms of Service for the BITAGENTS marketplace and DCA agent.",
};

export default function TermsPage() {
  return (
    <LegalDocument
      title="Terms of Service"
      subtitle="Rules for using the BITAGENTS marketplace, agents, and custodial deposit features."
      updated="June 18, 2026"
      sections={[
        {
          title: "1. Acceptance",
          body: [
            "By connecting a wallet, signing an authentication message, depositing funds, or using any BITAGENTS service, you agree to these Terms of Service, our Privacy Policy, and Risk Disclaimer.",
            "If you do not agree, do not use the platform.",
          ],
        },
        {
          title: "2. Service description",
          body: [
            "BITAGENTS provides software interfaces for autonomous AI agents, including a custodial deposit model where users transfer tokens to an agent-operated wallet to fund automated tasks such as dollar-cost averaging (DCA).",
            "We do not provide investment, financial, tax, or legal advice. Agent outputs are informational and may be incorrect.",
          ],
        },
        {
          title: "3. Eligibility",
          body: [
            "You must be at least 18 years old and legally permitted to use blockchain services in your jurisdiction.",
            "You are responsible for compliance with local laws, sanctions, and tax obligations.",
          ],
        },
        {
          title: "4. Custodial deposits & withdrawals",
          body: [
            "When you deposit tokens to the agent wallet, on-chain transfers are recorded in an internal ledger tied to your wallet address. Only verified deposits you signed may be credited to your balance.",
            "Withdrawals send tokens back to your connected wallet subject to available balance and active plan reservations. We may delay or reject withdrawals to prevent fraud, abuse, or technical errors.",
          ],
        },
        {
          title: "5. Fees & third parties",
          body: [
            "Blockchain network fees, swap fees, and third-party API costs may apply. Pricing for agent tasks may change without notice during beta.",
            "Swaps may route through third-party protocols such as Jupiter. We are not responsible for third-party protocol failures.",
          ],
        },
        {
          title: "6. Prohibited use",
          body: [
            "You may not use BITAGENTS for money laundering, market manipulation, unauthorized access, denial-of-service attacks, or any unlawful activity.",
            "You may not attempt to claim another user's deposits, forge transaction signatures, or circumvent authentication.",
          ],
        },
        {
          title: "7. Disclaimers & limitation of liability",
          body: [
            "The service is provided \"as is\" without warranties. Smart contracts, RPC providers, LLMs, and market data may fail or produce incorrect results.",
            "To the maximum extent permitted by law, BITAGENTS and its contributors are not liable for lost funds, failed transactions, smart contract bugs, or trading losses.",
          ],
        },
        {
          title: "8. Changes & contact",
          body: [
            "We may update these terms at any time. Continued use after changes constitutes acceptance.",
            "Questions: legal@bitagents.app",
          ],
        },
      ]}
    />
  );
}
