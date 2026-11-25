"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Check } from "lucide-react";
import Link from "next/link";

type ChatTurn = {
  id: string;
  role: "you" | "builder";
  content: string;
};

type BuildStepStatus = "done" | "active" | "pending";

type BuildStep = {
  id: string;
  label: string;
  tag?: string;
  meta: string;
  status: BuildStepStatus;
};

const INITIAL_TURNS: ChatTurn[] = [
  {
    id: "u1",
    role: "you",
    content:
      "Watch NVIDIA. If it drops 10% in a day, short Mag 7 for $200 each. Cover when NVDA is up 2% from that drop. Cap me at $500 in market.",
  },
  {
    id: "a1",
    role: "builder",
    content:
      "Mapped to signal_basket: short Mag 7 when NVDA 1d change ≤ -10%, reverse when ≥ +2% from entry. Size $200/name, max $500 exposure. How often should I check?",
  },
  {
    id: "u2",
    role: "you",
    content: "Every 15 minutes.",
  },
];

const SUGGESTIONS = ["Add a daily loss limit", "Paper trade first", "Explain the fees"];

const STRATEGY_ROWS: Array<[string, string]> = [
  ["Trigger", "NVDAx 1d change"],
  ["Short when", "≤ -10%"],
  ["Long when", "≥ +2%"],
  ["Basket", "7 names, equal weight"],
  ["Size", "$200 per entry"],
  ["Exit", "TP 12% · SL 6%"],
  ["Check", "every 15 min"],
];

const LIMIT_ROWS: Array<[string, string]> = [
  ["Max in market", "$500"],
  ["Programs", "Jupiter, Jupiter Perps"],
  ["Withdraw to", "6VZb…ChfeV"],
];

const INITIAL_BUILD_STEPS: BuildStep[] = [
  {
    id: "check",
    label: "Strategy checked against",
    tag: "signal_basket@1",
    meta: "0.4s",
    status: "done",
  },
  {
    id: "dry-run",
    label: "Dry run on the last 30 days",
    meta: "3 entries, 0 limit breaches",
    status: "done",
  },
  {
    id: "source",
    label: "Agent source generated and committed",
    meta: "bitagents-apps@9c1e7a2",
    status: "done",
  },
  {
    id: "compile",
    label: "Compiling the agent",
    meta: "usually 3 to 6 min",
    status: "active",
  },
  {
    id: "aomi",
    label: "Going live on Aomi",
    meta: "",
    status: "pending",
  },
  {
    id: "wallet",
    label: "Creating your agent wallet",
    meta: "",
    status: "pending",
  },
];

