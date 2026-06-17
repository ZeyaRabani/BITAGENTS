import { LinkButton, PageShell, Panel, SectionLabel } from "@/components/primitives";
import { DCA_RISK_WARNINGS } from "@bitagents/shared";

const EXAMPLES = [
  "Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total",
  "Buy SOL every day with 10 USDC for 30 days",
  "Buy <mint address> every hour with 0.05 SOL for 10 buys"
];

function DocSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <SectionLabel>{title}</SectionLabel>
      <div className="space-y-3 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </section>
  );
}

export default function DocsPage() {
  return (
    <PageShell
      eyebrow="Docs"
      title="How the DCA Agent works"
      description="BITAGENTS turns a plain-English instruction into a recurring on-chain buy plan that you confirm. Here's exactly what happens and how to stay safe."
      actions={
        <LinkButton href="/app" variant="outline" size="sm">
          Open the agent
        </LinkButton>
      }
    >
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-8">
          <DocSection title="What it is">
            <p>
              The DCA (dollar-cost averaging) Agent reads an instruction like &quot;buy BITAGENTS every 10 minutes with
              0.01 SOL using 1 SOL total&quot; and produces a structured plan: which token to buy, how much per buy, how
              often, and how many buys. You review the plan and confirm before anything is created.
            </p>
            <p>
              The agent never chooses a token for you, never recommends a trade, and never promises profit. It only
              automates the instruction you give it.
            </p>
          </DocSection>

          <DocSection title="Example prompts">
            <ul className="space-y-2">
              {EXAMPLES.map((example) => (
                <li key={example} className="pixel-corners border border-border bg-surface-2 px-3 py-2 font-mono text-xs text-foreground/80">
                  {example}
                </li>
              ))}
            </ul>
            <p>
              You can use a known symbol (BITAGENTS, SOL, USDC, USDT) or paste any Solana mint address. Unknown symbols
              will prompt you for a mint address — the agent won&apos;t guess.
            </p>
          </DocSection>

          <DocSection title="Mainnet Safe Mode">
            <p>
              When mainnet is enabled and selected, the agent creates a real recurring order through Jupiter&apos;s
              Recurring (DCA) program. You sign the order in your own wallet; BITAGENTS does not custody funds or hold
              private keys. Jupiter&apos;s keepers execute the schedule on-chain.
            </p>
            <p>
              Jupiter enforces a minimum value per order (≈ 50 USDC at the time of writing). Very small buys are
              rejected — the agent explains this and lets you increase the size or switch to Devnet Demo Mode.
            </p>
          </DocSection>

          <DocSection title="Devnet Demo Mode">
            <p>
              The default mode. The agent parses your instruction, builds the plan, and simulates each scheduled buy
              with real price reads. Every execution is clearly labelled as a simulation — no real tokens are bought.
              This lets anyone try the full flow without funds or a browser wallet.
            </p>
          </DocSection>
        </div>

        <div className="space-y-8">
          <Panel title="safety" bodyClassName="space-y-2">
            <ul className="space-y-2">
              {DCA_RISK_WARNINGS.map((warning) => (
                <li key={warning} className="flex items-start gap-2 text-sm text-foreground/80">
                  <span className="mt-1.5 h-1 w-1 shrink-0 bg-signal" />
                  {warning}
                </li>
              ))}
            </ul>
          </Panel>

          <DocSection title="Experimental Agent Wallet Mode">
            <p>
              An optional mode where a server-managed wallet executes swaps on a schedule without a per-order signature.
              It is <span className="text-foreground">disabled by default</span> and gated behind an environment flag,
              an admin allowlist, encryption of the wallet secret at rest, and hard caps on total spend, order count, and
              minimum interval. It is intended for advanced testing only, never as the default experience.
            </p>
          </DocSection>

          <DocSection title="How BITAGENTS makes money">
            <p>
              BITAGENTS does <span className="text-foreground">not</span> take a fee on Jupiter Recurring orders —
              integrators cannot add fees to that program. Any future revenue is designed to come from optional
              subscriptions, premium agent access, or an agent service fee on the experimental automated mode — never
              from hidden trading logic, fake volume, or custody of your funds.
            </p>
          </DocSection>

          <DocSection title="Scheduling">
            <p>
              Devnet Demo executions advance as you watch a plan (and via a local worker, <span className="font-mono text-foreground">npm run dca:worker</span>, or a Vercel Cron hitting <span className="font-mono text-foreground">/api/cron/dca</span>). Mainnet orders are executed by Jupiter&apos;s keepers, not by BITAGENTS.
            </p>
          </DocSection>
        </div>
      </div>
    </PageShell>
  );
}
