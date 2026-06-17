import { SectionLabel, PageShell } from "@/components/primitives";

const UTILITY = [
  {
    title: "Premium agent access",
    body: "Token holders are designed to unlock premium DCA Agent capabilities in future versions."
  },
  {
    title: "Higher plan limits",
    body: "Holding the token may raise limits such as the number of concurrent DCA plans or buys per plan."
  },
  {
    title: "Reduced agent service fees",
    body: "Any future, optional agent service fee on automated modes is designed to be discounted for holders."
  },
  {
    title: "Compute provider staking (later)",
    body: "A later phase may let compute or automation providers stake the token to participate."
  },
  {
    title: "Future marketplace access",
    body: "If a third-party agent marketplace ships, the token is planned to gate access and listings."
  },
  {
    title: "Planned buybacks",
    body: "Future versions may direct a portion of platform revenue toward planned token buybacks."
  }
];

const REVENUE = [
  "Optional subscriptions for higher limits and premium agent features.",
  "An optional agent service fee on the experimental automated (agent wallet) mode.",
  "Future marketplace listing or routing fees, if and when a marketplace ships."
];

const ROADMAP = [
  { phase: "Now", body: "DCA Agent MVP: natural-language planning, Devnet Demo Mode, and Mainnet Safe Mode via Jupiter Recurring." },
  { phase: "Next", body: "Saved plans, plan editing, alerts, and richer plan analytics." },
  { phase: "Later", body: "Experimental automated execution (opt-in), provider staking, and a third-party agent marketplace." }
];

export default function UtilityPage() {
  return (
    <PageShell
      eyebrow="Token utility"
      title="Utility & business model"
      description="How the BITAGENTS token is designed to be used and how the platform is designed to sustain itself. Forward-looking statements use careful wording and are subject to change."
    >
      <div className="space-y-14">
        <section className="space-y-5">
          <SectionLabel>Token utility</SectionLabel>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {UTILITY.map((item) => (
              <div key={item.title} className="pixel-corners border border-border bg-surface p-5">
                <h3 className="font-display text-base font-semibold text-foreground">{item.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{item.body}</p>
              </div>
            ))}
          </div>
          <div className="pixel-corners border border-warn/40 bg-warn/5 p-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              <span className="font-semibold text-warn">Important:</span> Everything on this page is forward-looking and
              may change. Nothing here is a promise of revenue share, profit, yield, token-price increase, or guaranteed
              returns, and none of it is financial advice. Token utility is designed to evolve as the platform matures.
            </p>
          </div>
        </section>

        <section className="space-y-5">
          <SectionLabel>How BITAGENTS makes money</SectionLabel>
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
            BITAGENTS does <span className="text-foreground">not</span> take a fee on Jupiter Recurring orders —
            integrators cannot add fees to that program, so we don&apos;t claim to. The model is designed around
            transparent, optional revenue:
          </p>
          <ul className="grid gap-3 sm:grid-cols-3">
            {REVENUE.map((line) => (
              <li key={line} className="pixel-corners border border-border bg-surface p-4 text-sm text-foreground/80">
                {line}
              </li>
            ))}
          </ul>
        </section>

        <section className="space-y-5">
          <SectionLabel>Roadmap</SectionLabel>
          <div className="grid gap-4 md:grid-cols-3">
            {ROADMAP.map((item) => (
              <div key={item.phase} className="pixel-corners border border-border bg-surface p-5">
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-signal">{item.phase}</span>
                <p className="mt-2 text-sm text-muted-foreground">{item.body}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </PageShell>
  );
}
