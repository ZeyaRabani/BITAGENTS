import { ArrowRight, Cpu, Wallet, Zap } from "lucide-react";
import { LinkButton, Panel, SectionLabel, Tag } from "@/components/primitives";
import { Roadmap } from "@/components/Roadmap";
import { TokenUtilitySection } from "@/components/TokenUtilitySection";
import { AGENTS } from "@/lib/agents";

const STEPS = [
  { icon: Wallet, title: "Connect wallet", body: "Connect Phantom on Solana. Devnet Demo Mode is on by default." },
  { icon: Zap, title: "Choose an agent", body: "Pick Wallet Watcher, Token Research, or Market Research." },
  { icon: Cpu, title: "Pay devnet fee", body: "Pay a 0.001 SOL devnet fee, or run a free demo with no wallet." },
  { icon: ArrowRight, title: "Get a real result", body: "Real Solana RPC compute, hashed and timestamped, with an explorer link." }
];

export default function LandingPage() {
  return (
    <div className="grid-bg-fade">
      <section className="mx-auto w-full max-w-6xl px-4 pb-16 pt-14 sm:px-6 sm:pb-20 sm:pt-20">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
          <div className="space-y-6">
            <SectionLabel>Crypto AI agent platform</SectionLabel>
            <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight text-foreground sm:text-6xl">
              Run crypto AI agents <span className="text-signal">without setup</span>.
            </h1>
            <p className="max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              Connect a Solana wallet, choose an agent, submit a task, and get a real, useful on-chain result. No
              infrastructure, no API keys, no boilerplate.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <LinkButton href="/app">
                Launch app <ArrowRight size={15} />
              </LinkButton>
              <LinkButton href="/agents" variant="outline">
                Explore agents
              </LinkButton>
            </div>
            <div className="flex flex-wrap gap-2">
              <Tag>Solana wallet adapter</Tag>
              <Tag>Devnet payments</Tag>
              <Tag>Mainnet read-only</Tag>
              <Tag>Real RPC compute</Tag>
            </div>
          </div>

          <Panel title="bitagents@solana ~ wallet_watcher" className="glow-signal">
            <pre className="overflow-x-auto font-mono text-[12px] leading-relaxed text-foreground/90">
              <span className="text-muted-foreground">$</span> bitagents run wallet_watcher \{"\n"}
              {"  "}--address So111…1112 --network devnet{"\n\n"}
              <span className="text-signal">›</span> task created      <span className="text-muted-foreground">id=2f9a…</span>
              {"\n"}
              <span className="text-signal">›</span> devnet payment    <span className="text-success">0.001 SOL ✓</span>
              {"\n"}
              <span className="text-signal">›</span> provider assigned <span className="text-muted-foreground">BITAGENTS Local Compute</span>
              {"\n"}
              <span className="text-signal">›</span> computing…        <span className="text-muted-foreground">real RPC fetch</span>
              {"\n\n"}
              <span className="text-success">✓ completed</span> in 842ms{"\n"}
              {"  "}sol_balance      = 12.4071{"\n"}
              {"  "}token_accounts   = 7{"\n"}
              {"  "}recent_sigs      = 5{"\n"}
              {"  "}result_hash      = 7c1f…a9{"\n"}
              {"  "}engine           = deterministic{"\n"}
            </pre>
          </Panel>
        </div>
      </section>

      <Section id="agents" eyebrow="Agents" title="Three working agents, real output">
        <div className="grid gap-4 md:grid-cols-3">
          {AGENTS.map((agent) => {
            const Icon = agent.icon;
            return (
              <div key={agent.type} className="pixel-corners flex flex-col border border-border bg-surface p-5">
                <span className="pixel-corners flex h-10 w-10 items-center justify-center border border-signal/40 bg-signal/10 text-signal">
                  <Icon size={18} />
                </span>
                <h3 className="mt-4 font-display text-lg font-semibold text-foreground">{agent.label}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{agent.description}</p>
                <ul className="mt-4 space-y-1.5">
                  {agent.outputs.map((output) => (
                    <li key={output} className="flex items-center gap-2 font-mono text-xs text-foreground/75">
                      <span className="h-1 w-1 bg-signal" />
                      {output}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </Section>

      <Section id="how" eyebrow="How it works" title="From wallet to result in four steps">
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

      <Section id="compute" eyebrow="Compute marketplace" title="Bring your own compute">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:items-center">
          <div className="space-y-4">
            <p className="text-sm leading-relaxed text-muted-foreground sm:text-base">
              Providers can register a compute profile, choose a type (CPU, simulated GPU, or an LLM endpoint), set a
              price per task, and sign a message proving wallet ownership. Tasks are routed to an online provider, and a
              built-in local provider keeps the demo running when none are registered.
            </p>
            <div className="flex flex-wrap gap-2">
              <Tag>CPU</Tag>
              <Tag>GPU (simulated)</Tag>
              <Tag>LLM endpoint</Tag>
              <Tag>Signed registration</Tag>
              <Tag>Reputation</Tag>
            </div>
            <LinkButton href="/compute" variant="outline" size="sm">
              Open compute marketplace <ArrowRight size={14} />
            </LinkButton>
          </div>
          <Panel title="provider.register">
            <pre className="overflow-x-auto font-mono text-[12px] leading-relaxed text-foreground/90">
              {`{
  "name": "edge-node-01",
  "computeType": "LLM",
  "pricePerTaskSol": 0.001,
  "status": "online",
  "signature": "5h2k…verified ✓"
}`}
            </pre>
          </Panel>
        </div>
      </Section>

      <Section id="token-utility" eyebrow="Token utility" title="What the token is designed to do">
        <TokenUtilitySection />
        <p className="mt-4 max-w-3xl text-xs italic text-muted-foreground">
          Forward-looking and subject to change. Nothing here is a promise of revenue share, profit, or guaranteed
          returns, and none of it is financial advice.
        </p>
      </Section>

      <Section id="roadmap" eyebrow="Roadmap" title="Where BITAGENTS is going">
        <Roadmap />
      </Section>

      <section className="mx-auto w-full max-w-6xl px-4 pb-20 sm:px-6">
        <div className="pixel-corners glow-signal flex flex-col items-start gap-4 border border-signal/40 bg-surface p-7 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-display text-2xl font-bold text-foreground">Ready to run your first agent?</h2>
            <p className="mt-1 text-sm text-muted-foreground">Devnet Demo Mode is on by default. No mainnet funds at risk.</p>
          </div>
          <LinkButton href="/app">
            Launch app <ArrowRight size={15} />
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
