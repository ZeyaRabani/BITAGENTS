"use client";

import { Lock } from "lucide-react";

const items = [
  {
    title: "Platform Fees & Buybacks",
    body: "A portion of future platform fees is planned to support buybacks.",
  },
  {
    title: "Agent Staking",
    body: "Developers and power users may stake BIT Agents to access premium agents and build reputation.",
  },
  {
    title: "Premium Agent Access",
    body: "Token holders may receive access to advanced agents, higher limits, and premium workflows.",
  },
  {
    title: "Marketplace Settlement",
    body: "Future versions may use BIT Agents for agent task payments and marketplace settlement.",
  },
];

export function TokenUtility() {
  return (
    <section id="token-utility" className="border-b border-grid/70">
      <div className="mx-auto max-w-7xl px-6 py-20 md:py-24">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">
          Token Utility
        </div>
        <h2 className="mt-4 max-w-3xl font-display text-4xl font-bold leading-tight md:text-5xl">
          Designed around real platform usage.
        </h2>
        <p className="mt-5 max-w-2xl text-muted-foreground">
          The BIT Agents token is designed to connect product usage with marketplace access, agent
          rewards, and future settlement flows.
        </p>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((i) => (
            <div key={i.title} className="rounded-2xl border border-grid bg-surface/40 p-6">
              <Lock className="h-4 w-4 text-signal" />
              <div className="mt-5 font-display text-base font-bold">{i.title}</div>
              <p className="mt-2 text-sm text-muted-foreground">{i.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
