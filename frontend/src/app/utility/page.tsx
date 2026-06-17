import { SectionLabel, PageShell } from "@/components/primitives";
import { Roadmap } from "@/components/Roadmap";
import { TokenUtilitySection } from "@/components/TokenUtilitySection";

export default function UtilityPage() {
  return (
    <PageShell
      eyebrow="Token utility"
      title="Utility &amp; roadmap"
      description="How the BITAGENTS token is designed to be used, and where the platform is heading. Forward-looking statements use careful wording and are subject to change."
    >
      <div className="space-y-14">
        <section className="space-y-5">
          <SectionLabel>Token utility</SectionLabel>
          <TokenUtilitySection />
          <div className="pixel-corners border border-warn/40 bg-warn/5 p-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              <span className="font-semibold text-warn">Important:</span> Everything on this page is forward-looking and
              may change. Nothing here is a promise of revenue share, profit, yield, or guaranteed returns, and none of
              it is financial advice. Token utility is designed to evolve as the platform matures.
            </p>
          </div>
        </section>

        <section className="space-y-5">
          <SectionLabel>Roadmap</SectionLabel>
          <Roadmap />
        </section>
      </div>
    </PageShell>
  );
}
