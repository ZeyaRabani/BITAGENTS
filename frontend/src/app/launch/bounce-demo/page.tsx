"use client";

import { useState } from "react";
import { AppShell, Panel } from "@/components/AppShell";

/**
 * Demo-only comparison: what launching a strategy agent looks like today
 * (plain form, zero validation, no real execution once live) vs. what we're
 * proposing (a guided checklist with a backtest gate before "live").
 *
 * Nothing on this page calls the backend. Every number is illustrative.
 * Built to show Harshal the actual problem and the actual shape of the fix,
 * not to be a working feature.
 */

type ChecklistField = {
  key: string;
  label: string;
  why: string;
  value: string;
};

const CHECKLIST: ChecklistField[] = [
  { key: "asset", label: "Asset", why: "Locked to SOL for now — that's what we can actually backtest against.", value: "SOL" },
  { key: "entry", label: "Entry trigger", why: "What the agent is watching for. Too loose and it trades on noise; too tight and it may never fire.", value: "Drops 10% from recent high, then bounces 5% off the low" },
  { key: "stop", label: "Stop-loss", why: "The most you're willing to lose if the trade goes wrong. Without this the agent has no way to know when to cut losses.", value: "At the original low" },
  { key: "target", label: "Take-profit", why: "When the agent locks in the win. Without this it has no way to know when to stop.", value: "3x the distance between entry and stop (3R)" },
  { key: "size", label: "Position size", why: "Stops one bad trade from wiping the whole deposit.", value: "Max 20% of deposited balance per position" },
  { key: "confirm", label: "Confirmation", why: "Every real buy or sell pauses and asks first — nothing fires silently.", value: "Required before every buy or sell" },
];

const SCRIPT = [
  {
    speaker: "user" as const,
    text: "I want an agent that buys SOL when it dips and bounces back, with a stop and a target.",
  },
  {
    speaker: "agent" as const,
    text: "Got it. A few things I need before I can build this properly — I'll ask one at a time.",
  },
  { speaker: "agent" as const, text: "How big a drop counts as a dip, and how much of a bounce confirms it's turning around?", fill: "entry" },
  { speaker: "user" as const, text: "10% drop, then a 5% bounce off the low." },
  { speaker: "agent" as const, text: "Where should the stop-loss sit if I'm wrong?", fill: "stop" },
  { speaker: "user" as const, text: "At the original low." },
  { speaker: "agent" as const, text: "And the take-profit — I'd suggest a risk multiple so it scales with the stop. 3x the stop distance (3R)?", fill: "target" },
  { speaker: "user" as const, text: "Yeah, 3R works." },
  { speaker: "agent" as const, text: "Last one — how much of your deposited balance can one position use? I won't let this exceed what you set.", fill: "size" },
  { speaker: "user" as const, text: "No more than 20%." },
  { speaker: "agent" as const, text: "One more thing, not optional: I'll ask you to confirm before every buy or sell. Nothing fires without that.", fill: "confirm" },
  { speaker: "agent" as const, text: "Checklist's complete and coherent — your stop is a real distance from entry, your target is bigger than your risk, your position size is sane. Running it against a year of real SOL price history before I'll let this go live." },
  { speaker: "backtest" as const, text: "" },
  {
    speaker: "agent" as const,
    text: "This would have returned +34% over the last year, with a worst drawdown of 18%. Plain SOL buy-and-hold over the same window returned +21%. It beats the benchmark after estimated fees and slippage — eligible to go live. Want to launch it?",
  },
];

const PROBLEMS_TODAY = [
  "Free-text task box — type anything, no follow-up questions, no coherence check.",
  "Nothing stops you launching a stop-loss bigger than the take-profit, or a position size larger than your deposit.",
  "No backtest. Nothing checks whether the strategy as described would have ever made money.",
  "Once live, the agent can only talk about the task — it has no real tools wired in. It cannot actually buy or sell anything.",
];

