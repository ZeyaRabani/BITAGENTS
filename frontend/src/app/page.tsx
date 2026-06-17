import { ArrowRight, MessageSquare, ShieldCheck, Repeat, Wallet } from "lucide-react";
import { LinkButton, Panel, SectionLabel, Tag } from "@/components/primitives";

const STEPS = [
  {
    icon: MessageSquare,
    title: "Describe your buy",
    body: "Type a plain-English instruction like \"buy BITAGENTS every 10 minutes with 0.01 SOL\"."
  },
  {
    icon: Repeat,
    title: "Agent plans it",
    body: "The agent parses your message into a structured recurring-buy plan: per-buy amount, interval, and count."
  },
  {
    icon: ShieldCheck,
    title: "You confirm",
    body: "Review the exact plan and risk warnings. Nothing is created until you confirm — and sign, on mainnet."
  },
  {
    icon: Wallet,
    title: "It runs on-chain",
    body: "Mainnet Safe Mode uses Jupiter Recurring (you sign, no custody). Devnet Demo Mode simulates the schedule."
  }
];

const HERO_TERMINAL = `> buy BITAGENTS every 10 minutes with 0.01 SOL
> total budget: 1 SOL
> agent: planning 100 recurring buys
> status: ready for confirmation`;

export default function LandingPage() {
  return (
    <div className="grid-bg-fade">
      <section className="mx-auto w-full max-w-6xl px-4 pb-16 pt-14 sm:px-6 sm:pb-20 sm:pt-20">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
          <div className="space-y-6">
            <SectionLabel>DCA Agent on Solana</SectionLabel>
            <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight text-foreground sm:text-6xl">
              Create DCA bots <span className="text-signal">with AI</span>.
            </h1>
            <p className="max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              Tell BITAGENTS what token to buy, how much to spend, and how often. The DCA Agent turns your message into
              a recurring on-chain buy plan.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <LinkButton href="/app">
                Launch DCA Agent <ArrowRight size={15} />
              </LinkButton>
              <LinkButton href="/docs" variant="outline">
                How it works
              </LinkButton>
            </div>
            <div className="flex flex-wrap gap-2">
              <Tag>Natural-language planning</Tag>
              <Tag>You confirm every order</Tag>
              <Tag>Non-custodial</Tag>
              <Tag>Jupiter Recurring</Tag>
            </div>
          </div>

          <Panel title="bitagents@solana ~ dca.agent" className="glow-signal">
            <pre className="overflow-x-auto font-mono text-[12px] leading-relaxed text-foreground/90">
              {HERO_TERMINAL}
            </pre>
            <div className="mt-3 flex items-center gap-2 border-t border-border pt-3 font-mono text-[11px] text-muted-foreground">
              <span className="h-1.5 w-1.5 animate-pulse-dot bg-success" />
              awaiting your confirmation — no funds move until you approve
            </div>
          </Panel>
        </div>
      </section>

      <Section id="how" eyebrow="How it works" title="From a message to a recurring buy">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <div key={step.title} className="pixel-corners border border-border bg-surface p-5">
                <div className="flex items-center justify-between">
                  <span className="pixel-corners flex h-9 w-9 items-center justify-center border border-border text-signal">
                    <Icon size={16} />
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">0{index + 1}</span>
                </div>
                <h3 className="mt-3 font-display text-base font-semibold text-foreground">{step.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{step.body}</p>
              </div>
            );
          })}
        </div>
      </Section>

      <Section id="modes" eyebrow="Two safe modes" title="Mainnet Safe Mode or Devnet Demo Mode">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="pixel-corners border border-border bg-surface p-6">
            <Tag className="border-success/40 text-success">Mainnet Safe Mode</Tag>
            <h3 className="mt-3 font-display text-lg font-semibold text-foreground">Real recurring buys, you sign</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Orders are created through Jupiter&apos;s Recurring (DCA) program. You sign the order in your own wallet —
              BITAGENTS never custodies your funds or holds your keys. Jupiter&apos;s keepers run the schedule on-chain.
            </p>
          </div>
          <div className="pixel-corners border border-border bg-surface p-6">
            <Tag className="border-signal/40 text-signal">Devnet Demo Mode</Tag>
            <h3 className="mt-3 font-display text-lg font-semibold text-foreground">Simulated, end-to-end</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              The agent parses your instruction, builds a plan, and simulates each scheduled buy with real price reads.
              Executions are clearly labelled as simulations — no real tokens are purchased. Perfect for trying the flow.
            </p>
          </div>
        </div>
      </Section>

      <Section id="safety" eyebrow="Safety first" title="The agent automates — it never advises">
        <ul className="grid gap-3 sm:grid-cols-2">
          {[
            "You choose the token and every parameter. The agent only turns your instruction into a plan.",
            "Nothing is created until you confirm; mainnet orders require your wallet signature.",
            "No profit promises. DCA does not guarantee returns and tokens can lose value.",
            "Small or new tokens can be illiquid — slippage and minimum-order limits may apply.",
            "You can cancel an active plan at any time.",
            "This is not financial advice."
          ].map((line) => (
            <li
              key={line}
              className="pixel-corners flex items-start gap-2.5 border border-border bg-surface p-4 text-sm text-foreground/80"
            >
              <ShieldCheck size={15} className="mt-0.5 shrink-0 text-signal" />
              {line}
            </li>
          ))}
        </ul>
      </Section>

      <section className="mx-auto w-full max-w-6xl px-4 pb-20 sm:px-6">
        <div className="pixel-corners glow-signal flex flex-col items-start gap-4 border border-signal/40 bg-surface p-7 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-display text-2xl font-bold text-foreground">Ready to plan your first DCA?</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Mainnet Safe Mode is on by default — no funds move without your wallet signature. Switch to Devnet Demo Mode anytime to simulate first.
            </p>
          </div>
          <LinkButton href="/app">
            Launch DCA Agent <ArrowRight size={15} />
          </LinkButton>
        </div>
      </section>
    </div>
  );
}

function Section({
  id,
  eyebrow,
  title,
  children
}: {
  id: string;
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="border-t border-border">
      <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-16">
        <div className="mb-8 space-y-3">
          <SectionLabel>{eyebrow}</SectionLabel>
          <h2 className="font-display text-2xl font-bold tracking-tight text-foreground sm:text-3xl">{title}</h2>
        </div>
        {children}
      </div>
    </section>
  );
}
