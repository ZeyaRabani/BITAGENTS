"use client";

import {
  EXECUTION_MODE_LABELS,
  formatDuration,
  formatInterval,
  networkLabel,
  type DcaPlan
} from "@bitagents/shared";
import { AlertTriangle } from "lucide-react";
import { Tag } from "@/components/primitives";
import { cn } from "@/lib/utils";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-2 last:border-0">
      <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{label}</span>
      <span className="text-right font-mono text-sm text-foreground">{value}</span>
    </div>
  );
}

function trim(value: number, max = 6): string {
  if (!Number.isFinite(value)) return "0";
  const fixed = value.toFixed(max);
  return fixed.replace(/\.?0+$/, "");
}

export function PlanPreview({ plan, className }: { plan: DcaPlan; className?: string }) {
  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Tag className="border-signal/40 text-signal">{EXECUTION_MODE_LABELS[plan.executionMode]}</Tag>
        <Tag>{networkLabel(plan.network)}</Tag>
      </div>

      <div className="pixel-corners border border-border bg-surface-2 px-4 py-2">
        <Row label="Buy token" value={plan.outputSymbol} />
        <Row label="Pay with" value={plan.inputSymbol} />
        <Row label="Per buy" value={`${trim(plan.perOrderAmountUi)} ${plan.inputSymbol}`} />
        <Row label="Total budget" value={`${trim(plan.totalInputAmountUi)} ${plan.inputSymbol}`} />
        <Row label="Number of buys" value={String(plan.numberOfOrders)} />
        <Row label="Every" value={formatInterval(plan.intervalSeconds)} />
        <Row label="Est. duration" value={formatDuration(plan.estimatedDurationSeconds)} />
        <Row label="Max slippage" value={`${(plan.slippageBps / 100).toFixed(2)}%`} />
      </div>

      {plan.warnings.length ? (
        <ul className="space-y-1.5">
          {plan.warnings.map((warning) => (
            <li key={warning} className="flex items-start gap-2 font-mono text-[11px] leading-relaxed text-warn">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
