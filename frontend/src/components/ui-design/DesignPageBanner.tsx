"use client";

type PageKey = "marketplace" | "launch" | "dca";

const PAGE_HELP: Record<
  PageKey,
  { title: string; steps: [string, string, string] }
> = {
  marketplace: {
    title: "How to use an agent",
    steps: ["Pick an agent below", "Connect your wallet", "Fund it and start"],
  },
  launch: {
    title: "How to create an agent",
    steps: ["Name it and write the task", "Choose modules", "Pay the launch fee and go live"],
  },
  dca: {
    title: "How DCA works",
    steps: ["Deposit SOL or USDC", "Set a buy schedule", "The agent buys for you on repeat"],
  },
};

/** Clear how-to strip - same across every visual look. */
export function DesignPageBanner({ page }: { page: PageKey }) {
  const help = PAGE_HELP[page];

  return (
    <div className="ui-design-banner mb-8 border border-grid bg-surface/60 px-4 py-4 sm:px-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">
        {help.title}
      </div>
      <ol className="mt-3 grid gap-3 sm:grid-cols-3">
        {help.steps.map((step, i) => (
          <li key={step} className="flex items-start gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center border border-grid bg-background font-mono text-xs font-bold text-signal">
              {i + 1}
            </span>
            <span className="pt-1 text-sm leading-snug text-foreground">{step}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
