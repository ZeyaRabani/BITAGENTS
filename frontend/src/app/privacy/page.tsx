import type { Metadata } from "next";
import { LegalDocument } from "@/components/legal/LegalDocument";

export const metadata: Metadata = {
  title: "Privacy Policy - BITAGENTS",
  description: "How BITAGENTS collects, uses, and stores information.",
};

export default function PrivacyPage() {
  return (
    <LegalDocument
      title="Privacy Policy"
      subtitle="What we collect when you use BITAGENTS and how we use it."
      updated="June 18, 2026"
      sections={[
        {
          title: "1. Information we collect",
          body: [
            "Wallet addresses you connect, authentication signatures, session tokens, and chat messages sent to agents.",
            "On-chain transaction signatures, deposit amounts, token symbols/mints, DCA plan configuration, and agent tool execution logs.",
            "Technical data such as IP address, browser type, and request timestamps may be collected by our hosting providers.",
          ],
        },
        {
          title: "2. How we use information",
          body: [
            "To authenticate you, credit verified deposits, enforce per-user balances, execute DCA plans, and display activity in the UI.",
            "To secure the platform, prevent duplicate deposit claims, debug failures, and improve reliability.",
            "We do not sell your personal information.",
          ],
        },
        {
          title: "3. Storage & retention",
          body: [
            "Session tokens, ledger entries, plan data, and chat history may be stored in our database (e.g. Neon PostgreSQL).",
            "On-chain data is public by nature. We retain operational records as long as needed for security, accounting, and legal compliance.",
          ],
        },
        {
          title: "4. Third-party services",
          body: [
            "We use third-party infrastructure including Solana RPC providers, OpenRouter for LLM inference, Jupiter for swaps, and cloud hosting.",
            "Those providers process data under their own policies. Avoid sharing sensitive personal data in agent chat.",
          ],
        },
        {
          title: "5. Your choices",
          body: [
            "You may disconnect your wallet and stop using the service at any time.",
            "You may withdraw unused credited balances where supported, subject to active plan reservations and on-chain constraints.",
          ],
        },
        {
          title: "6. Security",
          body: [
            "We use wallet signature authentication, internal API keys, and ledger accounting controls. No system is perfectly secure.",
            "You are responsible for securing your wallet, seed phrase, and device.",
          ],
        },
        {
          title: "7. Contact",
          body: ["Privacy questions: privacy@bitagents.app"],
        },
      ]}
    />
  );
}
