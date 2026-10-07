"use client";

import { Check, X } from "lucide-react";

export function Platform() {
  return (
    <section id="platform" >
      <div className="mx-auto max-w-7xl px-6 py-20 md:py-24">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">Platform</div>
        <div className="mt-4 grid gap-12 md:grid-cols-[1.1fr_1.4fr] md:items-start">
          <div>
            <h2 className="font-display text-4xl font-bold leading-tight md:text-5xl">
              Built for agent-native workflows.
            </h2>
            <p className="mt-6 max-w-md text-muted-foreground">
              BIT Agents is focused on active automation: agents that watch, research, alert, prepare, and coordinate workflows across on-chain activity from a single marketplace.
            </p>
          </div>
          <div className="grid gap-px bg-[color:var(--border)] border-2 border-grid sm:grid-cols-2">
            <div className="bg-background p-6">
              <div className="font-display text-base font-bold">Manual crypto workflows</div>
              <ul className="mt-5 space-y-3 text-sm text-muted-foreground">
                {["Manual wallet checks", "Fragmented research", "Repeated operational tasks"].map((t) => (
                  <li key={t} className="flex items-start gap-2"><X className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" /> {t}</li>
                ))}
              </ul>
            </div>
            <div className="bg-[color:var(--surface-2)] p-6">
              <div className="font-display text-base font-bold text-signal">BIT Agents</div>
              <ul className="mt-5 space-y-3 text-sm text-foreground">
                {["Active automation", "AI agents", "Marketplace-native workflows"].map((t) => (
                  <li key={t} className="flex items-start gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-signal" /> {t}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}