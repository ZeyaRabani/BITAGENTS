"use client";

import { Panel } from "@/components/AppShell";
import { CODE_BOX, Field } from "@/components/agents/builder/BuilderUi";
import { formatUsd, type BuilderAgent, type BuilderLimits } from "@/lib/builderClient";

export function LimitsPanel({ limits, className }: { limits: BuilderLimits; className?: string }) {
  return (
    <Panel title="Limits" className={className}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Quote">{limits.quote}</Field>
        <Field label="Max per trade">{formatUsd(limits.max_trade_usd)}</Field>
        <Field label="Max per day">{formatUsd(limits.max_daily_usd)}</Field>
        <Field label="Slippage">{limits.slippage_bps} bps</Field>
      </div>
    </Panel>
  );
}

export function StrategyPanel({ agent, className }: { agent: BuilderAgent; className?: string }) {
  const { strategy } = agent.spec;
  const params = strategy.params;
  return (
    <Panel title="Rules" className={className}>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Template">{strategy.template}</Field>
        {params.trigger_symbol != null && (
          <Field label="Trigger">
            {params.trigger_symbol} +{params.trigger_pct}% in {params.window_minutes} min
          </Field>
        )}
        <Field label={params.trigger_symbol != null ? "Buys" : "Symbols"}>{params.symbols?.join(", ") || "-"}</Field>
        <Field label="Per symbol">{formatUsd(params.per_symbol_usd)}</Field>
        {params.buy_threshold != null && <Field label="Buy threshold">{params.buy_threshold}</Field>}
        {params.sell_threshold != null && <Field label="Sell threshold">{params.sell_threshold}</Field>}
        {params.lookback_days != null && <Field label="Lookback">{params.lookback_days} days</Field>}
        <Field label="Check every">{strategy.schedule_minutes} min</Field>
      </div>
    </Panel>
  );
}

/** The composed spec, straight from the agent object. */
export function SpecPanels({ agent }: { agent: BuilderAgent }) {
  const meta = agent.compose_meta;
  const repaired = meta?.repaired_errors ?? [];
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <StrategyPanel agent={agent} className="lg:col-span-2" />
        <LimitsPanel limits={agent.spec.limits} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Brief">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
            {agent.spec.app.brief}
          </p>
        </Panel>
        <Panel title="Skill">
          <pre className={`${CODE_BOX} max-h-80 whitespace-pre-wrap`}>{agent.spec.app.skill}</pre>
        </Panel>
      </div>
      <div className="space-y-2 font-mono text-xs text-muted-foreground">
        {meta && (
          <p>
            composed by {meta.model ?? "-"} in {meta.llm_passes ?? "-"} pass(es)
          </p>
        )}
        {repaired.length > 0 && (
          <div>
            <p className="text-warn">Errors repaired during composition:</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-warn">
              {repaired.map((item, index) => (
                <li key={index} className="break-words">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
        <details className="border border-grid">
          <summary className="cursor-pointer px-3 py-2 uppercase tracking-[0.14em]">Raw spec JSON</summary>
          <pre className={`${CODE_BOX} max-h-96 border-0 border-t`}>{JSON.stringify(agent.spec, null, 2)}</pre>
        </details>
      </div>
    </div>
  );
}
