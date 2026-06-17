import { DcaAgent } from "@/components/dca/DcaAgent";
import { LinkButton, PageShell } from "@/components/primitives";

export default function AppWorkspacePage() {
  return (
    <PageShell
      eyebrow="DCA Agent"
      title="Create a DCA bot with AI"
      description="Tell the agent what token to buy, how much to spend, and how often. It turns your message into a recurring on-chain buy plan that you confirm. You choose the token and parameters — this is not financial advice."
      actions={
        <LinkButton href="/plans" variant="outline" size="sm">
          My Plans
        </LinkButton>
      }
    >
      <DcaAgent />
    </PageShell>
  );
}