function formatElapsed(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function BuildStepIcon({ status }: { status: BuildStepStatus }) {
  if (status === "done") {
    return (
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center text-signal">
        <Check size={16} strokeWidth={2.5} />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="mt-1.5 flex h-5 w-5 shrink-0 items-start justify-center">
        <span className="mt-1 h-2.5 w-2.5 animate-pulse rounded-full bg-signal" />
      </span>
    );
  }
  return (
    <span className="mt-1.5 flex h-5 w-5 shrink-0 items-start justify-center">
      <span className="mt-1 h-3.5 w-3.5 rounded-full border border-muted-foreground/50" />
    </span>
  );
}

function BuildingProgress({ agentName }: { agentName: string }) {
  const [elapsed, setElapsed] = useState(0);
  const [steps, setSteps] = useState<BuildStep[]>(INITIAL_BUILD_STEPS);

  useEffect(() => {
    const tick = window.setInterval(() => {
      setElapsed((value) => value + 1);
    }, 1000);
    return () => window.clearInterval(tick);
  }, []);

  useEffect(() => {
    const timers = [
      window.setTimeout(() => {
        setSteps((current) =>
          current.map((step) => {
            if (step.id === "compile") {
              return { ...step, status: "done", meta: "4m 12s" };
            }
            if (step.id === "aomi") {
              return { ...step, status: "active", meta: "publishing" };
            }
            return step;
          })
        );
      }, 8000),
      window.setTimeout(() => {
        setSteps((current) =>
          current.map((step) => {
            if (step.id === "aomi") {
              return { ...step, status: "done", meta: "live" };
            }
            if (step.id === "wallet") {
              return { ...step, status: "active", meta: "provisioning" };
            }
            return step;
          })
        );
      }, 14000),
      window.setTimeout(() => {
        setSteps((current) =>
          current.map((step) =>
            step.id === "wallet"
              ? { ...step, status: "done", meta: "ready" }
              : step
          )
        );
      }, 18000),
    ];
    return () => {
      for (const id of timers) window.clearTimeout(id);
    };
  }, []);

  const complete = useMemo(
    () => steps.every((step) => step.status === "done"),
    [steps]
  );

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 sm:py-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <h1 className="font-display text-4xl font-bold leading-[0.98] tracking-tight text-foreground md:text-5xl">
          Building {agentName}
        </h1>
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-signal">
          <span className="h-2 w-2 animate-pulse rounded-full bg-signal" />
          {formatElapsed(elapsed)} elapsed
        </div>
      </div>

      <div className="mt-8 border border-grid bg-card">
        <ol>
          {steps.map((step, index) => (
            <li
              key={step.id}
              className={`flex items-start justify-between gap-4 px-5 py-5 ${
                index > 0 ? "border-t border-grid" : ""
              }`}
            >
              <div className="flex min-w-0 items-start gap-3">
                <BuildStepIcon status={step.status} />
                <div
                  className={`min-w-0 text-sm ${
                    step.status === "pending"
                      ? "text-muted-foreground"
                      : step.status === "active"
                        ? "font-medium text-foreground"
                        : "text-muted-foreground"
                  }`}
                >
                  <span>{step.label}</span>
                  {step.tag ? (
                    <span className="ml-2 inline-block bg-signal/20 px-1.5 py-0.5 font-mono text-[11px] text-signal">
                      {step.tag}
                    </span>
                  ) : null}
                </div>
              </div>
              {step.meta ? (
                <div
                  className={`shrink-0 text-right font-mono text-[11px] ${
                    step.status === "active" ? "text-signal" : "text-muted-foreground"
                  }`}
                >
                  {step.meta}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </div>

      <p className="mt-6 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        You can leave this page. The agent appears under{" "}
        <Link href="/my-agents" className="text-signal underline-offset-2 hover:underline">
          My agents
        </Link>{" "}
        when it is ready, and nothing trades until you fund it and press Go live.
      </p>

      {complete ? (
        <div className="mt-6">
          <Link
            href="/my-agents"
            className="inline-flex items-center justify-center bg-signal px-5 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90"
          >
            Open My agents
          </Link>
        </div>
      ) : null}
    </div>
  );
}

export function LaunchAgentConsole() {
  const [phase, setPhase] = useState<"draft" | "building">("draft");
  const [turns, setTurns] = useState<ChatTurn[]>(INITIAL_TURNS);
  const [draft, setDraft] = useState("");

  function sendMessage(raw: string) {
    const text = raw.trim();
    if (!text) return;
    setTurns((current) => [
      ...current,
      { id: `u-${Date.now()}`, role: "you", content: text },
      {
        id: `a-${Date.now()}`,
        role: "builder",
        content:
          "Noted. Update the draft on the right, or keep describing changes in plain words.",
      },
    ]);
    setDraft("");
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    sendMessage(draft);
  }

  if (phase === "building") {
    return <BuildingProgress agentName="NVDA Momentum Basket" />;
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="font-display text-4xl font-bold leading-[0.98] tracking-tight text-foreground md:text-5xl">
        Create an agent
      </h1>

      <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(280px,0.9fr)]">
        <section className="flex min-h-[640px] flex-col border border-grid bg-card">
          <div className="flex items-center justify-between border-b border-grid bg-surface-2 px-4 py-2.5">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
              Describe your strategy
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Draft 2
            </span>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto px-4 py-5">
            {turns.map((turn) =>
              turn.role === "you" ? (
                <div key={turn.id}>
                  <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                    You
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-foreground">{turn.content}</p>
                </div>
              ) : (
                <div key={turn.id} className="border border-signal/40 bg-signal/5 px-4 py-3">
                  <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                    Agent builder
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{turn.content}</p>
                </div>
              )
            )}
          </div>

          <div className="space-y-3 border-t border-grid px-4 py-4">
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((label) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => sendMessage(label)}
                  className="border border-grid px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-foreground"
                >
                  {label}
                </button>
              ))}
            </div>
            <form onSubmit={onSubmit} className="flex gap-2">
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Change anything in plain words…"
                className="min-w-0 flex-1 border border-grid bg-background px-3 py-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/60 focus:border-signal"
              />
              <button
                type="submit"
                className="shrink-0 border border-grid bg-surface-2 px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal hover:text-signal"
              >
                Send
              </button>
            </form>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="border border-grid bg-card p-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
              Strategy · Python data · signal_basket@1
            </div>
            <dl className="mt-4 space-y-2.5">
              {STRATEGY_ROWS.map(([label, value]) => (
                <div key={label} className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-3 text-sm">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="font-medium text-foreground">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="border border-grid bg-card p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                Agent brief · Aomi app
              </div>
              <button
                type="button"
                className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition hover:text-signal"
              >
                Edit
              </button>
            </div>
            <p className="mt-4 border-l-2 border-signal/50 pl-3 text-sm leading-relaxed text-muted-foreground">
              “Short Mag 7 when NVDA dumps 10% in a day. Cover on a 2% bounce. $200 per name, $500
              max in market. Check every 15 minutes.”
            </p>
          </div>

          <div className="border border-grid bg-card p-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
              Limits · Enforced on-chain
            </div>
            <dl className="mt-4 space-y-2.5">
              {LIMIT_ROWS.map(([label, value]) => (
                <div key={label} className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-3 text-sm">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="font-medium text-foreground">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <button
            type="button"
            onClick={() => setPhase("building")}
            className="inline-flex w-full items-center justify-center bg-signal px-5 py-4 font-mono text-sm font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90"
          >
            Compile and deploy · 1 SOL
          </button>
        </aside>
      </div>
    </div>
  );
}
