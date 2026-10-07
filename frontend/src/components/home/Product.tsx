"use client";

import { ArrowLeftRight, Bot, Clock, Repeat2 } from "lucide-react";

const cards = [
  {
    icon: ArrowLeftRight,
    title: "DCA Agent",
    body: "Set up recurring Solana buys from natural language. Schedule swaps, preview quotes, and manage plans without leaving chat.",
  },
  {
    icon: Repeat2,
    title: "On-Chain Automation",
    body: "Deposits, custodial agent wallet flows, and a background scheduler execute DCA plans on mainnet with on-chain proof and ledger tracking.",
  },
  {
    icon: Bot,
    title: "Agent Marketplace",
    body: "Discover and run BIT Agents from one catalog. Browse live agents today - third-party deployment is not open yet.",
  },
  {
    icon: Clock,
    title: "Scheduled Execution",
    body: "From seconds to monthly intervals, automation keeps buying on your schedule while you monitor balances, history, and platform metrics.",
  },
];

export function Product() {
  return (
    <section id="product" className="border-b-2 border-grid">
      <div className="mx-auto max-w-7xl px-6 py-20 md:py-24">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">Product</div>
        <div className="mt-4 grid gap-12 md:grid-cols-[1fr_1.4fr] md:items-start">
          <div>
            <h2 className="font-display text-4xl font-bold leading-tight md:text-5xl">
              Agents that run on-chain workflows.
            </h2>
            <p className="mt-6 max-w-md text-muted-foreground">
              BIT Agents is an agent marketplace for running specialized automation - starting with DCA on Solana.
              Users can discover agents, connect a wallet, and execute tasks from one place. Listing your own agent
              is not available yet.
            </p>
          </div>
          <div className="grid gap-px border-2 border-grid bg-border sm:grid-cols-2">
            {cards.map(({ icon: Icon, title, body }) => (
              <div key={title} className="bg-background p-6">
                <Icon className="h-5 w-5 text-signal" />
                <div className="mt-5 font-display text-lg font-bold">{title}</div>
                <p className="mt-2 text-sm text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
