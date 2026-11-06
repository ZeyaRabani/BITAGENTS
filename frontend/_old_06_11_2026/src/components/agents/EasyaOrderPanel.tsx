"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Panel } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  cancelEasyaOrder,
  fetchEasyaOrderExecutions,
  fetchEasyaOrders,
  orderExplorerUrl,
  updateEasyaLimitOrder,
  type EasyaOrderExecution,
  type EasyaOrderSummary,
} from "@/lib/easyaOrderClient";

const SECTION_MAX_HEIGHT = "max-h-[280px]";
const MARKET_METRICS_REFRESH_MS = 15 * 60 * 1000;

type OrderStatusFilter = "all" | "active" | "filled" | "completed" | "cancelled" | "failed";

function shortMint(mint?: string | null) {
  if (!mint) return "-";
  if (mint.length <= 12) return mint;
  return `${mint.slice(0, 4)}…${mint.slice(-4)}`;
}

function formatTime(iso?: string | null) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatUsd(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "n/a";
  if (value < 0.0001) return `$${value.toExponential(2)}`;
  if (value < 1) return `$${value.toFixed(6)}`;
  return `$${value.toFixed(4)}`;
}

function formatMcap(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatCheckSeconds(seconds?: number) {
  const value = seconds ?? 900;
  if (value < 60) return `every ${value}s`;
  if (value % 60 === 0) {
    const mins = value / 60;
    return mins === 1 ? "every 1 min" : `every ${mins} min`;
  }
  return `every ${value}s`;
}

function statusClass(status: string) {
  if (status === "active") return "text-signal";
  if (status === "pending") return "text-warn";
  if (status === "filled" || status === "completed") return "text-signal";
  if (status === "failed") return "text-warn";
  if (status === "cancelled") return "text-muted-foreground";
  return "text-foreground";
}

function orderTitle(order: EasyaOrderSummary) {
  if (order.order_type === "threshold" || order.recurring) {
    return `Threshold buy · ${order.output_token}`;
  }
  if (order.order_type === "limit") {
    return `Limit buy · ${order.output_token}`;
  }
  return `Market buy · ${order.output_token}`;
}

function formatExecutions(order: EasyaOrderSummary) {
  const done = order.executions ?? 0;
  const max = order.max_executions;
  if (order.order_type === "threshold" || order.recurring) {
    if (max != null) return `${done} / ${max}`;
    return `${done} / until SOL out`;
  }
  return `${done} / 1`;
}

function hasOrderHistory(order: EasyaOrderSummary) {
  return (
    Boolean(order.signature) ||
    (order.executions ?? 0) > 0 ||
    order.status === "filled" ||
    order.status === "completed"
  );
}

function normalizedOrderStatus(order: EasyaOrderSummary) {
  return (order.status || "").trim().toLowerCase();
}

function isLimitOrThreshold(order: EasyaOrderSummary) {
  const type = (order.order_type || "").trim().toLowerCase();
  return type === "limit" || type === "threshold" || Boolean(order.recurring);
}

function OrderExecutionsDialog({
  open,
  onOpenChange,
  order,
  authToken,
  cluster,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  order: EasyaOrderSummary;
  authToken: string;
  cluster?: string;
}) {
  const [executions, setExecutions] = useState<EasyaOrderExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchEasyaOrderExecutions(order.id, authToken)
      .then((data) => {
        if (cancelled) return;
        setExecutions(data?.executions ?? []);
      })
      .catch((err) => {
        if (cancelled) return;
        setExecutions([]);
        setError(err instanceof Error ? err.message : "Could not load transaction history.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, order.id, authToken]);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-h-[85vh] max-w-lg overflow-hidden">
        <AlertDialogHeader>
          <AlertDialogTitle>Transaction history</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-1 font-mono text-[11px] text-muted-foreground">
              <p>
                {orderTitle(order)} · ID <code className="text-foreground">{order.id}</code>
              </p>
              <p>
                {formatExecutions(order)} buys · {(order.total_spent ?? 0).toLocaleString()}{" "}
                {order.input_token} spent
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="max-h-[50vh] space-y-2 overflow-y-auto pr-1">
          {loading && (
            <p className="font-mono text-[11px] text-muted-foreground">Loading transactions…</p>
          )}
          {error && <p className="font-mono text-[11px] text-warn">{error}</p>}
          {!loading && !error && executions.length === 0 && (
            <p className="font-mono text-[11px] text-muted-foreground">
              No fills recorded yet for this order.
            </p>
          )}
          {executions.map((row, index) => {
            const href = orderExplorerUrl(row.signature, cluster);
            const ok = row.status === "success";
            return (
              <div key={row.id ?? `${row.signature ?? "row"}-${index}`} className="border border-grid bg-background/60 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-foreground">
                    Buy #{executions.length - index}
                  </span>
                  <span
                    className={`font-mono text-[10px] uppercase ${ok ? "text-signal" : "text-warn"}`}
                  >
                    {row.error_message ? "failed" : row.status ?? "unknown"}
                  </span>
                </div>
                <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {formatTime(row.executed_at)} · {row.amount_input} {order.input_token}
                  {row.platform_fee != null && row.platform_fee > 0 && (
                    <> · fee {row.platform_fee} {order.input_token}</>
                  )}
                  {row.price_usd != null && <> · price {formatUsd(row.price_usd)}</>}
                  {row.output_amount != null && (
                    <> → {row.output_amount} {order.output_token}</>
                  )}
                </div>
                {row.error_message && (
                  <p className="mt-1 font-mono text-[10px] text-warn">{row.error_message}</p>
                )}
                {href && row.signature && (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block font-mono text-[10px] text-signal hover:underline"
                  >
                    {row.signature.slice(0, 8)}…{row.signature.slice(-8)} ↗ Explorer
                  </a>
                )}
              </div>
            );
          })}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Close</AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function CollapsibleSection({
  title,
  count,
  defaultOpen = true,
  headerExtra,
  maxHeight = SECTION_MAX_HEIGHT,
  children,
}: {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  headerExtra?: ReactNode;
  maxHeight?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Panel
      title={`${title}${count != null ? ` (${count})` : ""}`}
      action={
        <div className="flex items-center gap-2">
          {headerExtra}
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground transition hover:text-signal"
            aria-expanded={open}
          >
            {open ? "Hide" : "Show"}
            <ChevronDown
              size={14}
              className={`transition-transform ${open ? "rotate-180" : ""}`}
            />
          </button>
        </div>
      }
    >
      {open ? (
        <div className={`${maxHeight} overflow-y-auto pr-1`}>{children}</div>
      ) : (
        <p className="font-mono text-[10px] text-muted-foreground">Section collapsed.</p>
      )}
    </Panel>
  );
}

function LimitOrderRow({
  order,
  authToken,
  busy,
  onUpdated,
  cluster,
}: {
  order: EasyaOrderSummary;
  authToken: string;
  busy: boolean;
  onUpdated: () => void;
  cluster?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [amountSol, setAmountSol] = useState(String(order.amount_input));
  const [limitPrice, setLimitPrice] = useState(
    order.limit_price_usd != null ? String(order.limit_price_usd) : ""
  );
  const [limitMcap, setLimitMcap] = useState(
    order.limit_market_cap_usd != null ? String(order.limit_market_cap_usd) : ""
  );
  const [stopMcap, setStopMcap] = useState(
    order.stop_market_cap_usd != null ? String(order.stop_market_cap_usd) : ""
  );
  const [slippageBps, setSlippageBps] = useState(String(order.slippage_bps ?? 100));
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const status = normalizedOrderStatus(order);
  const canEdit = isLimitOrThreshold(order) && status === "active";
  const canCancel = status === "active" || status === "pending";
  const removeLabel =
    order.order_type === "threshold" || order.recurring ? "Remove order" : "Remove limit order";

  const actionButtons = (
    <div className="flex flex-wrap gap-2">
      {canEdit && !editing && (
        <button
          type="button"
          disabled={busy || actionBusy}
          onClick={() => {
            setEditing(true);
            setActionError(null);
          }}
          className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-signal disabled:opacity-40"
        >
          Edit
        </button>
      )}
      {editing && (
        <>
          <button
            type="button"
            disabled={busy || actionBusy}
            onClick={() => void runSave()}
            className="border border-signal px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-signal transition hover:bg-signal/10 disabled:opacity-40"
          >
            {actionBusy ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            disabled={actionBusy}
            onClick={() => {
              setEditing(false);
              setAmountSol(String(order.amount_input));
              setLimitPrice(order.limit_price_usd != null ? String(order.limit_price_usd) : "");
              setLimitMcap(order.limit_market_cap_usd != null ? String(order.limit_market_cap_usd) : "");
              setStopMcap(order.stop_market_cap_usd != null ? String(order.stop_market_cap_usd) : "");
              setSlippageBps(String(order.slippage_bps ?? 100));
              setActionError(null);
            }}
            className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:text-foreground disabled:opacity-40"
          >
            Cancel edit
          </button>
        </>
      )}
      {canCancel && !editing && (
        <button
          type="button"
          disabled={busy || actionBusy}
          onClick={() => setConfirmCancel(true)}
          className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-warn hover:text-warn disabled:opacity-40"
        >
          {removeLabel}
        </button>
      )}
      {hasOrderHistory(order) && !editing && (
        <button
          type="button"
          disabled={busy || actionBusy}
          onClick={() => setHistoryOpen(true)}
          className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-signal disabled:opacity-40"
        >
          Tx history
        </button>
      )}
    </div>
  );

  async function runCancel() {
    setActionBusy(true);
    setActionError(null);
    const result = await cancelEasyaOrder(order.id, authToken);
    setActionBusy(false);
    setConfirmCancel(false);
    if (result.error) {
      setActionError(result.error);
      return;
    }
    onUpdated();
  }

  async function runSave() {
    const parsedAmount = Number(amountSol);
    const parsedLimit = limitPrice.trim() ? Number(limitPrice) : null;
    const parsedMcap = limitMcap.trim() ? Number(limitMcap) : null;
    const parsedStopMcap = stopMcap.trim() ? Number(stopMcap) : null;
    const parsedSlippage = Number(slippageBps);

    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setActionError("Enter a valid SOL amount.");
      return;
    }
    if (parsedLimit != null && (!Number.isFinite(parsedLimit) || parsedLimit <= 0)) {
      setActionError("Enter a valid limit price or leave blank.");
      return;
    }
    if (parsedMcap != null && (!Number.isFinite(parsedMcap) || parsedMcap <= 0)) {
      setActionError("Enter a valid market cap limit or leave blank.");
      return;
    }
    if (parsedLimit == null && parsedMcap == null) {
      setActionError("Set at least one buy trigger: limit price and/or market cap.");
      return;
    }
    if (parsedStopMcap != null && (!Number.isFinite(parsedStopMcap) || parsedStopMcap <= 0)) {
      setActionError("Enter a valid stop market cap or leave blank.");
      return;
    }
    if (!Number.isFinite(parsedSlippage) || parsedSlippage < 1 || parsedSlippage > 5000) {
      setActionError("Slippage must be between 1 and 5000 bps.");
      return;
    }

    setActionBusy(true);
    setActionError(null);
    const result = await updateEasyaLimitOrder(
      order.id,
      {
        amount_sol: parsedAmount,
        limit_price_usd: parsedLimit,
        limit_market_cap_usd: parsedMcap,
        stop_market_cap_usd:
          order.order_type === "threshold" ? parsedStopMcap : undefined,
        slippage_bps: Math.round(parsedSlippage),
      },
      authToken
    );
    setActionBusy(false);
    if (result.error) {
      setActionError(result.error);
      return;
    }
    setEditing(false);
    onUpdated();
  }

  const priceDistance =
    order.limit_price_usd != null && order.current_price_usd != null
      ? order.current_price_usd <= order.limit_price_usd
        ? "price ready"
        : `${(((order.current_price_usd - order.limit_price_usd) / order.limit_price_usd) * 100).toFixed(1)}% above price limit`
      : null;
  const mcapDistance =
    order.limit_market_cap_usd != null && order.current_market_cap_usd != null
      ? order.current_market_cap_usd <= order.limit_market_cap_usd
        ? "mcap ready"
        : `${(((order.current_market_cap_usd - order.limit_market_cap_usd) / order.limit_market_cap_usd) * 100).toFixed(1)}% above mcap limit`
      : null;

  return (
    <div className="border border-grid bg-background/60 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs text-foreground">{orderTitle(order)}</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            ID `{order.id}` · {order.pair}
          </div>
        </div>
        <span className={`font-mono text-[10px] uppercase tracking-[0.16em] ${statusClass(order.status)}`}>
          {order.status}
        </span>
      </div>

      {(canEdit || canCancel || hasOrderHistory(order)) && (
        <div className="mt-3 border-b border-grid pb-3">{actionButtons}</div>
      )}

      {!editing ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[10px] text-muted-foreground">
          <div>
            <dt>Executions</dt>
            <dd className="text-foreground">{formatExecutions(order)}</dd>
          </div>
          <div>
            <dt>Total spent</dt>
            <dd className="text-foreground">
              {(order.total_spent ?? 0).toLocaleString()} {order.input_token}
            </dd>
          </div>
          {(order.order_type === "threshold" || order.recurring) && (
            <div>
              <dt>Check interval</dt>
              <dd className="text-foreground">
                {formatCheckSeconds(order.check_interval_seconds)}
              </dd>
            </div>
          )}
          <div>
            <dt>Spend per buy</dt>
            <dd className="text-foreground">
              {order.amount_input} {order.input_token}
              <span className="block text-[9px] text-muted-foreground">+ 0.1% fee on fill</span>
            </dd>
          </div>
          <div>
            <dt>Limit price</dt>
            <dd className="text-foreground">
              {order.limit_price_usd != null ? formatUsd(order.limit_price_usd) : "-"}
            </dd>
          </div>
          <div>
            <dt>Limit market cap</dt>
            <dd className="text-foreground">
              {order.limit_market_cap_usd != null ? formatMcap(order.limit_market_cap_usd) : "-"}
            </dd>
          </div>
          <div>
            <dt>Current price</dt>
            <dd className="text-foreground">{formatUsd(order.current_price_usd)}</dd>
          </div>
          <div>
            <dt>Current market cap</dt>
            <dd className="text-foreground">{formatMcap(order.current_market_cap_usd)}</dd>
          </div>
          <div className="col-span-2">
            <dt>Buy trigger</dt>
            <dd className="text-foreground">
              {order.trigger_summary ?? (order.limit_price_usd != null ? "price ≤ limit" : "market cap ≤ limit")}
            </dd>
          </div>
          {(order.order_type === "threshold" || order.recurring) && order.stop_summary && (
            <div className="col-span-2">
              <dt>Stop rule</dt>
              <dd className="text-foreground">{order.stop_summary}</dd>
            </div>
          )}
          {(priceDistance || mcapDistance) && (
            <div className="col-span-2">
              <dt>Fill status</dt>
              <dd>
                {priceDistance && (
                  <span className={priceDistance === "price ready" ? "text-signal" : "text-warn"}>
                    {priceDistance}
                  </span>
                )}
                {priceDistance && mcapDistance && " · "}
                {mcapDistance && (
                  <span className={mcapDistance === "mcap ready" ? "text-signal" : "text-warn"}>
                    {mcapDistance}
                  </span>
                )}
              </dd>
            </div>
          )}
          <div>
            <dt>Slippage</dt>
            <dd className="text-foreground">{order.slippage_bps ?? 100} bps</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd className="text-foreground">{formatTime(order.created_at)}</dd>
          </div>
          <div className="col-span-2">
            <dt>Mints</dt>
            <dd className="break-all text-foreground">
              in {shortMint(order.input_mint)} → out {shortMint(order.output_mint)}
            </dd>
          </div>
        </dl>
      ) : (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            SOL amount
            <input
              type="number"
              min="0"
              step="any"
              value={amountSol}
              onChange={(e) => setAmountSol(e.target.value)}
              disabled={actionBusy}
              className="border border-grid bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-signal"
            />
          </label>
          <label className="grid gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Limit price USD
            <input
              type="number"
              min="0"
              step="any"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              disabled={actionBusy}
              placeholder="optional"
              className="border border-grid bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-signal"
            />
          </label>
          <label className="grid gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Limit market cap USD
            <input
              type="number"
              min="0"
              step="any"
              value={limitMcap}
              onChange={(e) => setLimitMcap(e.target.value)}
              disabled={actionBusy}
              placeholder="optional"
              className="border border-grid bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-signal"
            />
          </label>
          {(order.order_type === "threshold" || order.recurring) && (
            <label className="grid gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              Stop market cap USD
              <input
                type="number"
                min="0"
                step="any"
                value={stopMcap}
                onChange={(e) => setStopMcap(e.target.value)}
                disabled={actionBusy}
                placeholder="optional"
                className="border border-grid bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-signal"
              />
            </label>
          )}
          <label className="grid gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Slippage bps
            <input
              type="number"
              min="1"
              max="5000"
              step="1"
              value={slippageBps}
              onChange={(e) => setSlippageBps(e.target.value)}
              disabled={actionBusy}
              className="border border-grid bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-signal"
            />
          </label>
        </div>
      )}

      {actionError && <p className="mt-2 font-mono text-[10px] text-warn">{actionError}</p>}

      <OrderExecutionsDialog
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        order={order}
        authToken={authToken}
        cluster={cluster}
      />

      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        title={removeLabel}
        description={
          <p>
            {removeLabel} for{" "}
            <strong className="text-foreground">{order.output_token}</strong> (ID `{order.id}`)?
            No further buys will run and reserved SOL will be released. This cannot be undone.
          </p>
        }
        confirmLabel={removeLabel}
        cancelLabel="Keep order"
        busy={actionBusy}
        onConfirm={() => void runCancel()}
      />
    </div>
  );
}

function MarketOrderRow({
  order,
  cluster,
  authToken,
}: {
  order: EasyaOrderSummary;
  cluster?: string;
  authToken: string;
}) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const href = orderExplorerUrl(order.signature, cluster);
  const ok = order.status === "filled" && !order.error_message;

  return (
    <div className="border border-grid bg-background/40 px-3 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs text-foreground">Market buy · {order.output_token}</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            ID `{order.id}` · {order.pair}
          </div>
        </div>
        <span className={`font-mono text-[10px] uppercase ${ok ? "text-signal" : statusClass(order.status)}`}>
          {order.error_message ? "failed" : order.status}
        </span>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[10px] text-muted-foreground">
        <div>
          <dt>Spent</dt>
          <dd className="text-foreground">
            {order.amount_input} {order.input_token}
            {order.platform_fee != null && order.platform_fee > 0 && (
              <span className="block text-[9px] text-muted-foreground">
                incl. {order.platform_fee} fee
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd className="text-foreground">
            {order.output_amount != null ? `${order.output_amount} ${order.output_token}` : "-"}
          </dd>
        </div>
        <div>
          <dt>Current price</dt>
          <dd className="text-foreground">{formatUsd(order.current_price_usd)}</dd>
        </div>
        <div>
          <dt>Current market cap</dt>
          <dd className="text-foreground">{formatMcap(order.current_market_cap_usd)}</dd>
        </div>
        <div className="col-span-2">
          <dt>Executed</dt>
          <dd className="text-foreground">{formatTime(order.filled_at ?? order.created_at)}</dd>
        </div>
        {order.metrics_cached_at && (
          <div className="col-span-2">
            <dt>Token prices cached</dt>
            <dd className="text-foreground">{formatTime(order.metrics_cached_at)}</dd>
          </div>
        )}
      </dl>

      {order.error_message && (
        <p className="mt-2 font-mono text-[10px] text-warn">{order.error_message}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {href && order.signature && (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-signal transition hover:bg-signal/10"
          >
            Explorer ↗
          </a>
        )}
        {hasOrderHistory(order) && (
          <button
            type="button"
            onClick={() => setHistoryOpen(true)}
            className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-signal"
          >
            Tx history
          </button>
        )}
      </div>

      <OrderExecutionsDialog
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        order={order}
        authToken={authToken}
        cluster={cluster}
      />
    </div>
  );
}

export function EasyaOrderPanel({
  authToken,
  cluster,
  refreshTick = 0,
}: {
  authToken?: string | null;
  cluster?: string;
  refreshTick?: number;
}) {
  const [orders, setOrders] = useState<EasyaOrderSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [marketLoading, setMarketLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [marketMetricsNote, setMarketMetricsNote] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<OrderStatusFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const reload = useCallback(async () => {
    if (!authToken) {
      setOrders([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEasyaOrders(authToken);
      setOrders(data?.orders ?? []);
      const firstMarket = data?.orders?.find((order) => order.order_type === "market");
      if (firstMarket?.metrics_cached_at) {
        setMarketMetricsNote(`Token prices cached at ${formatTime(firstMarket.metrics_cached_at)}`);
      }
    } catch (err) {
      setOrders([]);
      setError(err instanceof Error ? err.message : "Could not load trading orders.");
    } finally {
      setLoading(false);
    }
  }, [authToken]);

  const reloadMarket = useCallback(
    async (forceRefresh = false) => {
      if (!authToken) return;
      setMarketLoading(true);
      try {
        const data = await fetchEasyaOrders(authToken, { refreshMetrics: forceRefresh });
        setOrders(data?.orders ?? []);
        const ttlMins = Math.round((data?.metrics_cache_ttl_seconds ?? 900) / 60);
        const firstMarket = data?.orders?.find((order) => order.order_type === "market");
        if (firstMarket?.metrics_cached_at) {
          setMarketMetricsNote(
            forceRefresh
              ? `Token prices refreshed at ${formatTime(firstMarket.metrics_cached_at)}`
              : `Token prices cached at ${formatTime(firstMarket.metrics_cached_at)} (auto-refresh every ${ttlMins} min)`
          );
        } else if (forceRefresh) {
          setMarketMetricsNote("Orders refreshed.");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not refresh market orders.");
      } finally {
        setMarketLoading(false);
      }
    },
    [authToken]
  );

  useEffect(() => {
    void reload();
  }, [reload, refreshTick]);

  useEffect(() => {
    if (!authToken) return;
    const interval = window.setInterval(() => {
      void reload();
    }, 30_000);
    return () => window.clearInterval(interval);
  }, [authToken, reload]);

  useEffect(() => {
    if (!authToken) return;
    const interval = window.setInterval(() => {
      void reloadMarket(false);
    }, MARKET_METRICS_REFRESH_MS);
    return () => window.clearInterval(interval);
  }, [authToken, reloadMarket]);

  const limitOrders = useMemo(
    () => orders.filter((order) => order.order_type === "limit" || order.order_type === "threshold"),
    [orders]
  );

  const marketOrders = useMemo(
    () => orders.filter((order) => order.order_type === "market"),
    [orders]
  );

  const filteredLimitOrders = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return limitOrders.filter((order) => {
      if (statusFilter === "active") {
        if (order.status !== "active" && order.status !== "pending") return false;
      } else if (statusFilter !== "all" && order.status !== statusFilter) {
        return false;
      }
      if (!query) return true;
      return (
        order.output_token.toLowerCase().includes(query) ||
        order.pair.toLowerCase().includes(query) ||
        order.id.toLowerCase().includes(query) ||
        (order.output_mint ?? "").toLowerCase().includes(query)
      );
    });
  }, [limitOrders, statusFilter, searchQuery]);

  if (!authToken) {
    return (
      <CollapsibleSection title="Your limit orders" defaultOpen>
        <p className="font-mono text-xs text-muted-foreground">
          Sign in with your wallet to view and manage limit orders here — no need to ask the agent
          to list them.
        </p>
      </CollapsibleSection>
    );
  }

  return (
    <div className="space-y-6">
      <CollapsibleSection
        title="Your limit orders"
        count={filteredLimitOrders.length}
        defaultOpen
        maxHeight="max-h-[420px]"
        headerExtra={
          <button
            type="button"
            onClick={() => void reload()}
            disabled={loading}
            className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground transition hover:text-signal disabled:opacity-40"
          >
            {loading ? "…" : "Refresh"}
          </button>
        }
      >
        {error && <p className="mb-3 font-mono text-[11px] text-warn">{error}</p>}

        <p className="mb-3 text-sm text-muted-foreground">
          Active limit and threshold orders can be <strong className="text-foreground">edited</strong> or{" "}
          <strong className="text-foreground">stopped</strong> anytime. One-time limits check frequently;
          threshold orders check EASY Screener every ~15 minutes and buy when your conditions are met
          until SOL runs out (0.1% platform fee per successful buy).
        </p>

        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search token, pair, id, mint…"
            className="flex-1 border border-grid bg-background px-3 py-2 font-mono text-[11px] text-foreground outline-none focus:border-signal"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as OrderStatusFilter)}
            className="border border-grid bg-background px-3 py-2 font-mono text-[11px] uppercase tracking-[0.12em] text-foreground outline-none focus:border-signal"
          >
            <option value="all">All limit orders</option>
            <option value="active">Active only</option>
            <option value="filled">Filled</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        {filteredLimitOrders.length === 0 && !loading && (
          <p className="font-mono text-xs text-muted-foreground">
            {limitOrders.length === 0
              ? "No limit orders yet. Create one via chat, e.g. “Place a limit buy for 0.05 SOL of BITAGENTS at $0.02”."
              : "No orders match your filters."}
          </p>
        )}

        <div className="grid gap-3 lg:grid-cols-2">
          {filteredLimitOrders.map((order) => (
            <LimitOrderRow
              key={order.id}
              order={order}
              authToken={authToken}
              busy={loading}
              onUpdated={() => void reload()}
              cluster={cluster}
            />
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Market orders"
        count={marketOrders.length}
        defaultOpen={false}
        headerExtra={
          <button
            type="button"
            onClick={() => void reloadMarket(true)}
            disabled={marketLoading || loading}
            className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground transition hover:text-signal disabled:opacity-40"
          >
            {marketLoading ? "…" : "Refresh"}
          </button>
        }
      >
        <p className="mb-3 text-sm text-muted-foreground">
          Immediate market buys with current token price and market cap (cached every 15 minutes).
          Use Refresh to fetch the latest EASY Screener data and recent transactions.
        </p>
        {marketMetricsNote && (
          <p className="mb-3 font-mono text-[10px] text-muted-foreground">{marketMetricsNote}</p>
        )}
        {marketOrders.length === 0 && !loading && !marketLoading && (
          <p className="font-mono text-xs text-muted-foreground">
            Immediate market buys appear here after execution.
          </p>
        )}
        <div className="space-y-2">
          {marketOrders.map((order) => (
            <MarketOrderRow
              key={order.id}
              order={order}
              authToken={authToken}
              cluster={cluster}
            />
          ))}
        </div>
      </CollapsibleSection>
    </div>
  );
}
