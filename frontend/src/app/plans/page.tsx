import { LinkButton, PageShell } from "@/components/primitives";
import { MyPlans } from "@/components/dca/MyPlans";

export default function MyPlansPage() {
  return (
    <PageShell
      eyebrow="My Plans"
      title="Your DCA plans"
      description="Every plan for your connected wallet (or local demo wallet). Track buys completed, amount spent, the next scheduled buy, and on-chain transactions. Cancel an active plan at any time."
      actions={
        <LinkButton href="/app" variant="outline" size="sm">
          New plan
        </LinkButton>
      }
    >
      <MyPlans />
    </PageShell>
  );
}
