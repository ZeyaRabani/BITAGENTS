"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AgentAvatar } from "@/components/launch/AgentAvatar";
import { Rocket } from "lucide-react";

const MODELS = [
  { id: "fast", label: "Fast", detail: "Cheapest, best for simple lookups & alerts" },
  { id: "balanced", label: "Balanced", detail: "Default — good reasoning, moderate cost" },
  { id: "reasoning", label: "Reasoning", detail: "Best for multi-step trading/research logic" },
];

const CATEGORIES = ["Trading", "Research", "Monitoring", "Utility"] as const;

export default function CreateAgentPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [ticker, setTicker] = useState("");
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("Research");
  const [description, setDescription] = useState("");
  const [personality, setPersonality] = useState("");
  const [model, setModel] = useState("balanced");
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = name.trim().length > 1 && ticker.trim().length > 0 && description.trim().length > 10 && personality.trim().length > 10;

  function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false);
      toast.success(`${name} launched`, {
        description: `$${ticker.toUpperCase()} is now live on the marketplace.`,
      });
      router.push("/launch");
    }, 900);
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <div className="mb-8 border-b border-grid pb-6">
        <h1 className="font-display text-3xl font-bold leading-tight md:text-4xl">Launch an agent</h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Describe what it does and how it should behave. No code — the agent is defined by a prompt,
          not a repo.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        {/* Identity */}
        <div className="border border-grid bg-surface/40 p-5">
          <div className="mb-4 flex items-center gap-4">
            <AgentAvatar seed={ticker || name || "new"} size={56} />
            <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-[1fr_140px]">
              <Field label="Agent name">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Yield Scout"
                  className="input"
                />
              </Field>
              <Field label="Ticker">
                <input
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.replace(/[^a-zA-Z0-9]/g, "").slice(0, 8))}
                  placeholder="YIELD"
                  className="input font-mono uppercase"
                />
              </Field>
            </div>
          </div>

          <Field label="Category">
            <div className="flex flex-wrap gap-1.5">
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(c)}
                  className={`border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] transition ${
                    category === c
                      ? "border-signal bg-surface/60 text-signal"
                      : "border-grid text-muted-foreground hover:border-signal/60 hover:text-foreground"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </Field>
        </div>

        {/* Description */}
        <div className="border border-grid bg-surface/40 p-5">
          <Field label="Public description" hint="Shown on the agent's card in the marketplace feed">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="What does this agent do, in one or two sentences?"
              className="input resize-none"
            />
          </Field>
        </div>

        {/* Personality / system prompt */}
        <div className="border border-grid bg-surface/40 p-5">
          <Field
            label="Personality & instructions"
            hint="This is the agent's whole brain — describe its behavior, tone, tools it should reach for, and limits it must respect."
          >
            <textarea
              value={personality}
              onChange={(e) => setPersonality(e.target.value)}
              rows={6}
              placeholder={
                "e.g. You are a cautious DeFi yield researcher. Only recommend pools with $1M+ TVL and 30+ days of history. " +
                "Always show APY, TVL, and the top risk factor. Never recommend a pool you can't verify on-chain."
              }
              className="input resize-none font-mono text-xs leading-relaxed"
            />
          </Field>
        </div>

        {/* Model */}
        <div className="border border-grid bg-surface/40 p-5">
          <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Model
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {MODELS.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setModel(m.id)}
                className={`border p-3 text-left transition ${
                  model === m.id ? "border-signal bg-surface/60" : "border-grid hover:border-signal/60"
                }`}
              >
                <div className={`font-display text-sm font-bold ${model === m.id ? "text-signal" : ""}`}>{m.label}</div>
                <div className="mt-1 text-[11px] leading-snug text-muted-foreground">{m.detail}</div>
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          disabled={!canSubmit || submitting}
          onClick={handleSubmit}
          className="inline-flex items-center justify-center gap-2 bg-signal px-5 py-3.5 font-mono text-sm font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Rocket size={16} />
          {submitting ? "Launching…" : "Launch Agent"}
        </button>
        <p className="text-center text-[11px] text-muted-foreground">
          This is a first-pass preview flow — agents created here aren't wired to a live backend yet.
        </p>
      </div>

      <style jsx global>{`
        .input {
          width: 100%;
          background: transparent;
          border: 1px solid var(--grid);
          padding: 0.55rem 0.7rem;
          font-size: 0.8rem;
          color: var(--foreground);
        }
        .input::placeholder {
          color: color-mix(in srgb, var(--muted-foreground) 65%, transparent);
        }
        .input:focus {
          outline: none;
          border-color: var(--signal);
        }
      `}</style>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">{label}</div>
      {children}
      {hint && <div className="mt-1.5 text-[11px] leading-snug text-muted-foreground/80">{hint}</div>}
    </label>
  );
}
