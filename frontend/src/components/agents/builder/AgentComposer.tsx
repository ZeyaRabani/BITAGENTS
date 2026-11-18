"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell, Panel } from "@/components/AppShell";
import { BuildPanel } from "@/components/agents/builder/BuildPanel";
import {
  BTN_GHOST_PLAIN,
  BTN_PRIMARY,
  Field,
  INPUT,
  Notice,
  WalletGate,
} from "@/components/agents/builder/BuilderUi";
import { SpecPanels } from "@/components/agents/builder/SpecPanels";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import {
  builderApi,
  errorText,
  type BuilderAgent,
  type BuilderTemplate,
} from "@/lib/builderClient";

// Input suggestions only: clicking one fills the textarea.
const EXAMPLE_BRIEFS = [
  "When Nvidia goes up by 2% in 1 hour, buy the Mag7. Put 1 dollar into each stock, at most 7 dollars a day. Check every 5 minutes.",
  "Trade NVIDIA and Tesla for me. Check every hour. Put at most 3 dollars into each when the analysts say buy, and never more than 12 dollars a day.",
  "Watch Apple, Microsoft and Google once a day. Buy 5 dollars of any that the analysts rate a buy, sell when they turn bearish. Cap spending at 20 dollars per day.",
  "Follow Coinbase and MicroStrategy every 30 minutes. Buy 2 dollars on a strong buy signal only, max 10 dollars a day, 0.5% slippage.",
];

const MIN_PROMPT = 20;
const MAX_PROMPT = 2000;

export function AgentComposer() {
  const { wallet, token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [prompt, setPrompt] = useState("");
  const [composing, setComposing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agent, setAgent] = useState<BuilderAgent | null>(null);
  const [templates, setTemplates] = useState<BuilderTemplate[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    builderApi
      .templates()
      .then((data) => {
        if (!cancelled) setTemplates(data.templates ?? []);
      })
      .catch((err) => {
        if (!cancelled) setTemplatesError(errorText(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onAgent = useCallback((next: BuilderAgent) => setAgent(next), []);

  const length = prompt.trim().length;
  const lengthOk = length >= MIN_PROMPT && length <= MAX_PROMPT;

  async function compose(event: FormEvent) {
    event.preventDefault();
    if (!token || !lengthOk) return;
    setComposing(true);
    setError(null);
    try {
      setAgent(await builderApi.compose(prompt.trim(), token));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setComposing(false);
    }
  }

  return (
    <AppShell
      title="Create an agent"
      subtitle="Describe the trading strategy you want. The builder composes a spec from your brief, then deploys it to Aomi, where the BIT Agents agent runs it."
    >
      <div className="space-y-6">
        <WalletGate
          authBusy={authBusy}
          authError={authError}
          isAuthenticated={isAuthenticated}
          purpose="compose and deploy a strategy"
        />

        <div className="grid gap-6 lg:grid-cols-3">
          <Panel title="Brief" className="lg:col-span-2">
            <form onSubmit={compose} className="space-y-4">
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                disabled={composing}
                rows={6}
                maxLength={MAX_PROMPT}
                placeholder="What should it trade, how often should it check, and what are its spending limits?"
                className={`${INPUT} w-full resize-y leading-relaxed`}
              />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  {length} / {MAX_PROMPT} characters · minimum {MIN_PROMPT}
                </span>
                <button type="submit" disabled={!token || !lengthOk || composing} className={BTN_PRIMARY}>
                  {composing ? "Composing…" : agent ? "Compose a new strategy" : "Compose strategy"}
                </button>
              </div>
              {composing && (
                <p className="animate-pulse font-mono text-xs text-muted-foreground">
                  Waiting for the builder to answer. This request usually takes 5 to 30 seconds.
                </p>
              )}
              {error && <Notice tone="warn">{error}</Notice>}
              <div className="space-y-2 border-t border-grid pt-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  Example briefs
                </div>
                {EXAMPLE_BRIEFS.map((brief) => (
                  <button
                    key={brief}
                    type="button"
                    disabled={composing}
                    onClick={() => setPrompt(brief)}
                    className={`${BTN_GHOST_PLAIN} block w-full text-left text-[11px] leading-relaxed`}
                  >
                    {brief}
                  </button>
                ))}
              </div>
            </form>
          </Panel>

          <Panel title="Strategy templates">
            {templatesError && <Notice tone="warn">{templatesError}</Notice>}
            {!templates && !templatesError && (
              <p className="font-mono text-xs text-muted-foreground">Loading templates…</p>
            )}
            {templates && templates.length === 0 && (
              <p className="font-mono text-xs text-muted-foreground">The builder reports no templates.</p>
            )}
            <div className="space-y-4">
              {templates?.map((template) => (
                <div key={template.name}>
                  <div className="font-display text-sm font-bold">{template.title}</div>
                  <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-signal">
                    {template.name}
                  </div>
                  <p className="mt-2 text-sm leading-snug text-muted-foreground">{template.summary}</p>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        {agent && (
          <>
            <Panel title="Composed strategy">
              <h2 className="font-display text-2xl font-bold">{agent.spec.name}</h2>
              <p className="mt-2 text-sm text-muted-foreground">{agent.spec.description}</p>
              <div className="mt-4 grid grid-cols-2 gap-4 border-t border-grid pt-4 sm:grid-cols-4">
                <Field label="Strategy id">{agent.id}</Field>
                <Field label="App name">{agent.build?.hosted?.app ?? agent.app_name}</Field>
                <Field label="Spec sha">{agent.spec_sha}</Field>
                <Field label="Template">{agent.spec.strategy.template}</Field>
              </div>
            </Panel>

            <SpecPanels agent={agent} />

            <BuildPanel agent={agent} token={token} wallet={wallet} onAgent={onAgent} />

            <Link
              href={`/agents/custom/${agent.id}`}
              className="inline-flex items-center gap-3 border border-grid px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal hover:text-signal"
            >
              Open agent console
              <ArrowRight size={14} />
            </Link>
          </>
        )}

        <LegalSignInNotice />
      </div>
    </AppShell>
  );
}
