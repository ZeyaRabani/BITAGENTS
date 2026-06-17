"use client";

import {
  DCA_PLAN_STATUS_LABELS,
  EXECUTION_MODE_LABELS,
  dcaPlanProgress,
  formatInterval,
  makeExplorerAddressUrl,
  makeExplorerTxUrl,
  shortAddress,
  type DcaExecution,
  type DcaPlan
} from "@bitagents/shared";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { VersionedTransaction } from "@solana/web3.js";
import { ExternalLink, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ActionButton, Tag } from "@/components/primitives";
import { cancelDcaPlan, getDcaPlan } from "@/lib/dca";
import { cn } from "@/lib/utils";

const ACTIVE_STATUSES = new Set(["active", "creating"]);

function trim(value: number, max = 6): string {
  if (!Number.isFinite(value)) return "0";
  return value.toFixed(max).replace(/\.?0+$/, "");
}

function StatusTag({ status }: { status: DcaPlan["status"] }) {
  const tone =
    status === "active"
      ? "border-success/40 text-success"
      : status === "failed"
        ? "border-danger/40 text-danger"
        : status === "completed"
          ? "border-signal/40 text-signal"
          : "text-muted-foreground";
  return <Tag className={tone}>{DCA_PLAN_STATUS_LABELS[status]}</Tag>;
}

export function PlanCard({
  planId,
  initialPlan,
  onChange
}: {
  planId: string;
  initialPlan?: DcaPlan;
  onChange?: (plan: DcaPlan) => void;
}) {
  const [plan, setPlan] = useState<DcaPlan | null>(initialPlan ?? null);
  const [executions, setExecutions] = useState<DcaExecution[]>([]);
  const [cancelling, setCancelling] = useState(false);
  const { connection } = useConnection();
  const { signTransaction } = useWallet();
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const refresh = useCallback(async () => {
    try {
      const detail = await getDcaPlan(planId);
      setPlan(detail.plan);
      setExecutions(detail.executions);
      onChangeRef.current?.(detail.plan);
    } catch {
      // transient — keep last known state
    }
  }, [planId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while the plan is still running so Devnet Demo executions stream in.
  useEffect(() => {
    if (plan && !ACTIVE_STATUSES.has(plan.status)) return;
    const timer = setInterval(() => void refresh(), 4000);
    return () => clearInterval(timer);
  }, [plan, refresh]);

  const cancel = useCallback(async () => {
    if (!plan) return;
    setCancelling(true);
    try {
      const result = await cancelDcaPlan(plan.id);
      if (result.ok && "needsSignature" in result && result.needsSignature) {
        if (!signTransaction) {
          toast.error("Connect your wallet to sign the cancellation.");
          return;
        }
        const bytes = Uint8Array.from(Buffer.from(result.transaction, "base64"));
        const tx = VersionedTransaction.deserialize(bytes);
        const signed = await signTransaction(tx);
        const signature = await connection.sendRawTransaction(signed.serialize());
        await connection.confirmTransaction(signature, "confirmed");
        await cancelDcaPlan(plan.id, { signature });
        toast.success("Cancellation submitted.");
      } else if (result.ok) {
        toast.success("Plan cancelled.");
      } else {
        toast.error(result.error);
      }
      await refresh();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setCancelling(false);
    }
  }, [plan, signTransaction, connection, refresh]);

  if (!plan) {
    return (
      <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <Loader2 className="animate-spin" size={14} /> loading plan…
      </div>
    );
  }

  const progress = dcaPlanProgress(plan);
  const canCancel = plan.status === "active" || plan.status === "creating";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-sm font-semibold text-foreground">
            {trim(plan.perOrderAmountUi)} {plan.inputSymbol} → {plan.outputSymbol}
          </span>
          <StatusTag status={plan.status} />
        </div>
        <Tag>{EXECUTION_MODE_LABELS[plan.executionMode]}</Tag>
      </div>

      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="h-full bg-signal transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[11px] sm:grid-cols-3">
        <Meta label="Buys done" value={`${plan.ordersExecuted}/${plan.numberOfOrders}`} />
        <Meta label="Spent" value={`${trim(plan.spentInputUi)} ${plan.inputSymbol}`} />
        <Meta label="Received" value={`${trim(plan.receivedOutputUi)} ${plan.outputSymbol}`} />
        <Meta label="Every" value={formatInterval(plan.intervalSeconds)} />
        <Meta
          label="Next buy"
          value={plan.nextExecutionAt ? new Date(plan.nextExecutionAt).toLocaleTimeString() : "—"}
        />
        <Meta label="Budget" value={`${trim(plan.totalInputAmountUi)} ${plan.inputSymbol}`} />
      </div>

      {plan.jupiterOrderAccount ? (
        <a
          href={makeExplorerAddressUrl(plan.jupiterOrderAccount, "mainnet")}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 font-mono text-[11px] text-signal hover:text-signal-soft"
        >
          <ExternalLink size={12} /> order {shortAddress(plan.jupiterOrderAccount)}
        </a>
      ) : null}
      {plan.createSignature ? (
        <a
          href={makeExplorerTxUrl(plan.createSignature, "mainnet")}
          target="_blank"
          rel="noreferrer"
          className="ml-3 inline-flex items-center gap-1.5 font-mono text-[11px] text-signal hover:text-signal-soft"
        >
          <ExternalLink size={12} /> create tx
        </a>
      ) : null}

      {plan.error ? <p className="border-l-2 border-danger pl-3 font-mono text-xs text-danger">{plan.error}</p> : null}

      {executions.length ? (
        <div className="space-y-1.5">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            execution history
          </p>
          <div className="max-h-44 space-y-1 overflow-auto">
            {executions.map((execution) => (
              <ExecutionRow key={execution.id} execution={execution} />
            ))}
          </div>
        </div>
      ) : null}

      {canCancel ? (
        <ActionButton variant="outline" size="sm" onClick={cancel} disabled={cancelling}>
          {cancelling ? <Loader2 className="animate-spin" size={13} /> : <X size={13} />}
          Cancel plan
        </ActionButton>
      ) : null}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="text-foreground">{value}</p>
    </div>
  );
}

function ExecutionRow({ execution }: { execution: DcaExecution }) {
  const explorer = execution.signature && !execution.simulated ? makeExplorerTxUrl(execution.signature, execution.network) : null;
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-2 border border-border/60 bg-surface-2 px-2.5 py-1.5 font-mono text-[11px]",
        execution.status === "failed" && "border-danger/40"
      )}
    >
      <span className="text-muted-foreground">#{execution.orderIndex + 1}</span>
      <span className="text-foreground">
        {trim(execution.inputAmountUi, 4)} → {execution.outputAmountUi != null ? trim(execution.outputAmountUi, 4) : "—"}
      </span>
      <span className={execution.status === "success" ? "text-success" : execution.status === "failed" ? "text-danger" : "text-muted-foreground"}>
        {execution.status}
      </span>
      {explorer ? (
        <a href={explorer} target="_blank" rel="noreferrer" className="text-signal hover:text-signal-soft">
          tx
        </a>
      ) : (
        <span className="text-muted-foreground/60" title={execution.note}>
          sim
        </span>
      )}
    </div>
  );
}
