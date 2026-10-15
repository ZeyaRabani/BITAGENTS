"use client";

import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  addCapitalToYieldPosition,
  unwindYieldPosition,
  yieldInvestTotalCost,
  yieldPlatformFee,
  YIELD_PLATFORM_FEE_RATE,
  type YieldPosition,
} from "@/lib/yieldAgentClient";

function statusClass(status: string) {
  if (status === "active") return "text-signal";
  if (status === "closed") return "text-muted-foreground";
  return "text-warn";
}

function YieldPositionCard({
  position,
  authToken,
  busy,
  onUpdated,
}: {
  position: YieldPosition;
  authToken: string;
  busy: boolean;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [addAmount, setAddAmount] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNote, setActionNote] = useState<string | null>(null);

  const canManage = position.status === "active";
  const parsedAdd = Number(addAmount);
  const feePreview =
    Number.isFinite(parsedAdd) && parsedAdd > 0 ? yieldPlatformFee(parsedAdd) : null;
  const totalPreview =
    Number.isFinite(parsedAdd) && parsedAdd > 0 ? yieldInvestTotalCost(parsedAdd) : null;

  async function runAdd() {
    if (!Number.isFinite(parsedAdd) || parsedAdd <= 0) {
      setActionError("Enter an amount greater than 0 SOL.");
      return;
    }
    setActionBusy(true);
    setActionError(null);
    setActionNote(null);
    try {
      const result = await addCapitalToYieldPosition(position.id, parsedAdd, authToken);
      setActionNote(result.message ?? "Position updated.");
      setEditing(false);
      setAddAmount("");
      onUpdated();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Add capital failed");
    } finally {
      setActionBusy(false);
    }
  }

  async function runRemove() {
    setActionBusy(true);
    setActionError(null);
    setActionNote(null);
    try {
      const result = await unwindYieldPosition(position.id, authToken);
      setConfirmRemove(false);
      setActionNote(result.message ?? "Position removed.");
      onUpdated();
    } catch (err) {
      setConfirmRemove(false);
      setActionError(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <div className="border border-grid bg-background/60 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs text-foreground">{position.protocol_name}</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            ID `{position.id}` · {position.protocol_id}
          </div>
        </div>
        <span
          className={`font-mono text-[10px] uppercase tracking-[0.16em] ${statusClass(position.status)}`}
        >
          {position.status}
        </span>
      </div>

      {!editing ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[10px] text-muted-foreground">
          <div>
            <dt>Position</dt>
            <dd className="text-foreground">
              {position.amount} {position.symbol}
            </dd>
          </div>
          <div>
            <dt>Entry APY</dt>
            <dd className="text-foreground">
              {position.entry_apy != null ? `${position.entry_apy.toFixed(2)}%` : "—"}
            </dd>
          </div>
          <div className="col-span-2">
            <dt>Fee on add</dt>
            <dd className="text-foreground">
              {(YIELD_PLATFORM_FEE_RATE * 100).toFixed(1)}% of added capital (on top)
            </dd>
          </div>
          {position.explorer_url && (
            <div className="col-span-2">
              <dt>Last tx</dt>
              <dd>
                <a
                  href={position.explorer_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-all text-signal hover:underline"
                >
                  {position.explorer_url}
                </a>
              </dd>
            </div>
          )}
        </dl>
      ) : (
        <div className="mt-3 space-y-2">
          <label className="grid gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Add SOL to this position
            <input
              type="number"
              min="0"
              step="any"
              value={addAmount}
              onChange={(e) => setAddAmount(e.target.value)}
              disabled={actionBusy}
              placeholder="e.g. 0.1"
              className="border border-grid bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-signal"
            />
          </label>
          {feePreview != null && totalPreview != null && (
            <p className="font-mono text-[10px] text-muted-foreground">
              Platform fee {(YIELD_PLATFORM_FEE_RATE * 100).toFixed(1)}%: {feePreview} SOL · total
              from idle balance: {totalPreview} SOL (+ gas)
            </p>
          )}
        </div>
      )}

      {actionError && <p className="mt-2 font-mono text-[10px] text-warn">{actionError}</p>}
      {actionNote && <p className="mt-2 font-mono text-[10px] text-signal">{actionNote}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        {canManage && !editing && (
          <button
            type="button"
            disabled={busy || actionBusy}
            onClick={() => {
              setEditing(true);
              setActionError(null);
              setActionNote(null);
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
              onClick={() => void runAdd()}
              className="border border-signal px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-signal transition hover:bg-signal/10 disabled:opacity-40"
            >
              {actionBusy ? "Saving…" : "Add capital"}
            </button>
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => {
                setEditing(false);
                setAddAmount("");
                setActionError(null);
              }}
              className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:text-foreground disabled:opacity-40"
            >
              Cancel edit
            </button>
          </>
        )}
        {canManage && (
          <button
            type="button"
            disabled={busy || actionBusy || editing}
            onClick={() => setConfirmRemove(true)}
            className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-warn hover:text-warn disabled:opacity-40"
          >
            Remove position
          </button>
        )}
      </div>

      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={(open) => {
          if (!open) setConfirmRemove(false);
        }}
        title="Remove yield position"
        description={
          <>
            Unwind {position.amount} {position.symbol} from {position.protocol_name} back to idle
            SOL in your Yield Circle wallet? This cannot be undone from the UI.
          </>
        }
        confirmLabel="Remove position"
        cancelLabel="Keep position"
        busy={actionBusy}
        onConfirm={() => void runRemove()}
      />
    </div>
  );
}

export function YieldPositionPanel({
  positions,
  authToken,
  busy = false,
  onUpdated,
}: {
  positions: YieldPosition[];
  authToken: string | null;
  busy?: boolean;
  onUpdated: () => void;
}) {
  if (!authToken) {
    return <p className="text-sm text-muted-foreground">Sign in to manage yield positions.</p>;
  }
  if (positions.length === 0) {
    return <p className="text-sm text-muted-foreground">No deployed yield yet.</p>;
  }

  return (
    <div className="space-y-3">
      {positions.map((position) => (
        <YieldPositionCard
          key={position.id}
          position={position}
          authToken={authToken}
          busy={busy}
          onUpdated={onUpdated}
        />
      ))}
    </div>
  );
}