export default function BounceDemoPage() {
  const [tab, setTab] = useState<"today" | "proposed">("today");
  const [step, setStep] = useState(0);

  const filled = new Set(SCRIPT.slice(0, step + 1).map((s) => ("fill" in s ? s.fill : null)).filter(Boolean));
  const atBacktest = SCRIPT[step]?.speaker === "backtest";
  const atEnd = step >= SCRIPT.length - 1;

  return (
    <AppShell
      title="Bounce Agent — demo"
      subtitle="Mocked comparison, not connected to the backend. Built to show the actual gap and the actual shape of the fix."
    >
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setTab("today")}
          className={`rounded-full px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] transition ${
            tab === "today" ? "bg-signal text-background" : "border border-grid text-muted-foreground hover:text-foreground"
          }`}
        >
          What happens today
        </button>
        <button
          onClick={() => setTab("proposed")}
          className={`rounded-full px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] transition ${
            tab === "proposed" ? "bg-signal text-background" : "border border-grid text-muted-foreground hover:text-foreground"
          }`}
        >
          What we're proposing
        </button>
      </div>

      {tab === "today" && (
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <Panel title="The real /launch form">
            <div className="space-y-3">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Name</div>
                <div className="mt-1 rounded-xl border border-grid bg-background px-3 py-2 text-sm">Bounce Agent</div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Task (free text)</div>
                <div className="mt-1 rounded-xl border border-grid bg-background px-3 py-2 text-sm text-muted-foreground">
                  Watch SOL. If the price drops 10% from its recent high and then bounces 5% off the low, buy using my deposited balance...
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Modules</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {["agent_wallet", "jupiter_swaps", "solana_rpc"].map((m) => (
                    <span key={m} className="rounded-full bg-surface-2 px-3 py-1 font-mono text-[10px]">{m}</span>
                  ))}
                </div>
              </div>
              <div className="rounded-full bg-signal px-4 py-2.5 text-center font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-background">
                Launch agent →
              </div>
            </div>
          </Panel>
          <Panel title="What's actually wrong with this">
            <ul className="space-y-3">
              {PROBLEMS_TODAY.map((p) => (
                <li key={p} className="flex gap-3 text-sm text-muted-foreground">
                  <span className="text-warn">!</span>
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}

      {tab === "proposed" && (
        <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Panel title="Guided checklist — click through">
            <div className="flex max-h-125 flex-col gap-3 overflow-y-auto pr-1">
              {SCRIPT.slice(0, step + 1).map((line, i) =>
                line.speaker === "backtest" ? (
                  <div key={i} className="rounded-xl bg-surface-2 p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">Backtest — 1yr SOL, illustrative</div>
                    <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                      <div>
                        <div className="font-display text-xl font-bold text-signal">+34%</div>
                        <div className="font-mono text-[9px] uppercase text-muted-foreground">Return</div>
                      </div>
                      <div>
                        <div className="font-display text-xl font-bold text-warn">18%</div>
                        <div className="font-mono text-[9px] uppercase text-muted-foreground">Max drawdown</div>
                      </div>
                      <div>
                        <div className="font-display text-xl font-bold">+21%</div>
                        <div className="font-mono text-[9px] uppercase text-muted-foreground">SOL hold (bench)</div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div
                    key={i}
                    className={`rounded-xl px-4 py-3 text-sm ${
                      line.speaker === "user" ? "ml-8 bg-surface/60" : "mr-8 bg-surface-2"
                    }`}
                  >
                    <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                      {line.speaker === "user" ? "You" : "Bounce Agent builder"}
                    </div>
                    {line.text}
                  </div>
                )
              )}
            </div>
            <button
              onClick={() => setStep((s) => Math.min(s + 1, SCRIPT.length - 1))}
              disabled={atEnd}
              className="mt-4 w-full rounded-full bg-signal px-4 py-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-background disabled:opacity-40"
            >
              {atEnd ? "End of demo" : atBacktest ? "Show backtest result" : "Next"}
            </button>
          </Panel>

          <Panel title="Checklist state">
            <div className="space-y-3">
              {CHECKLIST.map((f) => {
                const done = filled.has(f.key);
                return (
                  <div key={f.key} className={`rounded-xl p-3 ${done ? "bg-surface-2" : "bg-surface/30 opacity-40"}`}>
                    <div className="flex items-center gap-2">
                      <span className={done ? "text-signal" : "text-muted-foreground"}>{done ? "✓" : "○"}</span>
                      <span className="font-mono text-[10px] uppercase tracking-[0.14em]">{f.label}</span>
                    </div>
                    {done && (
                      <>
                        <div className="mt-1.5 text-sm">{f.value}</div>
                        <div className="mt-1 text-xs text-muted-foreground">{f.why}</div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>
      )}
    </AppShell>
  );
}
