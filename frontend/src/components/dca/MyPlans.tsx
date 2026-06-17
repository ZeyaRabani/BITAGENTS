"use client";

import type { DcaPlan } from "@bitagents/shared";
import { Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ActionButton, LinkButton, Panel } from "@/components/primitives";
import { PlanCard } from "@/components/dca/PlanCard";
import { useDcaWallet } from "@/components/dca/useDcaWallet";
import { listDcaPlans } from "@/lib/dca";

export function MyPlans() {
  const wallet = useDcaWallet();
  const [plans, setPlans] = useState<DcaPlan[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!wallet.address) return;
    setLoading(true);
    try {
      const result = await listDcaPlans(wallet.address);
      setPlans(result);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [wallet.address]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!wallet.address || plans === null) {
    return (
      <div className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
        <Loader2 className="animate-spin" size={15} /> loading plans…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-xs text-muted-foreground">
          {wallet.connected ? "Connected wallet" : "Demo wallet"}: {wallet.address.slice(0, 4)}…{wallet.address.slice(-4)}
        </p>
        <ActionButton variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : undefined} /> Refresh
        </ActionButton>
      </div>

      {plans.length === 0 ? (
        <Panel bodyClassName="space-y-3 text-center">
          <p className="font-mono text-sm text-muted-foreground">No DCA plans yet.</p>
          <LinkButton href="/app" variant="primary" size="sm">
            Create your first plan
          </LinkButton>
        </Panel>
      ) : (
        <div className="grid gap-4">
          {plans.map((plan) => (
            <Panel key={plan.id} bodyClassName="space-y-3">
              <PlanCard planId={plan.id} initialPlan={plan} />
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
