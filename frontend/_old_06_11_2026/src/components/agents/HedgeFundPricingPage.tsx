"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Panel } from "@/components/AppShell";
import { fetchHedgeFundFees, type HedgeFundFeeStructure } from "@/lib/hedgeFundClient";
import { HEDGE_FUND } from "@/lib/hedgeFundConfig";

export function HedgeFundPricingPage() {
  const [fees, setFees] = useState<HedgeFundFeeStructure | null>(null);

  useEffect(() => {
    void fetchHedgeFundFees().then(setFees);
  }, []);

  const ex = fees?.example_100k_12mo;

  return (
    <div className="space-y-8">
      <div className="border border-grid bg-surface/40 px-6 py-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">Fee schedule</p>
        <h2 className="mt-2 text-2xl font-semibold text-foreground">1/10 Model</h2>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          BIT Agents Hedge Fund uses a simplified fee stack — half the traditional 2/20: 1% management
          and 10% performance.
        </p>
        <Link
          href="/agents/hedge-fund"
          className="mt-4 inline-block font-mono text-xs uppercase tracking-wider text-signal underline"
        >
          ← Back to Hedge Fund Agent
        </Link>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Management fee">
          <p className="text-3xl font-semibold tabular-nums text-foreground">
            {fees?.management_fee_annual_pct ?? HEDGE_FUND.managementFeePct}%
          </p>
          <p className="mt-2 text-sm text-muted-foreground">Annual fee on assets under management (AUM).</p>
          <p className="mt-4 font-mono text-xs text-muted-foreground">
            Traditional funds: {fees?.traditional_2_20.management_pct ?? 2}% · You save 1% per year on AUM.
          </p>
        </Panel>

        <Panel title="Performance fee">
          <p className="text-3xl font-semibold tabular-nums text-foreground">
            {fees?.performance_fee_pct ?? HEDGE_FUND.performanceFeePct}%
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Charged on net profits above the high-water mark only.
          </p>
          <p className="mt-4 font-mono text-xs text-muted-foreground">
            Traditional funds: {fees?.traditional_2_20.performance_pct ?? 20}% · You keep an extra 10% of gains.
          </p>
        </Panel>
      </div>

      {ex && (
        <Panel title="Example — $100,000 AUM, $15,000 profit (12 months)">
          <dl className="grid gap-3 font-mono text-sm md:grid-cols-2">
            <div className="flex justify-between border-b border-grid py-2">
              <dt className="text-muted-foreground">Management (1%)</dt>
              <dd className="tabular-nums">${ex.management_fee_usd.toLocaleString()}</dd>
            </div>
            <div className="flex justify-between border-b border-grid py-2">
              <dt className="text-muted-foreground">Performance (10%)</dt>
              <dd className="tabular-nums">${ex.performance_fee_usd.toLocaleString()}</dd>
            </div>
            <div className="flex justify-between border-b border-grid py-2">
              <dt className="text-muted-foreground">Total fees</dt>
              <dd className="tabular-nums text-warn">${ex.total_fees_usd.toLocaleString()}</dd>
            </div>
            <div className="flex justify-between border-b border-grid py-2">
              <dt className="text-muted-foreground">Net profit after fees</dt>
              <dd className="tabular-nums text-signal">${ex.net_profit_after_fees_usd.toLocaleString()}</dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-muted-foreground">
            Under 2/20, performance fee alone would be $3,000 (20% of $15k) vs $1,500 at 10%.
          </p>
        </Panel>
      )}

      <Panel title="How it works">
        <ul className="list-inside list-disc space-y-2 text-sm text-muted-foreground">
          <li>Deterministic quant/value analysts score each Solana token from on-chain data.</li>
          <li>Risk engine enforces max position sizes and liquidity minimums in code.</li>
          <li>LLM macro layer synthesizes a portfolio thesis — never overrides hard risk limits.</li>
          <li>MVP: analysis and allocation suggestions only; execution via DCA Agent / Jupiter separately.</li>
        </ul>
      </Panel>

      <p className="font-mono text-xs text-muted-foreground">
        Not financial advice. Past backtests do not guarantee future results.
      </p>
    </div>
  );
}
